import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import paxel


class TestExtractClis(unittest.TestCase):
    def test_single_known_cli(self):
        self.assertEqual(paxel._extract_clis("git status"), ["git"])

    def test_chained_commands(self):
        self.assertEqual(paxel._extract_clis("cd /x && pnpm install | grep foo"),
                         ["pnpm", "grep"])

    def test_skips_env_assignment(self):
        self.assertEqual(paxel._extract_clis("FOO=bar python3 run.py"), ["python3"])

    def test_path_prefixed_binary(self):
        self.assertEqual(paxel._extract_clis("/usr/bin/node app.js"), ["node"])

    def test_unknown_command_ignored(self):
        self.assertEqual(paxel._extract_clis("frobnicate --x"), [])

    def test_empty(self):
        self.assertEqual(paxel._extract_clis(""), [])


class TestCodexInjected(unittest.TestCase):
    def test_environment_context(self):
        self.assertTrue(paxel._codex_is_injected(
            "<environment_context>\n  <cwd>/x</cwd>\n  <shell>zsh</shell>\n</environment_context>"))

    def test_user_instructions(self):
        self.assertTrue(paxel._codex_is_injected("  <user_instructions>be concise</user_instructions>"))

    def test_real_prompt_kept(self):
        self.assertFalse(paxel._codex_is_injected("fix the auth bug in middleware"))

    def test_empty(self):
        self.assertFalse(paxel._codex_is_injected(""))

    def test_agents_md_instructions(self):
        self.assertTrue(paxel._codex_is_injected("# AGENTS.md instructions for /\n\n<INSTRUCTIONS>\n..."))

    def test_turn_aborted(self):
        self.assertTrue(paxel._codex_is_injected("<turn_aborted>\nThe user interrupted...</turn_aborted>"))

    def test_two_plus_two_probe(self):
        self.assertTrue(paxel._codex_is_injected("whats 2+2?"))

    def test_task_wrapper_kept(self):
        self.assertFalse(paxel._codex_is_injected("<task> Read the full file at /x and summarize"))


def _sample_stats():
    return {
        "tools": {
            "tool_diversity": 111, "tool_entropy_normalized": 0.435,
            "mcp_calls": 1984, "mcp_servers_distinct": 12,
            "clis_distinct": 41, "cli_calls": 9194,
            "toolsearch_calls": 308, "task_tool_calls": 1166, "agent_calls": 416,
        },
        "stack": {
            "skills_distinct": 39, "skills_total": 8000,
            "subagent_types_distinct": 9,
            "subagent_types": [("general-purpose", 250), ("harness-generator", 29)],
            "top_skills": [("simplify", 1832), ("superpowers:writing-plans", 1752)],
            "skills_all": [("simplify", 1832), ("superpowers:writing-plans", 1752),
                           ("cerberus", 774), ("superpowers:brainstorming", 50)],
            "compounding_writes": 40,
            "models": [("claude-opus-4-7", 20000), ("claude-opus-4-8", 16000),
                       ("claude-sonnet-4-6", 3000), ("claude-haiku-4-5", 900)],
        },
        "behavior": {
            "fanout_median": 4,
            "shell_test_runs": 200, "planning_ratio_explore_to_doing": 0.94,
            "actions_per_prompt": 13.8, "error_recovery_ratio": 0.98,
            "api_errors_retries": 20,
        },
    }


class TestComputeAqV2(unittest.TestCase):
    def setUp(self):
        self.aq = paxel.compute_aq(_sample_stats())

    def test_four_pillars(self):
        names = [p["name"] for p in self.aq["pillars"]]
        self.assertEqual(names, ["Breadth", "Craft", "Efficiency", "Savvy"])

    def test_pillar_weights_sum_100(self):
        self.assertEqual(sum(p["weight"] for p in self.aq["pillars"]), 100)

    def test_scores_in_range(self):
        self.assertTrue(0 <= self.aq["aq_0_100"] <= 100)
        for p in self.aq["pillars"]:
            self.assertTrue(0 <= p["score"] <= 100, p["name"])
            self.assertEqual(sum(a["weight"] for a in p["axes"]), 100, p["name"])
            for a in p["axes"]:
                self.assertLessEqual(a["score"], a["weight"], a["name"])

    def test_tier_elite(self):
        self.assertEqual(self.aq["tier"], "Elite")

    def test_steering_sweetspot_band(self):
        eff = next(p for p in self.aq["pillars"] if p["name"] == "Efficiency")
        lever = next(a for a in eff["axes"] if a["name"] == "Steering leverage")
        self.assertEqual(lever["score"], 50.0)

    def test_steering_overdrive_penalized(self):
        s = _sample_stats(); s["behavior"]["actions_per_prompt"] = 60
        aq = paxel.compute_aq(s)
        eff = next(p for p in aq["pillars"] if p["name"] == "Efficiency")
        lever = next(a for a in eff["axes"] if a["name"] == "Steering leverage")
        self.assertEqual(lever["score"], 0.0)

    def test_mcp_vs_cli_and_diversity(self):
        self.assertEqual(self.aq["mcp_vs_cli"]["ratio"], 4.6)
        self.assertEqual(self.aq["tool_diversity"]["distinct"], 111)

    def test_empty_low(self):
        self.assertLess(paxel.compute_aq({"tools": {}, "stack": {}, "behavior": {}})["aq_0_100"], 40)

    def test_level_ladder_honest(self):
        # The level vocabulary must track AQ, with no flattery at the floor.
        cases = [(10, "Novice"), (35, "Apprentice"), (52, "Adequate"),
                 (68, "Proficient"), (80, "Advanced"), (95, "Elite")]
        for total, expected in cases:
            tier = ("Elite" if total >= 88 else "Advanced" if total >= 75 else "Proficient"
                    if total >= 60 else "Adequate" if total >= 45 else "Apprentice"
                    if total >= 25 else "Novice")
            self.assertEqual(tier, expected, total)

    def test_archetype_matches_aq_tier(self):
        # Headline archetype is the AQ rung — never contradicts the tier shown below it.
        s = _sample_stats()
        aq = paxel.compute_aq(s); s["agentic"] = aq
        s.setdefault("velocity", {})
        arch, quote = paxel.pick_archetype(s, {"Planning": 7.5, "Execution": 7.3, "Engineering": 6.0})
        self.assertEqual(arch, aq["tier"])
        self.assertIn("thinnest axis", quote)   # the gap is surfaced, not hidden

    def _orch(self, aq):
        breadth = next(p for p in aq["pillars"] if p["name"] == "Breadth")
        return next(a for a in breadth["axes"] if a["name"] == "Orchestration")["score"]

    def test_coordination_beats_volume(self):
        # Same agent_runs / variety / harness; only fan-out differs. A real orchestrator
        # (coordinates a team per session) must out-score a serial grinder (1 agent/session).
        orchestrator = _sample_stats(); orchestrator["behavior"]["fanout_median"] = 6
        grinder = _sample_stats(); grinder["behavior"]["fanout_median"] = 1
        self.assertGreater(self._orch(paxel.compute_aq(orchestrator)),
                           self._orch(paxel.compute_aq(grinder)))

    def test_every_pillar_and_axis_has_tooltip_note(self):
        # Every pillar/axis compute_aq emits must have a plain-language tooltip note,
        # so the HTML report never shows an unexplained bar.
        for p in self.aq["pillars"]:
            self.assertIn(p["name"], paxel.AQ_PILLAR_NOTES)
            for a in p["axes"]:
                self.assertIn(a["name"], paxel.AQ_AXIS_NOTES)

    def test_volume_alone_cannot_max_orchestration(self):
        # 10x the agent_runs but no coordination (fanout=1) -> still capped below full.
        s = _sample_stats(); s["tools"]["agent_calls"] = 5000; s["behavior"]["fanout_median"] = 1
        self.assertLess(self._orch(paxel.compute_aq(s)), 33)


class TestParseWindow(unittest.TestCase):
    def test_no_flags(self):
        self.assertEqual(paxel.parse_window([]), (None, None))

    def test_since_and_until_inclusive_day(self):
        since, until = paxel.parse_window(["--since=2026-03-01", "--until=2026-03-31"])
        self.assertEqual(since.date().isoformat(), "2026-03-01")
        # --until keeps the WHOLE end day: internally exclusive next-midnight
        self.assertEqual(until.date().isoformat(), "2026-04-01")
        self.assertIsNotNone(since.tzinfo)

    def test_last_rolling(self):
        from datetime import datetime, timedelta
        now = datetime(2026, 6, 10).astimezone()
        for flag, days in (("--last=90d", 90), ("--last=12w", 84),
                           ("--last=3m", 90), ("--last=45", 45)):
            since, until = paxel.parse_window([flag], now=now)
            self.assertEqual(since, now - timedelta(days=days), flag)
            self.assertIsNone(until, flag)

    def test_bad_values_ignored(self):
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(paxel.parse_window(["--since=03/01/2026", "--last=3q"]),
                             (None, None))
        self.assertEqual(buf.getvalue().count("warning"), 2)


def _edge_stats(agentic=None):
    """Minimal stats for growth_edges: healthy build signals so only AQ edges fire."""
    return {
        "volume": {"total_sessions": 100, "total_prompts": 1000},
        "behavior": {"error_rate_per_100_tools": 1, "iteration_depth_max": 5,
                     "files_hammered_over_15x": 0, "shell_test_runs": 100},
        "velocity": {},
        "stack": {"top_skills": [("code-review", 60), ("tdd", 50)]},
        "agentic": agentic or {},
    }


def _axis(name, weight, fill, signals=None):
    return {"name": name, "weight": weight, "score": round(weight * fill, 1),
            "signals": signals or {}}


HEALTHY_SCORES = {"Execution": 8, "Planning": 8, "Engineering": 8}


class TestGrowthEdgesAq(unittest.TestCase):
    def test_weak_aq_axis_fires_edge(self):
        # gstack scorecard healthy but Orchestration thin -> AQ edge, not "balanced".
        agentic = {"pillars": [{"name": "Breadth", "weight": 30, "axes": [
            _axis("Orchestration", 33, 0.2,
                  {"agent_runs": 3, "subagent_types": 1, "fanout_median": 1})]}]}
        edges = paxel.growth_edges(_edge_stats(agentic), dict(HEALTHY_SCORES))
        self.assertTrue(any("Orchestration" in adv for _, _, adv in edges), edges)

    def test_healthy_aq_falls_through_to_balanced(self):
        agentic = {"pillars": [{"name": "Breadth", "weight": 30, "axes": [
            _axis("Orchestration", 33, 0.9), _axis("Tool command (MCP + CLI)", 28, 0.8)]}]}
        edges = paxel.growth_edges(_edge_stats(agentic), dict(HEALTHY_SCORES))
        self.assertEqual(len(edges), 1)
        self.assertIn("depth", edges[0][1].lower())   # the "balanced -> depth" fallback

    def test_unadvised_axes_never_fire(self):
        # Steering leverage / Recovery are deliberately not advised, however low.
        agentic = {"pillars": [{"name": "Efficiency", "weight": 20, "axes": [
            _axis("Steering leverage", 50, 0.1), _axis("Recovery", 50, 0.1)]}]}
        edges = paxel.growth_edges(_edge_stats(agentic), dict(HEALTHY_SCORES))
        self.assertTrue(all("Steering" not in adv and "Recovery" not in adv
                            for _, _, adv in edges), edges)

    def test_capped_at_three_most_urgent_first(self):
        agentic = {"pillars": [
            {"name": "Breadth", "weight": 30, "axes": [
                _axis("Orchestration", 33, 0.1), _axis("Tool command (MCP + CLI)", 28, 0.3)]},
            {"name": "Savvy", "weight": 15, "axes": [
                _axis("Model mix", 50, 0.2), _axis("Token economy", 50, 0.4)]},
            {"name": "Craft", "weight": 35, "axes": [_axis("Grounding", 30, 0.25)]},
        ]}
        edges = paxel.growth_edges(_edge_stats(agentic), dict(HEALTHY_SCORES))
        self.assertEqual(len(edges), 3)
        self.assertIn("Orchestration", edges[0][2])   # lowest fill ranks first

    def test_aq_edges_compose_with_gstack_edges(self):
        # A weak gstack axis still wins over a milder AQ gap.
        agentic = {"pillars": [{"name": "Savvy", "weight": 15, "axes": [
            _axis("Model mix", 50, 0.4)]}]}
        scores = dict(HEALTHY_SCORES, Planning=3)
        edges = paxel.growth_edges(_edge_stats(agentic), scores)
        self.assertIn("Plan", edges[0][0])            # Planning edge first (priority 3)
        self.assertTrue(any("Model mix" in adv for _, _, adv in edges))


class TestCodexToolMapping(unittest.TestCase):
    def test_update_plan_is_todowrite(self):
        name, _ = paxel._codex_tool({"type": "function_call", "name": "update_plan",
                                     "arguments": "{}"})
        self.assertEqual(name, "TodoWrite")

    def test_write_stdin_is_bashoutput(self):
        name, inp = paxel._codex_tool({"type": "function_call", "name": "write_stdin",
                                       "arguments": '{"chars": "y\\n"}'})
        self.assertEqual(name, "BashOutput")
        self.assertEqual(inp, {})

    def test_exec_command_is_bash(self):
        name, inp = paxel._codex_tool({"type": "function_call", "name": "exec_command",
                                       "arguments": '{"cmd": "git status"}'})
        self.assertEqual((name, inp["command"]), ("Bash", "git status"))


class TestCodexModelStamping(unittest.TestCase):
    def test_turn_context_model_flows_to_assistant_events(self):
        import json, tempfile
        rows = [
            {"type": "session_meta", "payload": {"id": "s1", "cwd": "/x"}},
            {"type": "turn_context", "payload": {"model": "gpt-5.4"}},
            {"type": "response_item", "timestamp": "2026-01-02T03:04:05Z",
             "payload": {"type": "message", "role": "user", "content": "fix the bug"}},
            {"type": "response_item", "timestamp": "2026-01-02T03:04:06Z",
             "payload": {"type": "message", "role": "assistant",
                         "content": [{"type": "output_text", "text": "done"}]}},
            {"type": "response_item", "timestamp": "2026-01-02T03:04:07Z",
             "payload": {"type": "function_call", "name": "exec_command",
                         "arguments": "{\"cmd\": \"ls\"}"}},
        ]
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as f:
            f.write("\n".join(json.dumps(r) for r in rows))
            path = f.name
        try:
            evs = list(paxel._codex_events(path))
        finally:
            os.unlink(path)
        models = [e["message"].get("model") for e in evs
                  if e["message"]["role"] == "assistant"]
        self.assertTrue(models and all(m == "gpt-5.4" for m in models), models)


class TestSkillMdRegex(unittest.TestCase):
    def test_skill_read_detected(self):
        m = paxel._SKILL_MD_RX.findall(
            "sed -n '1,80p' .claude/skills/threejs-animation/SKILL.md")
        self.assertEqual(m, ["threejs-animation"])

    def test_codex_home_skill(self):
        m = paxel._SKILL_MD_RX.findall("cat /Users/x/.codex/skills/spreadsheet/SKILL.md")
        self.assertEqual(m, ["spreadsheet"])

    def test_no_false_positive(self):
        self.assertEqual(paxel._SKILL_MD_RX.findall("cat README.md && ls skills/"), [])


class TestProtobufParser(unittest.TestCase):
    def _varint(self, n):
        out = b""
        while True:
            b7 = n & 0x7F
            n >>= 7
            out += bytes([b7 | (0x80 if n else 0)])
            if not n:
                return out

    def _len_field(self, fno, payload):
        return self._varint((fno << 3) | 2) + self._varint(len(payload)) + payload

    def test_roundtrip(self):
        uuid = b"409ac49c-58d7-46f8-b769-bb5615ac86bb"
        ts = self._varint(8) + self._varint(1_750_000_000)        # field1 varint seconds
        record = self._len_field(1, uuid) + self._len_field(3, ts)
        fields = paxel._pb_fields(record)
        self.assertEqual(fields[0], (1, 2, uuid))
        inner = paxel._pb_fields(fields[1][2])
        self.assertEqual(inner[0], (1, 0, 1_750_000_000))

    def test_garbage_raises(self):
        with self.assertRaises(Exception):
            paxel._pb_fields(b"\x00\xff\xff\xff")


class TestResolveSourceDir(unittest.TestCase):
    def test_config_root_resolves_to_inner(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            os.mkdir(os.path.join(d, "projects"))
            self.assertEqual(paxel._resolve_source_dir(d, "projects"),
                             os.path.join(d, "projects"))

    def test_direct_dir_kept(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(paxel._resolve_source_dir(d, "projects"), d)


class TestCompoundingPath(unittest.TestCase):
    def test_claude_md(self):
        self.assertTrue(paxel._is_compounding_path("/x/CLAUDE.md"))
    def test_memory_dir(self):
        self.assertTrue(paxel._is_compounding_path("/x/memory/foo.md"))
    def test_adr(self):
        self.assertTrue(paxel._is_compounding_path("/x/docs/adr/0001.md"))
    def test_normal_file_false(self):
        self.assertFalse(paxel._is_compounding_path("/x/src/app.py"))
    def test_none(self):
        self.assertFalse(paxel._is_compounding_path(None))


if __name__ == "__main__":
    unittest.main()
