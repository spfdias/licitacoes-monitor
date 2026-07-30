import asyncio
from datetime import date, timedelta

import httpx

BASE_URL = "https://pncp.gov.br/api/consulta/v1/contratacoes/publicacao"
PAGE_SIZE = 50
THROTTLE_SECONDS = 0.5  # PNCP rate-limits (429) if pages are fetched back-to-back

# Pregão Eletrônico é a modalidade mais comum para compras de TI/telecom.
# Outras modalidades podem ser adicionadas aqui se o volume de resultados relevantes justificar.
MODALIDADES = [6]


def _normalize(raw: dict) -> dict:
    orgao_entidade = raw.get("orgaoEntidade") or {}
    unidade_orgao = raw.get("unidadeOrgao") or {}
    return {
        "numero_controle_pncp": raw.get("numeroControlePNCP"),
        "orgao": orgao_entidade.get("razaoSocial", ""),
        "uf": unidade_orgao.get("ufSigla", ""),
        "municipio": unidade_orgao.get("municipioNome", ""),
        "objeto": raw.get("objetoCompra", ""),
        "modalidade": raw.get("modalidadeNome", ""),
        "valor_estimado": raw.get("valorTotalEstimado") or 0.0,
        "encerramento_proposta": raw.get("dataEncerramentoProposta"),
        "situacao": raw.get("situacaoCompraNome", ""),
        "link": raw.get("linkSistemaOrigem")
        or f"https://pncp.gov.br/app/editais/{orgao_entidade.get('cnpj', '')}/{raw.get('anoCompra', '')}/{raw.get('sequencialCompra', '')}",
    }


async def _fetch_page(client: httpx.AsyncClient, data_inicial: str, data_final: str, modalidade: int, pagina: int) -> dict:
    params = {
        "dataInicial": data_inicial,
        "dataFinal": data_final,
        "codigoModalidadeContratacao": modalidade,
        "pagina": pagina,
        "tamanhoPagina": PAGE_SIZE,
    }
    for attempt in range(4):
        try:
            resp = await client.get(BASE_URL, params=params, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as exc:
            if attempt == 3:
                raise
            wait = 8 * (attempt + 1) if exc.response.status_code == 429 else 2 * (attempt + 1)
            await asyncio.sleep(wait)
        except (httpx.HTTPError, httpx.TimeoutException):
            if attempt == 3:
                raise
            await asyncio.sleep(2 * (attempt + 1))


async def fetch_publicacoes(data_inicial: date, data_final: date) -> list[dict]:
    """Fetches every contratação published in [data_inicial, data_final] across the tracked
    modalidades, normalized to our internal schema. Skips a modalidade/page on repeated
    failure rather than aborting the whole run — PNCP's public API is known to be flaky."""
    resultados = []
    di, df = data_inicial.strftime("%Y%m%d"), data_final.strftime("%Y%m%d")
    async with httpx.AsyncClient() as client:
        for modalidade in MODALIDADES:
            pagina = 1
            total_paginas = None
            while total_paginas is None or pagina <= total_paginas:
                try:
                    body = await _fetch_page(client, di, df, modalidade, pagina)
                except (httpx.HTTPError, httpx.TimeoutException) as exc:
                    print(f"[pncp] falha ao buscar modalidade={modalidade} pagina={pagina}: {exc}")
                    if total_paginas is None:
                        break  # never got a first page for this modalidade — nothing to resume from
                    pagina += 1
                    await asyncio.sleep(THROTTLE_SECONDS)
                    continue
                resultados.extend(_normalize(item) for item in body.get("data", []))
                total_paginas = body.get("totalPaginas", 1)
                pagina += 1
                await asyncio.sleep(THROTTLE_SECONDS)
    return resultados


def default_date_range() -> tuple[date, date]:
    today = date.today()
    return today - timedelta(days=1), today
