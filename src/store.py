"""Durable event ledger used by the Flow HTTP monitor."""
from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from math import ceil
from pathlib import Path
import sqlite3
from typing import Any


class EventConflictError(ValueError):
    """Raised when an event identifier is reused with a new payload."""


class EventStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                  event_id TEXT PRIMARY KEY,
                  fingerprint TEXT NOT NULL,
                  event_type TEXT NOT NULL,
                  source TEXT NOT NULL,
                  amount REAL NOT NULL,
                  latency_ms REAL NOT NULL,
                  received_at TEXT NOT NULL,
                  reasons TEXT NOT NULL,
                  payload TEXT NOT NULL
                )
                """
            )
            connection.execute("CREATE INDEX IF NOT EXISTS events_received_at ON events(received_at DESC)")

    @staticmethod
    def _fingerprint(event: dict[str, Any]) -> str:
        canonical = json.dumps(event, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _serialize(row: sqlite3.Row, replayed: bool = False) -> dict[str, Any]:
        reasons = json.loads(row["reasons"])
        return {
            "event_id": row["event_id"],
            "state": "flagged" if reasons else "accepted",
            "alerts": reasons,
            "source": row["source"],
            "received_at": row["received_at"],
            "replayed": replayed,
        }

    def ingest(self, event: dict[str, Any], reasons: list[str]) -> dict[str, Any]:
        fingerprint = self._fingerprint(event)
        with self.connect() as connection:
            existing = connection.execute("SELECT * FROM events WHERE event_id = ?", (event["event_id"],)).fetchone()
            if existing:
                if existing["fingerprint"] != fingerprint:
                    raise EventConflictError("event_id already exists with a different payload")
                return self._serialize(existing, replayed=True)

            received_at = datetime.now(UTC).isoformat(timespec="seconds")
            connection.execute(
                """
                INSERT INTO events(event_id, fingerprint, event_type, source, amount, latency_ms, received_at, reasons, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event["event_id"],
                    fingerprint,
                    event["type"],
                    str(event.get("source", "manual")),
                    float(event["amount"]),
                    float(event["latency_ms"]),
                    received_at,
                    json.dumps(reasons),
                    json.dumps(event, ensure_ascii=False),
                ),
            )
            inserted = connection.execute("SELECT * FROM events WHERE event_id = ?", (event["event_id"],)).fetchone()
        return self._serialize(inserted)

    def metrics(self) -> dict[str, int | float]:
        with self.connect() as connection:
            rows = connection.execute("SELECT latency_ms, reasons FROM events ORDER BY latency_ms").fetchall()
        latencies = [float(row["latency_ms"]) for row in rows]
        p95 = latencies[ceil(len(latencies) * 0.95) - 1] if latencies else 0
        return {
            "events": len(rows),
            "alerts": sum(bool(json.loads(row["reasons"])) for row in rows),
            "avg_latency_ms": round(sum(latencies) / len(latencies), 1) if latencies else 0,
            "p95_latency_ms": round(p95, 1),
        }

    def alerts(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM events WHERE reasons != '[]' ORDER BY received_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._serialize(row) for row in rows]

    def reset(self) -> None:
        with self.connect() as connection:
            connection.execute("DELETE FROM events")
