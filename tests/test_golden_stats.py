import os, sys, io, json, shutil, tempfile, contextlib, unittest
from unittest import mock
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import paxel

FIX = os.path.join(HERE, "fixtures")
GOLDEN = os.path.join(FIX, "golden", "stats.json")

# Copy verbatim from tests/test_smoke.py (keep in sync if fixtures move).
SRC_DIRS = dict(
    BASE=os.path.join(FIX, "claude"),
    CODEX_DIR=os.path.join(FIX, "codex"),
    GEMINI_DIR=os.path.join(FIX, "gemini"),
    PI_DIR=os.path.join(FIX, "pi"),
    OPENCODE_DIR=os.path.join(FIX, "opencode"),
    CURSOR_DIR=os.path.join(FIX, "cursor", "projects"),
    CURSOR_DB=os.path.join(FIX, "cursor", "state.vscdb"),
)


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
        with open(GOLDEN) as f:
            golden = json.load(f)
        actual = run_paxel_stats()
        self.assertEqual(
            json.dumps(actual, sort_keys=True, default=str),
            json.dumps(golden, sort_keys=True, default=str),
        )


if __name__ == "__main__":
    unittest.main()
