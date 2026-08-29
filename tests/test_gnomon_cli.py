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


if __name__ == "__main__":
    unittest.main()
