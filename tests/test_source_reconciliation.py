import unittest

from gnomon.cli.local import _reconcile_sources
from gnomon.output.source_usage import build_source_usage


class TestReconcileSources(unittest.TestCase):
    def test_dropped_source_is_reported(self):
        # discovered has cursor; present (scoring_inputs) does not
        dropped = _reconcile_sources(
            discovered={"claude", "codex", "cursor"},
            present={"claude", "codex"},
            reasons={"cursor": "out-of-window"},
        )
        self.assertEqual(dropped, [("cursor", "out-of-window")])

    def test_all_reconciled_is_empty(self):
        dropped = _reconcile_sources(
            discovered={"claude", "codex"},
            present={"claude", "codex"},
            reasons={},
        )
        self.assertEqual(dropped, [])

    def test_reason_defaults_to_unknown(self):
        dropped = _reconcile_sources(
            discovered={"cursor"}, present=set(), reasons={},
        )
        self.assertEqual(dropped, [("cursor", "unknown")])


class TestLowSessionSourceSurvives(unittest.TestCase):
    def test_low_session_source_survives(self):
        sibs = {
            "cursor": {"window": {"volume": {"total_sessions": 2, "total_prompts": 3,
                                              "tool_calls_total": 5},
                                  "velocity": {"active_hours": 0.4}}},
            "codex":  {"window": {"volume": {"total_sessions": 100, "total_prompts": 900,
                                              "tool_calls_total": 5000},
                                  "velocity": {"active_hours": 40.0}}},
        }
        out = build_source_usage(sibs)
        self.assertIn("cursor", out["by_source"])
        self.assertEqual(out["by_source"]["cursor"]["sessions"], 2)


if __name__ == "__main__":
    unittest.main()
