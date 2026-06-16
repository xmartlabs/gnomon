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
        # measured metrics + monthly progression, and NOTHING from the rubric or any
        # verbatim text (prompts / quotes / skill names) — safe-to-share by construction.
        _, out = _run(self, ["--summary"])
        path = os.path.join(out, "summary.json")
        self.assertTrue(os.path.exists(path), "summary.json was not written")
        with open(path, encoding="utf-8") as fh:
            summary = json.load(fh)
        self.assertEqual(set(summary), {
            "context", "planning_ratio_explore_to_doing", "errors", "iteration_depth",
            "churn", "orchestration", "compounding_writes", "ecosystem",
            "progression_monthly", "profile", "token_usage"})
        # profile must have the expected sub-keys
        prof = summary["profile"]
        self.assertEqual(set(prof), {"aq", "archetype", "scores", "steering",
                                     "growth_edges", "signature_moves", "model_usage"})
        # no raw prompt/verbatim text in the shareable summary
        raw = json.dumps(summary).lower()
        for banned in ("top_skills", "prompt_text"):
            self.assertNotIn(banned, raw, f"verbatim field leaked: {banned}")

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
    """A6: a session with source.subagent.thread_spawn must emit an Agent tool_use."""

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

    def test_subagent_session_emits_agent_tool_use(self):
        import tempfile
        fp = self._make_events(is_subagent=True)
        try:
            events = list(paxel._codex_events(fp))
        finally:
            os.unlink(fp)
        agent_uses = [
            b for e in events if e.get("type") == "assistant"
            for b in (e.get("message", {}).get("content") or [])
            if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") == "Agent"
        ]
        self.assertTrue(agent_uses, "no Agent tool_use emitted for subagent session")

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
