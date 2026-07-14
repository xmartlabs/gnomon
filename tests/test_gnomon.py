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


class TestShellVerificationDetection(unittest.TestCase):
    def test_gradle_detekt_counts_as_verification(self):
        from gnomon.taxonomy import bash_runs_tests

        self.assertTrue(bash_runs_tests("./gradlew detekt"))


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
            "subagent_types_distinct": 9, "max_session_subagent_types": 5,
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

    def test_context_intelligence_has_tooltip_note_when_live(self):
        # Context Intelligence is dropped in the default sample (no grounded sessions),
        # so it won't appear above — score it live here and confirm the note exists.
        s = _sample_stats()
        s["volume"] = {"total_sessions": 100}
        s["tools"]["mcp_grounded_sessions"] = 20
        aq = paxel.compute_aq(s)
        craft = next(p for p in aq["pillars"] if p["name"] == "Craft")
        self.assertIn("Context Intelligence", [a["name"] for a in craft["axes"]])
        self.assertIn("Context Intelligence", paxel.AQ_AXIS_NOTES)

    def test_volume_alone_cannot_max_orchestration(self):
        # 10x the agent_runs but no coordination (fanout=1) -> still capped below full.
        s = _sample_stats(); s["tools"]["agent_calls"] = 5000; s["behavior"]["fanout_median"] = 1
        self.assertLess(self._orch(paxel.compute_aq(s)), 33)

    def test_verification_does_not_count_planning_review_skills(self):
        s = _sample_stats()
        s["stack"]["top_skills"] = [("plan-eng-review", 10)]
        s["stack"]["skills_all"] = [("plan-eng-review", 10)]
        s["behavior"]["shell_test_runs"] = 0
        aq = paxel.compute_aq(s)
        craft = next(p for p in aq["pillars"] if p["name"] == "Craft")
        verification = next(a for a in craft["axes"] if a["name"] == "Verification")
        self.assertEqual(verification["signals"]["review_skills"], 0)
        self.assertEqual(verification["score"], 0.0)

    def test_craft_axes_drop_context_intelligence_when_field_absent(self):
        # _sample_stats does NOT set mcp_grounded_sessions -> the grounding field is
        # absent (legacy/external block) -> Context Intelligence is N/A and Craft
        # renormalizes to the remaining three axes summing to weight 100. Knowledge-MCP
        # CALL volume alone (no grounded-session field) must NOT resurrect the axis.
        s = _sample_stats()
        s["tools"]["mcp_knowledge_calls"] = 341
        s["tools"]["mcp_knowledge_servers"] = 3
        aq = paxel.compute_aq(s)
        craft = next(p for p in aq["pillars"] if p["name"] == "Craft")
        names = [a["name"] for a in craft["axes"]]
        self.assertEqual(names, ["Verification", "Grounding", "Compounding"])
        self.assertEqual(sum(a["weight"] for a in craft["axes"]), 100)
        self.assertIn("Context Intelligence", craft.get("not_applicable", []))

    def _craft_ci(self, grounded, sessions, no_tool_activity=False):
        s = _sample_stats()
        s["volume"] = {"total_sessions": sessions}
        s["tools"]["mcp_grounded_sessions"] = grounded
        s["behavior"]["no_tool_activity"] = no_tool_activity
        return paxel.compute_aq(s)

    def test_context_intelligence_dropped_when_no_tool_activity(self):
        # Even with a coverage that would otherwise be well above floor/target, a source
        # that cannot record ordered tool sequences (no_tool_activity) drops the axis.
        aq = self._craft_ci(grounded=40, sessions=100, no_tool_activity=True)
        craft = next(p for p in aq["pillars"] if p["name"] == "Craft")
        names = [a["name"] for a in craft["axes"]]
        self.assertNotIn("Context Intelligence", names)
        self.assertIn("Context Intelligence", craft.get("not_applicable", []))
        self.assertEqual(sum(a["weight"] for a in craft["axes"]), 100)

    def test_context_intelligence_field_absent_is_na(self):
        # No mcp_grounded_sessions field on the block (legacy/external export) -> the
        # source can't reconstruct grounding -> axis is N/A (dropped, Craft renormalized),
        # NOT scored 0. Backward-compat with blocks predating the field.
        s = _sample_stats()
        s["volume"] = {"total_sessions": 100}
        # deliberately do NOT set s["tools"]["mcp_grounded_sessions"]
        aq = paxel.compute_aq(s)
        craft = next(p for p in aq["pillars"] if p["name"] == "Craft")
        names = [a["name"] for a in craft["axes"]]
        self.assertNotIn("Context Intelligence", names)
        self.assertIn("Context Intelligence", craft.get("not_applicable", []))
        self.assertEqual(sum(a["weight"] for a in craft["axes"]), 100)

    def test_context_intelligence_scored_zero_when_measured_zero(self):
        # Field present, coverage = 0/100 = 0.0 (a real measured zero with tool activity)
        # -> axis is PRESENT and scored 0, NOT dropped. This removes the perverse
        # reward-for-not-grounding: a real zero must drag Craft down, not renormalize up.
        aq = self._craft_ci(grounded=0, sessions=100)
        craft = next(p for p in aq["pillars"] if p["name"] == "Craft")
        names = [a["name"] for a in craft["axes"]]
        self.assertIn("Context Intelligence", names)
        self.assertNotIn("Context Intelligence", craft.get("not_applicable", []))
        ci = next(a for a in craft["axes"] if a["name"] == "Context Intelligence")
        self.assertEqual(ci["score"], 0.0)
        self.assertEqual(sum(a["weight"] for a in craft["axes"]), 100)

    def test_context_intelligence_scored_at_low_coverage(self):
        # coverage = 5/100 = 0.05 -> scored (present), no floor gate.
        aq = self._craft_ci(grounded=5, sessions=100)
        craft = next(p for p in aq["pillars"] if p["name"] == "Craft")
        names = [a["name"] for a in craft["axes"]]
        self.assertIn("Context Intelligence", names)
        self.assertNotIn("Context Intelligence", craft.get("not_applicable", []))
        self.assertEqual(sum(a["weight"] for a in craft["axes"]), 100)

    def test_context_intelligence_present_and_scored_above_floor(self):
        # coverage = 20/100 = 0.20 -> scored, present as its own axis (weight 20 of 100).
        aq = self._craft_ci(grounded=20, sessions=100)
        craft = next(p for p in aq["pillars"] if p["name"] == "Craft")
        ci = next(a for a in craft["axes"] if a["name"] == "Context Intelligence")
        self.assertEqual(ci["weight"], 20)
        self.assertGreater(ci["score"], 0.0)
        self.assertEqual(sum(a["weight"] for a in craft["axes"]), 100)
        names = [a["name"] for a in craft["axes"]]
        self.assertEqual(names, ["Verification", "Grounding", "Context Intelligence", "Compounding"])

    def test_context_intelligence_full_credit_at_target(self):
        # coverage = 60/100 = 0.60 == TARGET -> full credit (sat=1.0 -> axis score ==
        # its full renormalized weight).
        aq = self._craft_ci(grounded=60, sessions=100)
        craft = next(p for p in aq["pillars"] if p["name"] == "Craft")
        ci = next(a for a in craft["axes"] if a["name"] == "Context Intelligence")
        self.assertEqual(ci["score"], ci["weight"])

    def test_context_intelligence_caps_at_full_credit_above_target(self):
        # coverage above TARGET must not exceed full credit (sat clamps at 1.0).
        aq = self._craft_ci(grounded=90, sessions=100)
        craft = next(p for p in aq["pillars"] if p["name"] == "Craft")
        ci = next(a for a in craft["axes"] if a["name"] == "Context Intelligence")
        self.assertEqual(ci["score"], ci["weight"])

    def test_context_intelligence_is_monotonic(self):
        # No floor gate -> the axis is monotonic in coverage: more grounding never
        # lowers overall AQ. Two otherwise-identical blocks differing only in grounded
        # coverage (0.04 vs 0.30) -> the higher-coverage block scores overall AQ >= the
        # lower one. This is the anti-cliff invariant: the old FLOOR inverted this by
        # DROPPING the sub-floor user (renormalizing Craft UP) so less grounding paid more.
        low = self._craft_ci(grounded=4, sessions=100)    # 0.04
        high = self._craft_ci(grounded=30, sessions=100)  # 0.30
        self.assertGreaterEqual(high["aq_0_100"], low["aq_0_100"])
        # both blocks measure grounding (field present + tool activity) -> both present.
        for aq in (low, high):
            craft = next(p for p in aq["pillars"] if p["name"] == "Craft")
            self.assertIn("Context Intelligence", [a["name"] for a in craft["axes"]])
        # and the per-axis score itself is monotonic.
        ci_low = next(a for a in next(p for p in low["pillars"] if p["name"] == "Craft")["axes"]
                      if a["name"] == "Context Intelligence")
        ci_high = next(a for a in next(p for p in high["pillars"] if p["name"] == "Craft")["axes"]
                       if a["name"] == "Context Intelligence")
        self.assertGreaterEqual(ci_high["score"], ci_low["score"])

    def test_context_intelligence_signals_shape(self):
        aq = self._craft_ci(grounded=20, sessions=100)
        craft = next(p for p in aq["pillars"] if p["name"] == "Craft")
        ci = next(a for a in craft["axes"] if a["name"] == "Context Intelligence")
        self.assertEqual(ci["signals"]["grounded_sessions"], 20)
        self.assertEqual(ci["signals"]["total_sessions"], 100)
        self.assertEqual(ci["signals"]["coverage"], 0.2)
        self.assertNotIn("knowledge_calls", ci["signals"])
        self.assertNotIn("knowledge_servers", ci["signals"])

    def test_context_intelligence_signals_explain_calculation(self):
        aq = self._craft_ci(grounded=20, sessions=100)
        craft = next(p for p in aq["pillars"] if p["name"] == "Craft")
        ci = next(a for a in craft["axes"] if a["name"] == "Context Intelligence")
        self.assertEqual(
            ci["signals"]["grounded_session_rule"],
            "knowledge-MCP call OR explore-class project/data/design MCP call before a later Edit/Write/MultiEdit/NotebookEdit in the same session",
        )
        self.assertEqual(
            ci["signals"]["score_formula"],
            "coverage = grounded_sessions / write_sessions; score = min(1, coverage / 0.60)",
        )
        self.assertEqual(ci["signals"]["target_coverage"], 0.6)

    def test_verification_counts_real_review_skills(self):
        # Genuine *-review verification skills (caveman-review, security-review) must
        # count toward Verification — they are not planning ceremonies.
        s = _sample_stats()
        s["stack"]["top_skills"] = [("caveman-review", 40), ("security-review", 30)]
        s["stack"]["skills_all"] = [("caveman-review", 40), ("security-review", 30)]
        s["behavior"]["shell_test_runs"] = 0
        aq = paxel.compute_aq(s)
        craft = next(p for p in aq["pillars"] if p["name"] == "Craft")
        verification = next(a for a in craft["axes"] if a["name"] == "Verification")
        self.assertEqual(verification["signals"]["review_skills"], 70)
        self.assertGreater(verification["score"], 0.0)

class TestBashRunsTests(unittest.TestCase):
    POSITIVE = [
        # JVM gradle (multi-module path, Android/integration task names, intermediate args)
        "./gradlew :maps-server:test", './gradlew :maps-server:test --tests "X"',
        "./gradlew :app:testDebugUnitTest", "./gradlew integrationTest",
        "./gradlew connectedAndroidTest", "./gradlew jvmTest", "./gradlew clean test",
        "gradle :a:b:check", "./gradlew test", "./gradlew check",
        # JVM maven (wrapper + intermediate args)
        "mvn test", "mvn verify", "./mvnw test", "mvn clean test", "mvn -pl mod test",
        "mvnw verify",
        # Scala / Clojure
        "sbt test", "sbt clean test", "sbt testOnly *Foo", "sbt it:test", "scala-cli test .",
        "lein test",
        # PHP
        "phpunit", "./vendor/bin/phpunit", "pest", "./vendor/bin/paratest", "behat",
        "php artisan test", "composer test", "composer run test", "codecept run",
        # Python
        "pytest", "python -m pytest", "python -m unittest", "tox", "uv run pytest",
        "hatch test", "hatch run test", "pdm run test", "python manage.py test",
        "./manage.py test",
        # Node / JS / TS
        "npm test", "npm t", "yarn t", "npm run test:unit", "node --test", "tsx --test",
        "npx jest", "vitest run", "npx playwright test",
        # Go / Rust / .NET / Dart / Elixir / Ruby
        "go test ./...", "cargo test", "cargo nextest run", "dotnet test", "flutter test",
        "dart test", "mix test", "bundle exec rspec", "rake spec",
    ]
    NEGATIVE = [
        "./gradlew build", "./gradlew :app:compileJava", "./gradlew :app:testClasses",
        "./gradlew spotlessCheck", "./gradlew processTestResources",
        "mvn -DskipTests package", "composer install", "composer update", "composer require x",
        "php artisan migrate", "php artisan serve", "php artisan make:test Foo",
        "python manage.py migrate", "git checkout test", "cat ava.json", "vim tox.ini",
        "find . -name test", "cd nox/ && ls", "npm install", "yarn add foo",
    ]

    def test_positive_cases(self):
        for cmd in self.POSITIVE:
            self.assertTrue(paxel.bash_runs_tests(cmd), f"should detect test run: {cmd!r}")

    def test_negative_cases(self):
        for cmd in self.NEGATIVE:
            self.assertFalse(paxel.bash_runs_tests(cmd), f"should NOT detect test run: {cmd!r}")


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
                _axis("Orchestration", 33, 0.1),
                _axis("Tool command (MCP + CLI)", 28, 0.3)]},
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


class TestCanonMcpServer(unittest.TestCase):
    def test_plugin_doubled_vendor_prefix(self):
        from gnomon.taxonomy import _canon_mcp_server
        self.assertEqual(_canon_mcp_server("plugin", "atlassian_atlassian_get_jira_issue"), "atlassian")
        self.assertEqual(_canon_mcp_server("plugin", "figma_figma_get_design_context"), "figma")

    def test_non_plugin_unchanged(self):
        from gnomon.taxonomy import _canon_mcp_server
        self.assertEqual(_canon_mcp_server("atlassian", "get_jira_issue"), "atlassian")


class TestCompoundingPath(unittest.TestCase):
    def test_claude_md(self):
        self.assertTrue(paxel._is_compounding_path("/x/CLAUDE.md"))
    def test_memory_dir(self):
        self.assertTrue(paxel._is_compounding_path("/x/memory/foo.md"))
    def test_adr(self):
        self.assertTrue(paxel._is_compounding_path("/x/docs/adr/0001.md"))
    def test_cursor_rules(self):
        self.assertTrue(paxel._is_compounding_path("/x/.cursor/rules/context7.mdc"))
    def test_normal_file_false(self):
        self.assertFalse(paxel._is_compounding_path("/x/src/app.py"))
    def test_none(self):
        self.assertFalse(paxel._is_compounding_path(None))


def _full_stats(sessions=10, tool_calls=5000):
    """Minimal but complete stats dict satisfying compute_scores, score_breakdown,
    compute_aq, pick_archetype, steering_reading, and build_summary."""
    aq = paxel.compute_aq({
        "tools": {"tool_diversity": 50, "tool_entropy_normalized": 0.5,
                  "mcp_calls": 200, "mcp_servers_distinct": 5,
                  "clis_distinct": 20, "cli_calls": 1000,
                  "toolsearch_calls": 100, "task_tool_calls": 400, "agent_calls": 80},
        "stack": {"skills_distinct": 15, "skills_total": 500, "subagent_types_distinct": 3,
                  "max_session_subagent_types": 3,
                  "subagent_types": [("general-purpose", 50)],
                  "top_skills": [("code-review", 80), ("superpowers:writing-plans", 60),
                                 ("tdd", 40), ("brainstorm", 30)],
                  "skills_all": [("code-review", 80), ("superpowers:writing-plans", 60),
                                 ("tdd", 40), ("brainstorm", 30)],
                  "compounding_writes": 12,
                  "models": [("claude-opus-4-7", 5000), ("claude-haiku-4-5", 1000)]},
        "behavior": {"fanout_median": 3, "shell_test_runs": 50, "actions_per_prompt": 10,
                     "error_recovery_ratio": 0.9, "api_errors_retries": 5,
                     "plan_sessions": 8,
                     "planning_ratio_explore_to_doing": 0.7},
    })
    return {
        "corpus": {"date_range": ["2026-01-01", "2026-06-01"], "sources": {"claude": {}},
                   "files_parsed": 20, "lines_total": 5000, "lines_unparseable": 0,
                   "span_days": 150, "active_days": 60,
                   "timezone": "UTC (UTC+00:00)", "antigravity_experimental": {}},
        "volume": {"total_sessions": sessions, "total_prompts": sessions * 30,
                   "command_invocations": 10, "avg_prompt_length_chars": 120.0,
                   "median_prompt_length_chars": 80.0, "assistant_turns": sessions * 50,
                   "tool_calls_total": tool_calls, "thinking_blocks": sessions * 8},
        "tools": {"tool_diversity": 50, "tool_entropy_normalized": 0.5,
                  "mcp_calls": 200, "native_calls": 800, "mcp_share": 0.2,
                  "top_tools": [("Bash", 500), ("Read", 300)], "category_breakdown": {},
                  "mcp_servers": [], "mcp_servers_distinct": 5,
                  "clis": [], "clis_distinct": 20, "cli_calls": 1000,
                  "toolsearch_calls": 100, "task_tool_calls": 400, "agent_calls": 80},
        "velocity": {"git_churn_total": 8000, "git_insertions": 6000, "git_deletions": 2000,
                     "git_commits_real": 50, "git_velocity_lines_per_hour": 100.0,
                     "git_repos_with_commits": 3, "git_repos_seen": 4, "git_per_repo": [],
                     "tool_churn_edit_write": 10000, "tool_lines_added": 7000,
                     "tool_lines_removed": 3000, "tool_velocity_lines_per_hour": 150.0,
                     "shell_write_calls": 20, "shell_authored_lines_est": 500,
                     "active_hours": 40.0, "git_commits_grep": 50},
        "behavior": {"planning_ratio_explore_to_doing": 0.7, "explore_actions": 200,
                     "produce_actions": 80, "execute_actions": 100, "delegate_actions": 30,
                     "avg_session_minutes": 45.0, "median_session_minutes": 40.0,
                     "longest_run_minutes": 120.0, "polite_prompts": 5,
                     "error_recovery_ratio": 0.9, "error_rate_per_100_tools": 2.5,
                     "tool_errors": 125, "recovered_errors": 112, "api_errors_retries": 5,
                     "fanout_median": 3, "iteration_depth_mean": 3.5,
                     "iteration_depth_median": 3.0, "iteration_depth_p90": 7,
                     "iteration_depth_max": 20, "files_hammered_over_15x": 1,
                     "actions_per_prompt": 10.0, "questions_asked": 15,
                     "background_tasks": 10, "scheduled_actions": 2, "shell_test_runs": 50,
                     "plan_sessions": 8},
        "rhythm": {"hour_histogram_local": {str(h): 0 for h in range(24)},
                   "weekday_histogram": {}, "peak_hours_local": [], "preferred_days": []},
        "progression": {"monthly": []},
        "stack": {"models": [("claude-opus-4-7", 5000), ("claude-haiku-4-5", 1000)],
                  "top_skills": [("code-review", 80), ("superpowers:writing-plans", 60),
                                 ("tdd", 40), ("brainstorm", 30)],
                  "skills_distinct": 15, "skills_total": 500, "subagent_types_distinct": 3,
                  "max_session_subagent_types": 3,
                  "skills_all": [("code-review", 80), ("superpowers:writing-plans", 60),
                                 ("tdd", 40), ("brainstorm", 30)],
                  "compounding_writes": 12,
                  "subagent_types": [("general-purpose", 50)],
                  "top_projects": []},
        "autonomy": {"autonomy_score_0_100": 50, "components": {
            "actions_per_prompt": 22.0, "delegation": 30.0,
            "scheduling_background": 5.0, "low_question_rate": 10.0}},
        "agentic": aq,
    }


def _zero_stats():
    """Stats dict with zero activity — tests the empty-corpus guard path."""
    s = _full_stats(sessions=0, tool_calls=0)
    s["volume"]["total_sessions"] = 0
    s["volume"]["tool_calls_total"] = 0
    return s


class TestScoreBreakdown(unittest.TestCase):
    def setUp(self):
        self.stats = _full_stats()
        self.bd = paxel.score_breakdown(self.stats)
        self.cs = paxel.compute_scores(self.stats)

    def test_three_axes_present(self):
        self.assertEqual(set(self.bd), {"execution", "planning", "engineering"})

    def test_execution_has_two_subs(self):
        self.assertEqual(len(self.bd["execution"]["subs"]), 2)

    def test_execution_sub_labels(self):
        """Execution must have exactly 'Tool output rate' and 'Delegation & parallelism';
        the removed subs ('Committed-code rate', 'Ship fidelity') must be absent."""
        labels = {s["label"] for s in self.bd["execution"]["subs"]}
        self.assertEqual(labels, {"Tool output rate", "Delegation & parallelism"})
        self.assertNotIn("Committed-code rate", labels)
        self.assertNotIn("Ship fidelity", labels)

    def test_planning_has_three_subs(self):
        self.assertEqual(len(self.bd["planning"]["subs"]), 3)

    def test_zero_axis_plan_ceremony_matches_live_target_and_unit(self):
        """The empty-corpus breakdown must show the SAME Plan ceremony target/unit as an
        active corpus — the zero-axis fallback drifted stale in a prior round."""
        def _pc(bd):
            return next(s for s in bd["planning"]["subs"] if s["label"] == "Planning skill practice")
        live = _pc(paxel.score_breakdown(_full_stats()))
        zero = _pc(paxel.score_breakdown(_zero_stats()))
        self.assertEqual(zero["target"], live["target"])
        self.assertEqual(zero["unit"], live["unit"])

    def test_plan_ceremony_counts_plan_sessions(self):
        """Plan ceremony must reflect the fraction of sessions with a planning signal
        (behavior.plan_sessions), not just plan-named Skill invocations — the fix for
        Claude Code's ExitPlanMode."""
        def _pc(stats):
            subs = paxel.score_breakdown(stats)["planning"]["subs"]
            return next(s for s in subs if s["label"] == "Planning skill practice")["your_value"]
        cold = _full_stats()
        cold["behavior"]["plan_sessions"] = 0
        hot = _full_stats()
        hot["behavior"]["plan_sessions"] = hot["volume"]["total_sessions"]
        self.assertGreater(_pc(hot), _pc(cold))

    def test_aq_discipline_credits_plan_sessions(self):
        """AQ Discipline's plan term must be satisfied by a planning session
        (behavior.plan_sessions), not only by a plan-named Skill — mirrors the
        gstack Planning fix. Strip any plan-named skill from the stack so the only
        difference between cold and hot is plan_sessions."""
        def _discipline(stats):
            aq = paxel.compute_aq(stats)
            breadth = next(p for p in aq["pillars"] if p["name"] == "Breadth")
            return next(a for a in breadth["axes"] if a["name"] == "Discipline")["score"]
        neutral_skills = [("read-file", 10)]
        cold = _full_stats()
        cold["stack"]["top_skills"] = list(neutral_skills)
        cold["stack"]["skills_all"] = list(neutral_skills)
        cold["behavior"]["plan_sessions"] = 0
        hot = _full_stats()
        hot["stack"]["top_skills"] = list(neutral_skills)
        hot["stack"]["skills_all"] = list(neutral_skills)
        hot["behavior"]["plan_sessions"] = 5
        self.assertEqual(_discipline(hot), _discipline(cold))

    def test_engineering_has_five_subs(self):
        self.assertEqual(len(self.bd["engineering"]["subs"]), 5)

    def test_pct_in_0_1_for_all_subs(self):
        for axis, d in self.bd.items():
            for s in d["subs"]:
                self.assertGreaterEqual(s["pct"], 0.0, f"{axis}/{s['label']}")
                self.assertLessEqual(s["pct"], 1.0, f"{axis}/{s['label']}")

    def test_exactly_one_is_drag_per_axis(self):
        for axis, d in self.bd.items():
            drags = [s for s in d["subs"] if s["is_drag"]]
            self.assertEqual(len(drags), 1, f"{axis}: expected exactly 1 is_drag, got {drags}")

    def test_value_equals_compute_scores(self):
        """Core invariant: score_breakdown values must equal compute_scores values exactly."""
        self.assertEqual(self.bd["execution"]["value"], self.cs["Execution"])
        self.assertEqual(self.bd["planning"]["value"], self.cs["Planning"])
        self.assertEqual(self.bd["engineering"]["value"], self.cs["Engineering"])

    def test_drag_note_is_string(self):
        for axis, d in self.bd.items():
            self.assertIsInstance(d["drag_note"], str, axis)
            self.assertGreater(len(d["drag_note"]), 0, axis)

    def test_gloss_present(self):
        for axis, d in self.bd.items():
            self.assertIsInstance(d["gloss"], str, axis)
            self.assertGreater(len(d["gloss"]), 0, axis)

    def test_empty_corpus_returns_well_formed_zeros(self):
        bd = paxel.score_breakdown(_zero_stats())
        self.assertEqual(set(bd), {"execution", "planning", "engineering"})
        for axis, d in bd.items():
            self.assertEqual(d["value"], 0.0, axis)
            drags = [s for s in d["subs"] if s["is_drag"]]
            self.assertEqual(len(drags), 1, axis)
            for s in d["subs"]:
                self.assertGreaterEqual(s["pct"], 0.0)
                self.assertLessEqual(s["pct"], 1.0)

    def test_empty_corpus_value_matches_compute_scores(self):
        zs = _zero_stats()
        bd = paxel.score_breakdown(zs)
        cs = paxel.compute_scores(zs)
        self.assertEqual(bd["execution"]["value"], cs["Execution"])
        self.assertEqual(bd["planning"]["value"], cs["Planning"])
        self.assertEqual(bd["engineering"]["value"], cs["Engineering"])

    def test_display_consistency_your_value_over_target_equals_pct(self):
        """For 'higher'-direction subs with no floor involved, pct must equal
        clamp(your_value/target) within floating-point tolerance.  Guards the bar-fill
        display invariant for the non-trivial full-stats fixture (plenty of prompts, so
        delegation floor doesn't fire).  Checked only for the three straightforward rate subs:
        Tool output rate (execution), Explore-before-build, Plan ceremony (planning).
        Does NOT assert on 'lower'-direction engineering subs or delegation."""
        tol = 1e-6
        checked = {
            "execution": {"Tool output rate"},
            "planning": {"Explore-before-build", "Planning skill practice"},
        }
        for axis, labels in checked.items():
            for sub in self.bd[axis]["subs"]:
                if sub["label"] in labels:
                    raw = sub["your_value"] / sub["target"]
                    expected_pct = max(0.0, min(1.0, raw))   # clamp(your_value/target)
                    self.assertAlmostEqual(
                        sub["pct"], expected_pct, delta=tol,
                        msg=f"{axis}/{sub['label']}: pct={sub['pct']!r} != clamp(your_value/target)={expected_pct!r}",
                    )

    # ---- narrative field tests ----

    _VALID_VERDICTS = {"excellent", "good", "adequate", "weak", "poor"}

    def test_sub_has_narrative_fields(self):
        """Every sub in every axis must carry verdict, score_pct, display_value,
        display_target, and narrative with the right types and constraints."""
        for axis, d in self.bd.items():
            for s in d["subs"]:
                ctx = f"{axis}/{s['label']}"
                self.assertIn(s["verdict"], self._VALID_VERDICTS, ctx)
                self.assertIsInstance(s["score_pct"], int, ctx)
                self.assertGreaterEqual(s["score_pct"], 0, ctx)
                self.assertLessEqual(s["score_pct"], 100, ctx)
                self.assertIsInstance(s["display_value"], str, ctx)
                self.assertGreater(len(s["display_value"]), 0, ctx)
                self.assertIsInstance(s["display_target"], str, ctx)
                self.assertGreater(len(s["display_target"]), 0, ctx)
                self.assertIsInstance(s["narrative"], str, ctx)
                self.assertIn(s["label"], s["narrative"], ctx)

    def test_axis_has_narrative_fields(self):
        """Every axis must carry axis_verdict, score_out_of_10, drag_narrative,
        and axis_narrative with the right types and constraints."""
        for axis, d in self.bd.items():
            ctx = axis
            self.assertIn(d["axis_verdict"], self._VALID_VERDICTS, ctx)
            self.assertIsInstance(d["score_out_of_10"], str, ctx)
            self.assertIn("/", d["score_out_of_10"], ctx)
            self.assertIsInstance(d["drag_narrative"], str, ctx)
            self.assertGreater(len(d["drag_narrative"]), 0, ctx)
            self.assertIsInstance(d["axis_narrative"], str, ctx)
            self.assertIn(axis.capitalize(), d["axis_narrative"], ctx)

    def test_verdict_consistency(self):
        """verdict must match score_pct thresholds exactly."""
        for axis, d in self.bd.items():
            for s in d["subs"]:
                ctx = f"{axis}/{s['label']}"
                pct = s["score_pct"]
                if pct >= 90:
                    expected = "excellent"
                elif pct >= 70:
                    expected = "good"
                elif pct >= 50:
                    expected = "adequate"
                elif pct >= 30:
                    expected = "weak"
                else:
                    expected = "poor"
                self.assertEqual(s["verdict"], expected,
                                 f"{ctx}: score_pct={pct}, expected verdict={expected!r}, got={s['verdict']!r}")

    def test_empty_corpus_has_narrative_fields(self):
        """Zero-activity output must carry all narrative fields on both subs and axes."""
        bd = paxel.score_breakdown(_zero_stats())
        valid_verdicts = {"excellent", "good", "adequate", "weak", "poor"}
        for axis, d in bd.items():
            ctx = f"zero/{axis}"
            # axis-level
            self.assertIn(d["axis_verdict"], valid_verdicts, ctx)
            self.assertIsInstance(d["score_out_of_10"], str, ctx)
            self.assertIn("/", d["score_out_of_10"], ctx)
            self.assertIsInstance(d["drag_narrative"], str, ctx)
            self.assertGreater(len(d["drag_narrative"]), 0, ctx)
            self.assertIsInstance(d["axis_narrative"], str, ctx)
            # sub-level
            for s in d["subs"]:
                sctx = f"zero/{axis}/{s['label']}"
                self.assertIn(s["verdict"], valid_verdicts, sctx)
                self.assertIsInstance(s["score_pct"], int, sctx)
                self.assertGreaterEqual(s["score_pct"], 0, sctx)
                self.assertLessEqual(s["score_pct"], 100, sctx)
                self.assertIsInstance(s["display_value"], str, sctx)
                self.assertGreater(len(s["display_value"]), 0, sctx)
                self.assertIsInstance(s["display_target"], str, sctx)
                self.assertGreater(len(s["display_target"]), 0, sctx)
                self.assertIsInstance(s["narrative"], str, sctx)

    def test_direction_in_display_target(self):
        """For 'lower'-direction subs, display_target must start with the le-sign prefix;
        for 'higher'-direction subs it must not."""
        for axis, d in self.bd.items():
            for s in d["subs"]:
                ctx = f"{axis}/{s['label']}"
                if s["direction"] == "lower":
                    self.assertTrue(s["display_target"].startswith("≤"),
                                    f"{ctx}: lower-direction target should start with ≤, got {s['display_target']!r}")
                else:
                    self.assertFalse(s["display_target"].startswith("≤"),
                                     f"{ctx}: higher-direction target should not start with ≤, got {s['display_target']!r}")


class TestBuildSummaryProfile(unittest.TestCase):
    def setUp(self):
        self.stats = _full_stats()
        self.summary = paxel.build_summary(self.stats)

    def test_original_keys_preserved(self):
        expected_original = {
            "context", "planning_ratio_explore_to_doing", "errors", "iteration_depth",
            "churn", "orchestration", "compounding_writes", "ecosystem",
            "progression_monthly",
        }
        self.assertTrue(expected_original.issubset(set(self.summary)))

    def test_profile_key_present(self):
        self.assertIn("profile", self.summary)

    def test_profile_has_expected_sub_keys(self):
        prof = self.summary["profile"]
        self.assertEqual(set(prof), {"aq", "archetype", "scores", "steering",
                                     "growth_edges", "signature_moves", "model_usage"})

    def test_profile_aq_is_dict(self):
        self.assertIsInstance(self.summary["profile"]["aq"], dict)

    def test_profile_archetype_has_title_and_quote(self):
        arch = self.summary["profile"]["archetype"]
        self.assertIn("title", arch)
        self.assertIn("quote", arch)
        self.assertIsInstance(arch["title"], str)
        self.assertIsInstance(arch["quote"], str)
        self.assertGreater(len(arch["title"]), 0)
        self.assertGreater(len(arch["quote"]), 0)

    def test_profile_scores_has_three_axes(self):
        self.assertEqual(set(self.summary["profile"]["scores"]),
                         {"execution", "planning", "engineering"})

    def test_profile_steering_has_label(self):
        st = self.summary["profile"]["steering"]
        self.assertIn("label", st)
        self.assertIn("detail", st)

    def test_no_prompt_text_in_summary(self):
        import json
        raw = json.dumps(self.summary).lower()
        for banned in ("prompt_text",):
            self.assertNotIn(banned, raw, f"verbatim field leaked: {banned}")

    def test_empty_corpus_profile_well_formed(self):
        summary = paxel.build_summary(_zero_stats())
        prof = summary["profile"]
        self.assertEqual(set(prof), {"aq", "archetype", "scores", "steering",
                                     "growth_edges", "signature_moves", "model_usage"})
        # scores all zero
        for axis in ("execution", "planning", "engineering"):
            self.assertEqual(prof["scores"][axis]["value"], 0.0)
        # archetype present
        self.assertIn("title", prof["archetype"])
        self.assertIn("quote", prof["archetype"])


class TestBuildSummaryPayloadFields(unittest.TestCase):
    """D1 + D4: build_summary must expose client_version, active_hours,
    total_prompts, and actions_per_prompt."""

    def setUp(self):
        self.stats = _full_stats()
        self.summary = paxel.build_summary(self.stats)

    # D1 — client_version in context
    def test_client_version_key_in_context(self):
        self.assertIn("client_version", self.summary["context"])

    def test_client_version_is_string(self):
        self.assertIsInstance(self.summary["context"]["client_version"], str)

    def test_client_version_nonempty(self):
        self.assertGreater(len(self.summary["context"]["client_version"]), 0)

    # D4 — active_hours in churn (or velocity sub-block)
    def test_active_hours_in_churn(self):
        self.assertIn("active_hours", self.summary["churn"])

    def test_active_hours_value(self):
        self.assertEqual(self.summary["churn"]["active_hours"],
                         self.stats["velocity"]["active_hours"])

    # D4 — total_prompts in context
    def test_total_prompts_in_context(self):
        self.assertIn("total_prompts", self.summary["context"])

    def test_total_prompts_value(self):
        self.assertEqual(self.summary["context"]["total_prompts"],
                         self.stats["volume"]["total_prompts"])

    # D4 — actions_per_prompt in churn (companion to active_hours)
    def test_actions_per_prompt_in_churn(self):
        self.assertIn("actions_per_prompt", self.summary["churn"])

    def test_actions_per_prompt_value(self):
        self.assertEqual(self.summary["churn"]["actions_per_prompt"],
                         self.stats["behavior"]["actions_per_prompt"])

    def test_noticed_stats_share_safe_slice(self):
        # noticed_stats was dropped from the summary payload (superseded by
        # scoring_inputs_by_source); the shaper itself is still exercised directly.
        ns = paxel._build_noticed_stats(self.stats)
        self.assertEqual(set(ns.keys()), {
            "volume", "shipping", "iteration", "errors", "models",
            "rhythm", "prompts", "agents", "sessions", "tools",
            "skills", "mcp_servers",
        })
        self.assertEqual(ns["volume"], {
            "total_sessions": self.stats["volume"]["total_sessions"],
            "total_prompts": self.stats["volume"]["total_prompts"],
            "tool_calls_total": self.stats["volume"]["tool_calls_total"],
            "assistant_turns": self.stats["volume"]["assistant_turns"],
            "thinking_blocks": self.stats["volume"]["thinking_blocks"],
        })
        self.assertEqual(ns["shipping"], {
            "git_churn_total": self.stats["velocity"]["git_churn_total"],
            "tool_churn_edit_write": self.stats["velocity"]["tool_churn_edit_write"],
            "shell_authored_lines_est": self.stats["velocity"]["shell_authored_lines_est"],
            "git_repos_seen": self.stats["velocity"]["git_repos_seen"],
            "git_repos_with_commits": self.stats["velocity"]["git_repos_with_commits"],
            "active_hours": self.stats["velocity"]["active_hours"],
        })
        self.assertEqual(ns["iteration"], {
            "depth_mean": self.stats["behavior"]["iteration_depth_mean"],
            "depth_median": self.stats["behavior"]["iteration_depth_median"],
            "depth_p90": self.stats["behavior"]["iteration_depth_p90"],
            "depth_max": self.stats["behavior"]["iteration_depth_max"],
            "files_over_15x": self.stats["behavior"]["files_hammered_over_15x"],
        })
        self.assertEqual(ns["errors"], {
            "tool_errors": self.stats["behavior"]["tool_errors"],
            "error_rate_per_100_tools": self.stats["behavior"]["error_rate_per_100_tools"],
            "error_recovery_ratio": self.stats["behavior"]["error_recovery_ratio"],
        })
        self.assertEqual(ns["models"]["top_models"][0], {
            "model_id": "claude-opus-4-7",
            "label": "Opus 4.7",
            "turns": 5000,
            "pct": 0.833,
        })
        self.assertEqual(set(ns["rhythm"]["weekday_histogram"].keys()),
                         {"Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"})
        self.assertEqual(ns["prompts"], {
            "avg_length_chars": self.stats["volume"]["avg_prompt_length_chars"],
            "median_length_chars": self.stats["volume"]["median_prompt_length_chars"],
            "polite_prompts": self.stats["behavior"]["polite_prompts"],
            "questions_asked": self.stats["behavior"]["questions_asked"],
        })
        self.assertEqual(ns["agents"], {
            "delegate_actions": self.stats["behavior"]["delegate_actions"],
            "background_tasks": self.stats["behavior"]["background_tasks"],
            "scheduled_actions": self.stats["behavior"]["scheduled_actions"],
            "fanout_median": self.stats["behavior"]["fanout_median"],
        })
        self.assertEqual(ns["sessions"], {
            "longest_run_minutes": self.stats["behavior"]["longest_run_minutes"],
        })
        self.assertEqual(ns["tools"]["top_tools"], [
            {"name": "Bash", "calls": 500},
            {"name": "Read", "calls": 300},
        ])

    def test_top_tools_keeps_20_global_and_monthly_entries(self):
        import contextlib, io, json, shutil, tempfile
        from unittest import mock

        proj = tempfile.mkdtemp(prefix="paxel-top-tools-")
        self.addCleanup(shutil.rmtree, proj, ignore_errors=True)
        sess_dir = os.path.join(proj, "proj-x")
        os.makedirs(sess_dir, exist_ok=True)

        content = [{"type": "thinking", "thinking": "rank tools"}]
        for idx in range(41):
            calls = 41 - idx
            name = f"mcp__server_{idx:02d}__action"
            content.extend(
                {"type": "tool_use", "name": name, "input": {}}
                for _ in range(calls)
            )
        rows = [
            {"type": "user", "sessionId": "top-tools", "cwd": "/tmp/proj",
             "timestamp": "2026-06-01T10:00:00.000Z",
             "message": {"role": "user", "content": "rank tools"}},
            {"type": "assistant", "sessionId": "top-tools", "cwd": "/tmp/proj",
             "timestamp": "2026-06-01T10:00:01.000Z",
             "message": {"role": "assistant", "model": "claude-opus-4-8", "content": content}},
        ]
        with open(os.path.join(sess_dir, "session.jsonl"), "w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row) + "\n")

        empty = tempfile.mkdtemp(prefix="paxel-top-tools-empty-")
        out = tempfile.mkdtemp(prefix="paxel-top-tools-out-")
        self.addCleanup(shutil.rmtree, empty, ignore_errors=True)
        self.addCleanup(shutil.rmtree, out, ignore_errors=True)
        overrides = dict(
            OUT_DIR=out, BASE=proj, CODEX_DIR=empty, GEMINI_DIR=empty, PI_DIR=empty,
            ANTIGRAVITY_CLI_DIR=empty, ANTIGRAVITY_DB=os.path.join(empty, "nope.vscdb"),
            OPENCODE_DIR=empty, CURSOR_DIR=empty,
            CURSOR_DB=os.path.join(empty, "nope.vscdb"),
        )
        with mock.patch.multiple(paxel, **overrides), \
                mock.patch.object(sys, "argv", ["paxel.py", "claude", "--no-open"]), \
                contextlib.redirect_stdout(io.StringIO()):
            paxel.main()

        with open(os.path.join(out, "stats.json"), encoding="utf-8") as fh:
            stats = json.load(fh)

        self.assertEqual(len(stats["tools"]["top_tools"]), 41)
        monthly = stats["monthly_noticed_stats"][0]["stats"]["tools"]["top_tools"]
        self.assertEqual(len(monthly), 41)


class TestAntigravityCli(unittest.TestCase):
    """Parse a synthetic Antigravity CLI conversation DB (protobuf step payloads) built
    with a tiny stdlib encoder, mirroring the real on-disk field layout."""

    @staticmethod
    def _varint(n):
        out = bytearray()
        while True:
            b = n & 0x7F
            n >>= 7
            out.append(b | 0x80 if n else b)
            if not n:
                return bytes(out)

    @classmethod
    def _vfield(cls, f, n):
        return cls._varint((f << 3) | 0) + cls._varint(n)

    @classmethod
    def _bfield(cls, f, b):
        if isinstance(b, str):
            b = b.encode("utf-8")
        return cls._varint((f << 3) | 2) + cls._varint(len(b)) + b

    def _meta(self, sec, usage=None):
        blob = self._bfield(1, self._vfield(1, sec) + self._vfield(2, 0))
        if usage:
            inp, out, cache = usage
            blob += self._bfield(9, self._vfield(2, inp) + self._vfield(3, out) + self._vfield(5, cache))
        return self._bfield(5, blob)

    def _step(self, step_type, body=b""):
        return self._vfield(1, step_type) + self._vfield(4, 3) + body

    def setUp(self):
        import sqlite3 as _sq
        import shutil, tempfile
        self.dir = tempfile.mkdtemp()
        self.db = os.path.join(self.dir, "abc12345-0000-0000-0000-000000000000.db")
        con = _sq.connect(self.db)
        con.execute("CREATE TABLE steps (idx INTEGER PRIMARY KEY, step_type INTEGER, step_payload BLOB)")
        con.execute("CREATE TABLE gen_metadata (idx INTEGER, data BLOB)")
        con.execute("CREATE TABLE trajectory_metadata_blob (id TEXT, data BLOB)")
        # cwd: trajectory_metadata_blob -> field 1 -> field 1 = file:// URI
        traj = self._bfield(1, self._bfield(1, "file:///Users/me/proj"))
        con.execute("INSERT INTO trajectory_metadata_blob VALUES (?,?)", ("main", traj))
        # user prompt (step_type 14): field 19 -> field 2 = text
        user = self._step(14, self._meta(1000) + self._bfield(19, self._bfield(2, "fix the build")))
        # assistant turn (step_type 15): meta with usage; field 20 -> {1: text, 7:{2:name,3:args}}
        tool = self._bfield(2, "run_command") + self._bfield(3, '{"CommandLine":"make","Cwd":"/x"}')
        asst = self._step(15, self._meta(1001, usage=(500, 40, 1200))
                          + self._bfield(20, self._bfield(1, "Running the build.") + self._bfield(7, tool)))
        err = self._step(17, self._meta(1002))
        con.execute("INSERT INTO steps VALUES (?,?,?)", (0, 14, user))
        con.execute("INSERT INTO steps VALUES (?,?,?)", (1, 15, asst))
        con.execute("INSERT INTO steps VALUES (?,?,?)", (2, 17, err))
        con.execute("INSERT INTO gen_metadata VALUES (?,?)", (1, b"...model gemini-3-pro stuff..."))
        con.commit()
        con.close()
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)

    def test_events(self):
        from gnomon.sources.antigravity import _antigravity_cli_events
        evs = list(_antigravity_cli_events(self.db))
        self.assertFalse(any(e.get("__bad__") for e in evs))
        self.assertEqual(evs[0]["cwd"], "/Users/me/proj")
        users = [e for e in evs if e["type"] == "user" and isinstance(e["message"]["content"], str)]
        self.assertEqual(users[0]["message"]["content"], "fix the build")
        asst = [e for e in evs if e["type"] == "assistant"][0]
        blocks = asst["message"]["content"]
        self.assertEqual(blocks[0], {"type": "text", "text": "Running the build."})
        tool = blocks[1]
        self.assertEqual(tool["type"], "tool_use")
        self.assertEqual(tool["name"], "Bash")               # run_command -> Bash
        self.assertEqual(tool["input"]["command"], "make")   # CommandLine -> command
        self.assertEqual(asst["message"]["usage"],
                         {"input_tokens": 500, "output_tokens": 40,
                          "cache_read_input_tokens": 1200, "cache_creation_input_tokens": 0})
        self.assertEqual(asst["message"]["model"], "gemini-3-pro")
        errs = [e for e in evs if e["type"] == "user" and isinstance(e["message"]["content"], list)
                and e["message"]["content"][0].get("is_error")]
        self.assertEqual(len(errs), 1)

    def test_arg_aliasing(self):
        from gnomon.sources.antigravity import _ag_args, _AG_TOOL
        self.assertEqual(_ag_args('{"AbsolutePath":"/a/b.py"}')["file_path"], "/a/b.py")
        self.assertEqual(_ag_args('{"CodeContent":"x"}')["content"], "x")
        self.assertEqual(_ag_args("not json"), {})
        self.assertEqual(_AG_TOOL["grep_search"], "Grep")
        self.assertEqual(_AG_TOOL["write_to_file"], "Write")

    def test_mcp_and_skill_cli(self):
        import sqlite3 as _sq
        import shutil, tempfile
        from gnomon.sources.antigravity import _antigravity_cli_events
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        db = os.path.join(d, "cli.db")
        con = _sq.connect(db)
        con.execute("CREATE TABLE steps (idx INTEGER PRIMARY KEY, step_type INTEGER, step_payload BLOB)")
        con.execute("CREATE TABLE gen_metadata (idx INTEGER, data BLOB)")
        con.execute("CREATE TABLE trajectory_metadata_blob (id TEXT, data BLOB)")
        # MCP call: tool name `supabase::execute_sql`
        mcp = self._bfield(2, "supabase::execute_sql") + self._bfield(3, "{}")
        s_mcp = self._step(15, self._meta(1000) + self._bfield(20, self._bfield(1, "q") + self._bfield(7, mcp)))
        # skill load: view_file of a skills/<name>/SKILL.md
        sk = self._bfield(2, "view_file") + self._bfield(3, '{"AbsolutePath":"/x/.agents/skills/data-scientist/SKILL.md"}')
        s_sk = self._step(15, self._meta(1001) + self._bfield(20, self._bfield(1, "look") + self._bfield(7, sk)))
        con.execute("INSERT INTO steps VALUES (?,?,?)", (0, 15, s_mcp))
        con.execute("INSERT INTO steps VALUES (?,?,?)", (1, 15, s_sk))
        con.commit(); con.close()
        evs = list(_antigravity_cli_events(db))
        tools = [b for e in evs if e["type"] == "assistant"
                 for b in e["message"]["content"] if b.get("type") == "tool_use"]
        self.assertIn("mcp__supabase__execute_sql", [t["name"] for t in tools])  # MCP server::tool
        self.assertEqual([e["attributionSkill"] for e in evs if e.get("attributionSkill")], ["data-scientist"])


class TestAntigravityIdeExport(unittest.TestCase):
    """Parse the combined IDE step export (CORTEX JSON from the language server)."""

    def _events(self, convs):
        import json, tempfile
        from gnomon.sources.antigravity import _antigravity_ide_export_events
        d = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, d, ignore_errors=True)
        p = os.path.join(d, "ide_steps_export.json")
        with open(p, "w") as fh:
            json.dump(convs, fh)
        return list(_antigravity_ide_export_events(p))

    def _step(self, t, **kw):
        return {"type": t, "metadata": {"createdAt": "2026-05-01T10:00:00Z"}, **kw}

    def test_step_mapping(self):
        convs = [{"cascade_id": "c1", "steps": [
            self._step("CORTEX_STEP_TYPE_USER_INPUT", userInput={"items": [{"text": "fix the build"}]}),
            self._step("CORTEX_STEP_TYPE_PLANNER_RESPONSE", plannerResponse={"thinking": "Let me look."}),
            self._step("CORTEX_STEP_TYPE_CODE_ACTION",
                       codeAction={"actionSpec": {"createFile": {"absolutePathUri": "file:///Users/me/proj/app.py",
                                                                 "instruction": "x=1\ny=2\n"}}}),
            self._step("CORTEX_STEP_TYPE_RUN_COMMAND", runCommand={"commandLine": "pnpm lint", "exitCode": 1}),
            self._step("CORTEX_STEP_TYPE_VIEW_FILE", viewFile={"absolutePathUri": "file:///Users/me/proj/app.py"}),
            self._step("CORTEX_STEP_TYPE_COMMAND_STATUS", commandStatus={"exitCode": 0}),  # skipped
        ]}]
        evs = self._events(convs)
        users = [e for e in evs if e["type"] == "user" and isinstance(e["message"]["content"], str)]
        self.assertEqual(users[0]["message"]["content"], "fix the build")
        think = [b for e in evs if e["type"] == "assistant"
                 for b in e["message"]["content"] if b.get("type") == "thinking"]
        self.assertEqual(think[0]["thinking"], "Let me look.")
        tools = [b for e in evs if e["type"] == "assistant"
                 for b in e["message"]["content"] if b.get("type") == "tool_use"]
        names = [t["name"] for t in tools]
        self.assertEqual(names, ["Write", "Bash", "Read"])     # code_action create, run, view
        bash = next(t for t in tools if t["name"] == "Bash")
        self.assertEqual(bash["input"]["command"], "pnpm lint")  # command text survives
        # run_command exitCode 1 -> errored tool_result
        errs = [e for e in evs if e["type"] == "user" and isinstance(e["message"]["content"], list)
                and e["message"]["content"][0].get("is_error")]
        self.assertEqual(len(errs), 1)
        # real per-step timestamp (not mtime); cwd from a real workspace path
        self.assertTrue(all(e["timestamp"] == "2026-05-01T10:00:00Z" for e in evs))
        self.assertEqual(evs[0]["cwd"], "/Users/me/proj")

    def test_mcp_and_skill(self):
        convs = [{"cascade_id": "c1", "steps": [
            # planner toolCalls are NOT emitted as tools — the execution steps are (no double count)
            self._step("CORTEX_STEP_TYPE_PLANNER_RESPONSE",
                       plannerResponse={"thinking": "search",
                                        "toolCalls": [{"name": "airbnb::airbnb_search"}]}),
            # MCP is counted from the dedicated MCP_TOOL step only
            self._step("CORTEX_STEP_TYPE_MCP_TOOL",
                       mcpTool={"serverName": "airbnb",
                                "toolCall": {"name": "airbnb_search", "argumentsJson": '{"q":"mvd"}'}}),
            self._step("CORTEX_STEP_TYPE_VIEW_FILE",
                       viewFile={"absolutePathUri": "file:///Users/me/.gemini/config/skills/data-engineer/SKILL.md"}),
        ]}]
        evs = self._events(convs)
        tools = [b for e in evs if e["type"] == "assistant"
                 for b in e["message"]["content"] if b.get("type") == "tool_use"]
        names = [t["name"] for t in tools]
        self.assertEqual(names.count("mcp__airbnb__airbnb_search"), 1)  # counted once (MCP_TOOL step)
        skill_evs = [e for e in evs if e.get("attributionSkill")]
        self.assertEqual(skill_evs[0]["attributionSkill"], "data-engineer")  # SKILL.md read

    def test_empty_and_malformed(self):
        self.assertEqual(self._events([]), [])
        self.assertEqual(self._events([{"cascade_id": "c", "steps": []}]), [])


class TestAntigravityIdeWindowGate(unittest.TestCase):
    """ide_window_overlaps decides whether to bother launching the IDE for a given window."""

    def setUp(self):
        from datetime import datetime
        from gnomon.sources.antigravity import ide_window_overlaps
        self.f = ide_window_overlaps
        self.dt = lambda s: datetime.fromisoformat(s).astimezone()
        self.summary = {"conversations": 5, "first": "2026-03-01T00:00:00+00:00",
                        "last": "2026-03-31T00:00:00+00:00"}

    def test_no_summary_is_false(self):
        self.assertFalse(self.f(None, None, None))

    def test_no_window_always_overlaps(self):
        self.assertTrue(self.f(self.summary, None, None))

    def test_window_after_range_skips(self):
        # window starts in April; IDE history ends in March -> no overlap
        self.assertFalse(self.f(self.summary, self.dt("2026-04-01"), None))

    def test_window_before_range_skips(self):
        # window ends (exclusive) in Feb; IDE history starts in March -> no overlap
        self.assertFalse(self.f(self.summary, None, self.dt("2026-02-01")))

    def test_overlapping_window_passes(self):
        self.assertTrue(self.f(self.summary, self.dt("2026-03-15"), self.dt("2026-04-15")))

    def test_missing_bounds_treated_open(self):
        self.assertTrue(self.f({"conversations": 1}, self.dt("2026-03-15"), self.dt("2026-03-20")))


class TestAntigravityExportStale(unittest.TestCase):
    """A failed aghistory refresh must NOT leave a previous export to be re-scored."""

    def test_failed_refresh_removes_stale(self):
        import shutil, tempfile
        from unittest import mock
        from gnomon.sources import antigravity as A
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        stale = os.path.join(d, "ide_steps_export.json")
        with open(stale, "w") as fh:
            fh.write('[{"cascade_id": "old", "steps": [{"type": "x"}]}]')
        with mock.patch.object(A, "_ANTIGRAVITY_APP", d), \
                mock.patch.object(A, "_discover_language_servers", return_value=[(1234, "csrf")]), \
                mock.patch.object(A, "_ide_cascade_ids", return_value=["x"]), \
                mock.patch.object(A, "_ls_post", return_value=None):   # server unreachable / no steps
            res = A.export_antigravity_ide(d, launch=False, log=lambda *a: None)
        self.assertIsNone(res)                      # no fresh steps -> no path
        self.assertFalse(os.path.exists(stale))     # stale export removed, not folded in


class TestAntigravityDirOverride(unittest.TestCase):
    """--antigravity-dir must accept the tool root, not only the leaf conversations dir."""

    def test_root_resolves_to_conversations(self):
        import shutil, tempfile
        from gnomon.sources.discovery import _DIR_FLAGS, _resolve_source_dir
        self.assertEqual(_DIR_FLAGS["antigravity"][1], "conversations")
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        leaf = os.path.join(root, "conversations")
        os.makedirs(leaf)
        self.assertEqual(_resolve_source_dir(root, "conversations"), leaf)   # root -> subdir
        self.assertEqual(_resolve_source_dir(leaf, "conversations"), leaf)    # leaf -> no double-nest


class TestScoringDoesNotPenalizeMissingCaps(unittest.TestCase):
    """A source must not be scored 0 on a signal its backend cannot emit — the axis/term is
    dropped and the rest renormalized (AQ build_pillar/wsum + gstack _axis_value)."""

    def _gstack_stats(self, source):
        return {"volume": {"total_sessions": 5, "total_prompts": 10, "tool_calls_total": 3000,
                         "thinking_blocks": 0},
              "behavior": {"planning_ratio_explore_to_doing": 0.5, "delegate_actions": 0,
                           "background_tasks": 0, "iteration_depth_mean": 2, "iteration_depth_p90": 3,
                           "files_hammered_over_15x": 0, "error_rate_per_100_tools": 0, "shell_test_runs": 0},
              "velocity": {"tool_churn_edit_write": 2000, "active_hours": 2},
              "stack": {"top_skills": []}, "corpus": {"sources": {source: {}}}}

    def _gstack(self, source):
        from gnomon.scoring.gstack import compute_scores
        return compute_scores(self._gstack_stats(source))

    def test_gstack_thinking_dropped_for_cli(self):
        # antigravity CLI emits no thinking -> reasoning-depth term drops -> Planning renormalizes
        # UP (not the 0-drag a full-caps source eats with thinking_blocks=0).
        self.assertGreater(self._gstack("antigravity")["Planning"], self._gstack("claude")["Planning"])

    def test_gstack_planning_skill_dropped_for_cursor(self):
        # Cursor has no first-class Skill tool (only skill_reads), so planning_skill_sessions
        # term is dropped and the rest of Planning renormalizes UP.
        self.assertGreater(self._gstack("cursor")["Planning"], self._gstack("claude")["Planning"])

    def test_gstack_cursor_breakdown_drops_planning_skill(self):
        from gnomon.scoring.gstack import score_breakdown
        planning = score_breakdown(self._gstack_stats("cursor"))["planning"]["subs"]
        self.assertNotIn("Planning skill practice", {sub["label"] for sub in planning})
        self.assertAlmostEqual(sum(sub["weight"] for sub in planning), 1.0, places=3)

    def test_aq_drops_unsupported_axes_for_ide(self):
        from gnomon.scoring.aq import compute_aq
        r = compute_aq({"corpus": {"sources": {"antigravity-ide": {}}},
                        "tools": {}, "stack": {"models": []}, "behavior": {}})
        na = {a for p in r["pillars"] for a in (p.get("not_applicable") or [])}
        self.assertIn("Orchestration", na)   # no delegate cap -> dropped, not scored 0
        self.assertIn("Model mix", na)        # masked model -> dropped, not scored 0

    def test_full_caps_source_unchanged(self):
        # a source that emits everything keeps every axis (no silent renormalization)
        from gnomon.scoring.aq import compute_aq
        r = compute_aq({"corpus": {"sources": {"claude": {}}},
                        "tools": {}, "stack": {"models": []}, "behavior": {}})
        na = {a for p in r["pillars"] for a in (p.get("not_applicable") or [])}
        self.assertNotIn("Orchestration", na)
        self.assertNotIn("Model mix", na)


class TestPlanBadgeCreditsPlanSessions(unittest.TestCase):
    """FU-1: the narrative 'Plan' signature move must fire on planning sessions
    (behavior.plan_sessions), not only plan-named Skill invocations — consistent with
    gstack Plan ceremony after the ExitPlanMode fix."""

    def _strip_plan_skills(self, stats):
        # Remove plan-named real skills so plan credit comes ONLY from plan_sessions.
        neutral = [("read-file", 10)]
        stats["stack"]["top_skills"] = neutral
        stats["stack"]["skills_all"] = neutral
        return stats

    def _has_plan_badge(self, stats):
        from gnomon.scoring.insights import signature_moves
        return any(title == "You write the plan before the code"
                   for _tag, title, _ev in signature_moves(stats))

    def test_plan_badge_absent_without_plan_signal(self):
        stats = self._strip_plan_skills(_full_stats())
        stats["behavior"]["plan_sessions"] = 0
        self.assertFalse(self._has_plan_badge(stats))

    def test_plan_badge_present_from_plan_sessions(self):
        # _full_stats has 10 sessions; 8 planning sessions clears the >=3 and >=35% gate.
        stats = self._strip_plan_skills(_full_stats())
        stats["behavior"]["plan_sessions"] = 8
        self.assertTrue(self._has_plan_badge(stats))


class TestRecoveryApiErrorRate(unittest.TestCase):
    """Recovery's API-error term is a RATE (per 100 tool calls), not an absolute count.
    Fixes the window-dependence and volume-penalty bugs of the old sat(api_errors, 50)."""

    def _recovery_score(self, api_retries, tool_calls, recovery_ratio=1.0):
        s = _sample_stats()
        s["behavior"]["error_recovery_ratio"] = recovery_ratio
        s["behavior"]["api_errors_retries"] = api_retries
        s["volume"] = {"tool_calls_total": tool_calls}
        aq = paxel.compute_aq(s)
        eff = next(p for p in aq["pillars"] if p["name"] == "Efficiency")
        return next(a for a in eff["axes"] if a["name"] == "Recovery")["score"]

    def test_rate_invariant_to_volume(self):
        # Identical rate (2 per 100), 100x different volume -> identical Recovery.
        self.assertAlmostEqual(self._recovery_score(20, 1000),
                               self._recovery_score(2000, 100000))

    def test_high_volume_low_rate_scores_near_max(self):
        # 200 retries over 100k tool calls = 0.2/100 -> near-full reward (volume bug gone).
        self.assertGreater(self._recovery_score(200, 100000), 49.0)

    def test_higher_rate_lowers_recovery(self):
        low = self._recovery_score(50, 100000)    # 0.05/100
        high = self._recovery_score(4000, 100000)  # 4/100, over target -> term zeroed
        self.assertGreater(low, high)

    def test_zero_tool_calls_full_reward(self):
        # No tools -> no errors possible -> the api term must not penalize.
        self.assertGreater(self._recovery_score(0, 0), 49.0)

    def test_signals_expose_rate(self):
        s = _sample_stats()
        s["behavior"]["api_errors_retries"] = 20
        s["volume"] = {"tool_calls_total": 10000}
        aq = paxel.compute_aq(s)
        eff = next(p for p in aq["pillars"] if p["name"] == "Efficiency")
        rec = next(a for a in eff["axes"] if a["name"] == "Recovery")
        self.assertEqual(rec["signals"]["api_per_100_tools"], 0.2)


class TestPlanCeremonySubagents(unittest.TestCase):
    """SDD planning phases run as Agent(subagent_type=...), not as typed Skills. They must
    still mark a plan session. sdd-explore (grounding, not planning) must not."""

    @staticmethod
    def _agent_ev(sid, subagent_type):
        return {"type": "assistant", "sessionId": sid, "timestamp": "2026-03-01T10:00:00Z",
                "message": {"role": "assistant", "content": [
                    {"type": "tool_use", "name": "Agent",
                     "input": {"subagent_type": subagent_type}}]}}

    @staticmethod
    def _tool_ev(sid, tool_name):
        return {"type": "assistant", "sessionId": sid, "timestamp": "2026-03-01T10:00:00Z",
                "message": {"role": "assistant", "content": [
                    {"type": "tool_use", "name": tool_name, "input": {}}]}}

    def _acc(self, events):
        from gnomon.cli.accumulator import Accumulator
        acc = Accumulator()
        acc.begin_file("claude", "f.jsonl")
        for ev in events:
            acc.observe(ev, None, None)
        return acc

    def test_sdd_planning_phases_mark_plan(self):
        for st in ("sdd-propose", "sdd-spec", "sdd-design", "sdd-tasks"):
            acc = self._acc([self._agent_ev("s-" + st, st)])
            self.assertIn("s-" + st, acc.plan_sessions, st)

    def test_builtin_plan_agent_marks_plan(self):
        acc = self._acc([self._agent_ev("s1", "Plan")])
        self.assertIn("s1", acc.plan_sessions)

    def test_planner_agent_marks_plan(self):
        acc = self._acc([self._agent_ev("s1", "orchestration-planner")])
        self.assertIn("s1", acc.plan_sessions)

    def test_sdd_explore_does_not_mark_plan(self):
        acc = self._acc([self._agent_ev("s2", "sdd-explore")])
        self.assertNotIn("s2", acc.plan_sessions)

    def test_non_planning_agent_does_not_mark_plan(self):
        acc = self._acc([self._agent_ev("s3", "general-purpose")])
        self.assertNotIn("s3", acc.plan_sessions)

    def test_idempotent_across_signals(self):
        # TodoWrite + sdd-propose in the same session -> counted once.
        acc = self._acc([self._tool_ev("s4", "TodoWrite"),
                         self._agent_ev("s4", "sdd-propose")])
        self.assertEqual(len(acc.plan_sessions), 1)
        self.assertIn("s4", acc.plan_sessions)


class TestHarnessBehavioral(unittest.TestCase):
    """o_harn credits real orchestration BEHAVIOR: a SINGLE session coordinating >=3 distinct
    subagent roles (max_session_subagent_types). Window-wide role variety alone
    (subagent_types_distinct) does NOT count — that would credit serial single-agent sessions."""

    def _orch(self, max_session_types):
        s = _sample_stats()
        s["stack"]["max_session_subagent_types"] = max_session_types
        aq = paxel.compute_aq(s)
        breadth = next(p for p in aq["pillars"] if p["name"] == "Breadth")
        return next(a for a in breadth["axes"] if a["name"] == "Orchestration")

    def test_session_with_three_roles_credits_harness(self):
        self.assertEqual(self._orch(3)["signals"]["o_harn"], 1.0)

    def test_fewer_than_three_roles_no_harness(self):
        # A session coordinating <3 distinct roles = ad-hoc delegation, not a team.
        self.assertEqual(self._orch(2)["signals"]["o_harn"], 0.6)

    def test_window_variety_without_session_coordination_no_credit(self):
        # Reviewer's scenario: 3 distinct types window-wide, but never >=3 in one session.
        s = _sample_stats()
        s["stack"]["subagent_types_distinct"] = 3     # window-wide variety
        s["stack"]["max_session_subagent_types"] = 1  # each session used a single role
        aq = paxel.compute_aq(s)
        breadth = next(p for p in aq["pillars"] if p["name"] == "Breadth")
        ax = next(a for a in breadth["axes"] if a["name"] == "Orchestration")
        self.assertEqual(ax["signals"]["o_harn"], 0.6)


class TestSessionSubagentTypes(unittest.TestCase):
    """max_session_subagent_types = the most distinct subagent roles coordinated in ONE session
    (per-session), not window-wide distinct types."""

    @staticmethod
    def _agent_ev(sid, subagent_type):
        return {"type": "assistant", "sessionId": sid, "timestamp": "2026-03-01T10:00:00Z",
                "message": {"role": "assistant", "content": [
                    {"type": "tool_use", "name": "Agent",
                     "input": {"subagent_type": subagent_type}}]}}

    def _acc(self, events):
        from gnomon.cli.accumulator import Accumulator
        acc = Accumulator()
        acc.begin_file("claude", "f.jsonl")
        for ev in events:
            acc.observe(ev, None, None)
        return acc

    def test_three_roles_one_session(self):
        acc = self._acc([self._agent_ev("s1", "sdd-propose"),
                         self._agent_ev("s1", "sdd-spec"),
                         self._agent_ev("s1", "sdd-apply")])
        self.assertEqual(max((len(v) for v in acc.session_subagent_types.values()), default=0), 3)

    def test_three_roles_across_separate_sessions(self):
        # Same 3 roles but one per session -> max per-session is 1, not 3.
        acc = self._acc([self._agent_ev("s1", "sdd-propose"),
                         self._agent_ev("s2", "sdd-spec"),
                         self._agent_ev("s3", "sdd-apply")])
        self.assertEqual(max((len(v) for v in acc.session_subagent_types.values()), default=0), 1)


class TestDetektVariantTasks(unittest.TestCase):
    """Bare `detekt` counts as verification; variant tasks (detektMain,
    detektGenerateConfig) don't — ideally they'd run via `check`."""

    def test_detekt_bare_counts(self):
        from gnomon.taxonomy import bash_runs_tests
        self.assertTrue(bash_runs_tests("./gradlew detekt"))
        self.assertTrue(bash_runs_tests("./gradlew :app:detekt"))

    def test_detekt_variants_excluded(self):
        from gnomon.taxonomy import bash_runs_tests
        for cmd in ("./gradlew detektMain", "./gradlew detektGenerateConfig",
                    "./gradlew detektBaselineMain"):
            self.assertFalse(bash_runs_tests(cmd), cmd)


class TestConfigurablePlanNeedles(unittest.TestCase):
    """GNOMON_PLAN_SKILL_NEEDLES extends (never replaces) the built-in plan-skill needles."""

    def test_env_extends_needles(self):
        import importlib, gnomon.taxonomy as tax
        os.environ["GNOMON_PLAN_SKILL_NEEDLES"] = "roadmap, my-planner"
        try:
            importlib.reload(tax)
            self.assertIn("roadmap", tax.PLAN_SKILL_NEEDLES)
            self.assertIn("my-planner", tax.PLAN_SKILL_NEEDLES)
            self.assertIn("brainstorm", tax.PLAN_SKILL_NEEDLES)  # builtins remain
        finally:
            os.environ.pop("GNOMON_PLAN_SKILL_NEEDLES", None)
            importlib.reload(tax)

    def test_no_env_builtins_only(self):
        import gnomon.taxonomy as tax
        self.assertNotIn("roadmap", tax.PLAN_SKILL_NEEDLES)
        self.assertIn("brainstorm", tax.PLAN_SKILL_NEEDLES)


class TestPerSessionRates(unittest.TestCase):
    """The converted metrics score per-session RATE, not absolute volume: the same rate at
    different session counts scores identically (kills the volume artifact), and a higher rate
    scores higher regardless of total sessions."""

    def _discipline(self, task_calls, sessions):
        s = _sample_stats()
        s["volume"] = {"total_sessions": sessions}
        s["tools"]["task_tool_calls"] = task_calls
        aq = paxel.compute_aq(s)
        breadth = next(p for p in aq["pillars"] if p["name"] == "Breadth")
        return next(a for a in breadth["axes"] if a["name"] == "Discipline")["score"]

    def test_same_rate_same_score(self):
        # 0.5 task-tool/session either way -> identical Discipline (volume artifact gone)
        self.assertEqual(self._discipline(50, 100), self._discipline(500, 1000))

    def test_low_session_high_intensity_beats_high_session_low_intensity(self):
        # fede-like (few sessions, dense) vs volume-heavy but sparse per session
        dense = self._discipline(150, 100)   # 1.5/session
        sparse = self._discipline(300, 1000)  # 0.3/session
        self.assertGreater(dense, sparse)

    def test_zero_sessions_guarded(self):
        self._discipline(10, 0)  # must not divide by zero


class TestToolsDiagnostic(unittest.TestCase):
    """--tools diagnostic: per-session tool rates from the already-computed agentic signals."""

    def _stats(self, sessions):
        return {
            "volume": {"total_sessions": sessions, "total_prompts": sessions * 4},
            "velocity": {"active_hours": 50.0},
            "agentic": {"pillars": [
                {"name": "Breadth", "axes": [
                    {"name": "Discipline", "signals": {"task_tool_calls": 50}},
                    {"name": "Orchestration", "signals": {"agent_runs": 200}},
                    {"name": "Tool command", "signals": {"toolsearch": 30}},
                ]},
                {"name": "Craft", "axes": [
                    {"name": "Verification", "signals": {"test_runs": 150, "review_skills": 20,
                                                         "knowledge_calls": 10}},
                ]},
            ]},
        }

    def test_rates_and_record(self):
        from gnomon.cli.local import tools_diagnostic
        lines, rec = tools_diagnostic(self._stats(100))
        self.assertEqual(rec["sessions"], 100)
        self.assertEqual(rec["rates"]["task_tool_calls"], 0.5)   # 50/100
        self.assertEqual(rec["rates"]["agent_runs"], 2.0)        # 200/100
        self.assertEqual(rec["rates"]["toolsearch_calls"], 0.3)  # 30/100
        self.assertEqual(rec["counts"]["review_skills"], 20)
        self.assertTrue(any("task_tool_calls" in l for l in lines))

    def test_zero_sessions_no_crash(self):
        from gnomon.cli.local import tools_diagnostic
        lines, rec = tools_diagnostic({"volume": {"total_sessions": 0}, "agentic": {"pillars": []}})
        self.assertEqual(rec["sessions"], 0)
        self.assertEqual(rec["rates"]["task_tool_calls"], 0.0)


class TestAggregateKnowledgeServerUnion(unittest.TestCase):
    """Aggregate knowledge_servers is the UNION of distinct server names across sources, not
    max(count) (which undercounts) and not sum (which double-counts a shared server)."""

    @staticmethod
    def _synth(*name_lists):
        from gnomon.scoring.aggregate import _synth_stats_for_aggregate
        items = [(f"src{i}", {"weight": 100, "block": {"tools": {
            "mcp_knowledge_server_names": names, "mcp_knowledge_servers": len(names)}}})
            for i, names in enumerate(name_lists)]
        return _synth_stats_for_aggregate(items, {})

    def test_distinct_servers_across_sources_union(self):
        # CodeGraph in one source, Context7 in another -> 2 distinct, not max(1,1)=1
        synth = self._synth(["codegraph"], ["context7"])
        self.assertEqual(synth["tools"]["mcp_knowledge_servers"], 2)

    def test_same_server_across_sources_not_double_counted(self):
        # same server in both sources -> 1, not sum=2
        synth = self._synth(["codegraph"], ["codegraph"])
        self.assertEqual(synth["tools"]["mcp_knowledge_servers"], 1)

    def test_mixed_names_and_legacy_count_combined_per_source(self):
        # One source has NAMES (['codegraph','context7']=2), a sibling legacy block has
        # only the COUNT (mcp_knowledge_servers=5, no names). Per-source combine: union
        # the 2 named + add the 5 legacy count = 7. The old GLOBAL `any(names)` guard took
        # the union branch and silently DROPPED the legacy block's 5 (contribution -> 0).
        from gnomon.scoring.aggregate import _synth_stats_for_aggregate
        items = [("a", {"weight": 100, "block": {"tools": {
                    "mcp_knowledge_server_names": ["codegraph", "context7"],
                    "mcp_knowledge_servers": 2}}}),
                 ("b", {"weight": 100, "block": {"tools": {"mcp_knowledge_servers": 5}}})]
        synth = _synth_stats_for_aggregate(items, {})
        self.assertEqual(synth["tools"]["mcp_knowledge_servers"], 7)

    def test_fallback_to_summed_counts_when_names_absent(self):
        # No block has names -> best-effort sum of the raw counts (can't dedup a count).
        from gnomon.scoring.aggregate import _synth_stats_for_aggregate
        items = [("a", {"weight": 100, "block": {"tools": {"mcp_knowledge_servers": 2}}}),
                 ("b", {"weight": 100, "block": {"tools": {"mcp_knowledge_servers": 3}}})]
        synth = _synth_stats_for_aggregate(items, {})
        self.assertEqual(synth["tools"]["mcp_knowledge_servers"], 5)

    def test_empty_items_no_crash(self):
        from gnomon.scoring.aggregate import _synth_stats_for_aggregate
        synth = _synth_stats_for_aggregate([], {})
        self.assertEqual(synth["tools"]["mcp_knowledge_servers"], 0)
        self.assertEqual(synth["tools"]["mcp_grounded_sessions"], 0)


class TestAggregateGroundedSessionUnion(unittest.TestCase):
    """Aggregate mcp_grounded_sessions is the UNION of grounded session IDs across
    sources (not a sum, which would double-count a session appearing in two source
    exports), while total_sessions stays the existing SUMMED denominator."""

    @staticmethod
    def _synth(name_lists, total_sessions_each=None):
        from gnomon.scoring.aggregate import _synth_stats_for_aggregate
        total_sessions_each = total_sessions_each or [10] * len(name_lists)
        items = [(f"src{i}", {"weight": 100, "block": {
            "tools": {"mcp_grounded_session_names": names,
                     "mcp_grounded_sessions": len(names)},
            "volume": {"total_sessions": ts},
        }}) for i, (names, ts) in enumerate(zip(name_lists, total_sessions_each))]
        return _synth_stats_for_aggregate(items, {})

    def test_same_session_across_sources_counted_once(self):
        synth = self._synth([["s1", "s2"], ["s1", "s3"]])
        self.assertEqual(synth["tools"]["mcp_grounded_sessions"], 3)  # s1,s2,s3 union

    def test_distinct_sessions_across_sources_both_counted(self):
        synth = self._synth([["x"], ["y"]])
        self.assertEqual(synth["tools"]["mcp_grounded_sessions"], 2)

    def test_total_sessions_stays_summed_denominator(self):
        synth = self._synth([["s1"], ["s2"]], total_sessions_each=[10, 15])
        self.assertEqual(synth["volume"]["total_sessions"], 25)

    def test_fallback_to_wsum_when_names_absent(self):
        from gnomon.scoring.aggregate import _synth_stats_for_aggregate
        items = [("a", {"weight": 100, "block": {"tools": {"mcp_grounded_sessions": 2},
                                                 "volume": {"total_sessions": 10}}}),
                 ("b", {"weight": 100, "block": {"tools": {"mcp_grounded_sessions": 3},
                                                 "volume": {"total_sessions": 10}}})]
        synth = _synth_stats_for_aggregate(items, {})
        self.assertEqual(synth["tools"]["mcp_grounded_sessions"], 5)  # summed counts fallback

    def test_mixed_names_and_legacy_count_combined_per_source(self):
        # One source has NAMES (['s1','s2']=2), a sibling legacy block has only the COUNT
        # (mcp_grounded_sessions=5, no names). Per-source combine: union the 2 named + add
        # the 5 legacy count = 7. The old GLOBAL `any(names)` guard took the union branch
        # and silently DROPPED the legacy block's 5.
        from gnomon.scoring.aggregate import _synth_stats_for_aggregate
        items = [("a", {"weight": 100, "block": {
                    "tools": {"mcp_grounded_session_names": ["s1", "s2"],
                              "mcp_grounded_sessions": 2},
                    "volume": {"total_sessions": 10}}}),
                 ("b", {"weight": 100, "block": {
                    "tools": {"mcp_grounded_sessions": 5},
                    "volume": {"total_sessions": 10}}})]
        synth = _synth_stats_for_aggregate(items, {})
        self.assertEqual(synth["tools"]["mcp_grounded_sessions"], 7)


if __name__ == "__main__":
    unittest.main()
