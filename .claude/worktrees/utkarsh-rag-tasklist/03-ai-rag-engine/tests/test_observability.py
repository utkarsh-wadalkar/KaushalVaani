from __future__ import annotations

import json
import unittest

from observability.logger import StructuredLogger
from observability.metrics import LatencyTracker


class ObservabilityTests(unittest.TestCase):
    def test_structured_logger_emits_request_id_and_stage_as_json(self):
        lines: list[str] = []
        logger = StructuredLogger(lines.append)
        event = logger.stage("r1", "retrieval", elapsed_ms=4.5)
        self.assertEqual(event["request_id"], "r1")
        self.assertEqual(event["stage"], "retrieval")
        self.assertEqual(json.loads(lines[0]), event)

    def test_latency_tracker_keeps_wall_clock_totals_and_components(self):
        ticks = iter([0.0, 0.010])
        tracker = LatencyTracker(clock=lambda: next(ticks))
        tracker.start()
        tracker.record("embedding", 2.0)
        tracker.record("retrieval", 3.0)
        tracker.record("reranking", 5.0)
        snapshot = tracker.finish()
        self.assertEqual(snapshot.total_ms, 10.0)
        self.assertEqual(snapshot.components["embedding_ms"], 2.0)
        self.assertEqual(snapshot.components["retrieval_ms"], 3.0)
        self.assertEqual(snapshot.components["reranking_ms"], 5.0)

    def test_latency_tracker_does_not_sum_overlapping_components_into_total(self):
        ticks = iter([0.0, 0.010])
        tracker = LatencyTracker(clock=lambda: next(ticks))
        tracker.start()
        tracker.record("retrieval_total", 8.0)
        tracker.record("embedding", 7.0)

        snapshot = tracker.finish()

        self.assertEqual(snapshot.total_ms, 10.0)


if __name__ == "__main__":
    unittest.main()
