"""Skill-counting dedup (honest-aq-series design decision C): a Skill usage
must count once per invocation, not once per assistant/sidechain turn that
carries an `attributionSkill` attribution.

Ground truth from a real /judgment-day run (session 2bc76698-17c1-411c-
b1fc-0722902d6b32): 1 Skill-tool event (parent) + 30 parent attributionSkill
turns + 62 sidechain-A turns + 103 sidechain-B turns, all one sessionId ->
196 raw occurrences -> MUST become 1.

The RED fixture is deliberately 3 files (not 1): a per-file dict resets on
begin_file (accumulator.py's per-file transient state) and yields 3, not 1 --
a single synthetic file would pass under that broken design while the real
corpus fails. See design.md decision C for the full arithmetic.
"""
import unittest
from datetime import datetime, timedelta

from gnomon.cli.accumulator import Accumulator

SID = "2bc76698-17c1-411c-b1fc-0722902d6b32"
BASE_DT = datetime(2026, 6, 15, 12, 0, 0)  # mid-month, safe from tz-boundary drift


def _ts(i):
    return (BASE_DT + timedelta(seconds=i)).isoformat() + "Z"


def _attribution_turn(sid, seq, skill, is_sidechain=False, agent_id=None):
    ev = {
        "type": "assistant", "sessionId": sid, "timestamp": _ts(seq),
        "isSidechain": is_sidechain,
        "attributionSkill": skill,
        "message": {"role": "assistant", "model": "claude-sonnet-4-6", "content": []},
    }
    if agent_id:
        ev["agentId"] = agent_id
    return ev


def _skill_tool_event(sid, seq, skill):
    return {
        "type": "assistant", "sessionId": sid, "timestamp": _ts(seq),
        "isSidechain": False,
        "message": {"role": "assistant", "model": "claude-sonnet-4-6", "content": [
            {"type": "tool_use", "name": "Skill", "input": {"skill": skill}},
        ]},
    }


def _feed(acc, fp, events):
    acc.begin_file("claude", fp)
    for ev in events:
        acc.observe(ev, None, None)
    acc.end_file()


def _three_file_fixture(skill=SID and "judgment-day"):
    """Returns [(fp, events), ...] matching the real-corpus ground truth:
    parent = 1 Skill-tool event + 30 attributionSkill turns (not sidechain);
    subagent A = 62 attributionSkill turns (sidechain);
    subagent B = 103 attributionSkill turns (sidechain)."""
    parent = [_skill_tool_event(SID, 0, skill)] + [
        _attribution_turn(SID, i, skill, is_sidechain=False) for i in range(1, 31)
    ]
    sub_a = [
        _attribution_turn(SID, 1000 + i, skill, is_sidechain=True, agent_id="agent-a")
        for i in range(62)
    ]
    sub_b = [
        _attribution_turn(SID, 2000 + i, skill, is_sidechain=True, agent_id="agent-b")
        for i in range(103)
    ]
    return [
        ("2bc76698-17c1-411c-b1fc-0722902d6b32.jsonl", parent),
        ("subagents/agent-ac24a2d848d2f5640.jsonl", sub_a),
        ("subagents/agent-af22a7bf92e07b0c9.jsonl", sub_b),
    ]


class TestThreeFileDedup(unittest.TestCase):
    def test_196_raw_occurrences_collapse_to_one(self):
        acc = Accumulator()
        for fp, events in _three_file_fixture():
            _feed(acc, fp, events)
        acc.to_corpus_stats(None, None, False)
        self.assertEqual(acc.skill_counter["judgment-day"], 1)

    def test_order_independence_reversed_files(self):
        acc = Accumulator()
        for fp, events in reversed(_three_file_fixture()):
            _feed(acc, fp, events)
        acc.to_corpus_stats(None, None, False)
        self.assertEqual(acc.skill_counter["judgment-day"], 1)

    def test_month_skill_counter_also_dedupes(self):
        acc = Accumulator()
        for fp, events in _three_file_fixture():
            _feed(acc, fp, events)
        acc.to_corpus_stats(None, None, False)
        self.assertEqual(acc.month_skill_counter["2026-06"]["judgment-day"], 1)

    def test_total_sessions_unaffected_by_dedup(self):
        acc = Accumulator()
        for fp, events in _three_file_fixture():
            _feed(acc, fp, events)
        stats = acc.to_corpus_stats(None, None, False)
        self.assertEqual(stats["volume"]["total_sessions"], 1)

    def test_per_source_accumulator_also_dedupes(self):
        """to_source_stats is a SEPARATE entry point reading the same
        skill_counter -- it must also see the flushed, deduped value."""
        acc = Accumulator()
        for fp, events in _three_file_fixture():
            _feed(acc, fp, events)
        acc.to_source_stats("claude", None, None)
        self.assertEqual(acc.skill_counter["judgment-day"], 1)


class TestNoOverCollapse(unittest.TestCase):
    def test_two_skill_tool_events_same_session_count_twice(self):
        acc = Accumulator()
        events = [_skill_tool_event(SID, 0, "judgment-day"),
                  _skill_tool_event(SID, 1, "judgment-day")]
        _feed(acc, "f.jsonl", events)
        acc.to_corpus_stats(None, None, False)
        self.assertEqual(acc.skill_counter["judgment-day"], 2)

    def test_same_skill_two_distinct_sessions_count_twice(self):
        acc = Accumulator()
        events = [_attribution_turn("sid-a", 0, "judgment-day"),
                  _attribution_turn("sid-b", 1, "judgment-day")]
        _feed(acc, "f.jsonl", events)
        acc.to_corpus_stats(None, None, False)
        self.assertEqual(acc.skill_counter["judgment-day"], 2)

    def test_second_invocation_in_same_session_after_flush_still_counts(self):
        """A discrete Skill-tool event AFTER the pending span was already
        claimed (or would-be-flushed) is a second real invocation and must
        add a second count -- discrete sites increment unconditionally."""
        acc = Accumulator()
        events = [
            _skill_tool_event(SID, 0, "judgment-day"),
            _attribution_turn(SID, 1, "judgment-day"),
            _skill_tool_event(SID, 2, "judgment-day"),
        ]
        _feed(acc, "f.jsonl", events)
        acc.to_corpus_stats(None, None, False)
        self.assertEqual(acc.skill_counter["judgment-day"], 2)


class TestFlushIsIdempotent(unittest.TestCase):
    def test_calling_to_corpus_stats_twice_does_not_double_count(self):
        acc = Accumulator()
        for fp, events in _three_file_fixture():
            _feed(acc, fp, events)
        acc.to_corpus_stats(None, None, False)
        acc.to_corpus_stats(None, None, False)
        self.assertEqual(acc.skill_counter["judgment-day"], 1)


if __name__ == "__main__":
    unittest.main()
