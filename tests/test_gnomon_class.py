import json
import os
import unittest
from unittest.mock import patch


class TestGnomon(unittest.TestCase):
    def test_analyze_returns_summary_json_without_dashboard_url(self):
        from gnomon.gnomon import Gnomon

        def fake_local_main(argv=None, output_dir=None):
            with open(os.path.join(output_dir, "summary.json"), "w", encoding="utf-8") as fh:
                json.dump({"profile": {"aq": 88}, "source": argv[0]}, fh)

        with patch("gnomon.gnomon.local.main", side_effect=fake_local_main) as local_main:
            summary = Gnomon(sources=["claude"]).analyze()

        self.assertEqual(summary, {"profile": {"aq": 88}, "source": "claude"})
        argv = local_main.call_args.kwargs["argv"]
        self.assertEqual(argv[0], "claude")
        self.assertIn("--summary", argv)

    def test_analyze_does_not_forward_upload_only_window(self):
        # --window=N is an upload-wrapper flag; local analysis never reads it.
        from gnomon.gnomon import Gnomon

        def fake_local_main(argv=None, output_dir=None):
            with open(os.path.join(output_dir, "summary.json"), "w", encoding="utf-8") as fh:
                json.dump({}, fh)

        with patch("gnomon.gnomon.local.main", side_effect=fake_local_main) as local_main:
            Gnomon(sources=["claude"], window_months=3).analyze()

        argv = local_main.call_args.kwargs["argv"]
        self.assertFalse(any(a.startswith("--window") for a in argv), argv)

    def test_upload_uses_configured_dashboard_url(self):
        from gnomon.gnomon import Gnomon

        summary = {"profile": {"aq": 88}}
        with patch("gnomon.gnomon._upload_summary", return_value="/p/report") as upload:
            result = Gnomon(dashboard_url="https://dashboard.example").upload(summary, "token")

        self.assertEqual(result, "/p/report")
        upload.assert_called_once_with("https://dashboard.example", "token", summary)

    def test_upload_requires_dashboard_url(self):
        from gnomon.gnomon import Gnomon

        with self.assertRaisesRegex(ValueError, "dashboard_url"):
            Gnomon().upload({}, "token")

    def test_run_delegates_to_web_pipeline_with_gnomon_brand(self):
        from gnomon.gnomon import Gnomon

        with patch("gnomon.gnomon._main_web") as main_web:
            Gnomon(dashboard_url="https://dashboard.example", sources=["claude"]).run()

        kwargs = main_web.call_args.kwargs
        self.assertEqual(kwargs["brand"], "gnomon")
        self.assertEqual(kwargs["dashboard_url"], "https://dashboard.example")
        self.assertEqual(kwargs["mode"], "auto")


if __name__ == "__main__":
    unittest.main()
