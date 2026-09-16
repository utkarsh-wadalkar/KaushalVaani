from __future__ import annotations

import unittest
import sys
from pathlib import Path

EVALUATION_ROOT = Path(__file__).resolve().parents[2] / "06-evaluation"
if str(EVALUATION_ROOT) not in sys.path:
    sys.path.insert(0, str(EVALUATION_ROOT))

from metrics.grounding import grounding_metrics
from metrics.latency import percentile_report


class EvaluationTests(unittest.TestCase):
    def test_latency_report_returns_p50_p70_p95_and_p100(self):
        report = percentile_report([10, 20, 30, 40, 50])
        self.assertEqual(set(report), {"count", "p50", "p70", "p95", "p100"})
        self.assertEqual(report["p50"], 30.0)
        self.assertEqual(report["p100"], 50.0)

    def test_grounding_metrics_classifies_supported_and_unsupported(self):
        report = grounding_metrics(
            [
                (True, True, "en-IN"),
                (False, False, "hi-IN"),
                (True, False, "en-IN"),
                (False, True, "hi-IN"),
            ]
        )
        self.assertEqual(report["overall"]["tp"], 1)
        self.assertEqual(report["overall"]["fp"], 1)
        self.assertIn("en-IN", report["per_language"])
        self.assertIn("hi-IN", report["per_language"])


if __name__ == "__main__":
    unittest.main()
