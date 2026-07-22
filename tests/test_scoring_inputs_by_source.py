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
from gnomon.cli.accumulator import Accumulator
from tests.test_smoke import _claude_turn, _run_claude_transcript


def _user_prompt_event(sid, ts, text="hello there refactor", cwd="/repo"):
    """A genuine human prompt event in the Claude-shaped form Accumulator.observe expects."""
    ev = {"type": "user", "sessionId": sid, "cwd": cwd,
          "message": {"role": "user", "content": text}}
    if ts is not None:
        ev["timestamp"] = ts
    return ev


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
                    ANTIGRAVITY_CLI_DIR=empty, ANTIGRAVITY_IDE_DIR=empty, ANTIGRAVITY_DB=os.path.join(empty, "nope.vscdb"),
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
                 "fanout_median", "shell_test_runs", "plan_sessions", "planning_skill_sessions",
                 "eligible_change_sessions", "planned_eligible_sessions",
                 "evidence_eligible_sessions", "ordered_facts_state", "delegate_actions",
                 "linked_model_pairs", "linked_model_routing_state",
                 "background_tasks", "iteration_depth_mean", "iteration_depth_p90",
                 "iteration_depth_max", "files_hammered_over_15x", "no_tool_activity"}
    _STACK = {"skills_distinct", "skills_total", "compounding_writes",
              "subagent_types_distinct", "subagent_types", "max_session_subagent_types",
              "top_skills", "skills_all", "models"}
    _TOOLS = {"agent_calls", "mcp_servers_distinct", "clis_distinct", "toolsearch_calls",
              "task_tool_calls", "cli_calls", "mcp_calls", "tool_diversity",
              "tool_entropy_normalized", "top_tools",
              "mcp_knowledge_calls", "mcp_knowledge_servers", "mcp_knowledge_server_names",
              "mcp_subcategory_breakdown", "mcp_grounded_sessions", "mcp_write_sessions"}

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
        self.assertEqual(summary["scoring_inputs_version"], 5)
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

    def test_shareable_payload_retains_raw_custom_skill_and_mcp_identifiers(self):
        custom_skill = "customer-acme-release-review"
        custom_mcp_server = "customer-acme-prod"
        skill_rows = _claude_turn(
            "raw-skill", "2026-03-01T10:00:00.000Z", prompt="use custom skill", tool="Skill")
        skill_rows[1]["message"]["content"][1]["input"]["skill"] = custom_skill
        mcp_rows = _claude_turn(
            "raw-mcp", "2026-03-01T11:00:00.000Z", prompt="query custom server",
            tool=f"mcp__{custom_mcp_server}__lookup")

        summary = paxel.build_summary(_run_claude_transcript(self, skill_rows + mcp_rows))

        self.assertIn(custom_skill, [entry["name"] for entry in summary["ecosystem"]["top_skills"]])
        self.assertIn(
            custom_mcp_server,
            [entry["server"] for entry in summary["ecosystem"]["top_mcp_servers"]],
        )
        window = summary["scoring_inputs_by_source"]["claude"]["window"]
        self.assertIn(custom_skill, dict(window["stack"]["skills_all"]))
        self.assertIn(
            f"mcp__{custom_mcp_server}__lookup",
            dict(window["tools"]["top_tools"]),
        )

    def _grounded_rows(self, sid, ts):
        return [
            {"type": "assistant", "sessionId": sid, "cwd": "/repo", "timestamp": ts,
             "message": {"role": "assistant", "content": [
                 {"type": "tool_use", "name": "mcp__engram__mem_search", "input": {}}]}},
            {"type": "assistant", "sessionId": sid, "cwd": "/repo", "timestamp": ts,
             "message": {"role": "assistant", "content": [
                 {"type": "tool_use", "name": "Edit",
                  "input": {"file_path": "/repo/a.py", "new_string": "x", "old_string": ""}}]}},
        ]

    def test_window_tools_block_carries_mcp_grounded_sessions(self):
        rows = _claude_turn("g1", "2026-03-01T10:00:00.000Z", prompt="ground it")
        rows += self._grounded_rows("g1", "2026-03-01T10:05:00.000Z")
        stats = _run_claude_transcript(self, rows)
        window = paxel.build_summary(stats)["scoring_inputs_by_source"]["claude"]["window"]
        self.assertEqual(window["tools"]["mcp_grounded_sessions"], 1)

    def test_monthly_tools_block_carries_mcp_grounded_sessions(self):
        rows = self._grounded_rows("g1", "2026-03-01T10:00:00.000Z")
        stats = _run_claude_transcript(self, rows)
        block = paxel.build_summary(stats)["scoring_inputs_by_source"]["claude"]
        march = next(m for m in block["monthly"] if m["month"] == "2026-03")
        self.assertEqual(march["tools"]["mcp_grounded_sessions"], 1)


class TestPerSourceParityRegressions(unittest.TestCase):
    """Per-source stats must match a per-slice _accumulate (the pre-single-pass path):
    source-local null-honesty, source-local git window, and the session-count fallback."""

    def test_single_active_source_among_many_does_not_crash(self):
        """P1: ≥2 source types discovered but only 1 active in-window must not make
        main() take the multi-source path with None entries (build_scoring_inputs(None))."""
        claude_dir = tempfile.mkdtemp(prefix="paxel-p1-claude-")
        gemini_dir = tempfile.mkdtemp(prefix="paxel-p1-gemini-")
        out = tempfile.mkdtemp(prefix="paxel-p1-out-")
        empty = tempfile.mkdtemp(prefix="paxel-p1-empty-")
        for d in (claude_dir, gemini_dir, out, empty):
            self.addCleanup(shutil.rmtree, d, ignore_errors=True)

        csess = os.path.join(claude_dir, "proj-a")
        os.makedirs(csess, exist_ok=True)
        with open(os.path.join(csess, "s.jsonl"), "w", encoding="utf-8") as fh:
            for r in _claude_turn("c1", "2026-04-01T10:00:00.000Z", cwd="/repoA",
                                  prompt="claude in window"):
                fh.write(json.dumps(r) + "\n")

        # Gemini is discovered (file mtime is now) but every event is far before the
        # window, so its slice ends up with zero in-window prompts/tools/sessions.
        gsess = os.path.join(gemini_dir, "hash1")
        os.makedirs(gsess, exist_ok=True)
        gem = {"sessionId": "g1", "projectHash": "hash1",
               "messages": [{"id": "u1", "type": "user", "content": "old gemini work",
                             "timestamp": "2020-01-01T10:00:00.000Z"}]}
        with open(os.path.join(gsess, "session-x.json"), "w", encoding="utf-8") as fh:
            json.dump(gem, fh)

        dirs = dict(BASE=claude_dir, GEMINI_DIR=gemini_dir, CODEX_DIR=empty,
                    ANTIGRAVITY_CLI_DIR=empty, ANTIGRAVITY_IDE_DIR=empty, ANTIGRAVITY_DB=os.path.join(empty, "nope.vscdb"),
                    PI_DIR=empty, OPENCODE_DIR=empty, CURSOR_DIR=empty,
                    CURSOR_DB=os.path.join(empty, "no.vscdb"))
        with mock.patch.multiple(paxel, OUT_DIR=out, **dirs), \
                mock.patch.object(sys, "argv",
                                  ["paxel.py", "claude", "gemini", "--no-open", "--since=2026-01-01"]), \
                contextlib.redirect_stdout(io.StringIO()):
            paxel.main()  # must not raise

        with open(os.path.join(out, "stats.json"), encoding="utf-8") as fh:
            stats = json.load(fh)
        # Both source types discovered → multi-source path, real entry for the active one.
        self.assertIn("claude", stats["scoring_inputs_by_source"])

    def test_prompt_only_source_reports_none_for_tool_metrics(self):
        """P2: a source with sessions but zero tool calls is null-honest source-locally
        (None), not numeric 0 inherited from a tool-active corpus."""
        acc = Accumulator()
        acc.begin_file("gemini", "/g/s.json")
        for ev in (_user_prompt_event("g1", "2026-03-01T10:00:00.000Z"),
                   _user_prompt_event("g1", "2026-03-01T10:05:00.000Z", "another note")):
            acc.observe(ev, None, None)
        acc.end_file()
        s = acc.to_source_stats("gemini", None, None)

        self.assertEqual(s["volume"]["tool_calls_total"], 0)
        self.assertGreater(s["volume"]["total_prompts"], 0)
        b = s["behavior"]
        self.assertIsNone(b["error_rate_per_100_tools"])
        self.assertIsNone(b["error_recovery_ratio"])
        self.assertIsNone(b["iteration_depth_mean"])
        self.assertIsNone(b["fanout_median"])

    def test_undated_session_counted_via_session_files_fallback(self):
        """P3: a slice whose events are undated (no parseable timestamp) still counts
        the session via the len(session_files) fallback."""
        acc = Accumulator()
        acc.begin_file("gemini", "/g/s.json")
        acc.observe(_user_prompt_event("u1", None, "undated work"), None, None)
        acc.end_file()
        s = acc.to_source_stats("gemini", None, None)
        self.assertEqual(s["volume"]["total_sessions"], 1)


class TestPlanCeremonyToolCounting(unittest.TestCase):
    """Plan-ceremony metric: a session with any plan-signal tool must mark exactly one
    planning session (behavior.plan_sessions), read-only plan tools must NOT, and the
    count must NOT leak a fabricated 'plan' skill into the raw skill exports.

    Regression: commit #22 counted only EnterPlanMode/TodoWrite, so Claude Code's native
    plan mode — which emits ExitPlanMode (shift+tab -> present plan) — scored 0."""

    def _source_stats(self, tool, sid="s1"):
        acc = Accumulator()
        acc.begin_file("claude", "/c/s.jsonl")
        for row in _claude_turn(sid, "2026-05-01T10:00:00.000Z",
                                tool=tool, prompt="plan it"):
            acc.observe(row, None, None)
        acc.end_file()
        return acc.to_source_stats("claude", None, None)

    def _plan_count(self, tool):
        return self._source_stats(tool)["behavior"]["plan_sessions"]

    def test_exit_plan_mode_counts(self):
        # The bug: Claude Code native plan mode emits ExitPlanMode, not EnterPlanMode.
        self.assertEqual(self._plan_count("ExitPlanMode"), 1)

    def test_enter_plan_mode_counts(self):
        # Cursor's create_plan normalizes to EnterPlanMode — must stay counted.
        self.assertEqual(self._plan_count("EnterPlanMode"), 1)

    def test_todo_write_counts(self):
        # Codex update_plan / Antigravity manage_task / Cursor todos normalize here.
        self.assertEqual(self._plan_count("TodoWrite"), 1)

    def test_todo_read_does_not_count(self):
        # TodoRead is a read, not a planning act — must not inflate the metric.
        self.assertEqual(self._plan_count("TodoRead"), 0)

    def test_non_plan_tool_does_not_count(self):
        self.assertEqual(self._plan_count("Read"), 0)

    def test_repeated_plan_tool_in_one_session_counts_once(self):
        # The whole point of Option B: TodoWrite fires many times per session but must
        # count the session ONCE, not per call.
        acc = Accumulator()
        acc.begin_file("claude", "/c/s.jsonl")
        for _ in range(5):
            for row in _claude_turn("s1", "2026-05-01T10:00:00.000Z",
                                    tool="TodoWrite", prompt="track"):
                acc.observe(row, None, None)
        acc.end_file()
        self.assertEqual(acc.to_source_stats("claude", None, None)["behavior"]["plan_sessions"], 1)

    def test_plan_tools_do_not_pollute_raw_skill_exports(self):
        # Issue 1: plan-tool counting must NOT fabricate a 'plan' skill in top_skills/
        # skills_all — those exports are for real Skill invocations only.
        st = self._source_stats("ExitPlanMode")["stack"]
        self.assertNotIn("plan", dict(st["top_skills"]))
        self.assertNotIn("plan", dict(st["skills_all"]))
        self.assertEqual(st["skills_total"], 0)

    def test_plan_sessions_never_exceeds_total_sessions(self):
        # Invariant: plan_sessions (numerator) must never exceed total_sessions
        # (denominator). An UNDATED planning session never enters session_ts, so it
        # is not in the denominator — it must not leak into the numerator either.
        acc = Accumulator()
        acc.begin_file("claude", "/c/s.jsonl")
        # One DATED non-plan session (enters session_ts).
        for row in _claude_turn("dated-1", "2026-05-01T10:00:00.000Z",
                                tool="Read", prompt="just read"):
            acc.observe(row, None, None)
        # One UNDATED plan session (ts=None → no timestamp → not in session_ts).
        for row in _claude_turn("undated-1", None,
                                tool="ExitPlanMode", prompt="plan it"):
            acc.observe(row, None, None)
        acc.end_file()
        s = acc.to_source_stats("claude", None, None)
        self.assertLessEqual(
            s["behavior"]["plan_sessions"], s["volume"]["total_sessions"])

    def test_exit_plan_mode_counts_in_monthly_slice(self):
        # The monthly scoring path must also credit the plan session: a dated ExitPlanMode
        # turn must yield behavior.plan_sessions == 1 for that month's slice, mirroring
        # month_shell_test_runs. Regression guard for the monthly aggregation.
        rows = _claude_turn("m1", "2026-05-01T10:00:00.000Z",
                            tool="ExitPlanMode", prompt="plan it")
        stats = _run_claude_transcript(self, rows)
        block = paxel.build_summary(stats)["scoring_inputs_by_source"]["claude"]
        may = next(m for m in block["monthly"] if m["month"] == "2026-05")
        self.assertEqual(may["behavior"]["plan_sessions"], 1)


class TestCrossSourcePlanToolNormalization(unittest.TestCase):
    """FU-3: close the chain — each source's NATIVE plan tool must normalize to a name
    the plan-ceremony counter recognizes ("EnterPlanMode"/"ExitPlanMode"/"TodoWrite").
    The accumulator tests above prove canonical names mark a planning session; these
    prove the source readers actually produce those canonical names before the session
    is marked as a planning session."""

    _COUNTED = {"EnterPlanMode", "ExitPlanMode", "TodoWrite"}

    def test_cursor_create_plan_normalizes_to_counted_name(self):
        from gnomon.sources.cursor import _cursor_tool_name
        self.assertEqual(_cursor_tool_name("create_plan"), "EnterPlanMode")
        self.assertIn(_cursor_tool_name("create_plan"), self._COUNTED)

    def test_cursor_todo_tools_normalize_to_counted_name(self):
        from gnomon.sources.cursor import _cursor_tool_name
        for native in ("update_todo", "update_todos", "update_current_step"):
            self.assertEqual(_cursor_tool_name(native), "TodoWrite", native)

    def test_codex_update_plan_normalizes_to_counted_name(self):
        from gnomon.sources.codex import _codex_tool
        name, _ = _codex_tool({"name": "update_plan", "arguments": "{}"})
        self.assertEqual(name, "TodoWrite")
        self.assertIn(name, self._COUNTED)

    def test_antigravity_manage_task_normalizes_to_counted_name(self):
        from gnomon.sources.antigravity import _AG_TOOL
        self.assertEqual(_AG_TOOL["manage_task"], "TodoWrite")
        self.assertIn(_AG_TOOL["manage_task"], self._COUNTED)


class TestContextGroundingStateMachine(unittest.TestCase):
    """Context Intelligence's behavioral grounding signal: a session is GROUNDED when a
    knowledge-MCP call (any) OR an explore-class project/data/design MCP call precedes
    a later Edit/Write/MultiEdit/NotebookEdit event in that SAME session. Mirrors the
    `_pending_error` per-session, per-file transient state machine pattern."""

    @staticmethod
    def _mcp_ev(sid, ts, server="engram", tool="mem_search"):
        return {"type": "assistant", "sessionId": sid, "timestamp": ts,
                "message": {"role": "assistant", "content": [
                    {"type": "tool_use", "name": f"mcp__{server}__{tool}", "input": {}}]}}

    @staticmethod
    def _native_ev(sid, ts, tool):
        return {"type": "assistant", "sessionId": sid, "timestamp": ts,
                "message": {"role": "assistant", "content": [
                    {"type": "tool_use", "name": tool,
                     "input": {"url": "https://example.com"}}]}}

    @staticmethod
    def _write_ev(sid, ts, name="Edit", file_path="/repo/a.py"):
        inp = {"file_path": file_path}
        if name == "Edit":
            inp["new_string"] = "x"
            inp["old_string"] = ""
        elif name == "Write":
            inp["content"] = "x"
        elif name == "NotebookEdit":
            inp = {"notebook_path": file_path, "new_source": "x"}
        elif name == "MultiEdit":
            inp = {"file_path": file_path,
                   "edits": [{"new_string": "x", "old_string": ""}]}
        return {"type": "assistant", "sessionId": sid, "timestamp": ts,
                "message": {"role": "assistant", "content": [
                    {"type": "tool_use", "name": name, "input": inp}]}}

    def _acc(self, events):
        acc = Accumulator()
        acc.begin_file("claude", "/c/s.jsonl")
        for ev in events:
            acc.observe(ev, None, None)
        acc.end_file()
        return acc

    def test_knowledge_call_then_edit_same_session_is_grounded(self):
        acc = self._acc([
            self._mcp_ev("s1", "2026-05-01T10:00:00.000Z"),
            self._write_ev("s1", "2026-05-01T10:01:00.000Z", "Edit"),
        ])
        self.assertIn("s1", acc.grounded_sessions)

    def test_edit_then_knowledge_call_wrong_order_not_grounded(self):
        acc = self._acc([
            self._write_ev("s1", "2026-05-01T10:00:00.000Z", "Edit"),
            self._mcp_ev("s1", "2026-05-01T10:01:00.000Z"),
        ])
        self.assertNotIn("s1", acc.grounded_sessions)

    def test_knowledge_call_with_no_later_write_not_grounded(self):
        acc = self._acc([self._mcp_ev("s1", "2026-05-01T10:00:00.000Z")])
        self.assertNotIn("s1", acc.grounded_sessions)

    def test_write_with_no_preceding_knowledge_call_not_grounded(self):
        acc = self._acc([self._write_ev("s1", "2026-05-01T10:00:00.000Z", "Edit")])
        self.assertNotIn("s1", acc.grounded_sessions)

    def test_two_writes_after_one_call_counts_one_grounded_session(self):
        # Consume-once: the first grounded write flips the pending flag off.
        acc = self._acc([
            self._mcp_ev("s1", "2026-05-01T10:00:00.000Z"),
            self._write_ev("s1", "2026-05-01T10:01:00.000Z", "Edit"),
            self._write_ev("s1", "2026-05-01T10:02:00.000Z", "Edit"),
        ])
        self.assertEqual(len(acc.grounded_sessions), 1)
        self.assertIn("s1", acc.grounded_sessions)

    def test_write_branch_covers_all_four_tool_types(self):
        for tool in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
            with self.subTest(tool=tool):
                acc = self._acc([
                    self._mcp_ev(f"s-{tool}", "2026-05-01T10:00:00.000Z"),
                    self._write_ev(f"s-{tool}", "2026-05-01T10:01:00.000Z", tool),
                ])
                self.assertIn(f"s-{tool}", acc.grounded_sessions, tool)

    def test_non_knowledge_mcp_call_does_not_ground(self):
        # A browser-category MCP call must NOT mark grounding.
        acc = self._acc([
            self._mcp_ev("s1", "2026-05-01T10:00:00.000Z", server="playwright", tool="navigate"),
            self._write_ev("s1", "2026-05-01T10:01:00.000Z", "Edit"),
        ])
        self.assertNotIn("s1", acc.grounded_sessions)

    def test_web_fetch_and_search_do_not_ground_while_disabled(self):
        for tool in ("WebFetch", "WebSearch"):
            with self.subTest(tool=tool):
                acc = self._acc([
                    self._native_ev("s1", "2026-05-01T10:00:00.000Z", tool),
                    self._write_ev("s1", "2026-05-01T10:01:00.000Z", "Edit"),
                ])
                self.assertNotIn("s1", acc.grounded_sessions)

    def test_distinct_sessions_independent(self):
        acc = self._acc([
            self._mcp_ev("s1", "2026-05-01T10:00:00.000Z"),
            self._write_ev("s1", "2026-05-01T10:01:00.000Z", "Edit"),
            self._write_ev("s2", "2026-05-01T10:02:00.000Z", "Edit"),  # no grounding call
        ])
        self.assertIn("s1", acc.grounded_sessions)
        self.assertNotIn("s2", acc.grounded_sessions)

    def test_corpus_stats_surfaces_grounded_sessions_count(self):
        acc = self._acc([
            self._mcp_ev("s1", "2026-05-01T10:00:00.000Z"),
            self._write_ev("s1", "2026-05-01T10:01:00.000Z", "Edit"),
        ])
        stats = acc.to_corpus_stats(None, None, False)
        self.assertEqual(stats["tools"]["mcp_grounded_sessions"], 1)

    def test_source_stats_surfaces_grounded_sessions_count(self):
        acc = self._acc([
            self._mcp_ev("s1", "2026-05-01T10:00:00.000Z"),
            self._write_ev("s1", "2026-05-01T10:01:00.000Z", "Edit"),
        ])
        s_stats = acc.to_source_stats("claude", None, None)
        self.assertEqual(s_stats["tools"]["mcp_grounded_sessions"], 1)

    def test_monthly_slice_surfaces_grounded_sessions(self):
        acc = self._acc([
            self._mcp_ev("s1", "2026-05-01T10:00:00.000Z"),
            self._write_ev("s1", "2026-05-01T10:01:00.000Z", "Edit"),
        ])
        stats = acc.to_corpus_stats(None, None, False)
        may = next(m for m in stats["_scoring_monthly_full"] if m["month"] == "2026-05")
        self.assertEqual(may["stats_full"]["tools"]["mcp_grounded_sessions"], 1)

    # ---- expanded context grounding (project/data/design explore calls) ----

    def test_project_read_mcp_grounds(self):
        acc = self._acc([
            self._mcp_ev("s1", "2026-05-01T10:00:00.000Z",
                         server="Atlassian", tool="get_issue"),
            self._write_ev("s1", "2026-05-01T10:01:00.000Z", "Edit"),
        ])
        self.assertIn("s1", acc.grounded_sessions)

    def test_project_write_mcp_does_not_ground(self):
        acc = self._acc([
            self._mcp_ev("s1", "2026-05-01T10:00:00.000Z",
                         server="Atlassian", tool="create_issue"),
            self._write_ev("s1", "2026-05-01T10:01:00.000Z", "Edit"),
        ])
        self.assertNotIn("s1", acc.grounded_sessions)

    def test_data_read_mcp_grounds(self):
        acc = self._acc([
            self._mcp_ev("s1", "2026-05-01T10:00:00.000Z",
                         server="claude_ai_Notion", tool="notion_search"),
            self._write_ev("s1", "2026-05-01T10:01:00.000Z", "Edit"),
        ])
        self.assertIn("s1", acc.grounded_sessions)

    def test_data_write_mcp_does_not_ground(self):
        acc = self._acc([
            self._mcp_ev("s1", "2026-05-01T10:00:00.000Z",
                         server="claude_ai_Notion", tool="notion_update_page"),
            self._write_ev("s1", "2026-05-01T10:01:00.000Z", "Edit"),
        ])
        self.assertNotIn("s1", acc.grounded_sessions)

    def test_design_read_mcp_grounds(self):
        acc = self._acc([
            self._mcp_ev("s1", "2026-05-01T10:00:00.000Z",
                         server="Figma", tool="get_design_context"),
            self._write_ev("s1", "2026-05-01T10:01:00.000Z", "Edit"),
        ])
        self.assertIn("s1", acc.grounded_sessions)

    def test_communication_read_mcp_does_not_ground(self):
        acc = self._acc([
            self._mcp_ev("s1", "2026-05-01T10:00:00.000Z",
                         server="claude_ai_Slack", tool="slack_read_channel"),
            self._write_ev("s1", "2026-05-01T10:01:00.000Z", "Edit"),
        ])
        self.assertNotIn("s1", acc.grounded_sessions)

    def test_infra_mcp_does_not_ground(self):
        acc = self._acc([
            self._mcp_ev("s1", "2026-05-01T10:00:00.000Z",
                         server="coolify", tool="status"),
            self._write_ev("s1", "2026-05-01T10:01:00.000Z", "Edit"),
        ])
        self.assertNotIn("s1", acc.grounded_sessions)


class TestSkillUsesAnyReadsFullList(unittest.TestCase):
    """Issue 2: _skill_uses_any must scan skills_all (up to 200), not just top_skills (15).
    A planning/quality skill ranked past the 15th slot must still count."""

    def test_counts_skill_beyond_top_15(self):
        from gnomon.scoring.gstack import _skill_uses_any
        # 15 unrelated high-use skills crowd out top_skills; the plan skill ranks 16th.
        filler = [[f"skill-{i}", 100 - i] for i in range(15)]
        skills_all = filler + [["writing-plan", 3]]
        stats = {"stack": {"top_skills": filler, "skills_all": skills_all}}
        self.assertEqual(_skill_uses_any(stats, ("writing-plan",)), 3)

    def test_falls_back_to_top_skills_when_no_skills_all(self):
        from gnomon.scoring.gstack import _skill_uses_any
        stats = {"stack": {"top_skills": [["writing-plan", 2]]}}
        self.assertEqual(_skill_uses_any(stats, ("writing-plan",)), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
