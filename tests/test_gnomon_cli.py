import contextlib
import io
import unittest
from unittest.mock import patch


class TestGnomonCli(unittest.TestCase):
    def test_help_is_branded_for_gnomon(self):
        from gnomon.cli import gnomon_cli

        output = io.StringIO()
        with contextlib.redirect_stdout(output), self.assertRaises(SystemExit) as raised:
            gnomon_cli.main(["--help"])

        self.assertEqual(raised.exception.code, 0)
        self.assertIn("gnomon", output.getvalue())

    def test_local_mode_delegates_to_local_main(self):
        from gnomon.cli import gnomon_cli

        with patch("gnomon.cli.gnomon_cli.local.main") as local_main:
            gnomon_cli.main(["--local", "claude"])

        local_main.assert_called_once()
        self.assertIn("claude", local_main.call_args.kwargs["argv"])
        self.assertIn("--summary", local_main.call_args.kwargs["argv"])

    def test_missing_url_analyzes_locally_before_upload_error(self):
        from gnomon.cli import gnomon_cli

        with patch("gnomon.cli.gnomon_cli.local.main") as local_main, contextlib.redirect_stderr(
            io.StringIO()
        ) as stderr:
            with self.assertRaisesRegex(SystemExit, "1"):
                gnomon_cli.main(["claude"])

        local_main.assert_called_once()
        self.assertIn("dashboard URL required", stderr.getvalue())

    def test_dashboard_url_delegates_to_shared_pipeline(self):
        from gnomon.cli import gnomon_cli

        with patch("gnomon.cli.gnomon_cli._maybe_offer_retention"), patch(
            "gnomon.cli.gnomon_cli._main_web"
        ) as main_web:
            gnomon_cli.main(["--dashboard-url=https://dashboard.example", "claude"])

        kwargs = main_web.call_args.kwargs
        self.assertEqual(kwargs["dashboard_url"], "https://dashboard.example")
        self.assertEqual(kwargs["brand"], "gnomon")
        self.assertEqual(kwargs["mode"], "auto")

    def _upload_kwargs(self, argv):
        from gnomon.cli import gnomon_cli

        with patch("gnomon.cli.gnomon_cli._maybe_offer_retention") as offer, patch(
            "gnomon.cli.gnomon_cli._main_web"
        ) as main_web, contextlib.redirect_stderr(io.StringIO()):
            gnomon_cli.main(argv)
        return main_web.call_args.kwargs, offer

    def test_bare_value_flags_do_not_swallow_the_next_argument(self):
        url = "--dashboard-url=https://dashboard.example"
        cases = (
            ([url, "--backfill", "claude"], ["claude"]),
            ([url, "claude", "--window", "codex"], ["claude", "codex"]),
            ([url, "--output-dir", "claude"], ["claude"]),
        )
        for argv, expected in cases:
            with self.subTest(argv=argv):
                kwargs, _ = self._upload_kwargs(argv)
                self.assertEqual(kwargs["paxel_forward"], expected)

    def test_bare_backfill_keeps_its_default_month_count(self):
        kwargs, _ = self._upload_kwargs(
            ["--dashboard-url=https://dashboard.example", "--backfill", "claude"]
        )
        self.assertEqual((kwargs["mode"], kwargs["token_count"]), ("backfill", 6))

    def test_separate_dashboard_url_value_is_still_consumed(self):
        kwargs, _ = self._upload_kwargs(["--dashboard-url", "https://dashboard.example", "claude"])
        self.assertEqual(kwargs["dashboard_url"], "https://dashboard.example")
        self.assertEqual(kwargs["paxel_forward"], ["claude"])

    def test_local_mode_strips_bare_backfill_without_dropping_sources(self):
        from gnomon.cli import gnomon_cli

        with patch("gnomon.cli.gnomon_cli.local.main") as local_main, patch(
            "gnomon.cli.gnomon_cli._maybe_offer_retention"
        ):
            gnomon_cli.main(["--local", "--backfill", "claude"])

        argv = local_main.call_args.kwargs["argv"]
        self.assertIn("claude", argv)
        self.assertNotIn("--backfill", argv)

    def test_dry_run_without_url_exits_before_local_analysis(self):
        from gnomon.cli import gnomon_cli

        with patch("gnomon.cli.gnomon_cli.resolve_dashboard_url", return_value=None), patch(
            "gnomon.cli.gnomon_cli.local.main"
        ) as local_main, contextlib.redirect_stderr(io.StringIO()) as stderr:
            with self.assertRaises(SystemExit) as raised:
                gnomon_cli.main(["--dry-run", "claude"])

        self.assertEqual(raised.exception.code, 1)
        local_main.assert_not_called()
        self.assertIn("dashboard URL required", stderr.getvalue())

    def test_upload_retention_offer_is_scoped_to_the_current_window(self):
        _, offer = self._upload_kwargs(["--dashboard-url=https://dashboard.example", "claude"])

        window = offer.call_args.kwargs["default_window"]
        self.assertEqual(len(window), 2)
        self.assertLess(window[0], window[1])

    def test_local_mode_offers_retention_for_the_local_period(self):
        from gnomon.cli import gnomon_cli
        from gnomon.cli.period import resolve_period

        with patch("gnomon.cli.gnomon_cli.local.main") as local_main, patch(
            "gnomon.cli.gnomon_cli._maybe_offer_retention"
        ) as offer:
            gnomon_cli.main(["--local", "claude"])

        period = resolve_period(local_main.call_args.kwargs["argv"])
        self.assertEqual(offer.call_args.kwargs["default_window"], (period.since, period.until))


if __name__ == "__main__":
    unittest.main()
