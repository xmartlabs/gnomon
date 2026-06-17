import os, sys, io, json, shutil, tempfile, contextlib, unittest
from unittest import mock
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
import paxel

# SRC_DIRS lives in tests/fixture_dirs.py so smoke + golden tests share one copy.
from fixture_dirs import FIX, SRC_DIRS

GOLDEN = os.path.join(FIX, "golden", "stats.json")


def run_paxel_stats():
    """Run main() hermetically over the fixtures; return parsed stats.json."""
    out = tempfile.mkdtemp(prefix="paxel-golden-")
    try:
        argv = ["paxel.py", "--no-open"]
        with mock.patch.multiple(paxel, OUT_DIR=out, **SRC_DIRS), \
                mock.patch.object(sys, "argv", argv), \
                contextlib.redirect_stdout(io.StringIO()):
            paxel.main()
        with open(os.path.join(out, "stats.json")) as f:
            return json.load(f)
    finally:
        shutil.rmtree(out, ignore_errors=True)


class TestGoldenStats(unittest.TestCase):
    def test_stats_match_golden(self):
        with open(GOLDEN, encoding="utf-8") as f:
            golden = json.load(f)
        actual = run_paxel_stats()
        self.assertEqual(
            json.dumps(actual, sort_keys=True, default=str),
            json.dumps(golden, sort_keys=True, default=str),
        )


if __name__ == "__main__":
    unittest.main()
