"""Alert dispatch with SQLite cooldown deduplication."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Callable

COOLDOWN_PRESETS: dict[str, int] = {
    "stuck": 15 * 60,
    "error_code": 60 * 60,
    "low_batt_off_dock": 30 * 60,
    "rain_pause": 4 * 60 * 60,
    "broker_offline": 0,          # one-shot until recovery; handled by caller
    "ticket_stalled": 24 * 60 * 60,
    "portal_login_failed": 24 * 60 * 60,
    "responder_offline": 24 * 60 * 60,
    "mbp_bridge_offline": 24 * 60 * 60,
    "gws_bridge_offline": 24 * 60 * 60,
    "capture_disk_low": 60 * 60,
    "case_persist_failed": 0,     # one-shot per case
}

# Transition rate-limit: max transitions per type per serial per hour
_TRANSITION_LIMIT = 3
_TRANSITION_WINDOW_SECONDS = 3600


class AlertDispatcher:
    def __init__(self, db_path: Path, egress_fn: Callable[[str], None]) -> None:
        self._db = db_path
        self._egress = egress_fn
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS alert_cooldown (
                    key      TEXT PRIMARY KEY,
                    fired_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS transition_log (
                    serial      TEXT NOT NULL,
                    from_state  TEXT NOT NULL,
                    to_state    TEXT NOT NULL,
                    occurred_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_transition_lookup
                ON transition_log (serial, from_state, to_state, occurred_at)
            """)

    def dispatch(self, key: str, cooldown_seconds: int, message: str) -> bool:
        now = datetime.now(timezone.utc)
        cutoff = (now - timedelta(seconds=cooldown_seconds)).isoformat()

        with self._connect() as conn:
            row = conn.execute(
                "SELECT fired_at FROM alert_cooldown WHERE key = ?", (key,)
            ).fetchone()

            if row is not None and row[0] >= cutoff:
                return False

            conn.execute(
                "INSERT OR REPLACE INTO alert_cooldown (key, fired_at) VALUES (?, ?)",
                (key, now.isoformat()),
            )

        self._egress(message)
        return True

    def check_transition_rate_limit(
        self, serial: str, from_state: str, to_state: str
    ) -> bool:
        now = datetime.now(timezone.utc)
        window_start = (now - timedelta(seconds=_TRANSITION_WINDOW_SECONDS)).isoformat()

        with self._connect() as conn:
            count = conn.execute(
                """SELECT COUNT(*) FROM transition_log
                   WHERE serial=? AND from_state=? AND to_state=?
                   AND occurred_at >= ?""",
                (serial, from_state, to_state, window_start),
            ).fetchone()[0]

            if count >= _TRANSITION_LIMIT:
                return False

            conn.execute(
                "INSERT INTO transition_log (serial, from_state, to_state, occurred_at) VALUES (?,?,?,?)",
                (serial, from_state, to_state, now.isoformat()),
            )

        return True
