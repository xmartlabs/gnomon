"""End-to-end coverage of the MULTI-SOURCE corpus AQ, driven through the CLI.

The golden vectors (tests/fixtures/scoring_vectors.json) cannot cover this. They enter at
`score_by_source`, which scores each source's slice through `stats_from_scoring_block` — a
shaper that reconstructs one source at a time and never assembles a merged corpus. So every
vector case is single-source by construction, however many sources the input carries.

The merged corpus is assembled in exactly one place: `gnomon/cli/local.py`, which pools every
source's accumulator into one stats dict and calls `compute_aq` on it (and again per rolling
bucket). That is the only path where a rate's numerator and denominator are summed across
sources, which is precisely where the cross-source denominator bug lived — and it had no test.
These run the real CLI over two real transcript corpora with deliberately opposite session
shapes (few dense Claude sessions, many one-shot Codex sessions) and pin the merged reading.
"""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paxel


def _claude_rows(sessions, calls_per_session, test_runs_per_session, day=10):
    """`sessions` dense Claude sessions, each running `calls_per_session` tools of which
    `test_runs_per_session` are recognisable test invocations."""
    rows = []
    for s in range(sessions):
        sid = f"claude-{s}"
        cwd = "/Users/demo/proj"
        for i in range(calls_per_session):
            # One call per minute, rolled over into hours: a bare `{i:02d}` minute field
            # silently emitted invalid timestamps (and dropped the calls) past i=59, which
            # capped this fixture at 60 calls/session however many were requested.
            minute_of_day = s * calls_per_session + i
            ts = (f"2026-03-{day:02d}T{minute_of_day // 60:02d}:"
                  f"{minute_of_day % 60:02d}:00.000Z")
            tool, tool_input = "Read", {"file_path": "/Users/demo/proj/a.py"}
            if i < test_runs_per_session:
                tool, tool_input = "Bash", {"command": "python3 -m pytest tests/"}
            rows.append({"type": "user", "sessionId": sid, "cwd": cwd, "timestamp": ts,
                         "message": {"role": "user", "content": "please keep going"}})
            rows.append({"type": "assistant", "sessionId": sid, "cwd": cwd, "timestamp": ts,
                         "message": {"role": "assistant", "model": "claude-opus-4-8",
                                     "content": [{"type": "tool_use", "name": tool,
                                                  "input": tool_input}]}})
            rows.append({"type": "user", "sessionId": sid, "cwd": cwd, "timestamp": ts,
                         "message": {"role": "user", "content": [
                             {"type": "tool_result", "content": "ok", "is_error": False}]}})
    return rows


def _codex_rows(index, calls):
    """One short `codex exec`-shaped session: a handful of tool calls, no test runs."""
    rows = [
        {"type": "session_meta", "timestamp": f"2026-03-12T{index % 24:02d}:00:00Z",
         "payload": {"id": f"codex-{index}", "cwd": "/x"}},
        {"type": "turn_context", "timestamp": f"2026-03-12T{index % 24:02d}:00:01Z",
         "payload": {"model": "gpt-5.4"}},
        {"type": "response_item", "timestamp": f"2026-03-12T{index % 24:02d}:00:02Z",
         "payload": {"type": "message", "role": "user",
                     "content": [{"type": "input_text", "text": "one shot please"}]}},
    ]
    for i in range(calls):
        ts = f"2026-03-12T{index % 24:02d}:{i + 3:02d}:00Z"
        rows.append({"type": "response_item", "timestamp": ts,
                     "payload": {"type": "function_call", "name": "shell",
                                 "call_id": f"c{index}-{i}",
                                 "arguments": json.dumps({"command": ["ls", "-la"]})}})
        rows.append({"type": "response_item", "timestamp": ts,
                     "payload": {"type": "function_call_output", "call_id": f"c{index}-{i}",
                                 "output": "ok"}})
    return rows


class TestMultiSourceCorpusAq(unittest.TestCase):
    """Both sources merged into ONE corpus, scored by the real CLI."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = []
        claude_dir = cls._mkdtemp("claude-")
        sess_dir = os.path.join(claude_dir, "proj-x")
        os.makedirs(sess_dir, exist_ok=True)
        with open(os.path.join(sess_dir, "session.jsonl"), "w", encoding="utf-8") as fh:
            # Three test runs per 175 tool calls keeps Claude's own rate BELOW target, so
            # the merged reading is an unsaturated number and the arithmetic stays visible.
            # The pooled 12/1000 is exact in the 6-decimal rounding the axis publishes, so
            # test_merged_rate_is_not_the_pooled_session_rate's ratio identity holds exactly.
            #
            # Both sources are sized so every slice clears aq.py's rate evidence floor
            # (RATE_MIN_EXPECTED_AT_TARGET): the review-skill target implies >250 tool calls,
            # and the earlier fixture gave Claude only 200, so its (measured zero) review
            # term was dropped on the slice while the pooled corpus kept it -- comparing a
            # one-term slice against a two-term merged axis. Rates are unchanged (still one
            # unsaturated Claude test-run rate, still no codex test runs); only the
            # denominators grew, to 175 and 10 calls/session against the 39-179
            # calls/session real corpora span documented in aq.py.
            for r in _claude_rows(sessions=4, calls_per_session=175, test_runs_per_session=3):
                fh.write(json.dumps(r) + "\n")
        codex_dir = cls._mkdtemp("codex-")
        for i in range(30):
            with open(os.path.join(codex_dir, f"s{i}.jsonl"), "w", encoding="utf-8") as fh:
                for r in _codex_rows(i, calls=10):
                    fh.write(json.dumps(r) + "\n")
        cls.stats, cls.summary = cls._run(claude_dir, codex_dir)

    @classmethod
    def tearDownClass(cls):
        for path in cls._tmp:
            shutil.rmtree(path, ignore_errors=True)

    @classmethod
    def _mkdtemp(cls, prefix):
        path = tempfile.mkdtemp(prefix="gnomon-multisource-" + prefix)
        cls._tmp.append(path)
        return path

    @classmethod
    def _run(cls, claude_dir, codex_dir):
        empty = cls._mkdtemp("empty-")
        out = cls._mkdtemp("out-")
        overrides = dict(
            BASE=claude_dir, CODEX_DIR=codex_dir, GEMINI_DIR=empty, PI_DIR=empty,
            ANTIGRAVITY_CLI_DIR=empty, ANTIGRAVITY_IDE_DIR=empty,
            ANTIGRAVITY_DB=os.path.join(empty, "nope.vscdb"),
            OPENCODE_DIR=empty, CURSOR_DIR=empty,
            CURSOR_DB=os.path.join(empty, "nope.vscdb"),
        )
        # The window is pinned in the past so the rolling recent-30d bucket is empty and the
        # published AQ is the raw full-window compute_aq, not a 65/35 blend of two of them.
        argv = ["paxel.py", "--no-open", "--summary",
                "--since=2026-03-01", "--until=2026-03-31"]
        with mock.patch.multiple(paxel, OUT_DIR=out, **overrides), \
                mock.patch.object(sys, "argv", argv), \
                contextlib.redirect_stdout(io.StringIO()):
            paxel.main()
        with open(os.path.join(out, "stats.json"), encoding="utf-8") as fh:
            stats = json.load(fh)
        with open(os.path.join(out, "summary.json"), encoding="utf-8") as fh:
            summary = json.load(fh)
        return stats, summary

    def _axis(self, aq, pillar, axis):
        p = next(p for p in aq["pillars"] if p["name"] == pillar)
        return next(a for a in p["axes"] if a["name"] == axis)

    def test_the_corpus_really_is_two_sources_with_opposite_session_shapes(self):
        """Guard the fixture itself: if either source stopped landing in the corpus these
        assertions would keep passing against a single-source run and prove nothing."""
        by_source = self.stats["scoring_inputs_by_source"]
        self.assertEqual({"claude", "codex"}, {s for s, b in by_source.items()
                                               if (b["window"]["volume"]["total_sessions"])})
        claude = by_source["claude"]["window"]["volume"]
        codex = by_source["codex"]["window"]["volume"]
        self.assertGreater(claude["tool_calls_total"] / claude["total_sessions"],
                           5 * codex["tool_calls_total"] / codex["total_sessions"])
        self.assertGreater(codex["total_sessions"], claude["total_sessions"])

    def test_merged_rate_denominator_is_the_pooled_tool_call_count(self):
        verification = self._axis(self.stats["agentic"], "Craft", "Verification")
        by_source = self.stats["scoring_inputs_by_source"]
        pooled_calls = sum(b["window"]["volume"]["tool_calls_total"]
                           for b in by_source.values())
        self.assertEqual(verification["signals"]["tool_calls"], pooled_calls)
        self.assertEqual(verification["signals"]["tool_calls"],
                         self.stats["volume"]["tool_calls_total"])
        self.assertAlmostEqual(
            verification["signals"]["test_runs_per_call"],
            round(verification["signals"]["test_runs"] / pooled_calls, 6), places=9)

    def test_merged_rate_is_not_the_pooled_session_rate(self):
        """The regression this replaces: dividing the same numerator by merged SESSIONS.

        Pin the RATIO between the two denominators rather than asserting some factor is
        "large": the ratio IS mean tool calls per session, so this fails both if the rate
        reverts to a session denominator (ratio collapses to 1) and if the fixture stops
        having sources of opposite density (ratio drifts). A magic threshold would only
        catch the first, and would silently track whatever the fixture happens to be.
        """
        verification = self._axis(self.stats["agentic"], "Craft", "Verification")
        sessions = self.stats["volume"]["total_sessions"]
        per_call = verification["signals"]["test_runs_per_call"]
        per_session = verification["signals"]["test_runs"] / sessions
        self.assertAlmostEqual(
            per_session / per_call,
            self.stats["volume"]["tool_calls_total"] / sessions, places=3)
        # And the denominators are far enough apart that the distinction is not academic:
        # a session on this corpus carries several tool calls, so scoring per session
        # inflates the same numerator severalfold.
        self.assertGreater(per_session, 5 * per_call)

    def test_codex_one_shots_do_not_bury_the_verification_claude_did(self):
        """The dilution the change exists to fix: 30 one-shot sessions carrying a fraction
        of the tool volume must move the merged reading by roughly their share of the WORK,
        not by their share of the session count."""
        merged = self._axis(self.stats["agentic"], "Craft", "Verification")["normalized_score"]
        by_source = self.summary["profiles_by_source"]["by_source"]
        claude_alone = self._axis(by_source["claude"]["aq"], "Craft",
                                  "Verification")["normalized_score"]
        codex_alone = self._axis(by_source["codex"]["aq"], "Craft",
                                 "Verification")["normalized_score"]
        self.assertGreater(claude_alone, codex_alone)
        self.assertGreaterEqual(merged, codex_alone)
        self.assertLessEqual(merged, claude_alone)
        # Codex carries 30% of the tool calls here, so it may not cost more than half.
        self.assertGreater(merged, claude_alone * 0.5)

    def test_summary_publishes_per_source_and_aggregate_profiles(self):
        """score_by_source's multi-source branch, exercised from a real two-source run —
        the golden vectors only ever reach its single-source shaper."""
        profiles = self.summary["profiles_by_source"]
        self.assertEqual(set(profiles["by_source"]), {"claude", "codex"})
        self.assertIn("aq_diagnostic", profiles["aggregate"])
        self.assertEqual(profiles["aggregate"]["canonical_aq"], "profile.aq")
        self.assertEqual(set(profiles["aggregate"]["combination"]["weights"]),
                         {"claude", "codex"})


if __name__ == "__main__":
    unittest.main()
