import os
import unittest
from unittest.mock import patch

import gnomon.upload.mirdash as mirdash


class TestDashboardUrlResolution(unittest.TestCase):
    def test_dashboard_url_precedence_has_seven_levels(self):
        config = {
            "dashboard_url": "https://config-dashboard.example/",
            "mirdash_base": "https://config-mirdash.example/",
        }
        cases = (
            (
                ["--dashboard-url=https://cli-dashboard.example/", "--mirdash-base=https://cli-mirdash.example/"],
                {"GNOMON_DASHBOARD_URL": "https://env-dashboard.example/", "GNOMON_MIRDASH_BASE": "https://env-mirdash.example/"},
                "https://cli-dashboard.example",
            ),
            (
                ["--mirdash-base=https://cli-mirdash.example/"],
                {"GNOMON_DASHBOARD_URL": "https://env-dashboard.example/", "GNOMON_MIRDASH_BASE": "https://env-mirdash.example/"},
                "https://env-dashboard.example",
            ),
            (
                ["--mirdash-base=https://cli-mirdash.example/"],
                {"GNOMON_MIRDASH_BASE": "https://env-mirdash.example/"},
                "https://cli-mirdash.example",
            ),
            (
                [],
                {"GNOMON_MIRDASH_BASE": "https://env-mirdash.example/"},
                "https://env-mirdash.example",
            ),
            ([], {}, "https://config-dashboard.example", config),
            ([], {}, "https://config-mirdash.example", {"mirdash_base": config["mirdash_base"]}),
            ([], {}, "https://fallback.example", {}),
        )

        for case in cases:
            argv, env, expected = case[:3]
            source_config = case[3] if len(case) == 4 else config
            with self.subTest(expected=expected), patch.dict(os.environ, env, clear=True), patch.object(
                mirdash, "_gnomon_config", return_value=source_config
            ):
                self.assertEqual(
                    mirdash.resolve_dashboard_url(argv, default="https://fallback.example/"),
                    expected,
                )

    def test_mirdash_wrapper_preserves_baked_default(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(mirdash, "_gnomon_config", return_value={}):
            self.assertEqual(mirdash._resolve_mirdash_base([]), mirdash._DEFAULT_MIRDASH_BASE)

    def test_missing_dashboard_url_can_return_none(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(mirdash, "_gnomon_config", return_value={}):
            self.assertIsNone(mirdash.resolve_dashboard_url([], default=None))


if __name__ == "__main__":
    unittest.main()
