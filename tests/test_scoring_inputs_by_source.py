import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

import paxel
from tests.test_smoke import _claude_turn, _run_claude_transcript


class TestPerSourceChurnIsolation(unittest.TestCase):
    """Per-source git churn must be restricted to each source's cwd set."""

    def test_each_source_churn_sees_only_its_own_cwds(self):
        claude_dir = tempfile.mkdtemp(prefix="paxel-iso-claude-")
        gemini_dir = tempfile.mkdtemp(prefix="paxel-iso-gemini-")
        out = tempfile.mkdtemp(prefix="paxel-iso-out-")
        empty = tempfile.mkdtemp(prefix="paxel-iso-empty-")
        for d in (claude_dir, gemini_dir, out, empty):
            self.addCleanup(shutil.rmtree, d, ignore_errors=True)

        csess = os.path.join(claude_dir, "proj-a")
        os.makedirs(csess, exist_ok=True)
        with open(os.path.join(csess, "s.jsonl"), "w", encoding="utf-8") as fh:
            for r in _claude_turn("c1", "2026-04-01T10:00:00.000Z", cwd="/repoA",
                                  tool="Edit", file_path="/repoA/x.py",
                                  new_string="a", prompt="claude work"):
                fh.write(json.dumps(r) + "\n")

        gsess = os.path.join(gemini_dir, "hash1")
        os.makedirs(gsess, exist_ok=True)
        gem = {"sessionId": "g1", "projectHash": "hash1",
               "messages": [
                   {"id": "u1", "type": "user", "content": "gemini work",
                    "timestamp": "2026-04-02T10:00:00.000Z"},
                   {"id": "m1", "type": "gemini", "content": "done",
                    "timestamp": "2026-04-02T10:00:01.000Z",
                    "toolCalls": [{"name": "read_file",
                                   "args": {"dir_path": "/repoB"}}]},
               ]}
        with open(os.path.join(gsess, "session-x.json"), "w", encoding="utf-8") as fh:
            json.dump(gem, fh)

        churn_cwds = []

        def spy(cwds, since, until):
            churn_cwds.append(set(cwds))
            return {"repos_seen": 0, "repos_with_commits": 0, "insertions": 0,
                    "deletions": 0, "churn": 0, "commits": 0, "per_repo": []}

        dirs = dict(BASE=claude_dir, GEMINI_DIR=gemini_dir, CODEX_DIR=empty,
                    ANTIGRAVITY_CLI_DIR=empty, ANTIGRAVITY_DB=os.path.join(empty, "nope.vscdb"),
                    PI_DIR=empty, OPENCODE_DIR=empty, CURSOR_DIR=empty,
                    CURSOR_DB=os.path.join(empty, "no.vscdb"))
        with mock.patch.multiple(paxel, OUT_DIR=out, **dirs), \
                mock.patch.object(paxel, "git_churn", spy), \
                mock.patch.object(sys, "argv",
                                  ["paxel.py", "claude", "gemini", "--no-open"]), \
                contextlib.redirect_stdout(io.StringIO()):
            paxel.main()

        self.assertTrue(any(c == {"/repoA"} for c in churn_cwds),
                        f"no claude-only churn call; saw {churn_cwds}")
        self.assertTrue(any(c == {"/repoB"} for c in churn_cwds),
                        f"no gemini-only churn call; saw {churn_cwds}")
        self.assertTrue(any(c == {"/repoA", "/repoB"} for c in churn_cwds),
                        f"expected a whole-corpus churn call over both repos; saw {churn_cwds}")


class TestScoringInputsBySource(unittest.TestCase):
    """scoring_inputs_by_source — raw scoring inputs per source x (window + month)."""

    _VOLUME = {"total_sessions", "total_prompts", "tool_calls_total", "thinking_blocks"}
    _VELOCITY = {"active_hours", "tool_churn_edit_write", "shell_authored_lines_est"}
    _BEHAVIOR = {"planning_ratio_explore_to_doing", "actions_per_prompt", "questions_asked",
                 "error_recovery_ratio", "error_rate_per_100_tools", "api_errors_retries",
                 "fanout_median", "shell_test_runs", "delegate_actions", "background_tasks",
                 "iteration_depth_mean", "iteration_depth_p90", "iteration_depth_max",
                 "files_hammered_over_15x"}
    _STACK = {"skills_distinct", "skills_total", "compounding_writes",
              "subagent_types_distinct", "subagent_types", "top_skills", "skills_all", "models"}
    _TOOLS = {"agent_calls", "mcp_servers_distinct", "clis_distinct", "toolsearch_calls",
              "task_tool_calls", "cli_calls", "mcp_calls", "tool_diversity",
              "tool_entropy_normalized", "top_tools"}

    def _stats(self):
        rows = []
        rows += _claude_turn("si-jan", "2026-01-10T10:00:00.000Z", tool="Edit",
                             file_path="/Users/demo/proj/a.py",
                             new_string="x\ny", prompt="jan one")
        rows += _claude_turn("si-feb", "2026-02-12T11:00:00.000Z", tool="Write",
                             file_path="/Users/demo/proj/b.py",
                             new_string="z", prompt="feb one")
        return _run_claude_transcript(self, rows)

    def test_payload_has_version_and_by_source(self):
        stats = self._stats()
        summary = paxel.build_summary(stats)
        self.assertEqual(summary["scoring_inputs_version"], 1)
        self.assertIn("claude", summary["scoring_inputs_by_source"])

    def test_block_field_set_window_and_monthly(self):
        stats = self._stats()
        sibs = paxel.build_summary(stats)["scoring_inputs_by_source"]
        block = sibs["claude"]
        self.assertIn("window", block)
        self.assertIn("monthly", block)
        all_blocks = [block["window"]] + list(block["monthly"])
        for b in all_blocks:
            self.assertEqual(b["source"], "claude")
            self.assertEqual(set(b["volume"]), self._VOLUME)
            self.assertEqual(set(b["velocity"]), self._VELOCITY)
            self.assertEqual(set(b["behavior"]), self._BEHAVIOR)
            self.assertEqual(set(b["stack"]), self._STACK)
            self.assertEqual(set(b["tools"]), self._TOOLS)
        months = sorted(m["month"] for m in block["monthly"])
        self.assertEqual(months, ["2026-01", "2026-02"])

    def test_window_volume_matches_corpus(self):
        stats = self._stats()
        sibs = paxel.build_summary(stats)["scoring_inputs_by_source"]
        w = sibs["claude"]["window"]["volume"]
        self.assertEqual(w["total_prompts"], stats["volume"]["total_prompts"])
        self.assertEqual(w["tool_calls_total"], stats["volume"]["tool_calls_total"])

    def test_scoring_monthly_full_not_serialized(self):
        stats = self._stats()
        self.assertNotIn("_scoring_monthly_full", stats)

    def test_raw_skill_names_present(self):
        rows = _claude_turn("sk", "2026-03-01T10:00:00.000Z", prompt="use skill",
                            tool="Skill")
        rows[1]["message"]["content"][1]["input"]["skill"] = "writing-plans"
        stats = _run_claude_transcript(self, rows)
        block = paxel.build_summary(stats)["scoring_inputs_by_source"]["claude"]["window"]
        names = [k for k, _ in block["stack"]["skills_all"]]
        self.assertIn("writing-plans", names)


if __name__ == "__main__":
    unittest.main(verbosity=2)
