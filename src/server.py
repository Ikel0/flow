#!/usr/bin/env python3
"""Flow local event monitor with HTTP ingestion and live metrics."""
from __future__ import annotations

import argparse
import json
from collections import deque
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = {"total": 0, "alerts": deque(maxlen=50), "latencies": deque(maxlen=500)}

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

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs): super().__init__(*args, directory=str(ROOT), **kwargs)
    def send_json(self, payload, status=HTTPStatus.OK):
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status); self.send_header("Content-Type", "application/json; charset=utf-8"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        if self.path == "/api/metrics":
            latencies = STATE["latencies"]
            return self.send_json({"events": STATE["total"], "alerts": len(STATE["alerts"]), "avg_latency_ms": round(sum(latencies) / len(latencies), 1) if latencies else 0})
        if self.path == "/api/alerts": return self.send_json({"alerts": list(STATE["alerts"])})
        return super().do_GET()
    def do_POST(self):
        if self.path != "/api/events": return self.send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        try:
            length = int(self.headers.get("Content-Length", 0)); event = json.loads(self.rfile.read(length)); return self.send_json(ingest(event), HTTPStatus.ACCEPTED)
        except (ValueError, json.JSONDecodeError): return self.send_json({"error": "invalid JSON"}, HTTPStatus.BAD_REQUEST)

def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--port", type=int, default=8000); args = parser.parse_args()
    with ThreadingHTTPServer(("127.0.0.1", args.port), Handler) as server:
        print(f"Flow is running at http://127.0.0.1:{args.port}"); server.serve_forever()

if __name__ == "__main__": main()
