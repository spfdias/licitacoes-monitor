import os
import sqlite3
from contextlib import contextmanager

DB_PATH = os.path.join(os.environ.get("DATA_DIR", "./data"), "licitacoes.db")


def _connect():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def get_conn():
    conn = _connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        conn.execute(
            """CREATE TABLE IF NOT EXISTS licitacoes (
                numero_controle_pncp TEXT PRIMARY KEY,
                orgao TEXT,
                uf TEXT,
                municipio TEXT,
                objeto TEXT,
                modalidade TEXT,
                valor_estimado REAL,
                encerramento_proposta TEXT,
                situacao TEXT,
                link TEXT,
                first_seen_at TEXT NOT NULL,
                alerted_new INTEGER NOT NULL DEFAULT 0,
                alerted_20d INTEGER NOT NULL DEFAULT 0,
                alerted_5d INTEGER NOT NULL DEFAULT 0,
                alerted_1d INTEGER NOT NULL DEFAULT 0
            )"""
        )
        existing_cols = {row["name"] for row in conn.execute("PRAGMA table_info(licitacoes)")}
        if "alerted_20d" not in existing_cols:
            conn.execute("ALTER TABLE licitacoes ADD COLUMN alerted_20d INTEGER NOT NULL DEFAULT 0")


def get_setting(key: str, default: str | None = None) -> str | None:
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


def get_licitacao(numero_controle_pncp: str) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM licitacoes WHERE numero_controle_pncp = ?", (numero_controle_pncp,)
        ).fetchone()


def upsert_licitacao(item: dict, first_seen_at: str) -> bool:
    """Inserts the licitação if new. Returns True if it was newly inserted."""
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT 1 FROM licitacoes WHERE numero_controle_pncp = ?",
            (item["numero_controle_pncp"],),
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE licitacoes SET situacao=?, encerramento_proposta=? WHERE numero_controle_pncp=?",
                (item["situacao"], item["encerramento_proposta"], item["numero_controle_pncp"]),
            )
            return False
        conn.execute(
            """INSERT INTO licitacoes
                (numero_controle_pncp, orgao, uf, municipio, objeto, modalidade,
                 valor_estimado, encerramento_proposta, situacao, link, first_seen_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                item["numero_controle_pncp"],
                item["orgao"],
                item["uf"],
                item["municipio"],
                item["objeto"],
                item["modalidade"],
                item["valor_estimado"],
                item["encerramento_proposta"],
                item["situacao"],
                item["link"],
                first_seen_at,
            ),
        )
        return True


_ALERT_FLAGS = ("alerted_new", "alerted_20d", "alerted_5d", "alerted_1d")


def mark_alerted(numero_controle_pncp: str, flag: str) -> None:
    assert flag in _ALERT_FLAGS
    with get_conn() as conn:
        conn.execute(
            f"UPDATE licitacoes SET {flag} = 1 WHERE numero_controle_pncp = ?",
            (numero_controle_pncp,),
        )


def list_pending_deadline_alerts(flag: str) -> list[sqlite3.Row]:
    assert flag in ("alerted_20d", "alerted_5d", "alerted_1d")
    with get_conn() as conn:
        return conn.execute(
            f"SELECT * FROM licitacoes WHERE {flag} = 0 AND encerramento_proposta IS NOT NULL"
        ).fetchall()


_SORTABLE_COLUMNS = {"encerramento_proposta", "first_seen_at", "valor_estimado", "orgao"}


def list_all(order_by: str = "encerramento_proposta") -> list[sqlite3.Row]:
    if order_by not in _SORTABLE_COLUMNS:
        raise ValueError(f"invalid order_by: {order_by}")
    with get_conn() as conn:
        return conn.execute(f"SELECT * FROM licitacoes ORDER BY {order_by}").fetchall()
