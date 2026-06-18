"""Regression: cursor-jsonl and cursor-sqlite have INDEPENDENT discovery gates.

CURSOR_DIR (~/.cursor/projects, the JSONL transcripts) and CURSOR_DB (state.vscdb,
the SQLite copy) are unrelated paths. A user may have one without the other, so
discover_sources(['cursor']) must emit each entry based on ITS OWN path existing —
not gate the SQLite entry behind the JSONL dir. The EventSource refactor regressed
this (both fell behind isdir(CURSOR_DIR)); these tests pin all four combos.
"""
import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
import paxel  # noqa: E402
from fixture_dirs import FIX  # noqa: E402

REAL_DIR = os.path.join(FIX, "cursor", "projects")
REAL_DB = os.path.join(FIX, "cursor", "state.vscdb")
MISSING = os.path.join(FIX, "cursor", "__nonexistent__")


def _fmts(triples):
    return [fmt for _, _, fmt in triples]


class CursorDiscoveryGates(unittest.TestCase):
    def test_both_present(self):
        with mock.patch.multiple(paxel, CURSOR_DIR=REAL_DIR, CURSOR_DB=REAL_DB):
            got = _fmts(paxel.discover_sources(["cursor"]))
        # jsonl entries (>=1) then exactly one sqlite, sqlite last.
        self.assertIn("cursor-jsonl", got)
        self.assertEqual(got.count("cursor-sqlite"), 1)
        self.assertEqual(got[-1], "cursor-sqlite")

    def test_only_db(self):
        # DB exists, JSONL dir does not → cursor-sqlite must STILL appear (the regression).
        with mock.patch.multiple(paxel, CURSOR_DIR=MISSING, CURSOR_DB=REAL_DB):
            got = paxel.discover_sources(["cursor"])
        self.assertEqual(got, [("cursor", REAL_DB, "cursor-sqlite")])

    def test_only_dir(self):
        # JSONL dir exists, DB does not → only cursor-jsonl entries, no sqlite.
        with mock.patch.multiple(paxel, CURSOR_DIR=REAL_DIR, CURSOR_DB=MISSING):
            got = _fmts(paxel.discover_sources(["cursor"]))
        self.assertTrue(got)
        self.assertNotIn("cursor-sqlite", got)
        self.assertEqual(set(got), {"cursor-jsonl"})

    def test_neither(self):
        with mock.patch.multiple(paxel, CURSOR_DIR=MISSING, CURSOR_DB=MISSING):
            got = paxel.discover_sources(["cursor"])
        self.assertEqual(got, [])


if __name__ == "__main__":
    unittest.main()
