# Licitações Monitor (Agente Juliana)

Monitora diariamente a **API pública do PNCP** (Portal Nacional de Contratações Públicas) em busca de licitações de TI/telecom no escopo definido, envia alertas automáticos no WhatsApp (novas licitações + lembretes de prazo) e mantém um painel web com tudo o que está sendo rastreado.

Projeto **independente** do `whatsapp-agent-orchestrator` — reutiliza apenas a mesma instância/número já conectado na Evolution API para enviar mensagens a um grupo diferente.

## Arquitetura

```
PNCP (API pública)  --diário-->  licitacoes-monitor (FastAPI)  --Evolution API-->  Grupo WhatsApp
                                        |
                                   SQLite (/data)
                                        |
                                   /painel (HTML, protegido por senha)
```

## Como funciona

1. Todo dia, no horário configurado, consulta `GET https://pncp.gov.br/api/consulta/v1/contratacoes/publicacao` para o dia anterior + hoje, modalidade Pregão Eletrônico (`codigoModalidadeContratacao=6`).
2. Filtra o campo `objetoCompra` pelas palavras-chave do escopo (`app/matcher.py`): TI, telefonia IP, PABX, SIP trunk, STFC, firewall/NGFW.
3. Licitação nova (nunca vista) → envia alerta no grupo e marca como "vista".
4. Todo dia também revisa as licitações já rastreadas: se faltam **5 dias** ou **1 dia** para o encerramento da proposta, envia um lembrete (uma vez cada).
5. `/painel` lista tudo o que já foi rastreado (protegido por login).

## Estrutura

```
app/
  pncp.py       # cliente da API do PNCP (paginação, retry, throttle anti-429)
  matcher.py    # filtro de palavras-chave (acento/case-insensitive)
  db.py         # SQLite: licitações rastreadas + flags de alerta já enviado
  evolution.py  # envio de texto via Evolution API
  alerts.py     # monta as mensagens e orquestra a checagem diária
  main.py       # FastAPI: /dashboard (config), /painel, loop diário
tests/
  test_app.py
```

## Rodando localmente

```bash
pip install -r requirements.txt
cp .env.example .env   # preencha os valores
python -m pytest tests/test_app.py -v
uvicorn app.main:app --reload
```

## Deploy (mesmo padrão do whatsapp-agent-orchestrator)

1. Criar um novo serviço **App** no EasyPanel (mesmo projeto `whatsapp-agents` ou um novo), apontando para este repositório.
2. Variáveis de ambiente:

   | Variável | Valor |
   |---|---|
   | `EVOLUTION_API_URL` | URL da Evolution API já em uso |
   | `EVOLUTION_API_KEY` | API key da Evolution API já em uso |
   | `DASHBOARD_PASSWORD` | senha própria para este painel |

3. Volume persistente em `/data`.
4. Porta do container: `8000`.
5. No `/dashboard` deste serviço, preencher:
   - **Instância WhatsApp**: a mesma já conectada (ex: `InstanciaWhatsapp`) — não precisa novo QR Code.
   - **Grupo (JID)**: o grupo dedicado a licitações (diferente do grupo do Jon Snow).
   - **Horário da checagem diária**.

## Limitações conhecidas

- A API do PNCP não tem busca por palavra-chave — o filtro é sempre feito no nosso lado, depois de baixar todas as publicações do período. Hoje cobre só a modalidade **Pregão Eletrônico** (a mais comum para TI); outras modalidades podem ser adicionadas em `app/pncp.py::MODALIDADES` se fizer sentido.
- A API do PNCP é instável (erros 500/429 esporádicos) — o cliente já tem retry com backoff e throttle entre páginas, mas uma falha persistente numa modalidade pode fazer o dia perder parte dos resultados (fica registrado no log do container).
- Sem editar manual de licitação no painel — hoje é só leitura.
