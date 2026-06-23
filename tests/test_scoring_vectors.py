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

from gnomon.output.summary import SCORING_INPUTS_VERSION
from gnomon.scoring.aggregate import score_by_source
from tests._scoring_vectors_cases import CLAUDE_BLOCK, CURSOR_BLOCK, cases

VECTORS_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "scoring_vectors.json")


def _load():
    with open(VECTORS_PATH, encoding="utf-8") as f:
        return json.load(f)


def _roundtrip(obj):
    """Normalize through json so tuples->lists etc. match the on-disk snapshot exactly."""
    return json.loads(json.dumps(obj, default=str))


class TestScoringVectorsFile(unittest.TestCase):
    def test_file_exists_and_has_cases(self):
        data = _load()
        self.assertGreaterEqual(len(data), 3)
        names = {c["name"] for c in data}
        self.assertEqual(names, {"claude_only", "cursor_only", "mixed_claude_cursor"})

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
    def test_cursor_only_drops_skills_terms(self):
        """A cursor-only slice cannot record skills/toolsearch/tasktool — those AQ axes
        must be marked not_applicable (dropped + renormalized), not scored 0."""
        out = score_by_source({"cursor": {"window": CURSOR_BLOCK, "monthly": []}})
        breadth = next(p for p in out["by_source"]["cursor"]["aq"]["pillars"]
                       if p["name"] == "Breadth")
        self.assertIn("Skill fluency", breadth.get("not_applicable", []))
        self.assertIn("Discipline", breadth.get("not_applicable", []))
        axis_names = {a["name"] for a in breadth["axes"]}
        self.assertNotIn("Skill fluency", axis_names)

    def test_claude_keeps_skills_terms(self):
        """A full-capability (claude) slice keeps every Breadth axis — no drops."""
        out = score_by_source({"claude": {"window": CLAUDE_BLOCK, "monthly": []}})
        breadth = next(p for p in out["by_source"]["claude"]["aq"]["pillars"]
                       if p["name"] == "Breadth")
        self.assertEqual(breadth.get("not_applicable", []), [])
        axis_names = {a["name"] for a in breadth["axes"]}
        self.assertIn("Skill fluency", axis_names)


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
