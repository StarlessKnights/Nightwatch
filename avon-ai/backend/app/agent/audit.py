"""Durable provenance; an unavailable audit disk never interrupts the simulator."""

import json
import sqlite3
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from uuid import uuid4


class Audit:
    def __init__(self, path):
        self.path = path
        self.error = None

    @contextmanager
    def _connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=0.2)) as db, db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS audit (id TEXT PRIMARY KEY, at TEXT, run TEXT, kind TEXT, payload TEXT)"
            )
            yield db

    def record(self, run, kind, payload, identity=None):
        row_id = identity or uuid4().hex
        try:
            with self._connect() as db:
                db.execute(
                    "INSERT OR IGNORE INTO audit VALUES (?, ?, ?, ?, ?)",
                    (
                        row_id,
                        datetime.now(UTC).isoformat(),
                        run,
                        kind,
                        json.dumps(payload, default=str),
                    ),
                )
            self.error = None
        except (OSError, sqlite3.Error):
            self.error = "Audit storage unavailable"
        return row_id

    def read(self, kinds=("event", "note"), limit=100):
        try:
            with self._connect() as db:
                rows = db.execute(
                    "SELECT id, at, run, kind, payload FROM audit WHERE kind IN ("
                    + ",".join("?" for _ in kinds)
                    + ") ORDER BY rowid DESC LIMIT ?",
                    (*kinds, min(limit, 500)),
                ).fetchall()
            return [
                {
                    "id": i,
                    "at": at,
                    "run_id": run,
                    "kind": kind,
                    "data": json.loads(data),
                }
                for i, at, run, kind, data in rows
            ]
        except (OSError, sqlite3.Error):
            self.error = "Audit storage unavailable"
            return []
