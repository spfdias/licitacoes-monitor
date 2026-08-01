import os
import tempfile
import unittest
from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

os.environ["DATA_DIR"] = tempfile.mkdtemp()
os.environ["DASHBOARD_PASSWORD"] = "testpass"

from fastapi.testclient import TestClient  # noqa: E402

from app import alerts, db, matcher, pncp  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)
db.init_db()  # TestClient doesn't run FastAPI startup events outside a `with` block

SAMPLE_ITEM = {
    "numero_controle_pncp": "87297982000103-1-000233/2026",
    "orgao": "MUNICIPIO DE LAJEADO",
    "uf": "RS",
    "municipio": "Lajeado",
    "objeto": "Contratação de solução de FIREWALL de próxima geração (NGFW) e telefonia IP com PABX virtual.",
    "modalidade": "Pregão - Eletrônico",
    "valor_estimado": 39492982.40,
    "encerramento_proposta": "2026-08-12T09:00:00",
    "situacao": "Divulgada no PNCP",
    "link": "https://pregaobanrisul.com.br/editais/0041_2026/354183",
}


class PncpNormalizationTests(unittest.TestCase):
    def test_normalizes_real_pncp_shape(self):
        raw = {
            "numeroControlePNCP": "87297982000103-1-000233/2026",
            "orgaoEntidade": {"razaoSocial": "MUNICIPIO DE LAJEADO", "cnpj": "87297982000103"},
            "unidadeOrgao": {"ufSigla": "RS", "municipioNome": "Lajeado"},
            "objetoCompra": "Aquisição de equipamentos.",
            "modalidadeNome": "Pregão - Eletrônico",
            "valorTotalEstimado": 1000.0,
            "dataEncerramentoProposta": "2026-08-12T09:00:00",
            "situacaoCompraNome": "Divulgada no PNCP",
            "linkSistemaOrigem": "https://example.com/edital/1",
            "anoCompra": 2026,
            "sequencialCompra": 233,
        }
        item = pncp._normalize(raw)
        self.assertEqual(item["numero_controle_pncp"], "87297982000103-1-000233/2026")
        self.assertEqual(item["orgao"], "MUNICIPIO DE LAJEADO")
        self.assertEqual(item["link"], "https://example.com/edital/1")

    def test_falls_back_to_pncp_link_when_no_source_link(self):
        raw = {
            "numeroControlePNCP": "x",
            "orgaoEntidade": {"cnpj": "12345678000199"},
            "unidadeOrgao": {},
            "anoCompra": 2026,
            "sequencialCompra": 7,
        }
        item = pncp._normalize(raw)
        self.assertIn("12345678000199/2026/7", item["link"])


class MatcherTests(unittest.TestCase):
    def test_matches_keyword_case_and_accent_insensitive(self):
        self.assertTrue(matcher.matches_scope("Contratação de FIREWALL de Próxima Geração"))
        self.assertTrue(matcher.matches_scope("aquisição de PABX em nuvem"))
        self.assertTrue(matcher.matches_scope("prestação de STFC para o municipio"))

    def test_does_not_match_unrelated_objeto(self):
        self.assertFalse(matcher.matches_scope("Aquisição de materiais de construção"))

    def test_empty_objeto_does_not_match(self):
        self.assertFalse(matcher.matches_scope(""))


class DbTests(unittest.TestCase):
    def tearDown(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM licitacoes WHERE numero_controle_pncp = ?", (SAMPLE_ITEM["numero_controle_pncp"],))

    def test_upsert_reports_new_then_not_new(self):
        first = db.upsert_licitacao(SAMPLE_ITEM, first_seen_at="2026-07-30T10:00:00")
        second = db.upsert_licitacao(SAMPLE_ITEM, first_seen_at="2026-07-30T10:00:00")
        self.assertTrue(first)
        self.assertFalse(second)

    def test_mark_alerted_and_pending_list(self):
        db.upsert_licitacao(SAMPLE_ITEM, first_seen_at="2026-07-30T10:00:00")
        pending_before = [r["numero_controle_pncp"] for r in db.list_pending_deadline_alerts("alerted_10d")]
        self.assertIn(SAMPLE_ITEM["numero_controle_pncp"], pending_before)

        db.mark_alerted(SAMPLE_ITEM["numero_controle_pncp"], "alerted_10d")
        pending_after = [r["numero_controle_pncp"] for r in db.list_pending_deadline_alerts("alerted_10d")]
        self.assertNotIn(SAMPLE_ITEM["numero_controle_pncp"], pending_after)


class AlertsFormattingTests(unittest.TestCase):
    def test_dias_restantes_computes_difference(self):
        today = date(2026, 7, 30)
        self.assertEqual(alerts._dias_restantes("2026-08-04T09:00:00", today), 5)
        self.assertEqual(alerts._dias_restantes("2026-07-31T09:00:00", today), 1)
        self.assertIsNone(alerts._dias_restantes(None, today))

    def test_format_new_digest_summarizes_count_and_lists_items(self):
        text = alerts.format_new_digest([SAMPLE_ITEM], "https://painel.example.com")
        self.assertIn("1 nova", text)
        self.assertIn("MUNICIPIO DE LAJEADO", text)
        self.assertIn("https://painel.example.com", text)

    def test_format_new_digest_truncates_long_lists(self):
        muitos = [{**SAMPLE_ITEM, "numero_controle_pncp": str(i)} for i in range(15)]
        text = alerts.format_new_digest(muitos, "")
        self.assertIn("15 nova", text)
        self.assertIn("e mais 5", text)

    def test_format_deadline_digest_sorts_by_urgency(self):
        item_a = {**SAMPLE_ITEM, "numero_controle_pncp": "a"}
        item_b = {**SAMPLE_ITEM, "numero_controle_pncp": "b"}
        text = alerts.format_deadline_digest([(item_a, 10), (item_b, 1)], "")
        self.assertLess(text.index("vence em 1d"), text.index("vence em 10d"))


class RunDailyCheckTests(unittest.TestCase):
    def tearDown(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM licitacoes WHERE numero_controle_pncp = ?", (SAMPLE_ITEM["numero_controle_pncp"],))

    @patch("app.alerts.evolution.send_text", new_callable=AsyncMock)
    @patch("app.alerts.pncp.fetch_publicacoes", new_callable=AsyncMock)
    def test_new_relevant_item_triggers_one_alert(self, mock_fetch, mock_send):
        # Deadline far enough out (>20 days) that no threshold alert fires in the same run.
        item = {**SAMPLE_ITEM, "encerramento_proposta": "2030-01-01T09:00:00"}
        mock_fetch.return_value = [item, {**item, "numero_controle_pncp": "irrelevante", "objeto": "compra de merenda escolar"}]

        import asyncio

        result = asyncio.run(alerts.run_daily_check("https://evo.example.com", "key", "inst", "grupo@g.us"))

        self.assertEqual(result["relevantes"], 1)
        self.assertEqual(result["novas_alertadas"], 1)
        mock_send.assert_awaited_once()
        row = db.get_licitacao(SAMPLE_ITEM["numero_controle_pncp"])
        self.assertEqual(row["alerted_new"], 1)

    @patch("app.alerts.evolution.send_text", new_callable=AsyncMock)
    @patch("app.alerts.pncp.fetch_publicacoes", new_callable=AsyncMock)
    def test_second_run_does_not_realert_same_item(self, mock_fetch, mock_send):
        item = {**SAMPLE_ITEM, "encerramento_proposta": "2030-01-01T09:00:00"}
        mock_fetch.return_value = [item]
        import asyncio

        asyncio.run(alerts.run_daily_check("https://evo.example.com", "key", "inst", "grupo@g.us"))
        mock_send.reset_mock()
        result = asyncio.run(alerts.run_daily_check("https://evo.example.com", "key", "inst", "grupo@g.us"))

        self.assertEqual(result["novas_alertadas"], 0)

    @patch("app.alerts.evolution.send_text", new_callable=AsyncMock)
    @patch("app.alerts.pncp.fetch_publicacoes", new_callable=AsyncMock)
    def test_30d_deadline_produces_one_digest_message(self, mock_fetch, mock_send):
        # Item já conhecido (não "novo" nesta execução), só o limiar de prazo deve disparar.
        prazo = (date.today() + timedelta(days=25)).isoformat() + "T09:00:00"
        item = {**SAMPLE_ITEM, "encerramento_proposta": prazo}
        db.upsert_licitacao(item, first_seen_at="2020-01-01T00:00:00")
        db.mark_alerted(item["numero_controle_pncp"], "alerted_new")
        mock_fetch.return_value = []

        import asyncio

        result = asyncio.run(alerts.run_daily_check("https://evo.example.com", "key", "inst", "grupo@g.us"))
        self.assertEqual(result["prazos_alertados"], 1)
        mock_send.assert_awaited_once()  # a única mensagem enviada é o resumo de prazos

        mock_send.reset_mock()
        result2 = asyncio.run(alerts.run_daily_check("https://evo.example.com", "key", "inst", "grupo@g.us"))
        self.assertEqual(result2["prazos_alertados"], 0)
        mock_send.assert_not_awaited()

    @patch("app.alerts.evolution.send_text", new_callable=AsyncMock)
    @patch("app.alerts.pncp.fetch_publicacoes", new_callable=AsyncMock)
    def test_item_crossing_multiple_thresholds_counted_once_in_digest(self, mock_fetch, mock_send):
        # Um item a 8 dias do prazo cruza 30d, 20d e 10d ao mesmo tempo — o resumo deve contar
        # essa licitação uma única vez (na urgência mais alta), não três.
        prazo_18 = (date.today() + timedelta(days=18)).isoformat() + "T09:00:00"
        prazo_8 = (date.today() + timedelta(days=8)).isoformat() + "T09:00:00"
        item_18 = {**SAMPLE_ITEM, "numero_controle_pncp": "item-18d", "encerramento_proposta": prazo_18}
        item_8 = {**SAMPLE_ITEM, "numero_controle_pncp": "item-8d", "encerramento_proposta": prazo_8}
        for item in (item_18, item_8):
            db.upsert_licitacao(item, first_seen_at="2020-01-01T00:00:00")
            db.mark_alerted(item["numero_controle_pncp"], "alerted_new")
        mock_fetch.return_value = []

        import asyncio

        try:
            result = asyncio.run(alerts.run_daily_check("https://evo.example.com", "key", "inst", "grupo@g.us"))
            self.assertEqual(result["prazos_alertados"], 2)  # 2 licitações distintas, não 5 cruzamentos
            mock_send.assert_awaited_once()
        finally:
            with db.get_conn() as conn:
                conn.execute("DELETE FROM licitacoes WHERE numero_controle_pncp IN ('item-18d','item-8d')")


class PainelTests(unittest.TestCase):
    def tearDown(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM licitacoes WHERE numero_controle_pncp = ?", (SAMPLE_ITEM["numero_controle_pncp"],))

    def test_painel_renders_tracked_item(self):
        db.upsert_licitacao(SAMPLE_ITEM, first_seen_at="2026-07-30T10:00:00")
        resp = client.get("/painel", auth=("admin", "testpass"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("MUNICIPIO DE LAJEADO", resp.text)
        self.assertIn(SAMPLE_ITEM["link"], resp.text)


class DashboardTests(unittest.TestCase):
    def test_dashboard_requires_login(self):
        resp = client.get("/dashboard")
        self.assertEqual(resp.status_code, 401)

    def test_dashboard_accepts_correct_password(self):
        resp = client.get("/dashboard", auth=("admin", "testpass"))
        self.assertEqual(resp.status_code, 200)

    def test_painel_requires_login(self):
        resp = client.get("/painel")
        self.assertEqual(resp.status_code, 401)

    def test_save_settings_persists(self):
        resp = client.post(
            "/dashboard/settings",
            data={
                "evolution_api_url": "https://evo.example.com",
                "evolution_api_key": "key",
                "whatsapp_instance": "InstanciaWhatsapp",
                "group_jid": "grupo@g.us",
                "check_time": "07:30",
            },
            auth=("admin", "testpass"),
            follow_redirects=False,
        )
        self.assertEqual(resp.status_code, 303)
        self.assertEqual(db.get_setting("check_time"), "07:30")

    @patch("app.main.alerts.run_daily_check", new_callable=AsyncMock)
    def test_run_now_uses_configured_settings(self, mock_run):
        mock_run.return_value = {"total_publicacoes": 10, "relevantes": 1, "novas_alertadas": 1, "prazos_alertados": 0}
        db.set_setting("evolution_api_url", "https://evo.example.com")
        db.set_setting("evolution_api_key", "key")
        db.set_setting("whatsapp_instance", "InstanciaWhatsapp")
        db.set_setting("group_jid", "grupo@g.us")
        db.set_setting("painel_url", "https://painel.example.com")

        resp = client.post("/dashboard/run-now", auth=("admin", "testpass"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["ran"], True)
        mock_run.assert_awaited_once_with(
            "https://evo.example.com", "key", "InstanciaWhatsapp", "grupo@g.us", "https://painel.example.com"
        )

    def test_run_now_without_config_reports_not_ran(self):
        db.set_setting("group_jid", "")
        resp = client.post("/dashboard/run-now", auth=("admin", "testpass"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"ran": False, "reason": "configuracao incompleta"})


if __name__ == "__main__":
    unittest.main()
