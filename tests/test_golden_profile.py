import os, sys, io, shutil, tempfile, contextlib, unittest
from unittest import mock
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
import paxel

# SRC_DIRS lives in tests/fixture_dirs.py so smoke + golden tests share one copy.
from fixture_dirs import FIX, SRC_DIRS

GOLDEN = os.path.join(FIX, "golden", "profile.html")


def run_paxel_profile():
    """Run main() hermetically over the fixtures; return profile.html text.

    OUT_DIR is a fresh tmp with no tern.png, so the logo chip is empty and the
    output is deterministic (no data-uri poster embed)."""
    out = tempfile.mkdtemp(prefix="paxel-golden-")
    try:
        argv = ["paxel.py", "--no-open"]
        with mock.patch.multiple(paxel, OUT_DIR=out, **SRC_DIRS), \
                mock.patch.object(sys, "argv", argv), \
                contextlib.redirect_stdout(io.StringIO()):
            paxel.main()
        with open(os.path.join(out, "profile.html"), encoding="utf-8") as f:
            return f.read()
    finally:
        shutil.rmtree(out, ignore_errors=True)


class TestGoldenProfile(unittest.TestCase):
    def test_profile_matches_golden(self):
        with open(GOLDEN, encoding="utf-8") as f:
            golden = f.read()
        actual = run_paxel_profile()
        self.assertEqual(actual, golden)


if __name__ == "__main__":
    unittest.main()
