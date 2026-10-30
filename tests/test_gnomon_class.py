import contextlib
import io
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

    def test_analyze_rejects_upload_only_window_keyword(self):
        from gnomon.gnomon import Gnomon

        with patch("gnomon.gnomon.local.main") as local_main:
            with self.assertRaisesRegex(ValueError, "window_months"):
                Gnomon(sources=["claude"]).analyze(window_months=3)
        local_main.assert_not_called()

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

    def _run_kwargs(self, **run_kwargs):
        from gnomon.gnomon import Gnomon

        with patch("gnomon.gnomon._main_web") as main_web:
            Gnomon(dashboard_url="https://dashboard.example", sources=["claude"]).run(**run_kwargs)
        return main_web.call_args.kwargs

    def test_run_token_count_follows_mode_and_months(self):
        cases = (
            ({"mode": "backfill"}, 6),
            ({"mode": "backfill", "months": 3}, 3),
            ({"mode": "force"}, 12),
        )
        for run_kwargs, expected in cases:
            with self.subTest(run_kwargs=run_kwargs):
                kwargs = self._run_kwargs(**run_kwargs)
                self.assertEqual(kwargs["mode"], run_kwargs["mode"])
                self.assertEqual(kwargs["token_count"], expected)

    def test_run_rejects_unknown_mode_months_and_options(self):
        cases = (
            (ValueError, {"mode": "Force"}),
            (ValueError, {"mode": "auto", "months": 3}),
            (ValueError, {"mode": "backfill", "months": 0}),
            (TypeError, {"bogus": True}),
        )
        for error, run_kwargs in cases:
            with self.subTest(run_kwargs=run_kwargs), self.assertRaises(error):
                self._run_kwargs(**run_kwargs)

    def test_run_force_and_backfill_dry_run_print_plan_without_auth(self):
        from gnomon.gnomon import Gnomon

        gnomon = Gnomon(dashboard_url="https://dashboard.example", sources=["claude"])
        for mode in ("force", "backfill"):
            with self.subTest(mode=mode), patch("gnomon.gnomon._main_web") as main_web, \
                    contextlib.redirect_stdout(io.StringIO()) as stdout:
                self.assertIsNone(gnomon.run(mode=mode, dry_run=True))
            main_web.assert_not_called()
            self.assertIn("Dry run -- no uploads, no tokens consumed.", stdout.getvalue())

    def test_run_absolutizes_forwarded_dir_flags_like_the_cli(self):
        from gnomon.upload.mirdash import _absolutize_dir_flags

        argv = ["claude", "--claude-dir=relative/projects"]
        for run_kwargs in ({"argv": argv}, {"argv": ["claude"], "paxel_forward": argv}):
            with self.subTest(run_kwargs=run_kwargs):
                kwargs = self._run_kwargs(**run_kwargs)
                self.assertEqual(kwargs["paxel_forward"], _absolutize_dir_flags(list(argv)))
                self.assertNotEqual(kwargs["paxel_forward"], argv)

    def test_run_turns_pipeline_failure_exit_into_gnomon_run_error(self):
        from gnomon.gnomon import Gnomon, GnomonRunError

        gnomon = Gnomon(dashboard_url="https://dashboard.example")
        with patch("gnomon.gnomon._main_web", side_effect=SystemExit(1)):
            with self.assertRaises(GnomonRunError) as raised:
                gnomon.run()
        self.assertEqual(raised.exception.exit_code, 1)
        self.assertIsInstance(raised.exception, Exception)

        with patch("gnomon.gnomon._main_web", side_effect=SystemExit(0)):
            self.assertIsNone(gnomon.run())


if __name__ == "__main__":
    unittest.main()
