"""
Audit store (SQLite): a durable, date-searchable history of every layer sync.

For each layer run we record when it happened, how many features were affected,
and — when a key field is known — the exact feature IDs that were upserted or
deleted. This backs the "History" tab: pick a date, see what was copied, drill
into the IDs, and optionally remove those features from the target database.
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime

# Vendored into GIS_BOX from the MIT gdb2postgis project; the audit DB lives in
# the writable config dir (git-ignored; frozen: outside the build, stable).
from tools.apppaths import data_path
AUDIT_PATH = data_path("gdb2postgis_audit.db")
ID_CAP = 50000  # max feature IDs stored per layer run (count is always exact)


class AuditStore:
    def __init__(self, path: str = AUDIT_PATH):
        self.path = path
        self._init()

    def _conn(self):
        c = sqlite3.connect(self.path)
        c.row_factory = sqlite3.Row
        return c

    def _init(self):
        with self._conn() as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS layer_runs(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT, date TEXT, profile TEXT,
                    source TEXT, layer TEXT,
                    schema TEXT, target_table TEXT, key_field TEXT,
                    mode TEXT, affected INTEGER, deleted INTEGER,
                    seconds REAL, ok INTEGER, message TEXT, id_capped INTEGER,
                    pg_host TEXT, pg_port INTEGER, pg_db TEXT)
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS feature_ids(
                    layer_run_id INTEGER, key_value TEXT, action TEXT)
            """)
            c.execute("CREATE INDEX IF NOT EXISTS idx_lr_date ON layer_runs(date)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_fid_lr ON feature_ids(layer_run_id)")

    # ---- writing ---------------------------------------------------------
    def record(self, rec: dict, upserted_ids=None, deleted_ids=None) -> int:
        upserted_ids = list(upserted_ids or [])
        deleted_ids = list(deleted_ids or [])
        capped = 1 if (len(upserted_ids) > ID_CAP or len(deleted_ids) > ID_CAP) else 0
        ts = rec.get("ts") or datetime.now().isoformat(timespec="seconds")
        with self._conn() as c:
            cur = c.execute("""
                INSERT INTO layer_runs(ts, date, profile, source, layer, schema,
                    target_table, key_field, mode, affected, deleted, seconds, ok,
                    message, id_capped, pg_host, pg_port, pg_db)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                ts, ts[:10], rec.get("profile", ""), rec.get("source", ""),
                rec.get("layer", ""), rec.get("schema", ""), rec.get("target_table", ""),
                rec.get("key_field", ""), rec.get("mode", ""),
                int(rec.get("affected", 0)), int(rec.get("deleted", 0)),
                float(rec.get("seconds", 0.0)), 1 if rec.get("ok") else 0,
                rec.get("message", ""), capped,
                rec.get("pg_host", ""), int(rec.get("pg_port", 0) or 0), rec.get("pg_db", ""),
            ))
            lr_id = cur.lastrowid
            rows = [(lr_id, v, "upsert") for v in upserted_ids[:ID_CAP]]
            rows += [(lr_id, v, "delete") for v in deleted_ids[:ID_CAP]]
            if rows:
                c.executemany(
                    "INSERT INTO feature_ids(layer_run_id, key_value, action) VALUES(?,?,?)",
                    rows)
            return lr_id

    # ---- reading ---------------------------------------------------------
    def dates(self) -> list[str]:
        with self._conn() as c:
            return [r[0] for r in c.execute(
                "SELECT DISTINCT date FROM layer_runs ORDER BY date DESC")]

    def runs_on(self, date: str) -> list[sqlite3.Row]:
        with self._conn() as c:
            return list(c.execute(
                "SELECT * FROM layer_runs WHERE date=? ORDER BY ts DESC, id DESC", (date,)))

    def run(self, layer_run_id: int) -> sqlite3.Row | None:
        with self._conn() as c:
            return c.execute("SELECT * FROM layer_runs WHERE id=?", (layer_run_id,)).fetchone()

    def ids(self, layer_run_id: int, action: str | None = None) -> list[str]:
        with self._conn() as c:
            if action:
                q = c.execute("SELECT key_value FROM feature_ids WHERE layer_run_id=? AND action=?",
                              (layer_run_id, action))
            else:
                q = c.execute("SELECT key_value FROM feature_ids WHERE layer_run_id=?",
                              (layer_run_id,))
            return [r[0] for r in q]

    def id_rows(self, layer_run_id: int) -> list[sqlite3.Row]:
        with self._conn() as c:
            return list(c.execute(
                "SELECT key_value, action FROM feature_ids WHERE layer_run_id=? ORDER BY action, key_value",
                (layer_run_id,)))

    def delete_run(self, layer_run_id: int) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM feature_ids WHERE layer_run_id=?", (layer_run_id,))
            c.execute("DELETE FROM layer_runs WHERE id=?", (layer_run_id,))
