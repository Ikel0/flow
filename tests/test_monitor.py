import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from server import validate
from store import EventConflictError, EventStore


def event(**extra):
    value = {"event_id": "evt-1", "amount": 20.0, "latency_ms": 90, "type": "order_created", "source": "test"}
    value.update(extra)
    return value


class FlowMonitorTest(unittest.TestCase):
    def test_high_latency_is_alerted(self):
        self.assertIn("high_latency", validate(event(latency_ms=2001)))

    def test_contract_errors_are_explicit(self):
        self.assertEqual(validate({"event_id": "1"}), ["missing_amount", "missing_latency_ms", "missing_type"])
        self.assertIn("invalid_latency_ms", validate(event(latency_ms=-1)))

    def test_event_id_is_idempotent_and_conflicts_are_visible(self):
        with tempfile.TemporaryDirectory() as folder:
            store = EventStore(Path(folder) / "flow.db")
            first = store.ingest(event(), [])
            replay = store.ingest(event(), [])
            with self.assertRaises(EventConflictError):
                store.ingest(event(amount=21.0), [])

        self.assertEqual(first["state"], "accepted")
        self.assertFalse(first["replayed"])
        self.assertTrue(replay["replayed"])

    def test_metrics_include_p95_and_alerts(self):
        with tempfile.TemporaryDirectory() as folder:
            store = EventStore(Path(folder) / "flow.db")
            store.ingest(event(event_id="evt-1", latency_ms=100), [])
            store.ingest(event(event_id="evt-2", latency_ms=3000), ["high_latency"])
            metrics = store.metrics()

        self.assertEqual(metrics["events"], 2)
        self.assertEqual(metrics["alerts"], 1)
        self.assertEqual(metrics["p95_latency_ms"], 3000.0)


if __name__ == "__main__":
    unittest.main()
