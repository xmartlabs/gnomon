"""Keep the docs site's metrics data in sync with the scoring code.

Every number the docs site shows on a metrics page is rendered from
docs/data/metrics.json. These tests fail when that file drifts from
gnomon/scoring/aq.py, gnomon/scoring/versioning.py or gnomon/config.py.
"""

import importlib.util
import inspect
import json
import re
import unittest
from pathlib import Path

from gnomon import config
from gnomon.scoring import aq, versioning

ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / "docs" / "data" / "metrics.json"
MACROS_PATH = ROOT / "overrides" / "macros.py"


def _load_data():
    with DATA_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def _load_macros():
    spec = importlib.util.spec_from_file_location("gnomon_docs_macros", MACROS_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _axes(data):
    return [axis for pillar in data["pillars"] for axis in pillar["axes"]]


class DocsMetricsSyncTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = _load_data()
        cls.source = inspect.getsource(aq.compute_aq)

    def test_contract_matches_code(self):
        self.assertEqual(self.data["contract"], versioning.SCORE_CONTRACT_ID)

    def test_pillar_weights_match_code(self):
        code = {name: int(w) for name, w in re.findall(r'build_pillar\("(\w+)", (\d+)', self.source)}
        self.assertEqual(code, {"Breadth": 30, "Craft": 35, "Efficiency": 20, "Savvy": 15})
        docs = {p["name"]: p["weight"] for p in self.data["pillars"]}
        self.assertEqual(docs, code)

    def test_axis_base_weights_match_code(self):
        code = {name: int(w) for name, w in re.findall(r'(?<!build_pillar)\("([^"]+)", (\d+), \w+', self.source)}
        docs = {a["code_name"]: a["base_weight"] for a in _axes(self.data)}
        self.assertEqual(len(code), 12)
        self.assertEqual(docs, code)

    def test_term_constants_match_code(self):
        for axis in _axes(self.data):
            for term in axis["terms"]:
                for name, value in term.get("constants", {}).items():
                    with self.subTest(axis=axis["id"], constant=name):
                        self.assertEqual(getattr(aq, name), value)

    def test_term_shares_sum_to_one(self):
        for axis in _axes(self.data):
            with self.subTest(axis=axis["id"]):
                self.assertAlmostEqual(sum(t["share"] for t in axis["terms"]), 1.0, places=2)

    def test_levels_match_tier_floors(self):
        docs = [(lvl["name"], lvl["floor"]) for lvl in self.data["levels"]]
        self.assertEqual(docs, list(reversed(aq.TIER_FLOORS)))

    def test_sources_match_config(self):
        self.assertEqual(set(self.data["sources"]), set(config.SOURCE_CAPS))
        for source_id, source in self.data["sources"].items():
            with self.subTest(source=source_id):
                self.assertEqual(set(source["caps"]), config.SOURCE_CAPS[source_id])
                self.assertEqual(source["planning_scope"], config.planning_session_scope(source_id))

    def test_requirements_are_known_capabilities(self):
        known = set().union(*config.SOURCE_CAPS.values())
        for axis in _axes(self.data):
            needed = set(axis["requires"]).union(*(t["requires"] for t in axis["terms"]))
            with self.subTest(axis=axis["id"]):
                self.assertLessEqual(needed, known)

    def test_rubric_shape(self):
        level_names = [lvl["name"] for lvl in self.data["levels"]]
        for axis in _axes(self.data):
            with self.subTest(axis=axis["id"]):
                if axis["status"] == "not_scored":
                    self.assertEqual(axis["rubric"], [])
                    continue
                self.assertEqual([band["level"] for band in axis["rubric"]], level_names)
                for band in axis["rubric"]:
                    self.assertTrue(band["looks_like"].strip())
                    if band["level"] == "Elite":
                        self.assertEqual(band["next"], "")
                    else:
                        self.assertTrue(band["next"].strip())

    def test_status_flags(self):
        status = {a["id"]: a["status"] for a in _axes(self.data)}
        self.assertIs(aq.STEERING_LEVERAGE_BAND_VALIDATED, False)
        self.assertEqual(status["steering-leverage"], "not_scored")
        self.assertEqual(status["context-intelligence"], "provisional")

    def test_axis_pages_exist(self):
        for axis in _axes(self.data):
            with self.subTest(axis=axis["id"]):
                self.assertTrue((ROOT / "docs" / axis["page"]).is_file())

    def test_coverage_states_follow_caps(self):
        macros = _load_macros()
        verification = macros.coverage(self.data, "verification")
        for source_id in ("claude", "codex", "cursor", "antigravity", "antigravity-ide"):
            self.assertEqual(verification[source_id], "full", source_id)
        for source_id in ("gemini", "pi", "opencode"):
            self.assertEqual(verification[source_id], "partial", source_id)
        self.assertEqual(macros.partial_terms(self.data, "verification", "gemini"), ["Tested change sessions"])

        orchestration = macros.coverage(self.data, "orchestration")
        for source_id in ("gemini", "pi", "opencode", "antigravity-ide"):
            self.assertEqual(orchestration[source_id], "none", source_id)

        model_mix = macros.coverage(self.data, "model-mix")
        self.assertEqual(model_mix["cursor"], "none")
        self.assertEqual(model_mix["gemini"], "partial")
        self.assertEqual(model_mix["claude"], "full")

    def test_effective_weight_redistributes_withheld_axis(self):
        macros = _load_macros()
        self.assertEqual(macros.effective_weight(self.data, "recovery"), 100.0)
        self.assertEqual(macros.effective_weight(self.data, "verification"), 35.0)

    def test_share_of_aq(self):
        macros = _load_macros()
        self.assertEqual(macros.share_of_aq(self.data, "verification"), 12)
        self.assertEqual(macros.share_of_aq(self.data, "recovery"), 20)
        self.assertEqual(macros.share_of_aq(self.data, "steering-leverage"), 0)

    def test_rendered_components_use_data(self):
        macros = _load_macros()
        rail = macros.render_axis_rail(self.data, "verification")
        self.assertIn('Gemini CLI</span><span class="gn-cov gn-cov--none">Not scored</span>',
                      macros.render_axis_rail(self.data, "orchestration"))
        self.assertIn("Partial (Tested change sessions)", rail)
        self.assertNotIn(">0<", rail)
        self.assertIn("(effective; base 50%)", macros.render_axis_rail(self.data, "recovery"))
        scale = macros.render_rubric_scale(self.data, "verification")
        for band in find_axis_rubric(self.data, "verification"):
            self.assertIn(band["looks_like"], scale)
        self.assertIn("Not scored yet", macros.render_rubric_scale(self.data, "steering-leverage"))
        formula = macros.render_formula(self.data, "context-intelligence")
        self.assertIn("Provisional", formula)


def find_axis_rubric(data, axis_id):
    return next(a for a in _axes(data) if a["id"] == axis_id)["rubric"]


if __name__ == "__main__":
    unittest.main()
