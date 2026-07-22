"""Golden parity vectors — the cross-language scoring contract.

tests/fixtures/scoring_vectors.json holds, per case, the raw scoring inputs
(scoring_inputs_by_source) and the expected per-source + aggregate profiles snapshotted
from the Python implementation. mirdash reimplements scoring in TS and tests against the
SAME file. These tests:

  1. Re-derive `expected` from the live Python impl and assert byte-for-byte equality, so
     the committed snapshot can never silently drift from the code (regenerate with
     `python3 tests/gen_scoring_vectors.py` when an intended scoring change lands).
  2. Assert the structural contract the vectors are meant to PROVE:
     - cursor-only drops the skills / toolsearch / tasktool terms (capability-aware).
     - the aggregate is the tool-volume WEIGHTED MEAN of per-source scores, NOT the
       pooled-union number.
"""
import json
import os
import unittest

from gnomon.scoring.inputs import SCORING_INPUTS_VERSION
from gnomon.scoring.aggregate import score_by_source
from tests._scoring_vectors_cases import (
    CLAUDE_BLOCK, CURSOR_BLOCK, CLAUDE_BOUNDARY_BLOCK, NO_TOOL_ACTIVITY_BLOCK,
    cases, rolling_cases,
)

VECTORS_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "scoring_vectors.json")


def _load():
    with open(VECTORS_PATH, encoding="utf-8") as f:
        return json.load(f)


def _roundtrip(obj):
    """Normalize through json so tuples->lists etc. match the on-disk snapshot exactly."""
    return json.loads(json.dumps(obj, default=str))


class TestScoringVectorsFile(unittest.TestCase):
    def test_scoring_contract_is_version_five(self):
        self.assertEqual(SCORING_INPUTS_VERSION, 5)

    def test_file_exists_and_has_cases(self):
        data = _load()
        self.assertGreaterEqual(len(data), 3)
        names = {c["name"] for c in data}
        self.assertEqual(names, {"claude_only", "cursor_only", "mixed_claude_cursor",
                                  "claude_boundary_above_floor", "no_tool_activity",
                                  "rolling_claude_all_buckets"})

    def test_version_tagged(self):
        for c in _load():
            self.assertEqual(c["scoring_inputs_version"], SCORING_INPUTS_VERSION)

    def test_expected_matches_live_implementation(self):
        """Re-derive expected from score_by_source and assert it equals the committed file
        (keeps the snapshot honest). If this fails after an intentional scoring change,
        regenerate with: python3 tests/gen_scoring_vectors.py"""
        data = {c["name"]: c for c in _load()}
        for name, sibs in cases():
            with self.subTest(case=name):
                got = _roundtrip(score_by_source(sibs))
                self.assertEqual(got, data[name]["expected"],
                                 f"{name}: live scoring diverged from committed vectors; "
                                 f"regenerate tests/fixtures/scoring_vectors.json")
        for name, sibs, bucket_sibs, metadata in rolling_cases():
            with self.subTest(case=name):
                got = _roundtrip(score_by_source(
                    sibs,
                    bucket_scoring_inputs_by_source=bucket_sibs,
                    bucket_metadata=metadata,
                ))
                self.assertEqual(got, data[name]["expected"],
                                 f"{name}: live rolling scoring diverged from committed vectors; "
                                 f"regenerate tests/fixtures/scoring_vectors.json")

    def test_rolling_vector_uses_exact_configured_weights(self):
        rolling = next(c for c in _load() if c["name"] == "rolling_claude_all_buckets")
        buckets = rolling["expected"]["by_source"]["claude"]["aq"]["blend"]["buckets"]
        self.assertEqual([bucket["id"] for bucket in buckets], ["recent_30d", "full_window"])
        self.assertEqual([bucket["configured_weight"] for bucket in buckets], [0.65, 0.35])
        self.assertEqual([bucket["effective_weight"] for bucket in buckets], [0.65, 0.35])

    def test_profile_shape(self):
        """Each profile carries the same shape build_summary's `profile` produces."""
        expected_keys = {"aq", "archetype", "scores", "steering",
                         "growth_edges", "signature_moves", "model_usage"}
        for c in _load():
            for prof in c["expected"]["by_source"].values():
                self.assertEqual(set(prof) & expected_keys, expected_keys)
                self.assertIn("aq_0_100", prof["aq"])
                self.assertIn("tier", prof["aq"])
                self.assertIn("pillars", prof["aq"])
                for axis in ("execution", "planning", "engineering"):
                    self.assertIn("value", prof["scores"][axis])
            if c["expected"]["aggregate"]:
                agg = c["expected"]["aggregate"]
                self.assertEqual(set(agg) & expected_keys, expected_keys)


class TestCapabilityContract(unittest.TestCase):
    def test_cursor_only_drops_tasktool_terms(self):
        """Cursor has no TaskCreate/TaskUpdate and no first-class Skill tool — Discipline
        drops entirely; Skill fluency stays (skills via Read / manually_attached)."""
        out = score_by_source({"cursor": {"window": CURSOR_BLOCK, "monthly": []}})
        breadth = next(p for p in out["by_source"]["cursor"]["aq"]["pillars"]
                       if p["name"] == "Breadth")
        axis_names = {a["name"] for a in breadth["axes"]}
        self.assertIn("Skill fluency", axis_names)
        self.assertIn("Discipline", breadth.get("not_applicable", []))

    def test_claude_keeps_skills_terms(self):
        """A full-capability (claude) slice keeps every Breadth axis — no drops."""
        out = score_by_source({"claude": {"window": CLAUDE_BLOCK, "monthly": []}})
        breadth = next(p for p in out["by_source"]["claude"]["aq"]["pillars"]
                       if p["name"] == "Breadth")
        self.assertEqual(breadth.get("not_applicable", []), [])
        axis_names = {a["name"] for a in breadth["axes"]}
        self.assertIn("Skill fluency", axis_names)


class TestContextIntelligenceVectorCases(unittest.TestCase):
    """Context Intelligence monotonic coverage (no floor), exercised through the
    golden-vector fixture cases (mirdash pulls these same cases for parity)."""

    def test_claude_only_above_target_scored_near_full(self):
        # 18/40 = 0.45 coverage, above TARGET (0.40) -> present, near-full credit.
        out = score_by_source({"claude": {"window": CLAUDE_BLOCK, "monthly": []}})
        craft = next(p for p in out["by_source"]["claude"]["aq"]["pillars"] if p["name"] == "Craft")
        ci = next(a for a in craft["axes"] if a["name"] == "Context Intelligence")
        self.assertEqual(ci["score"], ci["weight"])

    def test_cursor_only_measured_zero_scored_not_dropped(self):
        # 0/10 = 0.0 coverage, a REAL measured zero (field present + tool activity) ->
        # present and scored 0 (monotonic, no floor), NOT dropped/renormalized.
        out = score_by_source({"cursor": {"window": CURSOR_BLOCK, "monthly": []}})
        craft = next(p for p in out["by_source"]["cursor"]["aq"]["pillars"] if p["name"] == "Craft")
        self.assertNotIn("Context Intelligence", craft.get("not_applicable", []))
        ci = next(a for a in craft["axes"] if a["name"] == "Context Intelligence")
        self.assertEqual(ci["score"], 0.0)

    def test_low_coverage_scored_near_zero(self):
        # 3/40 = 0.075 coverage -> present, scored monotonically near zero (no floor,
        # well below TARGET 0.40). No boundary discontinuity remains.
        out = score_by_source({"claude-boundary": {"window": CLAUDE_BOUNDARY_BLOCK, "monthly": []}})
        craft = next(p for p in out["by_source"]["claude-boundary"]["aq"]["pillars"] if p["name"] == "Craft")
        ci = next(a for a in craft["axes"] if a["name"] == "Context Intelligence")
        self.assertGreater(ci["score"], 0.0)
        self.assertLess(ci["score"], ci["weight"] * 0.5)

    def test_no_tool_activity_drops_context_intelligence(self):
        out = score_by_source({"no-tool-activity": {"window": NO_TOOL_ACTIVITY_BLOCK, "monthly": []}})
        craft = next(p for p in out["by_source"]["no-tool-activity"]["aq"]["pillars"] if p["name"] == "Craft")
        self.assertIn("Context Intelligence", craft.get("not_applicable", []))


class TestAggregateIsWeightedMean(unittest.TestCase):
    def test_aggregate_aq_is_tool_weighted_mean_not_pooled(self):
        """The mixed aggregate AQ must equal the tool_calls_total-weighted mean of the
        per-source AQ scores — NOT the number you'd get by pooling the raw inputs."""
        sibs = {"claude": {"window": CLAUDE_BLOCK, "monthly": []},
                "cursor": {"window": CURSOR_BLOCK, "monthly": []}}
        out = score_by_source(sibs)
        ca = out["by_source"]["claude"]["aq"]["aq_0_100"]
        cu = out["by_source"]["cursor"]["aq"]["aq_0_100"]
        wa = CLAUDE_BLOCK["volume"]["tool_calls_total"]
        wu = CURSOR_BLOCK["volume"]["tool_calls_total"]
        expected = round((ca * wa + cu * wu) / (wa + wu))
        self.assertEqual(out["aggregate"]["aq"]["aq_0_100"], expected)
        # sanity: the weighted mean lands strictly between the two per-source scores
        self.assertLess(out["aggregate"]["aq"]["aq_0_100"], ca)
        self.assertGreater(out["aggregate"]["aq"]["aq_0_100"], cu)

    def test_aggregate_pillars_and_axes_are_weighted_means(self):
        sibs = {"claude": {"window": CLAUDE_BLOCK, "monthly": []},
                "cursor": {"window": CURSOR_BLOCK, "monthly": []}}
        out = score_by_source(sibs)
        wa = CLAUDE_BLOCK["volume"]["tool_calls_total"]
        wu = CURSOR_BLOCK["volume"]["tool_calls_total"]

        def axis_val(prof, ax):
            return prof["scores"][ax]["value"]

        for ax in ("execution", "planning", "engineering"):
            a = axis_val(out["by_source"]["claude"], ax)
            b = axis_val(out["by_source"]["cursor"], ax)
            expected = round((a * wa + b * wu) / (wa + wu), 1)
            self.assertAlmostEqual(out["aggregate"]["scores"][ax]["value"], expected, places=1,
                                   msg=f"axis {ax} aggregate not the weighted mean")

    def test_single_source_aggregate_equals_that_source(self):
        """With one source the aggregate is just that source's profile numbers."""
        out = score_by_source({"claude": {"window": CLAUDE_BLOCK, "monthly": []}})
        self.assertEqual(out["aggregate"]["aq"]["aq_0_100"],
                         out["by_source"]["claude"]["aq"]["aq_0_100"])


if __name__ == "__main__":
    unittest.main()
