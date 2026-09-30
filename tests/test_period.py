import unittest
from datetime import datetime
from unittest import mock

from gnomon.cli.period import Period, resolve_period


class TestResolvePeriod(unittest.TestCase):
    def test_default_is_all_history(self):
        with mock.patch("gnomon.cli.period.DEFAULT_PERIOD", "all_history"):
            period = resolve_period([])
        self.assertEqual(period, Period("all_history", None, None, None,
                                        "All history", None, None))

    def test_custom_window_shows_inclusive_end(self):
        period = resolve_period(["--since=2026-03-01", "--until=2026-05-31"])
        self.assertEqual(period.kind, "custom")
        self.assertEqual(period.until.date().isoformat(), "2026-06-01")
        self.assertEqual(period.label, "2026-03-01 → 2026-05-31")

    def test_current_month_has_progress_metadata(self):
        now = datetime.fromisoformat("2026-06-20T12:00:00").astimezone()
        with mock.patch("gnomon.cli.period.DEFAULT_PERIOD", "current_month"), \
                mock.patch("gnomon.cli.period.now_local", return_value=now):
            period = resolve_period([])
        self.assertEqual(period.kind, "current_month")
        self.assertEqual(period.since, now.replace(day=1, hour=0, minute=0,
                                                   second=0, microsecond=0))
        self.assertIsNone(period.until)
        self.assertEqual(period.month_key, "2026-06")
        self.assertEqual(period.days_elapsed, 20)
        self.assertEqual(period.days_in_month, 30)
        self.assertEqual(period.label, "Jun 2026 · in progress · 20 days")

    def test_open_bounds_have_stable_labels(self):
        now = datetime.fromisoformat("2026-06-20T12:00:00").astimezone()
        self.assertEqual(resolve_period(["--since=2026-06-01"], now).label,
                         "2026-06-01 → today")
        self.assertEqual(resolve_period(["--until=2026-06-20"], now).label,
                         "… → 2026-06-20")


if __name__ == "__main__":
    unittest.main()
