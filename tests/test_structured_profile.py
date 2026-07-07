"""Tests for structured growth_edges / signature_moves helpers introduced in the
feat-janus-supabase-sync task.

Structure:
  1. Characterization / golden tests  – byte-identical output from the HTML-facing
     growth_edges() and signature_moves() functions after the pool-helper refactor.
  2. Pool helpers  – _growth_edges_pool and _signature_moves_pool return dicts.
  3. Strip / command helpers  – _strip_html, _commands_in.
  4. Structured emitters  – growth_edges_structured, signature_moves_structured.
  5. Profile integration  – _build_profile and build_summary carry the new keys.
  6. Empty/zero corpus  – defensive path (no crash, well-formed dict).
"""
import os
import sys
import re
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import paxel


# ---------------------------------------------------------------------------
# Shared fixture builders
# ---------------------------------------------------------------------------

def _make_aq(models=None, fanout=1, planning_ratio=0.2):
    """Build an AQ block via compute_aq so signal values are realistic."""
    if models is None:
        models = [("claude-opus-4-7", 5000), ("claude-haiku-4-5", 1000)]
    return paxel.compute_aq({
        "tools": {
            "tool_diversity": 50, "tool_entropy_normalized": 0.5,
            "mcp_calls": 200, "mcp_servers_distinct": 5,
            "clis_distinct": 20, "cli_calls": 1000,
            "toolsearch_calls": 100, "task_tool_calls": 400, "agent_calls": 80,
        },
        "stack": {
            "skills_distinct": 15, "skills_total": 500, "subagent_types_distinct": 3,
            "subagent_types": [("general-purpose", 50)],
            "top_skills": [("code-review", 80), ("superpowers:writing-plans", 60),
                           ("tdd", 40), ("brainstorm", 30)],
            "skills_all": [("code-review", 80), ("superpowers:writing-plans", 60),
                           ("tdd", 40), ("brainstorm", 30)],
            "compounding_writes": 12,
            "models": models,
        },
        "behavior": {
            "fanout_median": fanout, "shell_test_runs": 50, "actions_per_prompt": 10,
            "error_recovery_ratio": 0.9, "api_errors_retries": 5,
            "planning_ratio_explore_to_doing": planning_ratio,
        },
    })


def _rich_stats():
    """Fixture that fires multiple growth_edges AND multiple signature_moves.

    Specifically wired to hit:
      - growth_edge "Stop the grind" (high iteration + high error rate)
      - two AQ-driven edges (Model mix thin, Grounding thin)
      - signature_moves: Review, Plan, Think
    """
    aq = _make_aq(models=[("claude-opus-4-7", 5000)], fanout=1, planning_ratio=0.2)
    return {
        "corpus": {
            "date_range": ["2026-01-01", "2026-06-01"], "sources": {"claude": {}},
            "files_parsed": 20, "lines_total": 5000, "lines_unparseable": 0,
            "span_days": 150, "active_days": 60,
            "timezone": "UTC (UTC+00:00)", "antigravity_experimental": {},
        },
        "volume": {
            "total_sessions": 10, "total_prompts": 300,
            "command_invocations": 10, "avg_prompt_length_chars": 120.0,
            "median_prompt_length_chars": 80.0, "assistant_turns": 500,
            "tool_calls_total": 5000, "thinking_blocks": 80,
        },
        "tools": {
            "tool_diversity": 50, "tool_entropy_normalized": 0.5,
            "mcp_calls": 200, "native_calls": 800, "mcp_share": 0.2,
            "top_tools": [("Bash", 500), ("Read", 300)], "category_breakdown": {},
            "mcp_servers": [], "mcp_servers_distinct": 5,
            "clis": [], "clis_distinct": 20, "cli_calls": 1000,
            "toolsearch_calls": 100, "task_tool_calls": 400, "agent_calls": 80,
        },
        "velocity": {
            "git_churn_total": 8000, "git_insertions": 6000, "git_deletions": 2000,
            "git_commits_real": 50, "git_velocity_lines_per_hour": 100.0,
            "git_repos_with_commits": 3, "git_repos_seen": 4, "git_per_repo": [],
            "tool_churn_edit_write": 10000, "tool_lines_added": 7000,
            "tool_lines_removed": 3000, "tool_velocity_lines_per_hour": 150.0,
            "shell_write_calls": 20, "shell_authored_lines_est": 500,
            "active_hours": 40.0, "git_commits_grep": 50,
        },
        "behavior": {
            "planning_ratio_explore_to_doing": 0.2, "explore_actions": 200,
            "produce_actions": 80, "execute_actions": 100, "delegate_actions": 30,
            "avg_session_minutes": 45.0, "median_session_minutes": 40.0,
            "longest_run_minutes": 120.0, "polite_prompts": 5,
            "error_recovery_ratio": 0.9, "error_rate_per_100_tools": 7.0,
            "tool_errors": 125, "recovered_errors": 112, "api_errors_retries": 5,
            "fanout_median": 1, "iteration_depth_mean": 3.5,
            "iteration_depth_median": 3.0, "iteration_depth_p90": 7,
            "iteration_depth_max": 50, "files_hammered_over_15x": 15,
            "actions_per_prompt": 10.0, "questions_asked": 15,
            "background_tasks": 10, "scheduled_actions": 2, "shell_test_runs": 50,
            "plan_sessions": 8,
        },
        "rhythm": {
            "hour_histogram_local": {str(h): 0 for h in range(24)},
            "weekday_histogram": {}, "peak_hours_local": [], "preferred_days": [],
        },
        "progression": {"monthly": []},
        "stack": {
            "models": [("claude-opus-4-7", 5000)],
            "top_skills": [("code-review", 80), ("superpowers:writing-plans", 60),
                           ("tdd", 40), ("brainstorm", 30)],
            "skills_distinct": 15, "skills_total": 500, "subagent_types_distinct": 3,
            "skills_all": [("code-review", 80), ("superpowers:writing-plans", 60),
                           ("tdd", 40), ("brainstorm", 30)],
            "compounding_writes": 12,
            "subagent_types": [("general-purpose", 50)],
            "top_projects": [],
        },
        "autonomy": {
            "autonomy_score_0_100": 50,
            "components": {
                "actions_per_prompt": 22.0, "delegation": 30.0,
                "scheduling_background": 5.0, "low_question_rate": 10.0,
            },
        },
        "agentic": aq,
    }


def _arch_scores(stats):
    sb = paxel.score_breakdown(stats)
    return {
        "Execution": sb["execution"]["value"],
        "Planning": sb["planning"]["value"],
        "Engineering": sb["engineering"]["value"],
    }


def _zero_stats():
    """Zero-activity stats — tests the defensive empty-corpus path."""
    from tests.test_gnomon import _zero_stats as _z
    return _z()


# ---------------------------------------------------------------------------
# 1. Characterization / golden tests
# ---------------------------------------------------------------------------

class TestGoldenHtmlOutput(unittest.TestCase):
    """Byte-identical output guard: the HTML-facing functions must not change after refactor."""

    def setUp(self):
        self.stats = _rich_stats()
        self.scores = _arch_scores(self.stats)

    def test_signature_moves_golden(self):
        moves = paxel.signature_moves(self.stats)
        self.assertEqual(len(moves), 3)
        # First move: Review
        tag, title, ev = moves[0]
        self.assertEqual(tag, "Review")
        self.assertEqual(title, "You review more than you write")
        self.assertIn("<b>80</b>", ev)
        self.assertIn("code-review passes", ev)
        # Second move: Plan
        tag2, title2, ev2 = moves[1]
        self.assertEqual(tag2, "Plan")
        self.assertEqual(title2, "You write the plan before the code")
        self.assertIn("sessions with a plan", ev2)
        # Third move: Think
        tag3, title3, ev3 = moves[2]
        self.assertEqual(tag3, "Think")
        self.assertEqual(title3, "You think before you touch the diff")
        self.assertIn("<b>80</b>", ev3)
        self.assertIn("reasoning blocks", ev3)

    def test_signature_moves_full_equality(self):
        """Full tuple equality guard — pins every character of each HTML string."""
        moves = paxel.signature_moves(self.stats)
        expected = [
            (
                "Review",
                "You review more than you write",
                "<b>80</b> code-review passes — one of your most-used skills."
                " You don't trust a diff until a second set of eyes has seen it.",
            ),
            (
                "Plan",
                "You write the plan before the code",
                "You opened <b>8</b> of 10 sessions with a plan — you scaffold the"
                " decision before the implementation, gstack-style.",
            ),
            (
                "Think",
                "You think before you touch the diff",
                "<b>80</b> reasoning blocks (~8/session) before edits land —"
                " you deliberate hard, then commit.",
            ),
        ]
        self.assertEqual(moves, expected)

    def test_growth_edges_golden(self):
        edges = paxel.growth_edges(self.stats, self.scores)
        self.assertEqual(len(edges), 3)
        # First edge (lowest priority): grind / iteration
        eyebrow0, title0, adv0 = edges[0]
        self.assertEqual(eyebrow0, "Stop the grind")
        self.assertIn("/investigate", adv0)
        # Remaining two are AQ-driven
        adv_texts = [adv for _, _, adv in edges[1:]]
        aq_axes_mentioned = any("Model mix" in a or "Grounding" in a or "Context Intelligence" in a for a in adv_texts)
        self.assertTrue(aq_axes_mentioned, adv_texts)

    def test_growth_edges_full_equality(self):
        """Full tuple equality guard — pins every character of each HTML string."""
        edges = paxel.growth_edges(self.stats, self.scores)
        expected = [
            (
                "Stop the grind",
                "When a file fights back, root-cause it",
                "<b>50×</b> on one file and <b>15</b> files past 15 edits,"
                " next to ~<b>7.0</b> errors per 100 tool calls — that pairing"
                " reads as retry-thrash more than deliberate iteration. When a file"
                " resists past ~15 tries, find the root cause before the next edit."
                " (gstack names this <code>/investigate</code>.)",
            ),
            (
                "Ground your work in knowledge tools",
                "Wire codegraph, memory, and docs into your workflow",
                "<b>Craft · Context Intelligence</b> is your thinnest AQ signal."
                " <b>0</b> knowledge-tool calls across <b>0</b> server(s)."
                " Connect a code graph, a memory layer, and a docs server so the"
                " agent reads indexed context instead of grepping from scratch"
                " each session.",
            ),
            (
                "Route the work",
                "Match the model to the task",
                "<b>Savvy · Model mix</b> is your thinnest AQ signal."
                " <b>1</b> model(s), with only <b>0%</b> of turns routed off your"
                " default. Send mechanical work — renames, bulk edits, summaries"
                " — to a faster model and save the heavyweight for design and review.",
            ),
        ]
        self.assertEqual(edges, expected)

    def test_growth_edges_tuple_shape(self):
        edges = paxel.growth_edges(self.stats, self.scores)
        for item in edges:
            self.assertEqual(len(item), 3, item)
            eyebrow, title, adv = item
            self.assertIsInstance(eyebrow, str)
            self.assertIsInstance(title, str)
            self.assertIsInstance(adv, str)

    def test_signature_moves_tuple_shape(self):
        moves = paxel.signature_moves(self.stats)
        for item in moves:
            self.assertEqual(len(item), 3, item)
            tag, title, ev = item
            self.assertIsInstance(tag, str)
            self.assertIsInstance(title, str)
            self.assertIsInstance(ev, str)


# ---------------------------------------------------------------------------
# 2. Pool helpers
# ---------------------------------------------------------------------------

class TestGrowthEdgesPool(unittest.TestCase):
    def setUp(self):
        self.stats = _rich_stats()
        self.scores = _arch_scores(self.stats)

    def test_returns_list_of_dicts(self):
        pool = paxel._growth_edges_pool(self.stats, self.scores)
        self.assertIsInstance(pool, list)
        for item in pool:
            self.assertIsInstance(item, dict)

    def test_required_keys_present(self):
        pool = paxel._growth_edges_pool(self.stats, self.scores)
        for item in pool:
            for key in ("priority", "eyebrow", "title", "advice_html", "axis"):
                self.assertIn(key, item, f"missing key '{key}' in {item}")

    def test_max_three_items(self):
        pool = paxel._growth_edges_pool(self.stats, self.scores)
        self.assertLessEqual(len(pool), 3)

    def test_sorted_by_priority_asc(self):
        pool = paxel._growth_edges_pool(self.stats, self.scores)
        priorities = [item["priority"] for item in pool]
        self.assertEqual(priorities, sorted(priorities))

    def test_aq_edge_has_axis_set(self):
        pool = paxel._growth_edges_pool(self.stats, self.scores)
        aq_items = [item for item in pool if item["axis"] is not None]
        self.assertTrue(len(aq_items) >= 1, "Expected at least one AQ-driven edge with axis set")
        for item in aq_items:
            self.assertIsInstance(item["axis"], str)
            self.assertGreater(len(item["axis"]), 0)

    def test_non_aq_edge_has_axis_none(self):
        pool = paxel._growth_edges_pool(self.stats, self.scores)
        non_aq = [item for item in pool if item["eyebrow"] == "Stop the grind"]
        self.assertTrue(len(non_aq) >= 1, "Expected 'Stop the grind' edge in pool")
        self.assertIsNone(non_aq[0]["axis"])


class TestSignatureMovesPool(unittest.TestCase):
    def setUp(self):
        self.stats = _rich_stats()

    def test_returns_list_of_dicts(self):
        pool = paxel._signature_moves_pool(self.stats)
        self.assertIsInstance(pool, list)
        for item in pool:
            self.assertIsInstance(item, dict)

    def test_required_keys_present(self):
        pool = paxel._signature_moves_pool(self.stats)
        for item in pool:
            for key in ("tag", "title", "evidence_html"):
                self.assertIn(key, item, f"missing key '{key}' in {item}")

    def test_max_five_items(self):
        pool = paxel._signature_moves_pool(self.stats)
        self.assertLessEqual(len(pool), 5)


# ---------------------------------------------------------------------------
# 3. _strip_html and _commands_in
# ---------------------------------------------------------------------------

class TestStripHtml(unittest.TestCase):
    def test_removes_bold_tags(self):
        self.assertEqual(paxel._strip_html("<b>hello</b> world"), "hello world")

    def test_removes_italic_tags(self):
        self.assertEqual(paxel._strip_html("<i>note</i>"), "note")

    def test_removes_code_tags(self):
        self.assertEqual(paxel._strip_html("<code>/qa</code>"), "/qa")

    def test_unescapes_amp(self):
        self.assertEqual(paxel._strip_html("planning &amp; brainstorming"), "planning & brainstorming")

    def test_unescapes_lt_gt(self):
        self.assertEqual(paxel._strip_html("a &lt;b&gt; c"), "a <b> c")

    def test_unescapes_quot(self):
        self.assertEqual(paxel._strip_html("say &quot;hi&quot;"), 'say "hi"')

    def test_unescapes_apos_numeric(self):
        self.assertEqual(paxel._strip_html("it&#39;s"), "it's")

    def test_collapses_whitespace(self):
        self.assertEqual(paxel._strip_html("a   b  c"), "a b c")

    def test_empty_string(self):
        self.assertEqual(paxel._strip_html(""), "")

    def test_no_tags(self):
        self.assertEqual(paxel._strip_html("plain text"), "plain text")

    def test_nested_tags_stripped(self):
        result = paxel._strip_html("<b><i>deep</i></b> text")
        self.assertEqual(result, "deep text")


class TestCommandsIn(unittest.TestCase):
    def test_single_slash_command(self):
        html = "gstack&#39;s <code>/qa</code> does this."
        self.assertEqual(paxel._commands_in(html), ["/qa"])

    def test_multiple_commands(self):
        html = "use <code>/office-hours</code> + <code>/autoplan</code>."
        self.assertEqual(paxel._commands_in(html), ["/office-hours", "/autoplan"])

    def test_deduplication(self):
        html = "<code>/qa</code> and again <code>/qa</code>"
        self.assertEqual(paxel._commands_in(html), ["/qa"])

    def test_preserves_order(self):
        html = "<code>/retro</code> before <code>/qa</code>"
        self.assertEqual(paxel._commands_in(html), ["/retro", "/qa"])

    def test_ignores_non_slash_code(self):
        html = "<code>pytest</code> and <code>go test</code>"
        self.assertEqual(paxel._commands_in(html), [])

    def test_empty_string(self):
        self.assertEqual(paxel._commands_in(""), [])


# ---------------------------------------------------------------------------
# 4. Structured emitters
# ---------------------------------------------------------------------------

class TestGrowthEdgesStructured(unittest.TestCase):
    def setUp(self):
        self.stats = _rich_stats()
        self.scores = _arch_scores(self.stats)
        self.structured = paxel.growth_edges_structured(self.stats, self.scores)

    def test_returns_list(self):
        self.assertIsInstance(self.structured, list)

    def test_max_three_items(self):
        self.assertLessEqual(len(self.structured), 3)

    def test_required_keys_per_item(self):
        for item in self.structured:
            for key in ("eyebrow", "title", "advice", "commands", "axis", "severity"):
                self.assertIn(key, item, f"missing '{key}' in {item}")

    def test_advice_has_no_html_tags(self):
        for item in self.structured:
            self.assertNotRegex(item["advice"], r"<[^>]+>",
                                f"HTML tag found in advice: {item['advice']!r}")

    def test_commands_is_list_of_strings(self):
        for item in self.structured:
            self.assertIsInstance(item["commands"], list)
            for cmd in item["commands"]:
                self.assertIsInstance(cmd, str)

    def test_investigate_edge_has_commands(self):
        grind = next((i for i in self.structured if i["eyebrow"] == "Stop the grind"), None)
        self.assertIsNotNone(grind, "Expected 'Stop the grind' edge")
        self.assertIn("/investigate", grind["commands"])

    def test_aq_edge_axis_is_string(self):
        aq_items = [i for i in self.structured if i["axis"] is not None]
        self.assertTrue(len(aq_items) >= 1)
        for item in aq_items:
            self.assertIsInstance(item["axis"], str)

    def test_non_aq_edge_axis_is_none(self):
        grind = next((i for i in self.structured if i["eyebrow"] == "Stop the grind"), None)
        if grind:
            self.assertIsNone(grind["axis"])

    def test_severity_values_valid(self):
        valid = {"high", "medium", "low"}
        for item in self.structured:
            self.assertIn(item["severity"], valid, item)

    def test_severity_bucketing(self):
        # priority < 2 -> high; < 5 -> medium; >= 5 -> low
        pool = paxel._growth_edges_pool(self.stats, self.scores)
        structured = paxel.growth_edges_structured(self.stats, self.scores)
        for pool_item, struct_item in zip(pool, structured):
            p = pool_item["priority"]
            expected = "high" if p < 2 else ("medium" if p < 5 else "low")
            self.assertEqual(struct_item["severity"], expected, f"priority={p}")

    def test_planning_edge_has_office_hours_and_autoplan(self):
        # Fire a planning edge by using a very low Planning score.
        from tests.test_gnomon import _full_stats
        s = _full_stats()
        sb = paxel.score_breakdown(s)
        sc = {
            "Execution": sb["execution"]["value"],
            "Planning": 2.0,   # force the Planning edge
            "Engineering": sb["engineering"]["value"],
        }
        structured = paxel.growth_edges_structured(s, sc)
        plan_edge = next((i for i in structured if i["eyebrow"] == "Plan first"), None)
        self.assertIsNotNone(plan_edge, "Expected 'Plan first' edge with Planning=2.0")
        self.assertIn("/office-hours", plan_edge["commands"])
        self.assertIn("/autoplan", plan_edge["commands"])

    def test_review_test_edge_has_qa_command(self):
        # Fire the review/test edge: many reviews, few tests.
        from tests.test_gnomon import _full_stats
        s = _full_stats()
        # Crank up code-review and zero out test runs
        s["stack"]["top_skills"] = [("code-review", 200), ("superpowers:writing-plans", 60)]
        s["stack"]["skills_all"] = s["stack"]["top_skills"]
        s["behavior"]["shell_test_runs"] = 0
        sb = paxel.score_breakdown(s)
        sc = {
            "Execution": sb["execution"]["value"],
            "Planning": sb["planning"]["value"],
            "Engineering": sb["engineering"]["value"],
        }
        structured = paxel.growth_edges_structured(s, sc)
        reflex_edge = next((i for i in structured if "reflex" in i["eyebrow"].lower()), None)
        self.assertIsNotNone(reflex_edge, f"Expected review/test edge; got {structured}")
        self.assertIn("/qa", reflex_edge["commands"])

    def test_planning_review_skills_do_not_trigger_review_reflex_edge(self):
        from tests.test_gnomon import _full_stats
        s = _full_stats()
        s["stack"]["top_skills"] = [("plan-eng-review", 200), ("superpowers:writing-plans", 60)]
        s["stack"]["skills_all"] = s["stack"]["top_skills"]
        s["behavior"]["shell_test_runs"] = 0
        sb = paxel.score_breakdown(s)
        sc = {
            "Execution": sb["execution"]["value"],
            "Planning": sb["planning"]["value"],
            "Engineering": sb["engineering"]["value"],
        }
        structured = paxel.growth_edges_structured(s, sc)
        reflex_edge = next((i for i in structured if "reflex" in i["eyebrow"].lower()), None)
        self.assertIsNone(reflex_edge, structured)


class TestSignatureMovesStructured(unittest.TestCase):
    def setUp(self):
        self.stats = _rich_stats()
        self.structured = paxel.signature_moves_structured(self.stats)

    def test_returns_list(self):
        self.assertIsInstance(self.structured, list)

    def test_max_five_items(self):
        self.assertLessEqual(len(self.structured), 5)

    def test_required_keys_per_item(self):
        for item in self.structured:
            for key in ("tag", "title", "evidence"):
                self.assertIn(key, item, f"missing '{key}' in {item}")

    def test_evidence_has_no_html_tags(self):
        for item in self.structured:
            self.assertNotRegex(item["evidence"], r"<[^>]+>",
                                f"HTML tag found in evidence: {item['evidence']!r}")

    def test_amp_unescaped_in_evidence(self):
        # Structured evidence is plain text — HTML entities must be unescaped, never
        # leaked raw. Exercise the unescape path on a fired badge whose evidence
        # literally contains "&amp;": the "Build" signature move ("delegated &amp;
        # backgrounded agent runs"). Its gate needs delegate_actions + background_tasks
        # >= 100 AND >= prompts * 0.3, so bump delegate_actions on a fresh copy (don't
        # mutate module-level _rich_stats — other golden tests need Build NOT firing).
        stats = _rich_stats()
        stats["behavior"]["delegate_actions"] = 120
        structured = paxel.signature_moves_structured(stats)
        build = next((i for i in structured if i["tag"] == "Build"), None)
        self.assertIsNotNone(build, f"Expected 'Build' move to fire; got {structured}")
        self.assertIn("&", build["evidence"])
        self.assertNotIn("&amp;", build["evidence"])
        # And the invariant holds for every item, not just Build.
        for item in structured:
            self.assertNotIn("&amp;", item["evidence"])

    def test_tag_and_title_are_strings(self):
        for item in self.structured:
            self.assertIsInstance(item["tag"], str)
            self.assertIsInstance(item["title"], str)


# ---------------------------------------------------------------------------
# 5. Profile integration (_build_profile + build_summary)
# ---------------------------------------------------------------------------

class TestBuildProfileStructuredKeys(unittest.TestCase):
    def setUp(self):
        self.stats = _rich_stats()
        self.profile = paxel._build_profile(self.stats)

    def test_growth_edges_present(self):
        self.assertIn("growth_edges", self.profile)

    def test_signature_moves_present(self):
        self.assertIn("signature_moves", self.profile)

    def test_existing_keys_preserved(self):
        for key in ("aq", "archetype", "scores", "steering"):
            self.assertIn(key, self.profile, f"existing key '{key}' disappeared")

    def test_growth_edges_is_list(self):
        self.assertIsInstance(self.profile["growth_edges"], list)

    def test_signature_moves_is_list(self):
        self.assertIsInstance(self.profile["signature_moves"], list)

    def test_aq_pillars_have_axes_with_signals(self):
        aq = self.profile["aq"]
        self.assertIn("pillars", aq)
        for pillar in aq["pillars"]:
            for axis in pillar["axes"]:
                self.assertIn("signals", axis,
                              f"signals missing on axis {axis.get('name')!r}")

    def test_growth_edges_items_have_no_html(self):
        for item in self.profile["growth_edges"]:
            self.assertNotRegex(item.get("advice", ""), r"<[^>]+>")

    def test_signature_moves_items_have_no_html(self):
        for item in self.profile["signature_moves"]:
            self.assertNotRegex(item.get("evidence", ""), r"<[^>]+>")


class TestBuildSummaryStructuredIntegration(unittest.TestCase):
    def setUp(self):
        self.stats = _rich_stats()
        self.summary = paxel.build_summary(self.stats)

    def test_profile_has_growth_edges(self):
        self.assertIn("growth_edges", self.summary["profile"])

    def test_profile_has_signature_moves(self):
        self.assertIn("signature_moves", self.summary["profile"])

    def test_no_pii_in_summary(self):
        import json
        raw = json.dumps(self.summary).lower()
        for banned in ("top_skills", "prompt_text", "skill_name"):
            self.assertNotIn(banned, raw, f"forbidden field leaked: {banned!r}")

    def test_advice_contains_no_raw_html_tags(self):
        import json
        # The entire serialised summary must not contain HTML open/close tags
        # in the structured advice/evidence fields.
        for item in self.summary["profile"]["growth_edges"]:
            self.assertNotIn("<b>", item.get("advice", ""))
            self.assertNotIn("<i>", item.get("advice", ""))
        for item in self.summary["profile"]["signature_moves"]:
            self.assertNotIn("<b>", item.get("evidence", ""))

    def test_original_profile_keys_still_present(self):
        prof = self.summary["profile"]
        for key in ("aq", "archetype", "scores", "steering"):
            self.assertIn(key, prof)

    def test_profile_scores_carry_narrative_fields(self):
        """Axis-level narrative fields must propagate through build_summary -> profile -> scores."""
        scores = self.summary["profile"]["scores"]
        valid_verdicts = {"excellent", "good", "adequate", "weak", "poor"}
        for axis in ("execution", "planning", "engineering"):
            d = scores[axis]
            ctx = f"profile/{axis}"
            self.assertIn(d["axis_verdict"], valid_verdicts, ctx)
            self.assertIsInstance(d["score_out_of_10"], str, ctx)
            self.assertIn("/", d["score_out_of_10"], ctx)
            self.assertIsInstance(d["drag_narrative"], str, ctx)
            self.assertGreater(len(d["drag_narrative"]), 0, ctx)
            self.assertIsInstance(d["axis_narrative"], str, ctx)
            self.assertIn(axis.capitalize(), d["axis_narrative"], ctx)


# ---------------------------------------------------------------------------
# 6. Empty / zero-activity corpus
# ---------------------------------------------------------------------------

class TestEmptyCorpusProfile(unittest.TestCase):
    def _zero_stats(self):
        from tests.test_gnomon import _zero_stats
        return _zero_stats()

    def test_build_profile_does_not_raise(self):
        stats = self._zero_stats()
        profile = paxel._build_profile(stats)
        self.assertIsInstance(profile, dict)

    def test_profile_has_required_keys(self):
        profile = paxel._build_profile(self._zero_stats())
        for key in ("aq", "archetype", "scores", "steering", "growth_edges", "signature_moves",
                    "model_usage"):
            self.assertIn(key, profile)

    def test_growth_edges_non_empty_fallback(self):
        # Even with zero activity the fallback "Go deeper"/"balanced" fires.
        profile = paxel._build_profile(self._zero_stats())
        edges = profile["growth_edges"]
        self.assertGreater(len(edges), 0, "Expected at least the fallback growth edge")

    def test_growth_edges_items_valid_shape(self):
        profile = paxel._build_profile(self._zero_stats())
        for item in profile["growth_edges"]:
            for key in ("eyebrow", "title", "advice", "commands", "axis", "severity"):
                self.assertIn(key, item)

    def test_signature_moves_is_list(self):
        profile = paxel._build_profile(self._zero_stats())
        self.assertIsInstance(profile["signature_moves"], list)


# ---------------------------------------------------------------------------
# 7. model_usage in profile payload
# ---------------------------------------------------------------------------

class TestModelUsageInProfile(unittest.TestCase):
    """model_usage is present, well-formed, sorted, and PII-free."""

    def _stats_with_models(self, models):
        """Return a minimal stats dict with the given models list."""
        s = _rich_stats()
        s["stack"]["models"] = models
        return s

    # --- presence and shape ---

    def test_model_usage_present_in_profile(self):
        profile = paxel._build_profile(self._stats_with_models(
            [("claude-opus-4-7", 550), ("gemini-2-0-flash", 300), ("claude-sonnet-4-5", 150)]
        ))
        self.assertIn("model_usage", profile)

    def test_model_usage_present_in_build_summary(self):
        summary = paxel.build_summary(self._stats_with_models(
            [("claude-opus-4-7", 550), ("claude-haiku-4-5", 450)]
        ))
        self.assertIn("model_usage", summary["profile"])

    def test_each_entry_has_model_count_pct(self):
        profile = paxel._build_profile(self._stats_with_models(
            [("claude-opus-4-7", 800), ("claude-sonnet-4-5", 200)]
        ))
        for entry in profile["model_usage"]:
            self.assertIn("model", entry)
            self.assertIn("count", entry)
            self.assertIn("pct", entry)

    # --- pretty display names ---

    def test_model_names_are_pretty(self):
        profile = paxel._build_profile(self._stats_with_models(
            [("claude-opus-4-7", 500), ("claude-haiku-4-5", 300), ("claude-sonnet-4-5", 200)]
        ))
        names = [e["model"] for e in profile["model_usage"]]
        self.assertIn("Opus 4.7", names)
        self.assertIn("Haiku 4.5", names)
        self.assertIn("Sonnet 4.5", names)
        # raw model ids must not appear
        for entry in profile["model_usage"]:
            self.assertNotIn("claude-", entry["model"])

    def test_pretty_model_claude_unchanged(self):
        """Claude labels must stay byte-identical to the original formatting."""
        self.assertEqual(paxel._pretty_model("claude-opus-4-7"), "Opus 4.7")
        self.assertEqual(paxel._pretty_model("claude-haiku-4-5"), "Haiku 4.5")
        self.assertEqual(paxel._pretty_model("claude-3-5-sonnet-20241022"), "Sonnet 3.5")
        self.assertEqual(paxel._pretty_model("claude-sonnet-4-5-20250101"), "Sonnet 4.5")

    def test_pretty_model_openai_dotted_versions_kept(self):
        """OpenAI versions carry the version in one dotted token — it must survive,
        and distinct GPT models must not collapse to a bare 'GPT'."""
        self.assertEqual(paxel._pretty_model("gpt-5.4"), "GPT 5.4")
        self.assertEqual(paxel._pretty_model("gpt-4.1"), "GPT 4.1")
        self.assertEqual(paxel._pretty_model("gpt-5-codex"), "GPT 5 Codex")
        self.assertNotEqual(paxel._pretty_model("gpt-5.4"), paxel._pretty_model("gpt-4.1"))

    def test_pretty_model_gemini_qualifier_kept(self):
        """Gemini dotted version + tier qualifier (pro/flash) must both show."""
        self.assertEqual(paxel._pretty_model("gemini-2.5-pro"), "Gemini 2.5 Pro")
        self.assertEqual(paxel._pretty_model("gemini-2.0-flash"), "Gemini 2.0 Flash")

    def test_pretty_model_distinct_gpt_variants_stay_distinct_in_profile(self):
        """Two different GPT raw ids must produce two distinct labels in model_usage."""
        profile = paxel._build_profile(self._stats_with_models(
            [("gpt-5.4", 70), ("gpt-4.1", 40)]
        ))
        names = [e["model"] for e in profile["model_usage"]]
        self.assertIn("GPT 5.4", names)
        self.assertIn("GPT 4.1", names)
        self.assertEqual(len(set(names)), len(names), "labels must be unique per raw id")

    # --- percentages ---

    def test_pct_sums_to_one(self):
        profile = paxel._build_profile(self._stats_with_models(
            [("claude-opus-4-7", 550), ("gemini-flash", 300), ("claude-sonnet-4-5", 150)]
        ))
        total_pct = sum(e["pct"] for e in profile["model_usage"])
        self.assertAlmostEqual(total_pct, 1.0, delta=0.01)

    def test_pct_single_model_is_one(self):
        profile = paxel._build_profile(self._stats_with_models(
            [("claude-opus-4-7", 1000)]
        ))
        self.assertEqual(profile["model_usage"][0]["pct"], 1.0)

    def test_pct_rounded_to_three_decimals(self):
        profile = paxel._build_profile(self._stats_with_models(
            [("claude-opus-4-7", 1), ("claude-haiku-4-5", 2)]
        ))
        for entry in profile["model_usage"]:
            # value should have at most 3 decimal places
            self.assertEqual(entry["pct"], round(entry["pct"], 3))

    # --- count type ---

    def test_count_is_int(self):
        profile = paxel._build_profile(self._stats_with_models(
            [("claude-opus-4-7", 100), ("claude-haiku-4-5", 50)]
        ))
        for entry in profile["model_usage"]:
            self.assertIsInstance(entry["count"], int)

    # --- ordering ---

    def test_sorted_desc_by_count(self):
        profile = paxel._build_profile(self._stats_with_models(
            [("claude-opus-4-7", 550), ("gemini-flash", 300), ("claude-haiku-4-5", 150)]
        ))
        counts = [e["count"] for e in profile["model_usage"]]
        self.assertEqual(counts, sorted(counts, reverse=True))

    # --- empty / zero guard ---

    def test_no_models_returns_empty_list(self):
        s = _rich_stats()
        s["stack"]["models"] = []
        profile = paxel._build_profile(s)
        self.assertEqual(profile["model_usage"], [])

    def test_zero_count_models_returns_empty_list(self):
        # If all counts are 0, total==0 → no division by zero, returns []
        s = _rich_stats()
        s["stack"]["models"] = [("claude-opus-4-7", 0)]
        profile = paxel._build_profile(s)
        self.assertEqual(profile["model_usage"], [])

    def test_missing_models_key_returns_empty_list(self):
        s = _rich_stats()
        del s["stack"]["models"]
        profile = paxel._build_profile(s)
        self.assertEqual(profile["model_usage"], [])

    def test_zero_corpus_model_usage_is_list(self):
        # _zero_stats still has models in the stack fixture, so model_usage is a list
        # (possibly non-empty). We just assert well-formedness, not emptiness.
        from tests.test_gnomon import _zero_stats
        profile = paxel._build_profile(_zero_stats())
        self.assertIsInstance(profile["model_usage"], list)
        for entry in profile["model_usage"]:
            self.assertIn("model", entry)
            self.assertIn("count", entry)
            self.assertIn("pct", entry)

    # --- payload cap ---

    def test_capped_at_12_entries(self):
        models = [(f"model-{i}", 100 - i) for i in range(20)]
        profile = paxel._build_profile(self._stats_with_models(models))
        self.assertLessEqual(len(profile["model_usage"]), 12)

    def test_small_list_not_truncated(self):
        models = [("claude-opus-4-7", 60), ("claude-haiku-4-5", 40)]
        profile = paxel._build_profile(self._stats_with_models(models))
        self.assertEqual(len(profile["model_usage"]), 2)

    # --- no PII ---

    def test_no_pii_leak_in_summary(self):
        import json
        summary = paxel.build_summary(self._stats_with_models(
            [("claude-opus-4-7", 550), ("claude-haiku-4-5", 450)]
        ))
        raw = json.dumps(summary).lower()
        for banned in ("top_skills", "prompt_text", "skill_name"):
            self.assertNotIn(banned, raw, f"forbidden field leaked: {banned!r}")


if __name__ == "__main__":
    unittest.main()
