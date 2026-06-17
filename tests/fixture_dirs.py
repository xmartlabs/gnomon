"""Shared fixture paths for the test suite.

The source-discovery globals are redirected at these committed fixtures so runs are
hermetic (never touch the developer's real ~/.claude, ~/.codex, etc.). Imported by
both tests/test_smoke.py and tests/test_golden_stats.py so the paths stay in one place.
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(HERE, "fixtures")

SRC_DIRS = dict(
    BASE=os.path.join(FIX, "claude"),
    CODEX_DIR=os.path.join(FIX, "codex"),
    GEMINI_DIR=os.path.join(FIX, "gemini"),
    PI_DIR=os.path.join(FIX, "pi"),
    OPENCODE_DIR=os.path.join(FIX, "opencode"),
    CURSOR_DIR=os.path.join(FIX, "cursor", "projects"),
    CURSOR_DB=os.path.join(FIX, "cursor", "state.vscdb"),
)
