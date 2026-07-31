import asyncio
import os
import secrets
from datetime import datetime, timedelta

from fastapi import Depends, FastAPI, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from . import alerts, db
from .painel_template import render_painel

app = FastAPI(title="Licitacoes Monitor")
security = HTTPBasic()


@app.on_event("startup")
def on_startup():
    db.init_db()
    for key, env_var in [
        ("evolution_api_url", "EVOLUTION_API_URL"),
        ("evolution_api_key", "EVOLUTION_API_KEY"),
    ]:
        if os.environ.get(env_var) and not db.get_setting(key):
            db.set_setting(key, os.environ[env_var])
    asyncio.create_task(_daily_loop())


def require_login(credentials: HTTPBasicCredentials = Depends(security)) -> None:
    expected = os.environ.get("DASHBOARD_PASSWORD", "")
    ok = credentials.username == "admin" and secrets.compare_digest(credentials.password, expected)
    if not expected or not ok:
        raise HTTPException(status_code=401, detail="Unauthorized", headers={"WWW-Authenticate": "Basic"})


async def _run_check_now() -> dict:
    evolution_url = db.get_setting("evolution_api_url")
    evolution_key = db.get_setting("evolution_api_key")
    instance = db.get_setting("whatsapp_instance")
    group_jid = db.get_setting("group_jid")
    if not (evolution_url and evolution_key and instance and group_jid):
        return {"ran": False, "reason": "configuracao incompleta"}
    result = await alerts.run_daily_check(evolution_url, evolution_key, instance, group_jid)
    return {"ran": True, **result}


async def _daily_loop() -> None:
    while True:
        send_time = db.get_setting("check_time", "07:00")
        try:
            hour, minute = (int(part) for part in send_time.split(":"))
        except ValueError:
            hour, minute = 7, 0
        now = datetime.now()
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        await asyncio.sleep((target - now).total_seconds())
        try:
            await _run_check_now()
        except Exception as exc:
            print(f"[licitacoes] falha na checagem diaria: {exc}")


@app.get("/health")
def health():
    return {"status": "ok"}


def _page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{title}</title>
<style>
body {{ font-family: system-ui, sans-serif; max-width: 960px; margin: 40px auto; padding: 0 16px; }}
input, textarea {{ width: 100%; padding: 8px; margin: 4px 0 12px; box-sizing: border-box; }}
fieldset {{ margin-bottom: 24px; }}
table {{ width: 100%; border-collapse: collapse; font-size: 0.9em; }}
td, th {{ border-bottom: 1px solid #ccc; padding: 6px 8px; text-align: left; vertical-align: top; }}
.btn {{ padding: 8px 16px; }}
</style></head>
<body><h1>{title}</h1>{body}</body></html>""")


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(_: None = Depends(require_login)):
    evolution_url = db.get_setting("evolution_api_url", "")
    evolution_key = db.get_setting("evolution_api_key", "")
    whatsapp_instance = db.get_setting("whatsapp_instance", "")
    group_jid = db.get_setting("group_jid", "")
    check_time = db.get_setting("check_time", "07:00")

    body = f"""
    <fieldset>
      <legend>Configuração</legend>
      <form method="post" action="/dashboard/settings">
        <label>Evolution API URL</label>
        <input name="evolution_api_url" value="{evolution_url}">
        <label>Evolution API Key</label>
        <input name="evolution_api_key" value="{evolution_key}">
        <label>Instância WhatsApp (a mesma já conectada)</label>
        <input name="whatsapp_instance" value="{whatsapp_instance}">
        <label>Grupo que recebe os alertas (JID)</label>
        <input name="group_jid" value="{group_jid}">
        <label>Horário da checagem diária (HH:MM)</label>
        <input name="check_time" value="{check_time}">
        <button class="btn" type="submit">Salvar</button>
      </form>
      <form method="post" action="/dashboard/run-now">
        <button class="btn" type="submit">Rodar checagem agora</button>
      </form>
    </fieldset>
    <p><a href="/painel">Ver painel de licitações rastreadas</a></p>
    """
    return _page("Dashboard - Licitações Monitor", body)


@app.post("/dashboard/settings")
def save_settings(
    evolution_api_url: str = Form(...),
    evolution_api_key: str = Form(...),
    whatsapp_instance: str = Form(...),
    group_jid: str = Form(...),
    check_time: str = Form(...),
    _: None = Depends(require_login),
):
    db.set_setting("evolution_api_url", evolution_api_url)
    db.set_setting("evolution_api_key", evolution_api_key)
    db.set_setting("whatsapp_instance", whatsapp_instance)
    db.set_setting("group_jid", group_jid)
    db.set_setting("check_time", check_time)
    return RedirectResponse("/dashboard", status_code=303)


@app.post("/dashboard/run-now")
async def run_now(_: None = Depends(require_login)):
    return await _run_check_now()


@app.get("/painel", response_class=HTMLResponse)
def painel(_: None = Depends(require_login)):
    items = [dict(r) for r in db.list_all()]
    return HTMLResponse(render_painel(items))
