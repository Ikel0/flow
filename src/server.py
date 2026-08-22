#!/usr/bin/env python3
"""Flow local event monitor with HTTP ingestion and live metrics."""
from __future__ import annotations

import argparse
import json
import os
from collections import deque
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = {"total": 0, "alerts": deque(maxlen=50), "latencies": deque(maxlen=500)}
DEMO_EVENTS = [
    {"event_id": "evt-demo-accepted", "amount": 42.5, "latency_ms": 180, "type": "order_created"},
    {"event_id": "evt-demo-latency", "amount": 95.0, "latency_ms": 2640, "type": "payment_captured"},
    {"event_id": "evt-demo-amount", "amount": 12400.0, "latency_ms": 340, "type": "order_created"},
]

def validate(event: dict) -> list[str]:
    problems = [f"missing_{field}" for field in ("event_id", "amount", "latency_ms", "type") if field not in event]
    if event.get("latency_ms", 0) > 2000: problems.append("high_latency")
    if event.get("amount", 0) > 10000: problems.append("unusual_amount")
    return problems

def ingest(event: dict) -> dict:
    reasons = validate(event)
    STATE["total"] += 1
    if isinstance(event.get("latency_ms"), (int, float)): STATE["latencies"].append(event["latency_ms"])
    if reasons: STATE["alerts"].appendleft({"event_id": event.get("event_id", "unknown"), "reasons": reasons, "event": event})
    return {"accepted": not reasons, "alerts": reasons}


def reset() -> None:
    STATE["total"] = 0
    STATE["alerts"].clear()
    STATE["latencies"].clear()

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs): super().__init__(*args, directory=str(ROOT), **kwargs)
    def send_json(self, payload, status=HTTPStatus.OK):
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status); self.send_header("Content-Type", "application/json; charset=utf-8"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        if self.path == "/health":
            return self.send_json({"status": "ok", "service": "flow", "events_buffered": STATE["total"]})
        if self.path == "/api/metrics":
            latencies = STATE["latencies"]
            return self.send_json({"events": STATE["total"], "alerts": len(STATE["alerts"]), "avg_latency_ms": round(sum(latencies) / len(latencies), 1) if latencies else 0})
        if self.path == "/api/alerts": return self.send_json({"alerts": list(STATE["alerts"])})
        return super().do_GET()
    def do_POST(self):
        if self.path == "/api/demo":
            reset()
            results = [ingest(event) for event in DEMO_EVENTS]
            return self.send_json({"inserted": len(results), "alerts": sum(bool(result["alerts"]) for result in results)}, HTTPStatus.CREATED)
        if self.path == "/api/reset":
            reset()
            return self.send_json({"status": "reset"})
        if self.path != "/api/events": return self.send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        try:
            length = int(self.headers.get("Content-Length", 0)); event = json.loads(self.rfile.read(length)); return self.send_json(ingest(event), HTTPStatus.ACCEPTED)
        except (ValueError, json.JSONDecodeError): return self.send_json({"error": "invalid JSON"}, HTTPStatus.BAD_REQUEST)

def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000"))); args = parser.parse_args()
    with ThreadingHTTPServer(("0.0.0.0", args.port), Handler) as server:
        print(f"Flow is running on port {args.port}"); server.serve_forever()

if __name__ == "__main__": main()
