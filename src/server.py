#!/usr/bin/env python3
"""Flow event monitor with contract checks, durable traces and live metrics."""
from __future__ import annotations

import argparse
import json
import os
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from store import EventConflictError, EventStore

ROOT = Path(__file__).resolve().parents[1]
DATABASE_PATH = Path(os.environ.get("FLOW_DATABASE_PATH", ROOT / "data" / "flow.db"))
STORE = EventStore(DATABASE_PATH)
DEMO_EVENTS = [
    {"event_id": "evt-demo-accepted", "amount": 42.5, "latency_ms": 180, "type": "order_created", "source": "demo"},
    {"event_id": "evt-demo-latency", "amount": 95.0, "latency_ms": 2640, "type": "payment_captured", "source": "demo"},
    {"event_id": "evt-demo-amount", "amount": 12400.0, "latency_ms": 340, "type": "order_created", "source": "demo"},
]


def validate(event: dict[str, Any]) -> list[str]:
    """Return explicit contract and monitoring reasons for one event."""
    reasons = [f"missing_{field}" for field in ("event_id", "amount", "latency_ms", "type") if field not in event]
    if reasons:
        return reasons
    if not isinstance(event["event_id"], str) or not event["event_id"].strip():
        reasons.append("invalid_event_id")
    if not isinstance(event["type"], str) or not event["type"].strip():
        reasons.append("invalid_type")
    if not isinstance(event["amount"], (int, float)) or isinstance(event["amount"], bool):
        reasons.append("invalid_amount")
    if not isinstance(event["latency_ms"], (int, float)) or isinstance(event["latency_ms"], bool) or event["latency_ms"] < 0:
        reasons.append("invalid_latency_ms")
    if any(reason.startswith("invalid_") for reason in reasons):
        return reasons
    if event["latency_ms"] > 2000:
        reasons.append("high_latency")
    if event["amount"] > 10000:
        reasons.append("unusual_amount")
    return reasons


def is_contract_error(reasons: list[str]) -> bool:
    return any(reason.startswith(("missing_", "invalid_")) for reason in reasons)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/health":
            return self.send_json({"status": "ok", "service": "flow", "storage": "sqlite", **STORE.metrics()})
        if path == "/api/metrics":
            return self.send_json(STORE.metrics())
        if path == "/api/alerts":
            return self.send_json({"alerts": STORE.alerts()})
        if path == "/api/overview":
            return self.send_json({"metrics": STORE.metrics(), "alerts": STORE.alerts(limit=12)})
        return super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/api/reset":
            STORE.reset()
            return self.send_json({"status": "reset"})
        if path == "/api/demo":
            STORE.reset()
            values = [STORE.ingest(event, validate(event)) for event in DEMO_EVENTS]
            return self.send_json({"inserted": len(values), "alerts": sum(bool(value["alerts"]) for value in values)}, HTTPStatus.CREATED)
        if path != "/api/events":
            return self.send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        try:
            length = int(self.headers.get("Content-Length", "0"))
            event = json.loads(self.rfile.read(length))
        except (ValueError, json.JSONDecodeError):
            return self.send_json({"error": "body must be valid JSON"}, HTTPStatus.BAD_REQUEST)
        if not isinstance(event, dict):
            return self.send_json({"error": "body must be a JSON object"}, HTTPStatus.BAD_REQUEST)
        reasons = validate(event)
        if is_contract_error(reasons):
            return self.send_json({"error": "event does not match the contract", "reasons": reasons}, HTTPStatus.UNPROCESSABLE_ENTITY)
        try:
            result = STORE.ingest(event, reasons)
        except EventConflictError as error:
            return self.send_json({"error": str(error)}, HTTPStatus.CONFLICT)
        return self.send_json(result, HTTPStatus.OK if result["replayed"] else HTTPStatus.ACCEPTED)

    def log_message(self, fmt: str, *args: Any) -> None:
        return


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    args = parser.parse_args()
    with ThreadingHTTPServer(("0.0.0.0", args.port), Handler) as server:
        print(f"Flow is running on port {args.port}")
        server.serve_forever()


if __name__ == "__main__":
    main()
