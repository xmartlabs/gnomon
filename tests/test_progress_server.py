import unittest

import progress_server


class TestBatchProgressRing(unittest.TestCase):
    def test_real_checkpoints_catch_up_smoothly_without_snap(self):
        page = progress_server._PROGRESS_PAGE

        self.assertNotIn("function snapToTarget()", page)
        self.assertNotIn("snapToTarget();", page)
        self.assertIn("var delta = targetPct - displayPct;", page)
        self.assertIn("var step = Math.max(1, Math.ceil(delta / 4));", page)
        self.assertIn("displayPct = Math.min(targetPct, displayPct + step);", page)
        self.assertIn("}, 250);", page)

    def test_batch_progress_uses_month_counts_not_percent_labels(self):
        page = progress_server._PROGRESS_PAGE

        self.assertIn('<span class="pct" id="ring-count">0/0</span>', page)
        self.assertNotIn('id="ring-pct"', page)
        self.assertNotIn("pct + '%'", page)
        self.assertNotIn("function setMidTarget(index)", page)
        self.assertNotIn("setMidTarget(d.index);", page)
        self.assertIn(
            "document.getElementById('ring-count').textContent = processed + '/' + total;",
            page,
        )


if __name__ == "__main__":
    unittest.main()
