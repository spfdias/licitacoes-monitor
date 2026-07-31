from datetime import date, datetime

from . import db, evolution, matcher, pncp


def _fmt_valor(valor: float) -> str:
    return f"R$ {valor:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _fmt_data(iso_str: str | None) -> str:
    if not iso_str:
        return "não informado"
    return datetime.fromisoformat(iso_str).strftime("%d/%m/%Y")


def format_new_alert(item: dict) -> str:
    return (
        f"📢 *Nova licitação no escopo!*\n\n"
        f"Órgão: {item['orgao']} ({item['municipio']}/{item['uf']})\n"
        f"Objeto: {item['objeto']}\n"
        f"Modalidade: {item['modalidade']}\n"
        f"Valor estimado: {_fmt_valor(item['valor_estimado'])}\n"
        f"Encerramento das propostas: {_fmt_data(item['encerramento_proposta'])}\n"
        f"Link: {item['link']}"
    )


def format_deadline_alert(item: dict, dias: int) -> str:
    urgencia = "🚨 *Encerra AMANHÃ!*" if dias <= 1 else f"⏰ *Encerra em {dias} dias*"
    return (
        f"{urgencia}\n\n"
        f"Órgão: {item['orgao']} ({item['municipio']}/{item['uf']})\n"
        f"Objeto: {item['objeto']}\n"
        f"Encerramento das propostas: {_fmt_data(item['encerramento_proposta'])}\n"
        f"Link: {item['link']}"
    )


def _dias_restantes(encerramento_iso: str | None, today: date) -> int | None:
    if not encerramento_iso:
        return None
    return (datetime.fromisoformat(encerramento_iso).date() - today).days


async def _check_deadline_threshold(
    evolution_url: str, evolution_key: str, instance: str, group_jid: str, flag: str, max_dias: int, today: date
) -> int:
    enviados = 0
    for row in db.list_pending_deadline_alerts(flag):
        dias = _dias_restantes(row["encerramento_proposta"], today)
        if dias is not None and 0 <= dias <= max_dias:
            await evolution.send_text(evolution_url, evolution_key, instance, group_jid, format_deadline_alert(dict(row), dias))
            db.mark_alerted(row["numero_controle_pncp"], flag)
            enviados += 1
    return enviados


async def run_daily_check(evolution_url: str, evolution_key: str, instance: str, group_jid: str) -> dict:
    today = date.today()
    now_iso = datetime.now().isoformat()

    data_inicial, data_final = pncp.default_date_range()
    publicacoes = await pncp.fetch_publicacoes(data_inicial, data_final)
    relevantes = [item for item in publicacoes if matcher.matches_scope(item["objeto"])]

    novas = 0
    for item in relevantes:
        is_new = db.upsert_licitacao(item, first_seen_at=now_iso)
        if is_new:
            await evolution.send_text(evolution_url, evolution_key, instance, group_jid, format_new_alert(item))
            db.mark_alerted(item["numero_controle_pncp"], "alerted_new")
            novas += 1

    args = (evolution_url, evolution_key, instance, group_jid)
    alertas_30d = await _check_deadline_threshold(*args, "alerted_30d", 30, today)
    alertas_5d = await _check_deadline_threshold(*args, "alerted_5d", 5, today)
    alertas_1d = await _check_deadline_threshold(*args, "alerted_1d", 1, today)

    return {
        "total_publicacoes": len(publicacoes),
        "relevantes": len(relevantes),
        "novas_alertadas": novas,
        "alertas_30d": alertas_30d,
        "alertas_5d": alertas_5d,
        "alertas_1d": alertas_1d,
    }
