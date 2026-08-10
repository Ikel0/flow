import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from server import validate

class FlowMonitorTest(unittest.TestCase):
    def test_high_latency_is_alerted(self):
        self.assertIn("high_latency", validate({"event_id":"1", "amount": 20, "latency_ms": 2001, "type":"order"}))

    def test_valid_event_is_accepted(self):
        self.assertEqual([], validate({"event_id":"1", "amount": 20, "latency_ms": 90, "type":"order"}))

if __name__ == "__main__": unittest.main()
