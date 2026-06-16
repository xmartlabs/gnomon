import unittest

import progress_server


class TestBatchProgressRing(unittest.TestCase):
    def test_real_checkpoints_snap_display_to_target(self):
        page = progress_server._PROGRESS_PAGE

        self.assertIn("function snapToTarget()", page)
        self.assertIn("updateRing();\n      snapToTarget();", page)
        self.assertIn("updateRing();\n      snapToTarget();", page)


if __name__ == "__main__":
    unittest.main()
