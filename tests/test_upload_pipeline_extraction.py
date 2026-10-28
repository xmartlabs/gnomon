import inspect
import unittest
from unittest.mock import patch

from gnomon.cli import insights, upload_pipeline


class TestUploadPipelineExtraction(unittest.TestCase):
    MOVED_NAMES = (
        "_REASON_LABELS",
        "_warn_unavailable_comparison",
        "_print_dry_run_plan",
        "offer_retention_config",
        "_maybe_offer_retention",
        "_main_web",
        "_main_console",
    )

    def test_upload_pipeline_owns_moved_symbols(self):
        for name in self.MOVED_NAMES:
            with self.subTest(name=name):
                symbol = getattr(upload_pipeline, name)
                self.assertEqual(symbol.__module__, upload_pipeline.__name__)

    def test_insights_reexports_same_symbols_for_legacy_imports(self):
        for name in self.MOVED_NAMES:
            with self.subTest(name=name):
                self.assertIs(getattr(insights, name), getattr(upload_pipeline, name))

    def test_pipeline_entrypoints_accept_generic_brand_and_dashboard_url(self):
        for name in ("_main_web", "_main_console"):
            params = inspect.signature(getattr(upload_pipeline, name)).parameters
            with self.subTest(name=name):
                self.assertIn("brand", params)
                self.assertIn("dashboard_url", params)

    def test_pipeline_entrypoints_reject_missing_required_inputs(self):
        complete = {"mode": "auto", "token_count": 1, "paxel_forward": [],
                    "dashboard_url": "https://dashboard.example"}
        # Validation must fail before any server, browser, or auth side effect.
        side_effect = AssertionError("pipeline started without validating its inputs")
        with patch.object(upload_pipeline, "ProgressServer", side_effect=side_effect), \
                patch.object(upload_pipeline.webbrowser, "open", side_effect=side_effect), \
                patch.object(upload_pipeline, "_capture_cli_token", side_effect=side_effect):
            for name in ("_main_web", "_main_console"):
                for missing in ("dashboard_url", "mode", "token_count"):
                    kwargs = dict(complete, **{missing: None})
                    with self.subTest(name=name, missing=missing), self.assertRaises(ValueError):
                        getattr(upload_pipeline, name)([], **kwargs)


if __name__ == "__main__":
    unittest.main()
