#!/usr/bin/env python3
"""Flow, dependency-free monitor for a JSON Lines stream."""
import argparse
import json
from pathlib import Path

def alerts(event):
    found = [f"missing_{key}" for key in ("event_id", "amount", "latency_ms", "type") if key not in event]
    if event.get("latency_ms", 0) > 2000:
        found.append("high_latency")
    if event.get("amount", 0) > 10000:
        found.append("unusual_amount")
    return found

def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=root / "data/events.jsonl")
    parser.add_argument("--output", type=Path, default=root / "out/alerts.jsonl")
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    total = alerted = 0
    with args.input.open(encoding="utf-8") as source, args.output.open("w", encoding="utf-8") as destination:
        for line in source:
            total += 1
            event = json.loads(line)
            reasons = alerts(event)
            if reasons:
                alerted += 1
                destination.write(json.dumps({"event_id": event.get("event_id"), "reasons": reasons}) + "\n")
                print(f"ALERT {event.get('event_id')}: {', '.join(reasons)}")
    print(f"Processed {total} events, {alerted} alerts")

if __name__ == "__main__":
    main()
