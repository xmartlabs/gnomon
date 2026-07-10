import pathlib
import unittest

from gnomon.cli.insights import _HELP_TEXT


ROOT = pathlib.Path(__file__).resolve().parents[1]


class TestPublicDocumentationContract(unittest.TestCase):
    def setUp(self):
        self.readme = (ROOT / "README.md").read_text(encoding="utf-8")

    def test_help_and_readme_both_publish_six_month_default(self):
        self.assertIn("default 6", _HELP_TEXT)
        self.assertIn("default 6", self.readme)

    def test_readme_explains_rolling_30_day_weighting(self):
        self.assertIn(
            "recent (rolling 30-day) + 35% full-window",
            " ".join(self.readme.split()),
        )
        self.assertIn("65%", self.readme)
        self.assertIn("35%", self.readme)

    def test_readme_discloses_raw_identifiers_without_claiming_project_names_never_upload(self):
        self.assertIn("custom skill and MCP server names", self.readme)
        self.assertIn("user-chosen identifiers", self.readme)
        self.assertIn("Prompts and file contents are not uploaded", self.readme)
        self.assertNotIn("No prompts, no quotes, no project names are ever sent", self.readme)

    def test_readme_documents_scoring_contract_v4_discontinuity(self):
        self.assertIn("scoring contract version 4", self.readme)
        self.assertIn("v0.4 methodology discontinuity", self.readme)


if __name__ == "__main__":
    unittest.main()
