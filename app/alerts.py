from datetime import date, datetime

from . import db, evolution, matcher, pncp

_MAX_LINHAS_RESUMO = 10
_DEADLINE_THRESHOLDS = (("alerted_30d", 30), ("alerted_20d", 20), ("alerted_10d", 10), ("alerted_1d", 1))


def _fmt_data(iso_str: str | None) -> str:
    if not iso_str:
        return "não informado"
    return datetime.fromisoformat(iso_str).strftime("%d/%m/%Y")


def _dias_restantes(encerramento_iso: str | None, today: date) -> int | None:
    if not encerramento_iso:
        return None
    return (datetime.fromisoformat(encerramento_iso).date() - today).days


def _resumo_linhas(items: list[dict], fmt_linha) -> str:
    linhas = "\n".join(fmt_linha(i) for i in items[:_MAX_LINHAS_RESUMO])
    if len(items) > _MAX_LINHAS_RESUMO:
        linhas += f"\n… e mais {len(items) - _MAX_LINHAS_RESUMO}."
    return linhas


def format_new_digest(items: list[dict], painel_url: str) -> str:
    linhas = _resumo_linhas(items, lambda i: f"• {i['orgao']} ({i['uf']}) — {i['objeto'][:80]}")
    rodape = f"\n\nVeja todas no painel: {painel_url}" if painel_url else ""
    return f"📢 *{len(items)} nova(s) licitação(ões) no escopo hoje*\n\n{linhas}{rodape}"


def format_deadline_digest(items: list[tuple[dict, int]], painel_url: str) -> str:
    ordenados = sorted(items, key=lambda par: par[1])
    linhas = _resumo_linhas(
        ordenados, lambda par: f"• {par[0]['orgao']} ({par[0]['uf']}) — vence em {par[1]}d ({_fmt_data(par[0]['encerramento_proposta'])})"
    )
    rodape = f"\n\nVeja todas no painel: {painel_url}" if painel_url else ""
    return f"⏰ *{len(ordenados)} licitação(ões) próxima(s) do encerramento*\n\n{linhas}{rodape}"


async def run_daily_check(
    evolution_url: str, evolution_key: str, instance: str, group_jid: str, painel_url: str = ""
) -> dict:
    today = date.today()
    now_iso = datetime.now().isoformat()

    data_inicial, data_final = pncp.default_date_range()
    publicacoes = await pncp.fetch_publicacoes(data_inicial, data_final)
    relevantes = [item for item in publicacoes if matcher.matches_scope(item["objeto"])]

    novos = []
    for item in relevantes:
        if db.upsert_licitacao(item, first_seen_at=now_iso):
            db.mark_alerted(item["numero_controle_pncp"], "alerted_new")
            novos.append(item)

    if novos:
        await evolution.send_text(evolution_url, evolution_key, instance, group_jid, format_new_digest(novos, painel_url))

    # Um item pode cruzar mais de um limiar no mesmo dia (ex: descoberto a 8 dias do prazo
    # cruza 30d, 20d e 10d de uma vez) — mantemos só a ocorrência mais urgente no resumo.
    prazos: dict[str, tuple[dict, int]] = {}
    for flag, max_dias in _DEADLINE_THRESHOLDS:
        for row in db.list_pending_deadline_alerts(flag):
            dias = _dias_restantes(row["encerramento_proposta"], today)
            if dias is None or not (0 <= dias <= max_dias):
                continue
            db.mark_alerted(row["numero_controle_pncp"], flag)
            chave = row["numero_controle_pncp"]
            if chave not in prazos or dias < prazos[chave][1]:
                prazos[chave] = (dict(row), dias)

    if prazos:
        await evolution.send_text(
            evolution_url, evolution_key, instance, group_jid, format_deadline_digest(list(prazos.values()), painel_url)
        )

    return {
        "total_publicacoes": len(publicacoes),
        "relevantes": len(relevantes),
        "novas_alertadas": len(novos),
        "prazos_alertados": len(prazos),
    }
