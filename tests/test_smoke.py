"""Smoke + invariant tests for paxel.py — stdlib only (no pytest), so `python3 -m unittest`
runs them anywhere, matching the project's zero-dependency ethos.

Strategy: tiny committed transcript fixtures (one per source) live under tests/fixtures/.
We point paxel's source-directory globals at them, run the WHOLE pipeline end-to-end into a
temp dir, and assert it produces a valid profile without crashing. This is the safety net a
future source-parser PR self-verifies against (the gap we hit hand-reviewing PR #1).
"""
import os
import sys
import io
import json
import re
import glob
import shutil
import tempfile
import subprocess
import contextlib
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FIX = os.path.join(HERE, "fixtures")
sys.path.insert(0, ROOT)
import paxel  # noqa: E402

# Redirect every source-discovery global at the fixtures so the run is hermetic
# (never touches the developer's real ~/.claude, ~/.codex, etc.).
SRC_DIRS = dict(
    BASE=os.path.join(FIX, "claude"),
    CODEX_DIR=os.path.join(FIX, "codex"),
    GEMINI_DIR=os.path.join(FIX, "gemini"),
    ANTIGRAVITY_CLI_DIR=os.path.join(FIX, "antigravity"),
    ANTIGRAVITY_DB=os.path.join(FIX, "nope.vscdb"),
    PI_DIR=os.path.join(FIX, "pi"),
    OPENCODE_DIR=os.path.join(FIX, "opencode"),
    CURSOR_DIR=os.path.join(FIX, "cursor", "projects"),
    CURSOR_DB=os.path.join(FIX, "cursor", "state.vscdb"),
)
EXPECTED_SOURCES = {"claude", "codex", "gemini", "pi", "opencode", "cursor"}
EXPECTED_FMTS = EXPECTED_SOURCES - {"cursor"} | {"cursor-jsonl", "cursor-sqlite"}
SCORED_AXES = {"Execution", "Planning", "Engineering"}


def _run(testcase, args):
    """Run paxel.main() over the fixtures into a fresh temp OUT_DIR; return (stdout, out_dir).

    --no-open prevents browser windows from opening in CI.  Tests that want to
    exercise the share flow should call paxel.main() directly with a tailored argv.
    """
    out = tempfile.mkdtemp(prefix="paxel-test-")
    testcase.addCleanup(shutil.rmtree, out, ignore_errors=True)
    tern = os.path.join(ROOT, "tern.png")          # poster logo loads from OUT_DIR/tern.png
    if os.path.exists(tern):
        shutil.copy(tern, os.path.join(out, "tern.png"))
    # --no-open prevents browser windows in CI.
    argv = ["paxel.py"] + args + ["--no-open"]
    buf = io.StringIO()
    with mock.patch.multiple(paxel, OUT_DIR=out, **SRC_DIRS), \
            mock.patch.object(sys, "argv", argv), \
            contextlib.redirect_stdout(buf):
        paxel.main()
    return buf.getvalue(), out


class TestDiscovery(unittest.TestCase):
    def test_all_sources_discovered(self):
        with mock.patch.multiple(paxel, **SRC_DIRS):
            found = paxel.discover_sources(list(paxel.ALL_SOURCES))
        fmts = {fmt for _, _, fmt in found}
        self.assertEqual(fmts, EXPECTED_FMTS,
                         f"a source fixture stopped being discovered: got {fmts}")


class TestPipeline(unittest.TestCase):
    def test_all_sources_end_to_end(self):
        out_text, out = _run(self, [])               # no args = all sources
        prof = os.path.join(out, "profile.html")
        self.assertTrue(os.path.exists(prof), "profile.html was not written")
        with open(prof, encoding="utf-8") as fh:
            html = fh.read()
        self.assertIn("scorecard", html.lower())
        self.assertIn('class="steerread"', html, "Steering reading block missing")
        # stats.json must be valid JSON
        with open(os.path.join(out, "stats.json"), encoding="utf-8") as fh:
            json.load(fh)
        # the run reported real activity — sessions must be NON-ZERO, so a silent parser
        # regression (discovery works but parsing yields nothing) fails instead of false-greening
        self.assertRegex(out_text, r"sessions=[1-9]\d*")

    def test_each_source_runs_in_isolation(self):
        # A broken single parser should be pinpointed, not hidden behind the others.
        for src in sorted(EXPECTED_SOURCES):
            with self.subTest(source=src):
                _, out = _run(self, [src])
                self.assertTrue(os.path.exists(os.path.join(out, "profile.html")),
                                f"{src}-only run produced no profile")

    def test_profile_invariants(self):
        _, out = _run(self, [])
        with open(os.path.join(out, "profile.html"), encoding="utf-8") as fh:
            html = fh.read()
        # exactly the three scored axes render as bar rows
        for axis in SCORED_AXES:
            self.assertIn(f'<span class="name">{axis}</span>', html)
        # Steering is DESCRIBED, never a scored bar row
        self.assertNotIn('<span class="name">Steering</span>', html)
        # the article fix: no archetype should read "You're a The Architect"
        self.assertNotIn("You're a The ", html)
        # the poster's embedded CARD payload must be valid JSON (guards the _js() escaper)
        card_line = next((ln for ln in html.splitlines()
                          if ln.strip().startswith("var CARD=")), None)
        self.assertIsNotNone(card_line, "var CARD= line not found in profile.html")
        card_json = card_line.strip()[len("var CARD="):].rstrip(";")
        card = json.loads(card_json)
        self.assertEqual({s[0] for s in card["scores"]}, SCORED_AXES)
        self.assertIn("steering", card)              # described row present on the poster too

    def test_summary_flag(self):
        # --summary writes the shareable subset of docs/metrics-evaluation.md: the 8
        # measured metrics + monthly progression + profile + noticed_stats, and NOTHING
        # verbatim (prompts / quotes / skill names) — safe-to-share by construction.
        _, out = _run(self, ["--summary"])
        path = os.path.join(out, "summary.json")
        self.assertTrue(os.path.exists(path), "summary.json was not written")
        with open(path, encoding="utf-8") as fh:
            summary = json.load(fh)
        self.assertEqual(set(summary), {
            "context", "planning_ratio_explore_to_doing", "errors", "iteration_depth",
            "churn", "orchestration", "compounding_writes", "ecosystem",
            "progression_monthly", "noticed_stats_monthly", "profile",
            "scoring_inputs_version", "scoring_inputs_by_source",
        "profiles_by_source", "source_usage", "source_usage_monthly", "token_usage",
        "aq_version", "gstack_version", "score_contract_id", "comparison_policy",
            "timing"})
        # profile must have the expected sub-keys
        prof = summary["profile"]
        self.assertEqual(set(prof), {"aq", "archetype", "scores", "steering",
                                     "growth_edges", "signature_moves", "model_usage"})
        # no raw prompt/verbatim text in the shareable summary. NOTE: raw skill names
        # ARE now intentionally present (scoring_inputs_by_source carries top_skills /
        # skills_all as the cross-language parity contract), so "top_skills" is no longer
        # banned — only verbatim PROMPT text is.
        raw = json.dumps(summary).lower()
        for banned in ("prompt_text",):
            self.assertNotIn(banned, raw, f"verbatim field leaked: {banned}")
        # scoring inputs are present and re-scorable
        self.assertEqual(summary["scoring_inputs_version"], 5)
        self.assertIsInstance(summary["scoring_inputs_by_source"], dict)

    def test_no_summary_without_flag(self):
        _, out = _run(self, [])
        self.assertFalse(os.path.exists(os.path.join(out, "summary.json")))

    def test_window_keeps_fixture_range(self):
        # Fixtures live in 2026 — a window covering them must match the full run.
        out_text, out = _run(self, ["--since=2020-01-01", "--summary"])
        self.assertRegex(out_text, r"sessions=[1-9]\d*")
        with open(os.path.join(out, "summary.json"), encoding="utf-8") as fh:
            summary = json.load(fh)
        self.assertEqual(summary["context"]["window"]["since"][:10], "2020-01-01")

    def test_window_excludes_everything(self):
        # A window before any fixture event must yield zero sessions WITHOUT crashing
        # (empty-corpus rendering path).
        out_text, out = _run(self, ["--until=2001-01-01"])
        self.assertRegex(out_text, r"sessions=0")
        self.assertTrue(os.path.exists(os.path.join(out, "profile.html")))

    @unittest.skipUnless(shutil.which("node"), "node not installed (CI installs it)")
    def test_poster_js_is_valid_syntax(self):
        # The poster JS is a hand-written raw string — the viral artifact. node --check it.
        _, out = _run(self, [])
        with open(os.path.join(out, "profile.html"), encoding="utf-8") as fh:
            html = fh.read()
        blocks = re.findall(r"<script>(.*?)</script>", html, re.S)
        self.assertTrue(blocks, "no <script> block found in profile.html")
        js_path = os.path.join(out, "poster.js")
        with open(js_path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(blocks))
        res = subprocess.run([shutil.which("node"), "--check", js_path],
                             capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"poster JS has a syntax error:\n{res.stderr}")


class TestUnits(unittest.TestCase):
    def test_hero_lead_article(self):
        self.assertEqual(paxel._hero_lead("The Architect"), "You're")
        self.assertEqual(paxel._hero_lead("The Director"), "You're")
        self.assertEqual(paxel._hero_lead("Velocity Machine"), "You're a")
        self.assertEqual(paxel._hero_lead("Brute-Force Architect"), "You're a")
        self.assertEqual(paxel._hero_lead(""), "You're a")
        self.assertEqual(paxel._hero_lead(None), "You're a")   # the None-guard is the refactor's whole point

    def test_crashout_witching_hour(self):
        t = "why is this still broken"
        day = paxel._crashout_score(t, hour=14)
        self.assertGreater(paxel._crashout_score(t, hour=3), day)   # 3am gets the bump
        self.assertGreater(paxel._crashout_score(t, hour=2), day)   # 2am inclusive
        self.assertEqual(paxel._crashout_score(t, hour=6), day)     # 6am exclusive
        self.assertEqual(paxel._crashout_score(t), day)             # no hour == daytime

    def test_canon_tool_normalizes_lowercase(self):
        self.assertEqual(paxel._canon_tool("bash"), "Bash")
        self.assertEqual(paxel._canon_tool("read"), "Read")
        self.assertEqual(paxel._canon_tool("edit"), "Edit")

    def test_cursor_tool_name_maps_cursor_tools(self):
        # SQLite-era snake_case names
        self.assertEqual(paxel._cursor_tool_name("read_file_v2"), "Read")
        self.assertEqual(paxel._cursor_tool_name("run_terminal_command_v2"), "Bash")
        self.assertEqual(paxel._cursor_tool_name("task_v2"), "Agent")
        # modern JSONL CamelCase names (the StrReplace miss zeroed Cursor tool churn)
        self.assertEqual(paxel._cursor_tool_name("StrReplace"), "Edit")
        self.assertEqual(paxel._cursor_tool_name("ApplyPatch"), "Edit")
        self.assertEqual(paxel._cursor_tool_name("ReadFile"), "Read")
        self.assertEqual(paxel._cursor_tool_name("ReadLints"), "Read")
        self.assertEqual(paxel._cursor_tool_name("Shell"), "Bash")
        self.assertEqual(paxel._cursor_tool_name("rg"), "Grep")
        self.assertEqual(paxel._cursor_tool_name("SemanticSearch"), "Grep")
        self.assertEqual(paxel._cursor_tool_name("Delete"), "Edit")
        self.assertEqual(paxel._cursor_tool_name("AskQuestion"), "AskUserQuestion")
        self.assertEqual(paxel._cursor_tool_name("CreatePlan"), "EnterPlanMode")
        self.assertEqual(paxel._cursor_tool_name("Subagent"), "Agent")
        self.assertEqual(paxel._cursor_tool_name("Task"), "Agent")

    def test_cursor_call_mcp_tool_counts_as_mcp(self):
        name, inp = paxel._cursor_tool("CallMcpTool",
                                       {"server": "linear", "toolName": "search_issues"})
        self.assertEqual(name, "mcp__linear__search_issues")
        self.assertEqual(paxel.classify_tool(name), "explore")

    def test_cursor_apply_patch_string_params_become_churn(self):
        patch = "*** Update File: src/foo.py\n+new line\n+another\n"
        name, inp = paxel._cursor_tool("ApplyPatch", patch)
        self.assertEqual(name, "Edit")
        self.assertEqual(inp["file_path"], "src/foo.py")
        self.assertGreater(paxel.line_count(inp["new_string"]), 0)

    def test_cursor_clean_prompt_extracts_user_query(self):
        wrapped = ("<attached_files>\n<file>x.py</file>\n</attached_files>\n"
                   "<user_query>\nfix the bug\n</user_query>")
        self.assertEqual(paxel._cursor_clean_prompt(wrapped), "fix the bug")
        # no <user_query>: harness wrapper blocks are stripped, human text kept
        bare = "<attached_files>\n<file>x.py</file>\n</attached_files>\nplain question"
        self.assertEqual(paxel._cursor_clean_prompt(bare), "plain question")

    def test_cursor_project_cwd_from_slug(self):
        cwd = paxel._cursor_project_cwd("Users-demo-cursorproj")
        self.assertEqual(cwd, "/Users/demo/cursorproj")

    def test_cursor_subagent_meta_attributes_to_parent_session(self):
        fp = os.path.join(SRC_DIRS["CURSOR_DIR"], "Users-demo-cursorproj",
                          "agent-transcripts", "demo-session", "subagents",
                          "sub-explore-1.jsonl")
        sid, cwd, sidechain = paxel._cursor_jsonl_meta(fp)
        self.assertTrue(sidechain)
        self.assertEqual(sid, "demo-session")
        self.assertEqual(cwd, "/Users/demo/cursorproj")

    def test_cursor_prefers_sqlite_copy_over_jsonl_twin(self):
        # SQLite bubbles carry timestamps + tool statuses the JSONL lacks, so the
        # JSONL twin of a composer in state.vscdb must be dropped — but subagent
        # sidechains and JSONL-only sessions must survive the dedup.
        with mock.patch.multiple(paxel, **SRC_DIRS):
            sources = paxel.discover_sources(["cursor"])
            kept, twins = paxel._cursor_dedup(sources)
        kept_jsonl = {os.path.basename(fp) for _, fp, fmt in kept if fmt == "cursor-jsonl"}
        self.assertNotIn("demo-session.jsonl", kept_jsonl)         # covered by sqlite
        self.assertIn("jsonl-only-session.jsonl", kept_jsonl)      # not in the DB
        self.assertIn("sub-explore-1.jsonl", kept_jsonl)           # sidechain, always kept
        self.assertEqual(twins.get("demo-session", {}).get("cwd"), "/Users/demo/cursorproj")

    def test_cursor_sqlite_events_carry_timestamps_and_cwd(self):
        db = SRC_DIRS["CURSOR_DB"]
        events = list(paxel._cursor_sqlite_events(
            db, {"demo-session": {"cwd": "/Users/demo/cursorproj"}}))
        prompts = [e for e in events if e.get("type") == "user"
                   and isinstance(e.get("message", {}).get("content"), str)]
        texts = [e["message"]["content"] for e in prompts]
        self.assertIn("legacy sqlite-only question thanks", texts)
        self.assertIn("duplicate prompt should not count", texts)  # canonical copy now
        demo = [e for e in events if e.get("sessionId") == "demo-session"]
        self.assertTrue(all(e.get("cwd") == "/Users/demo/cursorproj" for e in demo))
        self.assertTrue(any(e.get("timestamp") for e in demo))
        # tool statuses: one error, one cancelled (cancelled must NOT count as an error)
        results = [b for e in events if e.get("sessionId") == "demo-session"
                   for b in (e.get("message", {}).get("content") or [])
                   if isinstance(b, dict) and b.get("type") == "tool_result"]
        self.assertEqual(sum(1 for b in results if b.get("is_error")), 1)

    def test_cursor_sqlite_edit_churn_backfilled_from_jsonl_twin(self):
        # Real edit_file_v2 sqlite params carry only the file PATH — the old/new strings
        # exist only in the JSONL twin, so churn must be backfilled from it.
        jsonl = os.path.join(SRC_DIRS["CURSOR_DIR"], "Users-demo-cursorproj",
                             "agent-transcripts", "demo-session", "demo-session.jsonl")
        events = list(paxel._cursor_sqlite_events(
            SRC_DIRS["CURSOR_DB"],
            {"demo-session": {"cwd": "/Users/demo/cursorproj", "jsonl": jsonl}}))
        edits = [b for e in events if e.get("sessionId") == "demo-session"
                 for b in (e.get("message", {}).get("content") or [])
                 if isinstance(b, dict) and b.get("type") == "tool_use"
                 and b.get("name") == "Edit"]
        self.assertTrue(edits, "no Edit tool_use came out of the sqlite reader")
        self.assertEqual(edits[0]["input"]["new_string"], "a = 2\nb = 3\n")
        self.assertEqual(edits[0]["input"]["old_string"], "a = 1\n")
        self.assertEqual(edits[0]["input"]["file_path"], "/Users/demo/cursorproj/main.py")

    def test_compute_scores_has_three_axes_not_steering(self):
        # empty-data guard returns the canonical axis set — guards against re-adding Steering.
        zero = paxel.compute_scores({"volume": {"total_sessions": 0, "tool_calls_total": 0},
                                     "behavior": {}, "velocity": {}})
        self.assertEqual(set(zero), SCORED_AXES)
        self.assertNotIn("Steering", zero)

    def test_classify_mcp_subcategory_knowledge(self):
        from gnomon.taxonomy import classify_mcp_subcategory
        self.assertEqual(classify_mcp_subcategory("codegraph", "codegraph_explore"), "knowledge")
        self.assertEqual(classify_mcp_subcategory("plugin_engram_engram", "mem_save"), "knowledge")
        self.assertEqual(classify_mcp_subcategory("mem0", "add_memory"), "knowledge")

    def test_classify_mcp_subcategory_browser(self):
        from gnomon.taxonomy import classify_mcp_subcategory
        self.assertEqual(classify_mcp_subcategory("claude-in-chrome", "navigate"), "browser")
        self.assertEqual(classify_mcp_subcategory("playwright", "browser_click"), "browser")

    def test_classify_mcp_subcategory_layer2_fallback(self):
        from gnomon.taxonomy import classify_mcp_subcategory
        self.assertEqual(classify_mcp_subcategory("unknown_server", "search_knowledge_base"), "knowledge")
        self.assertEqual(classify_mcp_subcategory("unknown_server", "execute_sql"), "data")
        self.assertEqual(classify_mcp_subcategory("unknown_server", "unknown_tool"), "other")

    def test_codegraph_explore_classifies_as_explore(self):
        self.assertEqual(paxel.classify_tool("mcp__codegraph__codegraph_explore"), "explore")


class TestCursorStatsFixes(unittest.TestCase):
    """Regression tests for the four Cursor parser bugs that corrupted its stats:
    model mix, tool-name casing split, MCP server naming, and dashed-slug cwd."""

    # --- Bug 2: casing variants of one tool must collapse to a single canonical name ---
    def test_tool_name_casing_collapses_for_mapped_plan_tool(self):
        names = {paxel._cursor_tool_name(n) for n in
                 ("update_current_step", "UpdateCurrentStep", "updateCurrentStep")}
        self.assertEqual(names, {"TodoWrite"})  # mapped like Codex update_plan

    def test_tool_name_casing_collapses_for_unmapped_tool(self):
        names = {paxel._cursor_tool_name(n) for n in ("switch_mode", "SwitchMode", "switchMode")}
        self.assertEqual(names, {"switch_mode"})  # one canonical, not three

    # --- Bug 3: Cursor MCP tool names canonicalize to mcp__<server>__<tool> ---
    def test_mcp_name_splits_server_and_tool(self):
        self.assertEqual(paxel._cursor_tool_name("mcp-figma-get_design_context"),
                         "mcp__figma__get_design_context")

    def test_mcp_name_server_groups_multiple_tools(self):
        servers = {paxel._cursor_tool_name(n).split("__")[1] for n in
                   ("mcp_figma_get_screenshot", "mcp_figma_download_assets")}
        self.assertEqual(servers, {"figma"})  # one server bucket, not one-per-tool

    def test_mcp_name_single_token_does_not_emit_empty_server(self):
        out = paxel._cursor_tool_name("mcp_foo")
        self.assertEqual(out, "mcp__cursor__foo")
        self.assertNotIn("mcp--", out)

    def test_already_canonical_mcp_name_untouched(self):
        self.assertEqual(paxel._cursor_tool_name("mcp__github__create_issue"),
                         "mcp__github__create_issue")

    # --- Bug 4: dashed folder names reconstruct against disk, with naive fallback ---
    def test_cwd_reconstructs_dashed_leaf_against_disk(self):
        existing = {"/Users", "/Users/mirland", "/Users/mirland/Projects",
                    "/Users/mirland/Projects/carp-health-flutter"}
        with mock.patch("gnomon.sources.cursor.os.path.isdir", side_effect=existing.__contains__):
            cwd = paxel._cursor_project_cwd("Users-mirland-Projects-carp-health-flutter")
        self.assertEqual(cwd, "/Users/mirland/Projects/carp-health-flutter")

    def test_cwd_falls_back_to_naive_when_nothing_on_disk(self):
        with mock.patch("gnomon.sources.cursor.os.path.isdir", return_value=False):
            self.assertEqual(paxel._cursor_project_cwd("Users-demo-cursorproj"),
                             "/Users/demo/cursorproj")

    def test_cwd_none_for_non_home_slug(self):
        self.assertIsNone(paxel._cursor_project_cwd("1777578696277"))

    # --- Bug 1: the session model surfaces from composerData.modelConfig.modelName ---
    def test_session_model_read_from_model_config(self):
        temp_db = tempfile.NamedTemporaryFile(suffix=".vscdb", delete=False)
        temp_db.close()
        self.addCleanup(lambda: os.path.exists(temp_db.name) and os.unlink(temp_db.name))
        import sqlite3
        conn = sqlite3.connect(temp_db.name)
        conn.execute("CREATE TABLE cursorDiskKV (key TEXT PRIMARY KEY, value BLOB)")
        bid = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
        conn.execute("INSERT INTO cursorDiskKV VALUES (?, ?)",
                     ("composerData:mdl-session",
                      json.dumps({"modelConfig": {"modelName": "claude-4.5-sonnet-thinking"},
                                  "fullConversationHeadersOnly": [{"bubbleId": bid, "type": 2}]})))
        conn.execute("INSERT INTO cursorDiskKV VALUES (?, ?)",
                     (f"bubbleId:mdl-session:{bid}",
                      json.dumps({"type": 2, "createdAt": "2026-01-01T10:00:00.000Z",
                                  "text": "hello",
                                  "tokenCount": {"inputTokens": 10, "outputTokens": 5}})))
        conn.commit()
        conn.close()
        events = list(paxel._cursor_sqlite_events(temp_db.name, {}))
        asst = [e for e in events if e.get("type") == "assistant"]
        self.assertTrue(asst, "no assistant event emitted")
        self.assertEqual(asst[0]["message"]["model"], "claude-4.5-sonnet-thinking")

    def test_pretty_model_cursor_ids(self):
        self.assertEqual(paxel._pretty_model("default"), "Cursor Auto")
        self.assertEqual(paxel._pretty_model("composer-2.5-fast"), "Cursor Composer 2.5 Fast")
        self.assertEqual(paxel._pretty_model("claude-4.5-sonnet-thinking"), "Sonnet 4.5 Thinking")

    # --- Bug 5: cwd inferred from JSONL tool-input paths when the slug is unrecoverable ---
    def test_cwd_from_paths_recovers_dotted_username(self):
        # slug 'Users-jorge-artave-...' loses the '.' in 'jorge.artave'; the tool paths keep it.
        paths = [
            "/Users/jorge.artave/Projects/maps/maps-server/src/Main.java",
            "/Users/jorge.artave/Projects/maps/maps-server/src/Other.java",
            "/Users/jorge.artave/Projects/maps/maps-server/src/Main.java",
        ]
        cwd = paxel._cursor_cwd_from_paths(paths)
        self.assertTrue(cwd.startswith("/Users/jorge.artave/Projects/maps"))

    def test_cwd_from_paths_most_touched_dir_wins(self):
        paths = (["/Users/x/Projects/a/one.py"] * 1
                 + ["/Users/x/Projects/b/two.py"] * 3)
        self.assertEqual(paxel._cursor_cwd_from_paths(paths), "/Users/x/Projects/b")

    def test_cwd_from_paths_ignores_noise_dirs(self):
        paths = [
            "/Users/x/.cursor/skills/foo/SKILL.md",
            "/Users/x/Projects/app/src/main.ts",
            "/Users/x/Projects/app/src/util.ts",
        ]
        self.assertEqual(paxel._cursor_cwd_from_paths(paths), "/Users/x/Projects/app/src")

    def test_cwd_from_paths_none_when_no_abs_paths(self):
        self.assertIsNone(paxel._cursor_cwd_from_paths(["relative/x.py", "", None]))

    def test_resolve_cwd_prefers_existing_slug_dir(self):
        # when the slug already maps to a real dir, don't bother scanning content
        with mock.patch("gnomon.sources.cursor.os.path.isdir", return_value=True):
            self.assertEqual(paxel._cursor_resolve_cwd("/nonexistent.jsonl", "/Users/me/proj"),
                             "/Users/me/proj")

    # --- Fix 6: flat CLI MCP tool names -> mcp__server__tool via mcps/ sidecar ---
    def test_mcp_name_from_servers_matches_identifier_and_friendly_name(self):
        servers = {"plugin-atlassian-atlassian": "atlassian", "user-bitbucket": "bitbucket"}
        # full identifier prefix
        self.assertEqual(
            paxel._cursor_mcp_name_from_servers("plugin-atlassian-atlassian-search", servers),
            "mcp__atlassian__search")
        # friendly serverName prefix
        self.assertEqual(
            paxel._cursor_mcp_name_from_servers("bitbucket-listPullRequests", servers),
            "mcp__bitbucket__listPullRequests")

    def test_mcp_name_from_servers_none_when_no_match(self):
        self.assertIsNone(paxel._cursor_mcp_name_from_servers("read_file_v2", {"x": "x"}))
        self.assertIsNone(paxel._cursor_mcp_name_from_servers("anything", None))

    def test_mcp_servers_loaded_from_sidecar(self):
        import tempfile, json as _json
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        # <root>/<slug>/mcps/<ident>/SERVER_METADATA.json  +  a sibling agent-transcripts file
        slug = os.path.join(root, "Users-x-Projects-app")
        meta_dir = os.path.join(slug, "mcps", "plugin-atlassian-atlassian")
        os.makedirs(meta_dir)
        with open(os.path.join(meta_dir, "SERVER_METADATA.json"), "w") as fh:
            _json.dump({"serverIdentifier": "plugin-atlassian-atlassian",
                        "serverName": "atlassian"}, fh)
        fp = os.path.join(slug, "agent-transcripts", "sess1", "sess1.jsonl")
        os.makedirs(os.path.dirname(fp)); open(fp, "w").close()
        paxel._CURSOR_MCP_SERVERS_CACHE.clear()
        servers = paxel._cursor_mcp_servers(fp)
        self.assertEqual(servers.get("plugin-atlassian-atlassian"), "atlassian")

    # --- Fix 7: opener retries with immutable when mode=ro fails (and tolerates spaces) ---
    def test_open_sqlite_reads_db_with_space_in_name(self):
        import tempfile, sqlite3
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        path = os.path.join(d, "My State.vscdb")  # space in filename
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE t (k TEXT)"); conn.execute("INSERT INTO t VALUES ('x')")
        conn.commit(); conn.close()
        ro = paxel._cursor_open_sqlite(path)
        self.assertIsNotNone(ro)
        self.assertEqual(ro.execute("SELECT count(*) FROM t").fetchone()[0], 1)

    # --- Fix 9: CLI sessions enriched with model+timestamp from ~/.cursor/chats ---
    def test_chat_meta_reads_timestamp_and_model(self):
        import tempfile, sqlite3, json as _json
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        cid = "abc-123-chat"
        cdir = os.path.join(root, "wshash", cid)
        os.makedirs(cdir)
        with open(os.path.join(cdir, "meta.json"), "w") as fh:
            _json.dump({"createdAtMs": 1782167750008, "title": "X"}, fh)
        conn = sqlite3.connect(os.path.join(cdir, "store.db"))
        conn.execute("CREATE TABLE meta (key TEXT, value)")
        conn.execute("INSERT INTO meta VALUES ('0', ?)",
                     (_json.dumps({"lastUsedModel": "composer-2.5"}).encode().hex(),))
        conn.commit(); conn.close()
        paxel._CURSOR_CHAT_META_CACHE.clear()
        m = paxel._cursor_chat_meta(cid, chats_dir=root)
        self.assertEqual(m.get("model"), "composer-2.5")
        self.assertTrue((m.get("ts") or "").startswith("2026-06"))

    def test_chat_meta_empty_when_absent(self):
        paxel._CURSOR_CHAT_META_CACHE.clear()
        self.assertEqual(paxel._cursor_chat_meta("no-such-chat", chats_dir="/tmp/nope-xyz"), {})

    def test_jsonl_tool_paths_extracts_from_tool_inputs(self):
        import tempfile, json as _json
        ev = {"role": "assistant", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "name": "Read", "input": {"path": "/Users/j.a/Projects/m/A.java"}},
            {"type": "tool_use", "name": "Shell",
             "input": {"command": "cd /Users/j.a/Projects/m && ls"}},
        ]}}
        f = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False)
        f.write(_json.dumps(ev) + "\n"); f.close()
        self.addCleanup(lambda: os.path.exists(f.name) and os.unlink(f.name))
        paths = paxel._cursor_jsonl_tool_paths(f.name)
        self.assertIn("/Users/j.a/Projects/m/A.java", paths)
        self.assertTrue(any(p.startswith("/Users/j.a/Projects/m") for p in paths))


class TestCapabilityAwareScoring(unittest.TestCase):
    """Fase 4: a signal a source CANNOT record (skills/toolsearch/tasktool on Cursor) is
    dropped + renormalized, not scored 0. Full-capability corpora (Claude) are a no-op."""

    def _stats(self, sources, **over):
        base = {
            "corpus": {"sources": {s: {} for s in sources}},
            "tools": {"mcp_servers_distinct": 4, "clis_distinct": 10, "toolsearch_calls": 0,
                      "task_tool_calls": 0, "cli_calls": 100, "mcp_calls": 5},
            "stack": {"models": [["a", 10], ["b", 5]], "skills_all": [], "top_skills": [],
                      "skills_distinct": 0, "skills_total": 0, "compounding_writes": 6,
                      "subagent_types": [], "subagent_types_distinct": 1},
            "behavior": {"planning_ratio_explore_to_doing": 1.0, "actions_per_prompt": 10,
                         "error_recovery_ratio": 1.0, "shell_test_runs": 5, "fanout_median": 2},
        }
        base.update(over)
        return base

    def test_cursor_drops_unsupported_axes(self):
        aq = paxel.compute_aq(self._stats(["cursor"]))
        breadth = next(p for p in aq["pillars"] if p["name"] == "Breadth")
        axis_names = {a["name"] for a in breadth["axes"]}
        self.assertIn("Skill fluency", axis_names)
        self.assertIn("Discipline", axis_names)
        # surviving axes renormalize to the full pillar weight (100)
        self.assertEqual(sum(a["weight"] for a in breadth["axes"]), 100)
        savvy = next(p for p in aq["pillars"] if p["name"] == "Savvy")
        self.assertIn("Model mix", savvy.get("not_applicable", []))

    def test_claude_keeps_all_axes_noop(self):
        aq = paxel.compute_aq(self._stats(["claude"]))
        breadth = next(p for p in aq["pillars"] if p["name"] == "Breadth")
        self.assertNotIn("not_applicable", breadth)
        self.assertEqual({a["name"] for a in breadth["axes"]},
                         {"Orchestration", "Skill fluency", "Tool command (MCP + CLI)", "Discipline"})

    def test_mixed_sources_union_keeps_skills(self):
        # claude in the mix supports skills/toolsearch/tasktool -> nothing dropped
        aq = paxel.compute_aq(self._stats(["claude", "cursor"]))
        breadth = next(p for p in aq["pillars"] if p["name"] == "Breadth")
        self.assertNotIn("not_applicable", breadth)

    def test_cursor_not_penalized_below_claude_on_unmeasurable(self):
        # identical underlying behavior: cursor must not score LOWER than claude on the
        # Savvy Token-economy axis just because it lacks ToolSearch (it gets renormalized).
        cur = paxel.compute_aq(self._stats(["cursor"]))
        cla = paxel.compute_aq(self._stats(["claude"]))
        def tok(aq):
            sav = next(p for p in aq["pillars"] if p["name"] == "Savvy")
            return next(a["score"] for a in sav["axes"] if a["name"] == "Token economy")
        self.assertGreaterEqual(tok(cur), tok(cla))


class TestCanonToolGeminiMappings(unittest.TestCase):
    """_canon_tool must map Gemini-native tool names to Claude taxonomy."""

    def test_write_file_maps_to_Write(self):
        self.assertEqual(paxel._canon_tool("write_file"), "Write")

    def test_read_file_maps_to_Read(self):
        self.assertEqual(paxel._canon_tool("read_file"), "Read")

    def test_run_shell_command_maps_to_Bash(self):
        self.assertEqual(paxel._canon_tool("run_shell_command"), "Bash")

    def test_search_file_content_maps_to_Grep(self):
        self.assertEqual(paxel._canon_tool("search_file_content"), "Grep")

    def test_find_line_numbers_maps_to_Grep(self):
        self.assertEqual(paxel._canon_tool("find_line_numbers"), "Grep")


class TestGeminiEventsAdapter(unittest.TestCase):
    """_gemini_events must parse real-format Gemini session JSON correctly."""

    FP = os.path.join(FIX, "gemini", "session-gemini.json")

    def setUp(self):
        self.events = list(paxel._gemini_events(self.FP))

    def test_yields_user_event(self):
        users = [e for e in self.events if e.get("type") == "user"
                 and isinstance(e.get("message", {}).get("content"), str)]
        self.assertTrue(users, "no plain user prompt event found")

    def test_yields_assistant_event(self):
        asst = [e for e in self.events if e.get("type") == "assistant"]
        self.assertTrue(asst, "no assistant event found")

    def test_assistant_has_thinking_block(self):
        asst = [e for e in self.events if e.get("type") == "assistant"]
        self.assertTrue(asst)
        blocks = asst[0]["message"]["content"]
        thinking = [b for b in blocks if b.get("type") == "thinking"]
        self.assertTrue(thinking, "no thinking block in assistant content")

    def test_assistant_has_tool_use_blocks(self):
        asst = [e for e in self.events if e.get("type") == "assistant"]
        self.assertTrue(asst)
        blocks = asst[0]["message"]["content"]
        tool_uses = [b for b in blocks if b.get("type") == "tool_use"]
        self.assertTrue(tool_uses, "no tool_use blocks in assistant content")

    def test_tool_use_names_are_canonical(self):
        asst = [e for e in self.events if e.get("type") == "assistant"]
        blocks = asst[0]["message"]["content"]
        tool_uses = [b for b in blocks if b.get("type") == "tool_use"]
        names = {b["name"] for b in tool_uses}
        # write_file -> Write, run_shell_command -> Bash
        self.assertIn("Write", names)
        self.assertIn("Bash", names)

    def test_tool_result_event_emitted(self):
        # After the assistant event there should be a user event with tool_result blocks
        user_tool_result_events = [
            e for e in self.events
            if e.get("type") == "user"
            and isinstance(e.get("message", {}).get("content"), list)
            and any(b.get("type") == "tool_result"
                    for b in e["message"]["content"]
                    if isinstance(b, dict))
        ]
        self.assertTrue(user_tool_result_events, "no tool_result user event found")

    def test_error_tool_result_has_is_error_true(self):
        # The fixture has one toolCall with status "error" — its result must have is_error=True
        tool_results = [
            b
            for e in self.events
            if e.get("type") == "user"
            and isinstance(e.get("message", {}).get("content"), list)
            for b in e["message"]["content"]
            if isinstance(b, dict) and b.get("type") == "tool_result"
        ]
        self.assertTrue(any(b.get("is_error") for b in tool_results),
                        "no is_error=True tool_result found for the error toolCall")

    def test_assistant_usage_mapped(self):
        asst = [e for e in self.events if e.get("type") == "assistant"]
        self.assertTrue(asst)
        usage = asst[0]["message"].get("usage")
        self.assertIsNotNone(usage, "usage missing from assistant message")
        # input_tokens == m.tokens.input
        self.assertEqual(usage["input_tokens"], 1500)
        # output_tokens == output + thoughts (42 + 120 = 162)
        self.assertEqual(usage["output_tokens"], 162)
        # cache_read_input_tokens == cached (800)
        self.assertEqual(usage["cache_read_input_tokens"], 800)
        # cache_creation_input_tokens == 0
        self.assertEqual(usage["cache_creation_input_tokens"], 0)

    def test_assistant_model_field(self):
        asst = [e for e in self.events if e.get("type") == "assistant"]
        self.assertTrue(asst)
        self.assertEqual(asst[0]["message"].get("model"), "gemini-2.5-pro")

    def test_cwd_is_non_none(self):
        # fixture has dir_path="/Users/mirland/projects/myapp" on the git commit toolCall
        asst = [e for e in self.events if e.get("type") == "assistant"]
        self.assertTrue(asst)
        self.assertIsNotNone(asst[0].get("cwd"), "cwd should be resolved from dir_path")

    def test_cwd_is_absolute_path(self):
        asst = [e for e in self.events if e.get("type") == "assistant"]
        cwd = asst[0].get("cwd")
        self.assertTrue(str(cwd).startswith("/"), f"cwd should be absolute, got: {cwd!r}")


# ---------------------------------------------------------------------------
# Codex parser fixes: A7 (apply_patch churn), A8 (token_count), A6 (subagent)
# ---------------------------------------------------------------------------

class TestPatchChurn(unittest.TestCase):
    """_patch_churn must parse *** Begin/End Patch blocks correctly."""

    def test_additions_and_deletions_extracted(self):
        patch = (
            "*** Begin Patch\n"
            "*** Update File: src/foo.py\n"
            "@@\n"
            "-old line one\n"
            "-old line two\n"
            "+new line one\n"
            "+new line two\n"
            "+new line three\n"
            "*** End Patch\n"
        )
        new_s, old_s, fpath = paxel._patch_churn(patch)
        self.assertEqual(fpath, "src/foo.py")
        self.assertEqual(paxel.line_count(new_s), 3)
        self.assertEqual(paxel.line_count(old_s), 2)

    def test_add_file_has_only_additions(self):
        patch = (
            "*** Begin Patch\n"
            "*** Add File: lib/new.py\n"
            "+import os\n"
            "+\n"
            "+print('hello')\n"
            "*** End Patch\n"
        )
        new_s, old_s, fpath = paxel._patch_churn(patch)
        self.assertEqual(fpath, "lib/new.py")
        self.assertEqual(paxel.line_count(new_s), 3)
        self.assertEqual(paxel.line_count(old_s), 0)

    def test_delete_file_has_no_content(self):
        patch = (
            "*** Begin Patch\n"
            "*** Delete File: old/dead.py\n"
            "*** End Patch\n"
        )
        new_s, old_s, fpath = paxel._patch_churn(patch)
        self.assertEqual(fpath, "old/dead.py")
        self.assertEqual(paxel.line_count(new_s), 0)
        self.assertEqual(paxel.line_count(old_s), 0)

    def test_plus_plus_plus_header_excluded(self):
        """+++ and --- unified-diff file headers must NOT be counted as content."""
        patch = (
            "*** Begin Patch\n"
            "*** Update File: x.py\n"
            "+++ x.py\n"
            "--- x.py\n"
            "+actual addition\n"
            "*** End Patch\n"
        )
        new_s, old_s, fpath = paxel._patch_churn(patch)
        self.assertEqual(paxel.line_count(new_s), 1)
        self.assertEqual(paxel.line_count(old_s), 0)

    def test_context_lines_not_counted(self):
        patch = (
            "*** Begin Patch\n"
            "*** Update File: y.go\n"
            "@@\n"
            " context line\n"
            "+added\n"
            " another context\n"
            "*** End Patch\n"
        )
        new_s, old_s, fpath = paxel._patch_churn(patch)
        self.assertEqual(paxel.line_count(new_s), 1)
        self.assertEqual(paxel.line_count(old_s), 0)

    def test_empty_input_returns_empty(self):
        new_s, old_s, fpath = paxel._patch_churn("")
        self.assertEqual(fpath, "")
        self.assertEqual(new_s, "")
        self.assertEqual(old_s, "")

    def test_multi_hunk_sums_all_hunks(self):
        patch = (
            "*** Begin Patch\n"
            "*** Update File: z.py\n"
            "@@\n"
            "+hunk1 add\n"
            "-hunk1 del\n"
            "@@\n"
            "+hunk2 add\n"
            "+hunk2 add2\n"
            "*** End Patch\n"
        )
        new_s, old_s, fpath = paxel._patch_churn(patch)
        self.assertEqual(paxel.line_count(new_s), 3)
        self.assertEqual(paxel.line_count(old_s), 1)

    def test_multi_file_patch_splits_per_file(self):
        """A single apply_patch touching two files must yield per-file churn, not
        flatten both onto the first file."""
        patch = (
            "*** Begin Patch\n"
            "*** Update File: a.py\n"
            "@@\n"
            "+a add1\n"
            "-a del1\n"
            "*** Update File: b.py\n"
            "@@\n"
            "+b add1\n"
            "+b add2\n"
            "+b add3\n"
            "*** End Patch\n"
        )
        files = paxel._patch_files(patch)
        self.assertEqual([f[2] for f in files], ["a.py", "b.py"])
        # a.py: 1 add / 1 del
        self.assertEqual(paxel.line_count(files[0][0]), 1)
        self.assertEqual(paxel.line_count(files[0][1]), 1)
        # b.py: 3 add / 0 del — NOT merged onto a.py
        self.assertEqual(paxel.line_count(files[1][0]), 3)
        self.assertEqual(paxel.line_count(files[1][1]), 0)

    def test_codex_events_multi_file_apply_patch_emits_two_edits(self):
        """_codex_events must emit one Edit tool_use per file in a multi-file patch."""
        import tempfile, json as _json
        patch = ("*** Begin Patch\n*** Update File: a.py\n+x\n"
                 "*** Update File: b.py\n+y\n+z\n*** End Patch\n")
        rows = [
            {"type": "session_meta", "timestamp": "2026-01-01T10:00:00Z",
             "payload": {"id": "s1", "cwd": "/w"}},
            {"type": "turn_context", "timestamp": "2026-01-01T10:00:01Z",
             "payload": {"model": "gpt-5.4"}},
            {"type": "response_item", "timestamp": "2026-01-01T10:00:02Z",
             "payload": {"type": "custom_tool_call", "name": "apply_patch", "input": patch}},
        ]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as fh:
            for r in rows:
                fh.write(_json.dumps(r) + "\n")
            fp = fh.name
        try:
            events = list(paxel._codex_events(fp))
        finally:
            os.unlink(fp)
        edits = [
            b for e in events if e.get("type") == "assistant"
            for b in (e.get("message", {}).get("content") or [])
            if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") == "Edit"
        ]
        self.assertEqual([b["input"]["file_path"] for b in edits], ["a.py", "b.py"])

    def test_codex_events_multi_model_tokens_split(self):
        """Mixed-model Codex session must split token usage per model, not dump it
        all on the last model seen."""
        import tempfile, json as _json
        rows = [
            {"type": "session_meta", "timestamp": "2026-01-01T10:00:00Z",
             "payload": {"id": "s1", "cwd": "/w"}},
            {"type": "turn_context", "payload": {"model": "gpt-A"}},
            {"type": "event_msg", "timestamp": "t1", "payload": {"type": "token_count",
             "info": {"total_token_usage": {"input_tokens": 1000, "cached_input_tokens": 0,
                                            "output_tokens": 100, "reasoning_output_tokens": 0,
                                            "total_tokens": 1100}}}},
            {"type": "turn_context", "payload": {"model": "gpt-B"}},
            {"type": "event_msg", "timestamp": "t2", "payload": {"type": "token_count",
             "info": {"total_token_usage": {"input_tokens": 1500, "cached_input_tokens": 0,
                                            "output_tokens": 180, "reasoning_output_tokens": 0,
                                            "total_tokens": 1680}}}},
        ]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as fh:
            for r in rows:
                fh.write(_json.dumps(r) + "\n")
            fp = fh.name
        try:
            events = list(paxel._codex_events(fp))
        finally:
            os.unlink(fp)
        usage = {e["message"]["model"]: e["message"]["usage"]
                 for e in events if e.get("__codex_usage__")}
        # gpt-A got the first delta (1000/100); gpt-B the incremental delta (500/80)
        self.assertEqual(usage["gpt-A"]["input_tokens"], 1000)
        self.assertEqual(usage["gpt-A"]["output_tokens"], 100)
        self.assertEqual(usage["gpt-B"]["input_tokens"], 500)
        self.assertEqual(usage["gpt-B"]["output_tokens"], 80)


class TestCodexToolCustomApplyPatch(unittest.TestCase):
    """_codex_tool must parse custom_tool_call apply_patch from payload.input."""

    def _make_payload(self, patch_text):
        return {
            "type": "custom_tool_call",
            "name": "apply_patch",
            "input": patch_text,
        }

    def test_returns_edit_name(self):
        p = self._make_payload(
            "*** Begin Patch\n*** Update File: a.py\n+x=1\n*** End Patch\n"
        )
        name, inp = paxel._codex_tool(p)
        self.assertEqual(name, "Edit")

    def test_new_string_has_additions(self):
        patch = "*** Begin Patch\n*** Update File: b.py\n+line1\n+line2\n*** End Patch\n"
        _, inp = paxel._codex_tool(self._make_payload(patch))
        self.assertEqual(paxel.line_count(inp["new_string"]), 2)

    def test_old_string_has_deletions(self):
        patch = "*** Begin Patch\n*** Update File: c.py\n-del1\n-del2\n-del3\n*** End Patch\n"
        _, inp = paxel._codex_tool(self._make_payload(patch))
        self.assertEqual(paxel.line_count(inp["old_string"]), 3)

    def test_file_path_extracted(self):
        patch = "*** Begin Patch\n*** Update File: src/main.go\n+x\n*** End Patch\n"
        _, inp = paxel._codex_tool(self._make_payload(patch))
        self.assertEqual(inp["file_path"], "src/main.go")

    def test_delete_file_returns_path_only(self):
        patch = "*** Begin Patch\n*** Delete File: dead/code.py\n*** End Patch\n"
        _, inp = paxel._codex_tool(self._make_payload(patch))
        self.assertEqual(inp["file_path"], "dead/code.py")
        self.assertEqual(paxel.line_count(inp["new_string"]), 0)
        self.assertEqual(paxel.line_count(inp["old_string"]), 0)


class TestCodexMcp(unittest.TestCase):
    """_codex_tool must count both prefixed and namespaced Codex MCP calls."""

    def test_prefixed_name_kept_as_mcp(self):
        p = {"type": "function_call", "name": "mcp__supabase-bot__execute_sql",
             "arguments": "{}"}
        name, _ = paxel._codex_tool(p)
        self.assertEqual(name, "mcp__supabase-bot__execute_sql")

    def test_namespaced_short_name_becomes_mcp(self):
        p = {"type": "function_call", "name": "list_tables",
             "namespace": "mcp__supabase_bot__", "arguments": "{}"}
        name, _ = paxel._codex_tool(p)
        # server taken verbatim from the namespace (no underscore→hyphen aliasing)
        self.assertEqual(name, "mcp__supabase_bot__list_tables")
        self.assertEqual(name.split("__")[1], "supabase_bot")

    def test_namespaced_subapp_server_parses_first_segment(self):
        p = {"type": "function_call", "name": "_search_email_ids",
             "namespace": "mcp__codex_apps__gmail", "arguments": "{}"}
        name, _ = paxel._codex_tool(p)
        self.assertEqual(name, "mcp__codex_apps__gmail__search_email_ids")
        self.assertEqual(name.split("__")[1], "codex_apps")

    def test_mcp_tool_named_like_builtin_not_mapped_to_edit(self):
        """An MCP tool named 'create_file' under an mcp__ namespace must stay MCP,
        not be mis-mapped to Edit by the builtin-name branch."""
        p = {"type": "function_call", "name": "create_file",
             "namespace": "mcp__some_server__", "arguments": "{}"}
        name, _ = paxel._codex_tool(p)
        self.assertTrue(name.startswith("mcp__"))
        self.assertNotEqual(name, "Edit")

    def test_native_exec_command_still_bash(self):
        p = {"type": "function_call", "name": "exec_command",
             "arguments": "{\"command\": \"ls\"}"}
        name, _ = paxel._codex_tool(p)
        self.assertEqual(name, "Bash")

    def test_non_mcp_namespace_stays_native(self):
        """namespace='codex_app' (no mcp__ prefix) must NOT be reclassified as MCP."""
        p = {"type": "function_call", "name": "do_thing",
             "namespace": "codex_app", "arguments": "{}"}
        name, _ = paxel._codex_tool(p)
        self.assertFalse(name.startswith("mcp__"))

    def test_codex_events_emits_mcp_for_namespaced_call(self):
        """End-to-end through _codex_events: a namespaced MCP function_call must
        surface as an mcp__ tool_use (so the mcp_calls counter picks it up), while a
        native call stays native."""
        import tempfile, json as _json
        rows = [
            {"type": "session_meta", "payload": {"id": "s1", "cwd": "/w"}},
            {"type": "turn_context", "payload": {"model": "gpt-5.4"}},
            {"type": "response_item", "timestamp": "t1",
             "payload": {"type": "function_call", "name": "list_tables",
                         "namespace": "mcp__supabase_bot__", "arguments": "{}"}},
            {"type": "response_item", "timestamp": "t2",
             "payload": {"type": "function_call", "name": "exec_command",
                         "arguments": "{\"command\": \"ls\"}"}},
        ]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as fh:
            for r in rows:
                fh.write(_json.dumps(r) + "\n")
            fp = fh.name
        try:
            events = list(paxel._codex_events(fp))
        finally:
            os.unlink(fp)
        names = [b.get("name")
                 for e in events if e.get("type") == "assistant"
                 for b in (e.get("message", {}).get("content") or [])
                 if isinstance(b, dict) and b.get("type") == "tool_use"]
        self.assertIn("mcp__supabase_bot__list_tables", names)
        self.assertIn("Bash", names)


class TestCodexEventsFixture(unittest.TestCase):
    """_codex_events over the real-format fixture (A7 + A8)."""

    FP = os.path.join(FIX, "codex", "session-codex.jsonl")

    def setUp(self):
        self.events = list(paxel._codex_events(self.FP))

    def test_yields_user_prompt(self):
        users = [e for e in self.events if e.get("type") == "user"
                 and isinstance(e.get("message", {}).get("content"), str)]
        self.assertTrue(users, "no user prompt event found")

    def test_yields_edit_tool_use(self):
        """apply_patch custom_tool_call must produce an Edit tool_use."""
        tool_uses = [
            b
            for e in self.events if e.get("type") == "assistant"
            for b in (e.get("message", {}).get("content") or [])
            if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") == "Edit"
        ]
        self.assertTrue(tool_uses, "no Edit tool_use found from apply_patch")

    def test_edit_has_nonzero_churn(self):
        """The apply_patch fixture has add and del lines — both new_string and old_string
        must be non-empty so the churn accumulator gets both additions and deletions."""
        tool_uses = [
            b
            for e in self.events if e.get("type") == "assistant"
            for b in (e.get("message", {}).get("content") or [])
            if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") == "Edit"
        ]
        self.assertTrue(tool_uses)
        self.assertGreater(paxel.line_count(tool_uses[0]["input"].get("new_string", "")), 0)
        self.assertGreater(paxel.line_count(tool_uses[0]["input"].get("old_string", "")), 0)

    def test_token_usage_event_emitted(self):
        """A8: a synthetic assistant event carrying usage must be present."""
        usage_events = [
            e for e in self.events
            if e.get("type") == "assistant" and e.get("__codex_usage__")
        ]
        self.assertTrue(usage_events, "no __codex_usage__ event found")

    def test_token_usage_values_correct(self):
        """A8: fixture has total input=5000, cached=3000, output=120, reasoning=80.
        Expected: input=5000-3000=2000, cache_read=3000, output=120+80=200."""
        usage_events = [e for e in self.events if e.get("__codex_usage__")]
        self.assertTrue(usage_events)
        u = usage_events[0]["message"]["usage"]
        self.assertEqual(u["input_tokens"], 2000)
        self.assertEqual(u["cache_read_input_tokens"], 3000)
        self.assertEqual(u["output_tokens"], 200)
        self.assertEqual(u["cache_creation_input_tokens"], 0)

    def test_token_usage_model_is_set(self):
        """A8: usage event must carry the model from turn_context."""
        usage_events = [e for e in self.events if e.get("__codex_usage__")]
        self.assertTrue(usage_events)
        self.assertEqual(usage_events[0]["message"].get("model"), "gpt-5.4")


class TestCodexEventsSubagent(unittest.TestCase):
    """Child metadata must not synthesize a second parent Agent tool_use."""

    def _make_events(self, is_subagent):
        import tempfile, json as _json
        src = ({"subagent": {"thread_spawn": {
            "parent_thread_id": "parent-123", "depth": 1,
            "agent_nickname": "Ramanujan", "agent_role": "worker"}}}
               if is_subagent else "cli")
        rows = [
            {"type": "session_meta", "timestamp": "2026-01-01T10:00:00Z",
             "payload": {"id": "sub-sess-1", "cwd": "/work", "source": src,
                         "model_provider": "openai"}},
            {"type": "turn_context", "timestamp": "2026-01-01T10:00:01Z",
             "payload": {"model": "gpt-5.4"}},
            {"type": "response_item", "timestamp": "2026-01-01T10:00:02Z",
             "payload": {"type": "message", "role": "user",
                         "content": [{"type": "input_text", "text": "do something"}]}},
            {"type": "response_item", "timestamp": "2026-01-01T10:00:03Z",
             "payload": {"type": "message", "role": "assistant",
                         "content": [{"type": "output_text", "text": "done"}]}},
        ]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as fh:
            for row in rows:
                fh.write(_json.dumps(row) + "\n")
            return fh.name

    def test_subagent_session_does_not_duplicate_parent_spawn(self):
        """The real parent spawn is authoritative; child metadata only links routing."""
        import tempfile
        fp = self._make_events(is_subagent=True)
        try:
            events = list(paxel._codex_events(fp))
        finally:
            os.unlink(fp)
        agent_events = [
            e for e in events if e.get("type") == "assistant"
            for b in (e.get("message", {}).get("content") or [])
            if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") == "Agent"
        ]
        self.assertEqual(agent_events, [])

    def test_non_subagent_session_no_agent_tool_use(self):
        import tempfile
        fp = self._make_events(is_subagent=False)
        try:
            events = list(paxel._codex_events(fp))
        finally:
            os.unlink(fp)
        agent_uses = [
            b for e in events if e.get("type") == "assistant"
            for b in (e.get("message", {}).get("content") or [])
            if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") == "Agent"
        ]
        self.assertEqual(agent_uses, [], "Agent tool_use must NOT be emitted for non-subagent session")


# ---------------------------------------------------------------------------
# A5: null honesty for unmeasured metrics
# ---------------------------------------------------------------------------

def _run_single_source(testcase, source_name, gemini_dir=None, claude_dir=None):
    """Run paxel over fixtures with only one source active; return stats dict."""
    _empty = tempfile.mkdtemp(prefix="paxel-empty-")
    testcase.addCleanup(shutil.rmtree, _empty, ignore_errors=True)
    dirs = dict(
        BASE=claude_dir or _empty,
        CODEX_DIR=_empty,
        GEMINI_DIR=gemini_dir or _empty,
        ANTIGRAVITY_CLI_DIR=_empty,
        ANTIGRAVITY_DB=os.path.join(_empty, "nope.vscdb"),
        PI_DIR=_empty,
        OPENCODE_DIR=_empty,
        CURSOR_DIR=_empty,
        CURSOR_DB=os.path.join(_empty, "nonexistent.vscdb"),
    )
    out = tempfile.mkdtemp(prefix="paxel-test-null-")
    testcase.addCleanup(shutil.rmtree, out, ignore_errors=True)
    buf = io.StringIO()
    argv = ["paxel.py", source_name, "--no-open"]
    with mock.patch.multiple(paxel, OUT_DIR=out, **dirs), \
            mock.patch.object(sys, "argv", argv), \
            contextlib.redirect_stdout(buf):
        paxel.main()
    with open(os.path.join(out, "stats.json"), encoding="utf-8") as fh:
        return json.load(fh)


class TestNullHonestyMetrics(unittest.TestCase):
    """A5: fanout_median must be None for Gemini-only (can't dispatch agents);
    Claude-only must keep real 0 values, not null."""

    def test_claude_only_fanout_is_real_zero(self):
        # Claude CAN dispatch agents — a corpus where it didn't shows real 0, not null.
        stats = _run_single_source(self, "claude",
                                   claude_dir=SRC_DIRS["BASE"])
        b = stats["behavior"]
        self.assertEqual(b["fanout_median"], 0,
                         "Claude-only corpus with no delegation must show real 0, not null")

    def test_claude_only_error_rate_is_real(self):
        # Claude emits tool_result events so error_rate is always measurable.
        stats = _run_single_source(self, "claude",
                                   claude_dir=SRC_DIRS["BASE"])
        b = stats["behavior"]
        self.assertIsNotNone(b["error_rate_per_100_tools"],
                             "Claude-only error_rate must be a real value, not null")
        self.assertIsNotNone(b["error_recovery_ratio"],
                             "Claude-only error_recovery must be a real value, not null")

    def test_claude_only_iteration_depth_is_real(self):
        stats = _run_single_source(self, "claude",
                                   claude_dir=SRC_DIRS["BASE"])
        b = stats["behavior"]
        self.assertIsNotNone(b["iteration_depth_mean"],
                             "Claude-only iteration_depth_mean must be a real value, not null")

    def test_gemini_only_fanout_is_null(self):
        # Gemini has no subagent dispatch facility — fanout_median must be None.
        stats = _run_single_source(self, "gemini",
                                   gemini_dir=SRC_DIRS["GEMINI_DIR"])
        b = stats["behavior"]
        self.assertIsNone(b["fanout_median"],
                          "Gemini-only corpus must show fanout_median=None (can't dispatch agents)")

    def test_gemini_only_error_rate_is_real(self):
        # Post-A1, Gemini emits tool_result events with is_error flags — error_rate is real.
        stats = _run_single_source(self, "gemini",
                                   gemini_dir=SRC_DIRS["GEMINI_DIR"])
        b = stats["behavior"]
        self.assertIsNotNone(b["error_rate_per_100_tools"],
                             "Gemini-only error_rate must be a real value after A1 parser fix")
        self.assertIsNotNone(b["error_recovery_ratio"],
                             "Gemini-only error_recovery must be a real value after A1 parser fix")

    def test_gemini_only_iteration_depth_is_real(self):
        # Post-A1, Gemini emits Write tool_use events — iteration_depth is real.
        stats = _run_single_source(self, "gemini",
                                   gemini_dir=SRC_DIRS["GEMINI_DIR"])
        b = stats["behavior"]
        self.assertIsNotNone(b["iteration_depth_mean"],
                             "Gemini-only iteration_depth must be a real value after A1 parser fix")

    def test_null_fanout_passes_through_to_summary(self):
        # build_summary must emit JSON null (not 0) for fanout when it's None.
        stats = _run_single_source(self, "gemini",
                                   gemini_dir=SRC_DIRS["GEMINI_DIR"])
        summary = paxel.build_summary(stats)
        self.assertIsNone(summary["orchestration"]["fanout_median"],
                          "build_summary must preserve None for fanout in Gemini-only corpus")

    def test_null_fanout_does_not_crash_aq_scoring(self):
        # compute_aq and compute_scores must be tolerant of fanout_median=None.
        stats = _run_single_source(self, "gemini",
                                   gemini_dir=SRC_DIRS["GEMINI_DIR"])
        self.assertIsNone(stats["behavior"]["fanout_median"])
        aq = paxel.compute_aq(stats)
        self.assertIn("aq_0_100", aq)
        scores = paxel.compute_scores(stats)
        self.assertEqual(set(scores), {"Execution", "Planning", "Engineering"})


# ---------------------------------------------------------------------------
# GA1: per-month noticed_stats engine (stats["monthly_noticed_stats"])
# ---------------------------------------------------------------------------

def _run_claude_transcript(testcase, rows, extra_argv=None, spy_git_churn=None):
    """Write `rows` (list of event dicts) as a single claude .jsonl transcript,
    run paxel over a claude-only corpus, and return the parsed stats dict.

    `spy_git_churn`, if given, is installed in place of paxel.git_churn so a test
    can assert how it was called (per call: cwds, since, until)."""
    proj = tempfile.mkdtemp(prefix="paxel-ga1-claude-")
    testcase.addCleanup(shutil.rmtree, proj, ignore_errors=True)
    sess_dir = os.path.join(proj, "proj-x")
    os.makedirs(sess_dir, exist_ok=True)
    with open(os.path.join(sess_dir, "session.jsonl"), "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    _empty = tempfile.mkdtemp(prefix="paxel-ga1-empty-")
    testcase.addCleanup(shutil.rmtree, _empty, ignore_errors=True)
    dirs = dict(
        BASE=proj, CODEX_DIR=_empty, GEMINI_DIR=_empty, PI_DIR=_empty,
        ANTIGRAVITY_CLI_DIR=_empty, ANTIGRAVITY_DB=os.path.join(_empty, "nope.vscdb"),
        OPENCODE_DIR=_empty, CURSOR_DIR=_empty,
        CURSOR_DB=os.path.join(_empty, "nonexistent.vscdb"),
    )
    out = tempfile.mkdtemp(prefix="paxel-ga1-out-")
    testcase.addCleanup(shutil.rmtree, out, ignore_errors=True)
    argv = ["paxel.py", "claude", "--no-open"] + (extra_argv or [])
    buf = io.StringIO()
    patches = [
        mock.patch.multiple(paxel, OUT_DIR=out, **dirs),
        mock.patch.object(sys, "argv", argv),
        contextlib.redirect_stdout(buf),
    ]
    if spy_git_churn is not None:
        patches.append(mock.patch.object(paxel, "git_churn", spy_git_churn))
    with contextlib.ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        paxel.main()
    with open(os.path.join(out, "stats.json"), encoding="utf-8") as fh:
        return json.load(fh)


def _claude_turn(sid, ts, cwd="/Users/demo/proj", model="claude-opus-4-8",
                 prompt="please add a feature", tool="Read", file_path=None,
                 new_string="", is_error=False, usage=None):
    """One user prompt + one assistant turn (thinking + tool_use) + a tool_result."""
    rows = [
        {"type": "user", "sessionId": sid, "cwd": cwd, "timestamp": ts,
         "message": {"role": "user", "content": prompt}},
    ]
    tu = {"type": "tool_use", "name": tool, "input": {}}
    if file_path is not None:
        tu["input"]["file_path"] = file_path
    if tool in ("Edit", "Write"):
        tu["input"]["new_string" if tool == "Edit" else "content"] = new_string
        if tool == "Edit":
            tu["input"]["old_string"] = ""
    amsg = {"role": "assistant", "model": model,
            "content": [{"type": "thinking", "thinking": "think"}, tu]}
    if usage:
        amsg["usage"] = usage
    rows.append({"type": "assistant", "sessionId": sid, "cwd": cwd, "timestamp": ts,
                 "message": amsg})
    rows.append({"type": "user", "sessionId": sid, "cwd": cwd, "timestamp": ts,
                 "message": {"role": "user", "content": [
                     {"type": "tool_result", "content": "ok", "is_error": is_error}]}})
    return rows


class TestMonthlyNoticedStats(unittest.TestCase):
    """GA1: stats['monthly_noticed_stats'] — per-calendar-month noticed_stats."""

    def _two_month_rows(self):
        rows = []
        # ---- January: 2 prompts, Edit (5 lines), tokens A ----
        rows += _claude_turn("jan-1", "2026-01-05T10:00:00.000Z", tool="Edit",
                             file_path="/Users/demo/proj/a.py",
                             new_string="l1\nl2\nl3\nl4\nl5", prompt="please do jan one",
                             usage={"input_tokens": 100, "output_tokens": 10,
                                    "cache_read_input_tokens": 5, "cache_creation_input_tokens": 1})
        rows += _claude_turn("jan-1", "2026-01-05T10:05:00.000Z", tool="Read",
                             file_path="/Users/demo/proj/a.py", prompt="jan two")
        # ---- February: 3 prompts, Write (2 lines), tokens B (different) ----
        rows += _claude_turn("feb-1", "2026-02-10T09:00:00.000Z", tool="Write",
                             file_path="/Users/demo/proj/b.py", new_string="x\ny",
                             prompt="feb one", usage={"input_tokens": 500, "output_tokens": 50,
                             "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0})
        rows += _claude_turn("feb-1", "2026-02-10T09:05:00.000Z", tool="Read",
                             prompt="feb two")
        rows += _claude_turn("feb-1", "2026-02-10T09:10:00.000Z", tool="Grep",
                             prompt="feb three")
        return rows

    def test_two_entries_chronological(self):
        stats = _run_claude_transcript(self, self._two_month_rows())
        mns = stats["monthly_noticed_stats"]
        self.assertEqual([e["month"] for e in mns], ["2026-01", "2026-02"])
        for e in mns:
            self.assertIn("range_start", e)
            self.assertIn("range_end", e)
            self.assertIn("stats", e)
            self.assertIn("token_usage", e)

    def test_month_isolation_prompts_tools_tokens(self):
        stats = _run_claude_transcript(self, self._two_month_rows())
        mns = {e["month"]: e for e in stats["monthly_noticed_stats"]}
        jan, feb = mns["2026-01"], mns["2026-02"]
        # prompts per month differ and differ from the window total (5)
        self.assertEqual(jan["stats"]["volume"]["total_prompts"], 2)
        self.assertEqual(feb["stats"]["volume"]["total_prompts"], 3)
        self.assertEqual(stats["volume"]["total_prompts"], 5)
        # tokens isolated per month and != window total
        self.assertEqual(jan["token_usage"]["total_input"], 100)
        self.assertEqual(feb["token_usage"]["total_input"], 500)
        self.assertEqual(stats["token_usage"]["total_input"], 600)
        # tool calls isolated (jan 2, feb 3) and != window (5)
        self.assertEqual(jan["stats"]["volume"]["tool_calls_total"], 2)
        self.assertEqual(feb["stats"]["volume"]["tool_calls_total"], 3)
        self.assertEqual(stats["volume"]["tool_calls_total"], 5)

    def test_per_month_token_usage_shape_matches_window(self):
        stats = _run_claude_transcript(self, self._two_month_rows())
        win_keys = set(stats["token_usage"])
        for e in stats["monthly_noticed_stats"]:
            self.assertEqual(set(e["token_usage"]), win_keys)
            # by_model is a list of dicts shaped like the window block
            for bm in e["token_usage"]["by_model"]:
                self.assertEqual(
                    set(bm),
                    {"model_id", "model", "input", "output", "cache_read", "cache_creation"})

    def test_entry_stats_shape_matches_window_noticed_stats(self):
        stats = _run_claude_transcript(self, self._two_month_rows())
        window_noticed = paxel._build_noticed_stats(stats)
        for e in stats["monthly_noticed_stats"]:
            self.assertEqual(set(e["stats"]), set(window_noticed),
                             "per-month stats must have the same top-level keys as window noticed_stats")
            # nested keys identical too (single shaper guarantees this)
            for k in window_noticed:
                self.assertEqual(set(e["stats"][k]), set(window_noticed[k]),
                                 f"sub-shape drift in {k}")

    def test_git_churn_called_once_per_month_with_month_range(self):
        calls = []

        def spy(cwds, since, until):
            calls.append((tuple(sorted(cwds)), since, until))
            return {"repos_seen": 1, "repos_with_commits": 1, "insertions": 0,
                    "deletions": 0, "churn": 0, "commits": 0, "per_repo": []}

        stats = _run_claude_transcript(self, self._two_month_rows(), spy_git_churn=spy)
        # one window call + one per month (2) = 3 total
        self.assertEqual(len(calls), 3, f"expected window + 2 month calls, got {calls}")
        # month calls carry month-bounded since/until (not the full window)
        month_calls = [c for c in calls if c[1].startswith(("2026-01", "2026-02"))
                       and c[2].startswith(("2026-01", "2026-02", "2026-03"))]
        self.assertTrue(any(c[1].startswith("2026-01") and c[2].startswith("2026-02")
                            for c in month_calls),
                        f"January churn call must span Jan→Feb, got {month_calls}")
        self.assertTrue(any(c[1].startswith("2026-02") and c[2].startswith("2026-03")
                            for c in month_calls),
                        f"February churn call must span Feb→Mar, got {month_calls}")

    def test_degenerate_single_month_equals_window(self):
        # A single-month corpus → that month's derived stats must equal the window's.
        rows = []
        rows += _claude_turn("s1", "2026-03-01T10:00:00.000Z", tool="Edit",
                             file_path="/Users/demo/proj/a.py", new_string="1\n2\n3",
                             prompt="please p1", is_error=True)
        rows += _claude_turn("s1", "2026-03-01T10:05:00.000Z", tool="Edit",
                             file_path="/Users/demo/proj/a.py", new_string="4\n5",
                             prompt="p2")
        rows += _claude_turn("s1", "2026-03-01T10:10:00.000Z", tool="Read", prompt="p3?")
        stats = _run_claude_transcript(self, rows)
        mns = stats["monthly_noticed_stats"]
        self.assertEqual(len(mns), 1)
        b = stats["behavior"]
        m = mns[0]["stats"]
        # error rate / recovery — degenerate equality with window formula
        self.assertEqual(m["errors"]["error_rate_per_100_tools"],
                         b["error_rate_per_100_tools"])
        self.assertEqual(m["errors"]["error_recovery_ratio"], b["error_recovery_ratio"])
        # iteration depth stats
        self.assertEqual(m["iteration"]["depth_mean"], b["iteration_depth_mean"])
        self.assertEqual(m["iteration"]["depth_median"], b["iteration_depth_median"])
        self.assertEqual(m["iteration"]["depth_max"], b["iteration_depth_max"])
        # fanout median
        self.assertEqual(m["agents"]["fanout_median"], b["fanout_median"])
        # peak hours / preferred days
        self.assertEqual(m["rhythm"]["peak_hours_local"],
                         stats["rhythm"]["peak_hours_local"])
        self.assertEqual(m["rhythm"]["preferred_days"],
                         stats["rhythm"]["preferred_days"])


class TestGA2BuildSummaryMonthly(unittest.TestCase):
    """GA2: build_summary() exposes noticed_stats_monthly + reconciles with progression_monthly."""

    def _two_month_rows(self):
        """Two months of Claude turns with distinct token counts for isolation checks."""
        rows = []
        rows += _claude_turn("ga2-jan", "2026-01-10T10:00:00.000Z", tool="Edit",
                             file_path="/Users/demo/proj/a.py",
                             new_string="line1\nline2\nline3",
                             prompt="please do jan one",
                             usage={"input_tokens": 200, "output_tokens": 20,
                                    "cache_read_input_tokens": 10,
                                    "cache_creation_input_tokens": 2})
        rows += _claude_turn("ga2-jan", "2026-01-10T10:05:00.000Z", tool="Read",
                             file_path="/Users/demo/proj/a.py",
                             prompt="jan two")
        rows += _claude_turn("ga2-feb", "2026-02-15T09:00:00.000Z", tool="Write",
                             file_path="/Users/demo/proj/b.py",
                             new_string="alpha\nbeta",
                             prompt="feb one",
                             usage={"input_tokens": 400, "output_tokens": 40,
                                    "cache_read_input_tokens": 0,
                                    "cache_creation_input_tokens": 0})
        rows += _claude_turn("ga2-feb", "2026-02-15T09:05:00.000Z", tool="Read",
                             prompt="feb two")
        rows += _claude_turn("ga2-feb", "2026-02-15T09:10:00.000Z", tool="Grep",
                             prompt="feb three")
        return rows

    def _run(self, rows):
        return _run_claude_transcript(self, rows)

    # ------------------------------------------------------------------
    # noticed_stats_monthly present in build_summary() output
    # ------------------------------------------------------------------

    # NOTE: noticed_stats_monthly is KEPT in the build_summary() payload — mirdash's
    # ingest route unpacks it into the buildMetricMonthlyStats table. The per-month data
    # lives on stats["monthly_noticed_stats"] and is mirrored verbatim into the summary.

    def test_noticed_stats_monthly_in_summary(self):
        """summary must carry noticed_stats_monthly, mirroring stats['monthly_noticed_stats']."""
        stats = self._run(self._two_month_rows())
        summary = paxel.build_summary(stats)
        self.assertIn("monthly_noticed_stats", stats)
        self.assertIn("noticed_stats_monthly", summary)
        self.assertEqual(summary["noticed_stats_monthly"], stats["monthly_noticed_stats"])

    def test_noticed_stats_monthly_non_empty_for_multi_month(self):
        """monthly_noticed_stats is a non-empty list when window spans >=1 month."""
        stats = self._run(self._two_month_rows())
        nsm = stats["monthly_noticed_stats"]
        self.assertIsInstance(nsm, list)
        self.assertGreater(len(nsm), 0)

    def test_noticed_stats_monthly_entry_shape(self):
        """Each entry must carry month, range_start, range_end, stats, token_usage."""
        stats = self._run(self._two_month_rows())
        for entry in stats["monthly_noticed_stats"]:
            self.assertIn("month", entry)
            self.assertIn("range_start", entry)
            self.assertIn("range_end", entry)
            self.assertIn("stats", entry)
            self.assertIn("token_usage", entry)

    def test_noticed_stats_monthly_stats_shape_matches_window(self):
        """Each entry's stats must have the same top-level keys as window noticed_stats."""
        stats = self._run(self._two_month_rows())
        window_keys = set(paxel._build_noticed_stats(stats))
        for entry in stats["monthly_noticed_stats"]:
            self.assertEqual(set(entry["stats"]), window_keys,
                             "monthly_noticed_stats entry shape diverged from window noticed_stats")

    # ------------------------------------------------------------------
    # progression_monthly reconciliation with monthly_noticed_stats
    # ------------------------------------------------------------------

    def test_progression_monthly_prompts_match_noticed(self):
        """progression_monthly[i].prompts == monthly_noticed_stats[i].stats.volume.total_prompts."""
        stats = self._run(self._two_month_rows())
        summary = paxel.build_summary(stats)
        pm = {e["month"]: e for e in summary["progression_monthly"]}
        nm = {e["month"]: e for e in stats["monthly_noticed_stats"]}
        self.assertEqual(set(pm), set(nm),
                         "progression_monthly and monthly_noticed_stats must cover the same months")
        for month, p in pm.items():
            n = nm[month]
            self.assertEqual(p["prompts"], n["stats"]["volume"]["total_prompts"],
                             f"prompts mismatch for {month}: "
                             f"progression={p['prompts']} noticed={n['stats']['volume']['total_prompts']}")

    def test_progression_monthly_tool_calls_match_noticed(self):
        """progression_monthly[i].tool_calls == monthly_noticed_stats[i].stats.volume.tool_calls_total."""
        stats = self._run(self._two_month_rows())
        summary = paxel.build_summary(stats)
        pm = {e["month"]: e for e in summary["progression_monthly"]}
        nm = {e["month"]: e for e in stats["monthly_noticed_stats"]}
        for month, p in pm.items():
            n = nm[month]
            self.assertEqual(p["tool_calls"], n["stats"]["volume"]["tool_calls_total"],
                             f"tool_calls mismatch for {month}: "
                             f"progression={p['tool_calls']} noticed={n['stats']['volume']['tool_calls_total']}")

    def test_progression_monthly_tokens_total_match_noticed(self):
        """progression_monthly[i].tokens_total == sum of monthly_noticed_stats[i].token_usage totals."""
        stats = self._run(self._two_month_rows())
        summary = paxel.build_summary(stats)
        pm = {e["month"]: e for e in summary["progression_monthly"]}
        nm = {e["month"]: e for e in stats["monthly_noticed_stats"]}
        for month, p in pm.items():
            n = nm[month]
            tu = n["token_usage"]
            expected_total = (tu["total_input"] + tu["total_output"]
                              + tu["total_cache_read"] + tu["total_cache_creation"])
            self.assertEqual(p["tokens_total"], expected_total,
                             f"tokens_total mismatch for {month}: "
                             f"progression={p['tokens_total']} noticed_sum={expected_total}")

    def test_progression_monthly_order_matches_noticed(self):
        """Both lists must be in the same chronological order."""
        stats = self._run(self._two_month_rows())
        summary = paxel.build_summary(stats)
        pm_months = [e["month"] for e in summary["progression_monthly"]]
        nm_months = [e["month"] for e in stats["monthly_noticed_stats"]]
        self.assertEqual(pm_months, sorted(pm_months), "progression_monthly not chronological")
        self.assertEqual(nm_months, sorted(nm_months), "noticed_stats_monthly not chronological")
        # same set of months in same order
        self.assertEqual(pm_months, nm_months,
                         "progression_monthly and noticed_stats_monthly month order must match")


def _claude_prompt_only(sid, ts, cwd="/Users/demo/proj", model="claude-opus-4-8",
                        prompt="just a question"):
    """One user prompt + one assistant text-only reply — NO tool_use block.
    Month-level tool count stays at zero for this turn."""
    return [
        {"type": "user", "sessionId": sid, "cwd": cwd, "timestamp": ts,
         "message": {"role": "user", "content": prompt}},
        {"type": "assistant", "sessionId": sid, "cwd": cwd, "timestamp": ts,
         "message": {"role": "assistant", "model": model,
                     "content": [{"type": "text", "text": "Sure, here you go."}]}},
    ]


class TestPerMonthNullHonesty(unittest.TestCase):
    """Validate that per-month null-honesty uses per-month tool activity, not
    the window-level flag.  A month with ZERO tools inside a window that DOES
    have tools must report None (not 0) for iteration depth, error rate,
    error recovery ratio, and fanout median."""

    def _two_month_rows_tool_then_none(self):
        """Month A (Jan): tool activity (Edit + Read + an error).
        Month B (Feb): two prompts but ZERO tool calls."""
        rows = []
        # January — real tool activity: Edit file_a twice (depth 2), one error
        rows += _claude_turn("jan-a", "2026-01-10T10:00:00.000Z", tool="Edit",
                             file_path="/Users/demo/proj/file_a.py",
                             new_string="line1\nline2", prompt="jan edit one",
                             is_error=False)
        rows += _claude_turn("jan-a", "2026-01-10T10:05:00.000Z", tool="Edit",
                             file_path="/Users/demo/proj/file_a.py",
                             new_string="line3\nline4", prompt="jan edit two",
                             is_error=True)
        rows += _claude_turn("jan-a", "2026-01-10T10:10:00.000Z", tool="Edit",
                             file_path="/Users/demo/proj/file_a.py",
                             new_string="line5", prompt="jan edit three (recovery)")
        # February — prompts only, no tools at all
        rows += _claude_prompt_only("feb-b", "2026-02-05T09:00:00.000Z",
                                    prompt="feb question one")
        rows += _claude_prompt_only("feb-b", "2026-02-05T09:05:00.000Z",
                                    prompt="feb question two")
        return rows

    def test_toolless_month_iteration_depth_is_none(self):
        """Month with zero tools: iteration depth stats must all be None."""
        stats = _run_claude_transcript(self, self._two_month_rows_tool_then_none())
        mns = {e["month"]: e for e in stats["monthly_noticed_stats"]}
        feb = mns["2026-02"]["stats"]
        self.assertIsNone(feb["iteration"]["depth_mean"],
                          "depth_mean must be None for a tool-less month")
        self.assertIsNone(feb["iteration"]["depth_median"],
                          "depth_median must be None for a tool-less month")
        self.assertIsNone(feb["iteration"]["depth_max"],
                          "depth_max must be None for a tool-less month")

    def test_toolless_month_error_rate_is_none(self):
        """Month with zero tools: error_rate_per_100_tools must be None."""
        stats = _run_claude_transcript(self, self._two_month_rows_tool_then_none())
        mns = {e["month"]: e for e in stats["monthly_noticed_stats"]}
        feb = mns["2026-02"]["stats"]
        self.assertIsNone(feb["errors"]["error_rate_per_100_tools"],
                          "error_rate_per_100_tools must be None for a tool-less month")

    def test_toolless_month_error_recovery_ratio_is_none(self):
        """Month with zero tools: error_recovery_ratio must be None."""
        stats = _run_claude_transcript(self, self._two_month_rows_tool_then_none())
        mns = {e["month"]: e for e in stats["monthly_noticed_stats"]}
        feb = mns["2026-02"]["stats"]
        self.assertIsNone(feb["errors"]["error_recovery_ratio"],
                          "error_recovery_ratio must be None for a tool-less month")

    def test_toolless_month_fanout_median_is_none(self):
        """Month with zero tools: fanout_median must be None."""
        stats = _run_claude_transcript(self, self._two_month_rows_tool_then_none())
        mns = {e["month"]: e for e in stats["monthly_noticed_stats"]}
        feb = mns["2026-02"]["stats"]
        self.assertIsNone(feb["agents"]["fanout_median"],
                          "fanout_median must be None for a tool-less month")

    def test_tool_active_month_has_real_values(self):
        """Month A (Jan) has tool activity: iteration and error stats must be real numbers."""
        stats = _run_claude_transcript(self, self._two_month_rows_tool_then_none())
        mns = {e["month"]: e for e in stats["monthly_noticed_stats"]}
        jan = mns["2026-01"]["stats"]
        self.assertIsNotNone(jan["iteration"]["depth_mean"],
                             "depth_mean should be a real number for Jan (has tools)")
        self.assertIsNotNone(jan["errors"]["error_rate_per_100_tools"],
                             "error_rate_per_100_tools should be a real number for Jan")
        self.assertIsNotNone(jan["errors"]["error_recovery_ratio"],
                             "error_recovery_ratio should be a real number for Jan")

    def test_window_level_flags_unchanged(self):
        """Window behavior block must NOT be affected by the per-month fix."""
        stats = _run_claude_transcript(self, self._two_month_rows_tool_then_none())
        # Window has tool activity (Jan contributed 3 Edit calls), so these are real
        self.assertIsNotNone(stats["behavior"]["iteration_depth_mean"],
                             "Window iteration_depth_mean should not be None")
        self.assertIsNotNone(stats["behavior"]["error_rate_per_100_tools"],
                             "Window error_rate_per_100_tools should not be None")
        self.assertIsNotNone(stats["behavior"]["error_recovery_ratio"],
                             "Window error_recovery_ratio should not be None")


if __name__ == "__main__":
    unittest.main(verbosity=2)
