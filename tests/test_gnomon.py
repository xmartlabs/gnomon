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
            "background_tasks": 187, "scheduled_actions": 11,
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

    def test_tier_systems_builder(self):
        self.assertEqual(self.aq["tier"], "Systems Builder")

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
