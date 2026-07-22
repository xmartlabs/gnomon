import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gnomon.cli.accumulator import Accumulator
from gnomon.sources.cursor import (
    _cursor_bubble_blocks,
    _cursor_extract_injected_skills,
    _cursor_jsonl_events,
    _cursor_tool,
    _cursor_tool_name,
)
from gnomon.taxonomy import extract_skill_name_from_path


class TestCursorSkillMetrics(unittest.TestCase):
    def test_extract_skill_name_from_path(self):
        self.assertEqual(
            extract_skill_name_from_path("/Users/me/.cursor/skills/foo/SKILL.md"),
            "foo",
        )
        self.assertIsNone(extract_skill_name_from_path("/tmp/readme.md"))

    def test_injected_skills_parsed_from_context_blocks(self):
        text = (
            '<manually_attached_skills>'
            '<agent_skill fullPath="/Users/me/.cursor/skills/bar/SKILL.md">'
            '</agent_skill></manually_attached_skills>'
        )
        self.assertEqual(_cursor_extract_injected_skills(text), ["bar"])

    def test_available_skills_catalog_not_counted(self):
        skills = [f"skill-{i}" for i in range(5)]
        text = '<available_skills>' + ''.join(
            f'<agent_skill fullPath="/Users/x/.cursor/skills/{s}/SKILL.md"></agent_skill>'
            for s in skills) + '</available_skills>'
        self.assertEqual(_cursor_extract_injected_skills(text), [])

    def test_read_skill_md_counts_skill(self):
        acc = Accumulator()
        acc.begin_file("cursor", "s.jsonl")
        ev = {
            "type": "assistant",
            "sessionId": "s1",
            "timestamp": "2026-05-01T10:00:00.000Z",
            "message": {
                "role": "assistant",
                "content": [{
                    "type": "tool_use",
                    "name": "Read",
                    "input": {"file_path": "/Users/me/skills/code-review/SKILL.md"},
                }],
            },
        }
        acc.observe(ev, None, None)
        acc.end_file()
        self.assertEqual(acc.skill_counter["code-review"], 1)

    def test_injected_skills_on_user_event_counted(self):
        acc = Accumulator()
        acc.begin_file("cursor", "s.jsonl")
        ev = {
            "type": "user",
            "sessionId": "s2",
            "timestamp": "2026-05-01T10:00:00.000Z",
            "injectedSkills": ["slim-pr-description", "context7-mcp"],
            "message": {"role": "user", "content": "plan this"},
        }
        acc.observe(ev, None, None)
        acc.end_file()
        self.assertEqual(acc.skill_counter["slim-pr-description"], 1)
        self.assertEqual(acc.skill_counter["context7-mcp"], 1)
        self.assertEqual(acc.skill_counter.most_common(2),
                         [("slim-pr-description", 1), ("context7-mcp", 1)])

    def test_jsonl_injected_only_user_turn_yields_event(self):
        """JSONL must match SQLite: skill-only turns (no <user_query> text) still emit events."""
        injected = (
            '<manually_attached_skills>'
            '<agent_skill fullPath="/Users/me/.cursor/skills/foo/SKILL.md">'
            '</agent_skill></manually_attached_skills>'
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as fh:
            json.dump({"role": "user", "message": {"content": [{"type": "text", "text": injected}]}},
                      fh)
            fh.write("\n")
            path = fh.name
        try:
            events = list(_cursor_jsonl_events(path))
            user_events = [e for e in events if e.get("type") == "user"]
            self.assertEqual(len(user_events), 1)
            self.assertEqual(user_events[0].get("injectedSkills"), ["foo"])
            self.assertEqual(user_events[0]["message"]["content"], "")
        finally:
            os.unlink(path)


class TestCursorOrchestrationMetrics(unittest.TestCase):
    def test_task_tool_maps_to_agent(self):
        self.assertEqual(_cursor_tool_name("Task"), "Agent")

    def test_subagent_type_from_camel_case(self):
        name, inp = _cursor_tool("task_v2", {
            "subagentType": "explore",
            "prompt": "look around",
        })
        self.assertEqual(name, "Agent")
        self.assertEqual(inp["subagent_type"], "explore")

    def test_explore_subagent_counted(self):
        acc = Accumulator()
        acc.begin_file("cursor", "s.jsonl")
        ev = {
            "type": "assistant",
            "sessionId": "s1",
            "timestamp": "2026-05-01T10:00:00.000Z",
            "message": {
                "role": "assistant",
                "content": [{
                    "type": "tool_use",
                    "name": "Agent",
                    "input": {"subagent_type": "explore"},
                }],
            },
        }
        acc.observe(ev, None, None)
        acc.end_file()
        self.assertEqual(acc.subagent_counter["explore"], 1)

    def test_parallel_dispatch_turns_counted(self):
        acc = Accumulator()
        acc.begin_file("cursor", "s.jsonl")
        ev = {
            "type": "assistant",
            "sessionId": "s1",
            "timestamp": "2026-05-01T10:00:00.000Z",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "name": "Agent",
                     "input": {"subagent_type": "explore"}},
                    {"type": "tool_use", "name": "Agent",
                     "input": {"subagent_type": "general-purpose"}},
                ],
            },
        }
        acc.observe(ev, None, None)
        acc.end_file()
        stats = acc.to_source_stats("cursor", None, None)
        self.assertEqual(acc.parallel_dispatch_turns, 1)
        self.assertEqual(stats["behavior"]["max_session_fanout"], 2)
        self.assertEqual(stats["behavior"]["parallel_session_share"], 1.0)

    def test_general_purpose_subagent_type_normalized(self):
        name, inp = _cursor_tool("task_v2", {
            "subagentType": "generalPurpose",
            "prompt": "do work",
        })
        self.assertEqual(name, "Agent")
        self.assertEqual(inp["subagent_type"], "general-purpose")


class TestCursorPlanSessionsInvariant(unittest.TestCase):
    def test_synth_plan_sessions_not_counted_when_dated_sessions_exist(self):
        acc = Accumulator()
        acc.begin_file("cursor", "s.jsonl")
        for sid in ("dated-a", "dated-b"):
            acc.observe({
                "type": "user", "sessionId": sid,
                "timestamp": "2026-05-01T10:00:00.000Z",
                "message": {"role": "user", "content": "work"},
            }, None, None)
        for sid in ("plan-1", "plan-2", "plan-3"):
            acc.observe({
                "type": "assistant", "sessionId": sid,
                "timestamp": "2026-05-01T11:00:00.000Z", "__synth_ts__": True,
                "message": {"role": "assistant", "content": [
                    {"type": "tool_use", "name": "EnterPlanMode", "input": {}},
                ]},
            }, None, None)
        acc.end_file()
        stats = acc.to_source_stats("cursor", None, None)
        self.assertLessEqual(
            stats["behavior"]["plan_sessions"],
            stats["volume"]["total_sessions"])


class TestCursorPlanModeMetrics(unittest.TestCase):
    def test_switch_mode_to_plan_maps_to_enter_plan_mode(self):
        name, _ = _cursor_tool("SwitchMode", {"target_mode_id": "plan"})
        self.assertEqual(name, "EnterPlanMode")

    def test_switch_mode_to_plan_marks_plan_session(self):
        acc = Accumulator()
        acc.begin_file("cursor", "s.jsonl")
        ev = {
            "type": "assistant",
            "sessionId": "s-plan",
            "timestamp": "2026-05-01T10:00:00.000Z",
            "message": {
                "role": "assistant",
                "content": [{
                    "type": "tool_use",
                    "name": "EnterPlanMode",
                    "input": {},
                }],
            },
        }
        acc.observe(ev, None, None)
        acc.end_file()
        stats = acc.to_source_stats("cursor", None, None)
        self.assertEqual(stats["behavior"]["plan_sessions"], 1)

    def test_degraded_plan_sessions_fallback(self):
        acc = Accumulator()
        acc.begin_file("cursor", "s.jsonl")
        # Plan signal on a synth-timestamp-only session (no session_ts entry).
        acc.observe({
            "type": "assistant",
            "sessionId": "undated-plan",
            "timestamp": "2026-05-01T10:00:00.000Z",
            "__synth_ts__": True,
            "message": {"role": "assistant", "content": [
                {"type": "tool_use", "name": "EnterPlanMode", "input": {}},
            ]},
        }, None, None)
        acc.end_file()
        stats = acc.to_source_stats("cursor", None, None)
        self.assertEqual(stats["behavior"]["plan_sessions"], 1)


class TestCursorThinkingBlocks(unittest.TestCase):
    def test_malformed_thinking_values_are_ignored_without_losing_valid_order(self):
        bubble = {
            "thinking": {"text": ["not", "text"]},
            "allThinkingBlocks": [
                {"text": {"not": "text"}},
                {"text": "first"},
                {"thinking": "first"},
                "second",
            ],
        }
        blocks, _ = _cursor_bubble_blocks(bubble)
        self.assertEqual([b["thinking"] for b in blocks], ["first", "second"])

    def test_bubble_thinking_field_emits_thinking_block(self):
        bubble = {
            "type": 2,
            "thinking": {
                "text": "**Checking file context**\n\nLooking at the layout files.",
                "signature": "",
            },
            "text": "Here is the fix.",
            "allThinkingBlocks": [],
        }
        blocks, _ = _cursor_bubble_blocks(bubble)
        thinking = [b for b in blocks if b.get("type") == "thinking"]
        self.assertEqual(len(thinking), 1)
        self.assertIn("Checking file context", thinking[0]["thinking"])

    def test_bubble_thinking_counted_in_accumulator(self):
        acc = Accumulator()
        acc.begin_file("cursor", "s.jsonl")
        acc.observe({
            "type": "assistant",
            "sessionId": "s-think",
            "timestamp": "2026-05-01T10:00:00.000Z",
            "message": {
                "role": "assistant",
                "content": [{
                    "type": "thinking",
                    "thinking": "Reason about the API shape first.",
                }],
            },
        }, None, None)
        acc.end_file()
        stats = acc.to_source_stats("cursor", None, None)
        self.assertEqual(stats["volume"]["thinking_blocks"], 1)


class TestCursorGitCwdDiscovery(unittest.TestCase):
    def test_path_inferred_cwd_from_tool_paths(self):
        from gnomon.sources.cursor import _cursor_cwd_from_paths
        paths = ["/Users/belen.carozo/projects/gnomon/gnomon/cli/local.py"]
        cwd = _cursor_cwd_from_paths(paths)
        self.assertEqual(cwd, "/Users/belen.carozo/projects/gnomon/gnomon/cli")


class TestCursorSkillFluencyScoring(unittest.TestCase):
    def test_skill_fluency_scored_for_cursor_corpus(self):
        from gnomon.scoring.aq import compute_aq

        stats = {
            "corpus": {"sources": {"cursor": {}}},
            "volume": {"total_sessions": 10, "tool_calls_total": 100},
            "stack": {
                "skills_distinct": 8, "skills_total": 20,
                "top_skills": [("code-review", 10)], "skills_all": [("code-review", 10)],
            },
            "tools": {},
            "behavior": {},
        }
        aq = compute_aq(stats)
        breadth = next(p for p in aq["pillars"] if p["name"] == "Breadth")
        skill = next(a for a in breadth["axes"] if a["name"] == "Skill fluency")
        self.assertGreater(skill["score"], 0.0)


class TestCursorVerificationScoring(unittest.TestCase):
    def test_review_skills_count_for_cursor_skill_reads(self):
        from gnomon.scoring.aq import compute_aq

        stats = {
            "corpus": {"sources": {"cursor": {}}},
            "volume": {"total_sessions": 10, "tool_calls_total": 100},
            "stack": {"top_skills": [("code-review", 10)], "skills_all": [("code-review", 10)]},
            "tools": {},
            "behavior": {"shell_test_runs": 0},
        }
        aq = compute_aq(stats)
        craft = next(p for p in aq["pillars"] if p["name"] == "Craft")
        verification = next(a for a in craft["axes"] if a["name"] == "Verification")
        self.assertEqual(verification["signals"]["review_skills"], 10)
        self.assertGreater(verification["score"], 0.0)


class TestCursorModelMixScoring(unittest.TestCase):
    def test_cursor_models_do_not_change_mixed_corpus_model_mix(self):
        from copy import deepcopy
        from gnomon.scoring.aq import compute_aq

        baseline = {
            "corpus": {"sources": {"claude": {}, "cursor": {}}},
            "volume": {"total_sessions": 10, "tool_calls_total": 100},
            "stack": {"models": [["claude-sonnet", 100]]},
            "tools": {},
            "behavior": {},
            "scoring_inputs_by_source": {
                "claude": {"window": {"stack": {"models": [["claude-sonnet", 100]]}}},
                "cursor": {"window": {"stack": {"models": []}}},
            },
        }
        with_cursor_models = deepcopy(baseline)
        cursor_models = [["composer-2.5", 50], ["gpt-5", 50]]
        with_cursor_models["stack"]["models"] += cursor_models
        with_cursor_models["scoring_inputs_by_source"]["cursor"]["window"]["stack"][
            "models"] = cursor_models

        expected = compute_aq(baseline)
        actual = compute_aq(with_cursor_models)
        self.assertEqual(actual["aq_0_100"], expected["aq_0_100"])
        expected_savvy = next(p for p in expected["pillars"] if p["name"] == "Savvy")
        actual_savvy = next(p for p in actual["pillars"] if p["name"] == "Savvy")
        self.assertEqual(actual_savvy["axes"], expected_savvy["axes"])

    def test_model_mix_dropped_for_cursor_only_corpus(self):
        from gnomon.scoring.aq import compute_aq

        stats = {
            "corpus": {"sources": {"cursor": {}}},
            "volume": {"total_sessions": 5, "tool_calls_total": 100},
            "stack": {"models": [("composer-2.5", 40), ("claude-4.5-sonnet-thinking", 10)]},
            "tools": {},
            "behavior": {},
        }
        r = compute_aq(stats)
        na = {a for p in r["pillars"] for a in (p.get("not_applicable") or [])}
        self.assertIn("Model mix", na)

    def test_profile_html_notes_cursor_billing_for_savvy(self):
        from gnomon.scoring.aq import compute_aq
        from gnomon.scoring.gstack import CURSOR_SAVVY_MODEL_MIX_NOTE, savvy_cursor_model_mix_note

        stats = {
            "corpus": {"sources": {"cursor": {}}},
            "volume": {"total_sessions": 5, "tool_calls_total": 100},
            "stack": {"models": [("composer-2.5", 40)]},
            "tools": {"cli_calls": 5, "mcp_calls": 1},
            "behavior": {},
        }
        aq = compute_aq(stats)
        note = savvy_cursor_model_mix_note(stats, aq)
        self.assertEqual(note, CURSOR_SAVVY_MODEL_MIX_NOTE)
        self.assertIn("billing plan", note[1])

        claude_stats = {**stats, "corpus": {"sources": {"claude": {}}}}
        self.assertIsNone(savvy_cursor_model_mix_note(claude_stats, compute_aq(claude_stats)))


if __name__ == "__main__":
    unittest.main()
