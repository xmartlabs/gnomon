"""Tests for per-model / per-month token-usage extraction.

Covers:
  1. Basic accumulation — assistant events with usage produce correct totals in
     token_usage (top-level), model_usage (per entry), and progression (per month).
  2. Defensive paths — absent usage, None usage, missing individual fields,
     and non-int values all contribute 0 without crashing.
  3. build_summary surfaces token_usage at the top level.
  4. Multiple models across multiple months — aggregation boundaries are respected.
"""

import contextlib
import io
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FIX = os.path.join(HERE, "fixtures")
sys.path.insert(0, ROOT)
import paxel  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers — build minimal JSONL fixture bytes
# ---------------------------------------------------------------------------

def _assistant_event(model, ts, usage=None, session="s1"):
    """Return a Claude-format assistant JSONL line dict."""
    msg = {"role": "assistant", "model": model, "content": []}
    if usage is not None:
        msg["usage"] = usage
    return {
        "type": "assistant",
        "sessionId": session,
        "cwd": "/repo",
        "timestamp": ts,
        "message": msg,
    }


def _user_event(ts, text="hi", session="s1"):
    return {
        "type": "user",
        "sessionId": session,
        "cwd": "/repo",
        "timestamp": ts,
        "message": {"role": "user", "content": text},
    }


def _write_jsonl(path, events):
    with open(path, "w") as fh:
        for ev in events:
            fh.write(json.dumps(ev) + "\n")


# ---------------------------------------------------------------------------
# Fixtures that run main() against synthetic transcripts
# ---------------------------------------------------------------------------

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


def _run_with_events(testcase, events, extra_src_dirs=None):
    """Write *events* to a temporary Claude project dir, run main(), return stats dict."""
    out = tempfile.mkdtemp(prefix="paxel-tok-test-")
    claude_dir = tempfile.mkdtemp(prefix="paxel-tok-claude-")
    proj_dir = os.path.join(claude_dir, "proj-tok")
    os.makedirs(proj_dir)
    sess_path = os.path.join(proj_dir, "session.jsonl")
    _write_jsonl(sess_path, events)
    testcase.addCleanup(shutil.rmtree, out, ignore_errors=True)
    testcase.addCleanup(shutil.rmtree, claude_dir, ignore_errors=True)

    src_overrides = dict(SRC_DIRS)
    src_overrides["BASE"] = claude_dir
    # Point other sources at empty/non-existent dirs so only our events fire
    src_overrides["CODEX_DIR"] = os.path.join(claude_dir, "_nope_codex")
    src_overrides["GEMINI_DIR"] = os.path.join(claude_dir, "_nope_gemini")
    src_overrides["ANTIGRAVITY_CLI_DIR"] = os.path.join(claude_dir, "_nope_ag")
    src_overrides["ANTIGRAVITY_DB"] = os.path.join(claude_dir, "_nope.vscdb")
    src_overrides["PI_DIR"] = os.path.join(claude_dir, "_nope_pi")
    src_overrides["OPENCODE_DIR"] = os.path.join(claude_dir, "_nope_oc")
    src_overrides["CURSOR_DIR"] = os.path.join(claude_dir, "_nope_cursor")
    src_overrides["CURSOR_DB"] = os.path.join(claude_dir, "_nope.vscdb")
    if extra_src_dirs:
        src_overrides.update(extra_src_dirs)

    argv = ["paxel.py", "--no-open"]
    buf = io.StringIO()
    with mock.patch.multiple(paxel, OUT_DIR=out, **src_overrides), \
            mock.patch.object(sys, "argv", argv), \
            contextlib.redirect_stdout(buf):
        paxel.main()

    stats_path = os.path.join(out, "stats.json")
    with open(stats_path) as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# 1. Basic accumulation
# ---------------------------------------------------------------------------

class TestBasicTokenAccumulation(unittest.TestCase):
    """Two assistant turns, same model, same month; token counts must sum correctly."""

    def setUp(self):
        events = [
            _user_event("2026-01-10T10:00:00.000Z"),
            _assistant_event(
                "claude-opus-4-8", "2026-01-10T10:00:05.000Z",
                usage={"input_tokens": 100, "output_tokens": 50,
                       "cache_read_input_tokens": 200, "cache_creation_input_tokens": 300},
            ),
            _user_event("2026-01-10T10:01:00.000Z"),
            _assistant_event(
                "claude-opus-4-8", "2026-01-10T10:01:05.000Z",
                usage={"input_tokens": 400, "output_tokens": 150,
                       "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
            ),
        ]
        self.stats = _run_with_events(self, events)

    def test_token_usage_present_in_stats(self):
        self.assertIn("token_usage", self.stats)

    def test_total_input(self):
        self.assertEqual(self.stats["token_usage"]["total_input"], 500)

    def test_total_output(self):
        self.assertEqual(self.stats["token_usage"]["total_output"], 200)

    def test_total_cache_read(self):
        self.assertEqual(self.stats["token_usage"]["total_cache_read"], 200)

    def test_total_cache_creation(self):
        self.assertEqual(self.stats["token_usage"]["total_cache_creation"], 300)

    def test_by_model_has_one_entry(self):
        self.assertEqual(len(self.stats["token_usage"]["by_model"]), 1)

    def test_by_model_raw_id(self):
        entry = self.stats["token_usage"]["by_model"][0]
        self.assertEqual(entry["model_id"], "claude-opus-4-8")

    def test_by_model_pretty(self):
        entry = self.stats["token_usage"]["by_model"][0]
        # _pretty_model("claude-opus-4-8") == "Opus 4.8"
        self.assertEqual(entry["model"], paxel._pretty_model("claude-opus-4-8"))

    def test_by_model_input(self):
        entry = self.stats["token_usage"]["by_model"][0]
        self.assertEqual(entry["input"], 500)

    def test_by_model_output(self):
        entry = self.stats["token_usage"]["by_model"][0]
        self.assertEqual(entry["output"], 200)

    def test_by_model_cache_read(self):
        entry = self.stats["token_usage"]["by_model"][0]
        self.assertEqual(entry["cache_read"], 200)

    def test_by_model_cache_creation(self):
        entry = self.stats["token_usage"]["by_model"][0]
        self.assertEqual(entry["cache_creation"], 300)


# ---------------------------------------------------------------------------
# 2. Defensive paths (absent / None / partial / non-int usage)
# ---------------------------------------------------------------------------

class TestDefensiveUsageHandling(unittest.TestCase):
    """Events with missing or malformed usage must not crash and contribute 0."""

    def _run_single(self, usage_value):
        events = [
            _user_event("2026-02-01T09:00:00.000Z"),
            _assistant_event("claude-sonnet-4-5", "2026-02-01T09:00:05.000Z",
                             usage=usage_value),
        ]
        return _run_with_events(self, events)

    def test_no_usage_key_does_not_crash(self):
        """Assistant event with NO usage key at all."""
        events = [
            _user_event("2026-02-01T09:00:00.000Z"),
            # _assistant_event without usage= arg omits the key entirely
            _assistant_event("claude-sonnet-4-5", "2026-02-01T09:00:05.000Z"),
        ]
        stats = _run_with_events(self, events)
        self.assertIn("token_usage", stats)
        tu = stats["token_usage"]
        self.assertEqual(tu["total_input"], 0)
        self.assertEqual(tu["total_output"], 0)

    def test_none_usage_contributes_zero(self):
        stats = self._run_single(None)
        tu = stats["token_usage"]
        self.assertEqual(tu["total_input"], 0)
        self.assertEqual(tu["total_output"], 0)
        self.assertEqual(tu["total_cache_read"], 0)
        self.assertEqual(tu["total_cache_creation"], 0)

    def test_empty_dict_usage_contributes_zero(self):
        stats = self._run_single({})
        tu = stats["token_usage"]
        self.assertEqual(tu["total_input"], 0)
        self.assertEqual(tu["total_output"], 0)

    def test_partial_usage_only_input(self):
        """Only input_tokens present; output/cache fields default to 0."""
        stats = self._run_single({"input_tokens": 77})
        tu = stats["token_usage"]
        self.assertEqual(tu["total_input"], 77)
        self.assertEqual(tu["total_output"], 0)
        self.assertEqual(tu["total_cache_read"], 0)
        self.assertEqual(tu["total_cache_creation"], 0)

    def test_non_int_value_coerced(self):
        """Non-int values (e.g. float or string) must be safely coerced."""
        stats = self._run_single({"input_tokens": "50", "output_tokens": 3.7})
        tu = stats["token_usage"]
        self.assertIsInstance(tu["total_input"], int)
        self.assertIsInstance(tu["total_output"], int)
        self.assertEqual(tu["total_input"], 50)
        self.assertEqual(tu["total_output"], 3)

    def test_non_numeric_string_does_not_crash_and_contributes_zero(self):
        """Genuinely non-numeric string (e.g. 'abc') must not raise and must contribute 0."""
        stats = self._run_single({"input_tokens": "abc", "output_tokens": "n/a",
                                  "cache_read_input_tokens": "?", "cache_creation_input_tokens": "x"})
        tu = stats["token_usage"]
        self.assertEqual(tu["total_input"], 0)
        self.assertEqual(tu["total_output"], 0)
        self.assertEqual(tu["total_cache_read"], 0)
        self.assertEqual(tu["total_cache_creation"], 0)

    def test_by_model_zero_counts_present(self):
        """Even with zero tokens the model still appears in by_model (it was used)."""
        stats = self._run_single({})
        by_m = stats["token_usage"]["by_model"]
        model_ids = [e["model_id"] for e in by_m]
        self.assertIn("claude-sonnet-4-5", model_ids)


# ---------------------------------------------------------------------------
# 3. Progression — monthly token sums
# ---------------------------------------------------------------------------

class TestProgressionMonthlyTokens(unittest.TestCase):
    """Events spread across two months must produce correct per-month token totals."""

    def setUp(self):
        events = [
            # January — model A
            _user_event("2026-01-05T10:00:00.000Z", session="sA"),
            _assistant_event(
                "claude-opus-4-8", "2026-01-05T10:00:05.000Z",
                usage={"input_tokens": 10, "output_tokens": 5,
                       "cache_read_input_tokens": 0, "cache_creation_input_tokens": 20},
                session="sA",
            ),
            # February — model B
            _user_event("2026-02-10T11:00:00.000Z", session="sB"),
            _assistant_event(
                "claude-sonnet-4-6", "2026-02-10T11:00:05.000Z",
                usage={"input_tokens": 30, "output_tokens": 15,
                       "cache_read_input_tokens": 5, "cache_creation_input_tokens": 0},
                session="sB",
            ),
            # February — another turn
            _user_event("2026-02-15T12:00:00.000Z", session="sB"),
            _assistant_event(
                "claude-sonnet-4-6", "2026-02-15T12:00:05.000Z",
                usage={"input_tokens": 70, "output_tokens": 35,
                       "cache_read_input_tokens": 10, "cache_creation_input_tokens": 0},
                session="sB",
            ),
        ]
        self.stats = _run_with_events(self, events)

    def _month_entry(self, ym):
        for entry in self.stats["progression"]["monthly"]:
            if entry["month"] == ym:
                return entry
        return None

    def test_january_tokens_input(self):
        jan = self._month_entry("2026-01")
        self.assertIsNotNone(jan)
        self.assertEqual(jan["tokens_input"], 10)

    def test_january_tokens_output(self):
        jan = self._month_entry("2026-01")
        self.assertEqual(jan["tokens_output"], 5)

    def test_january_tokens_cache_creation(self):
        jan = self._month_entry("2026-01")
        self.assertEqual(jan["tokens_cache_creation"], 20)

    def test_january_tokens_total(self):
        jan = self._month_entry("2026-01")
        # 10 + 5 + 0 + 20 = 35
        self.assertEqual(jan["tokens_total"], 35)

    def test_february_tokens_input(self):
        feb = self._month_entry("2026-02")
        self.assertIsNotNone(feb)
        self.assertEqual(feb["tokens_input"], 100)

    def test_february_tokens_output(self):
        feb = self._month_entry("2026-02")
        self.assertEqual(feb["tokens_output"], 50)

    def test_february_tokens_cache_read(self):
        feb = self._month_entry("2026-02")
        self.assertEqual(feb["tokens_cache_read"], 15)

    def test_february_tokens_total(self):
        feb = self._month_entry("2026-02")
        # 100 + 50 + 15 + 0 = 165
        self.assertEqual(feb["tokens_total"], 165)


# ---------------------------------------------------------------------------
# 4. Multiple models — by_model ordering and per-model breakdown
# ---------------------------------------------------------------------------

class TestMultipleModels(unittest.TestCase):
    """Two distinct models; by_model entries are ordered by total tokens desc."""

    def setUp(self):
        events = [
            _user_event("2026-03-01T10:00:00.000Z", session="s1"),
            # Model A — heavy usage (total 600)
            _assistant_event(
                "claude-opus-4-8", "2026-03-01T10:00:05.000Z",
                usage={"input_tokens": 300, "output_tokens": 200,
                       "cache_read_input_tokens": 50, "cache_creation_input_tokens": 50},
                session="s1",
            ),
            _user_event("2026-03-02T10:00:00.000Z", session="s2"),
            # Model B — light usage (total 10)
            _assistant_event(
                "claude-haiku-4-5", "2026-03-02T10:00:05.000Z",
                usage={"input_tokens": 5, "output_tokens": 5,
                       "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
                session="s2",
            ),
        ]
        self.stats = _run_with_events(self, events)

    def test_two_models_in_by_model(self):
        by_m = self.stats["token_usage"]["by_model"]
        self.assertEqual(len(by_m), 2)

    def test_by_model_ordered_desc_by_total(self):
        by_m = self.stats["token_usage"]["by_model"]
        totals = [e["input"] + e["output"] + e["cache_read"] + e["cache_creation"]
                  for e in by_m]
        self.assertGreaterEqual(totals[0], totals[1])

    def test_global_totals_sum_across_models(self):
        tu = self.stats["token_usage"]
        self.assertEqual(tu["total_input"], 305)
        self.assertEqual(tu["total_output"], 205)
        self.assertEqual(tu["total_cache_read"], 50)
        self.assertEqual(tu["total_cache_creation"], 50)

    def test_model_usage_includes_raw_model_id(self):
        """_build_profile model_usage entries must include model_id."""
        profile = self.stats.get("agentic") or {}
        # model_usage lives under the profile that build_summary assembles;
        # in stats.json it's in stack.models — check build_summary directly.
        summary = paxel.build_summary(self.stats)
        mu = summary["profile"]["model_usage"]
        ids = [e["model_id"] for e in mu]
        self.assertIn("claude-opus-4-8", ids)

    def test_model_usage_has_token_fields(self):
        summary = paxel.build_summary(self.stats)
        mu = summary["profile"]["model_usage"]
        for entry in mu:
            self.assertIn("tokens_input", entry)
            self.assertIn("tokens_output", entry)
            self.assertIn("tokens_cache_read", entry)
            self.assertIn("tokens_cache_creation", entry)

    def test_model_usage_token_counts_correct(self):
        summary = paxel.build_summary(self.stats)
        mu = summary["profile"]["model_usage"]
        opus_entry = next(e for e in mu if e["model_id"] == "claude-opus-4-8")
        self.assertEqual(opus_entry["tokens_input"], 300)
        self.assertEqual(opus_entry["tokens_output"], 200)
        self.assertEqual(opus_entry["tokens_cache_read"], 50)
        self.assertEqual(opus_entry["tokens_cache_creation"], 50)


# ---------------------------------------------------------------------------
# 5. build_summary — token_usage at top level
# ---------------------------------------------------------------------------

class TestBuildSummaryTokenUsage(unittest.TestCase):
    """build_summary must include token_usage at the top level."""

    def setUp(self):
        events = [
            _user_event("2026-04-01T10:00:00.000Z"),
            _assistant_event(
                "claude-opus-4-8", "2026-04-01T10:00:05.000Z",
                usage={"input_tokens": 111, "output_tokens": 222,
                       "cache_read_input_tokens": 333, "cache_creation_input_tokens": 444},
            ),
        ]
        self.stats = _run_with_events(self, events)
        self.summary = paxel.build_summary(self.stats)

    def test_token_usage_key_present(self):
        self.assertIn("token_usage", self.summary)

    def test_total_input(self):
        self.assertEqual(self.summary["token_usage"]["total_input"], 111)

    def test_total_output(self):
        self.assertEqual(self.summary["token_usage"]["total_output"], 222)

    def test_total_cache_read(self):
        self.assertEqual(self.summary["token_usage"]["total_cache_read"], 333)

    def test_total_cache_creation(self):
        self.assertEqual(self.summary["token_usage"]["total_cache_creation"], 444)

    def test_by_model_list(self):
        by_m = self.summary["token_usage"]["by_model"]
        self.assertIsInstance(by_m, list)
        self.assertEqual(len(by_m), 1)

    def test_by_model_entry_shape(self):
        entry = self.summary["token_usage"]["by_model"][0]
        for key in ("model_id", "model", "input", "output", "cache_read", "cache_creation"):
            self.assertIn(key, entry, f"missing key: {key}")

    def test_by_model_model_id_raw(self):
        entry = self.summary["token_usage"]["by_model"][0]
        self.assertEqual(entry["model_id"], "claude-opus-4-8")

    def test_by_model_model_pretty(self):
        entry = self.summary["token_usage"]["by_model"][0]
        self.assertEqual(entry["model"], paxel._pretty_model("claude-opus-4-8"))


# ---------------------------------------------------------------------------
# 6. Zero-activity corpus — no crash, well-formed empty payload
# ---------------------------------------------------------------------------

class TestZeroActivityTokenUsage(unittest.TestCase):
    """Empty corpus must produce a valid token_usage block (all zeros, empty list)."""

    def setUp(self):
        # Single user event, no assistant turns at all
        events = [_user_event("2026-05-01T10:00:00.000Z")]
        self.stats = _run_with_events(self, events)
        self.summary = paxel.build_summary(self.stats)

    def test_token_usage_present(self):
        self.assertIn("token_usage", self.stats)
        self.assertIn("token_usage", self.summary)

    def test_totals_are_zero(self):
        tu = self.stats["token_usage"]
        self.assertEqual(tu["total_input"], 0)
        self.assertEqual(tu["total_output"], 0)
        self.assertEqual(tu["total_cache_read"], 0)
        self.assertEqual(tu["total_cache_creation"], 0)

    def test_by_model_is_empty_list(self):
        self.assertEqual(self.stats["token_usage"]["by_model"], [])



# ---------------------------------------------------------------------------
# 7. Gemini adapter — token mapping via real-format fixture
# ---------------------------------------------------------------------------

class TestGeminiTokenMapping(unittest.TestCase):
    """_gemini_events must translate m.tokens into Claude-style usage keys.

    Fixture values (from tests/fixtures/gemini/session-gemini.json):
      input=1500, output=42, cached=800, thoughts=120, total=2462

    Expected translation:
      input_tokens              = input  = 1500
      output_tokens             = output + thoughts = 42 + 120 = 162
      cache_read_input_tokens   = cached = 800
      cache_creation_input_tokens = 0
    """

    FP = os.path.join(FIX, "gemini", "session-gemini.json")

    def setUp(self):
        self.events = list(paxel._gemini_events(self.FP))
        self.asst = [e for e in self.events if e.get("type") == "assistant"]

    def test_assistant_event_present(self):
        self.assertTrue(self.asst, "no assistant event from gemini fixture")

    def test_usage_input_tokens(self):
        usage = self.asst[0]["message"].get("usage", {})
        self.assertEqual(usage.get("input_tokens"), 1500)

    def test_usage_output_tokens_folds_thoughts(self):
        usage = self.asst[0]["message"].get("usage", {})
        self.assertEqual(usage.get("output_tokens"), 162)  # 42 + 120

    def test_usage_cache_read_from_cached(self):
        usage = self.asst[0]["message"].get("usage", {})
        self.assertEqual(usage.get("cache_read_input_tokens"), 800)

    def test_usage_cache_creation_is_zero(self):
        usage = self.asst[0]["message"].get("usage", {})
        self.assertEqual(usage.get("cache_creation_input_tokens"), 0)

    def test_full_pipeline_gemini_model_appears_in_token_usage(self):
        """Running paxel.main() against only the Gemini fixture must yield a token row
        for gemini-2.5-pro."""
        out = tempfile.mkdtemp(prefix="paxel-gemini-tok-")
        gemini_dir = os.path.join(FIX, "gemini")
        self.addCleanup(shutil.rmtree, out, ignore_errors=True)
        argv = ["paxel.py", "--no-open"]
        buf = io.StringIO()
        empty = tempfile.mkdtemp(prefix="paxel-gemini-empty-")
        self.addCleanup(shutil.rmtree, empty, ignore_errors=True)
        overrides = dict(
            BASE=empty,
            CODEX_DIR=empty,
            GEMINI_DIR=gemini_dir,
            ANTIGRAVITY_CLI_DIR=empty, ANTIGRAVITY_DB=os.path.join(empty, "nope.vscdb"),
            PI_DIR=empty,
            OPENCODE_DIR=empty,
            CURSOR_DIR=empty,
            CURSOR_DB=os.path.join(empty, "nope.vscdb"),
        )
        with mock.patch.multiple(paxel, OUT_DIR=out, **overrides), \
                mock.patch.object(sys, "argv", argv), \
                contextlib.redirect_stdout(buf):
            paxel.main()
        with open(os.path.join(out, "stats.json")) as fh:
            stats = json.load(fh)
        by_model = stats["token_usage"]["by_model"]
        model_ids = [e["model_id"] for e in by_model]
        self.assertIn("gemini-2.5-pro", model_ids,
                      f"gemini-2.5-pro not in token_usage.by_model: {model_ids}")
        entry = next(e for e in by_model if e["model_id"] == "gemini-2.5-pro")
        self.assertEqual(entry["input"], 1500)
        self.assertEqual(entry["output"], 162)
        self.assertEqual(entry["cache_read"], 800)


# ---------------------------------------------------------------------------
# 8. Codex token_count → model-mix (A8)
# ---------------------------------------------------------------------------

class TestCodexTokenMapping(unittest.TestCase):
    """_codex_events must translate token_count event_msg into a usage-bearing assistant
    event, and the full pipeline must produce a token_usage row for the Codex model.

    Fixture values (tests/fixtures/codex/session-codex.jsonl):
      total_token_usage: input=5000, cached=3000, output=120, reasoning=80
    Expected Claude-shape:
      input_tokens              = input - cached = 2000
      output_tokens             = output + reasoning = 200
      cache_read_input_tokens   = cached = 3000
      cache_creation_input_tokens = 0
    """

    FP = os.path.join(FIX, "codex", "session-codex.jsonl")

    def setUp(self):
        self.events = list(paxel._codex_events(self.FP))
        self.usage_events = [e for e in self.events if e.get("__codex_usage__")]

    def test_usage_event_present(self):
        self.assertTrue(self.usage_events, "no __codex_usage__ assistant event found")

    def test_input_tokens_minus_cached(self):
        u = self.usage_events[0]["message"]["usage"]
        self.assertEqual(u["input_tokens"], 2000)

    def test_output_tokens_folds_reasoning(self):
        u = self.usage_events[0]["message"]["usage"]
        self.assertEqual(u["output_tokens"], 200)

    def test_cache_read_from_cached(self):
        u = self.usage_events[0]["message"]["usage"]
        self.assertEqual(u["cache_read_input_tokens"], 3000)

    def test_cache_creation_is_zero(self):
        u = self.usage_events[0]["message"]["usage"]
        self.assertEqual(u["cache_creation_input_tokens"], 0)

    def test_model_is_set(self):
        self.assertEqual(self.usage_events[0]["message"]["model"], "gpt-5.4")

    def test_full_pipeline_codex_model_in_token_usage(self):
        """Running paxel.main() with only the Codex fixture must yield a gpt-5.4 token row."""
        out = tempfile.mkdtemp(prefix="paxel-codex-tok-")
        codex_dir = os.path.dirname(self.FP)
        self.addCleanup(shutil.rmtree, out, ignore_errors=True)
        empty = tempfile.mkdtemp(prefix="paxel-codex-empty-")
        self.addCleanup(shutil.rmtree, empty, ignore_errors=True)
        overrides = dict(
            BASE=empty,
            CODEX_DIR=codex_dir,
            GEMINI_DIR=empty,
            ANTIGRAVITY_CLI_DIR=empty, ANTIGRAVITY_DB=os.path.join(empty, "nope.vscdb"),
            PI_DIR=empty,
            OPENCODE_DIR=empty,
            CURSOR_DIR=empty,
            CURSOR_DB=os.path.join(empty, "nope.vscdb"),
        )
        argv = ["paxel.py", "--no-open"]
        buf = io.StringIO()
        with mock.patch.multiple(paxel, OUT_DIR=out, **overrides), \
                mock.patch.object(sys, "argv", argv), \
                contextlib.redirect_stdout(buf):
            paxel.main()
        with open(os.path.join(out, "stats.json")) as fh:
            stats = json.load(fh)
        by_model = stats["token_usage"]["by_model"]
        model_ids = [e["model_id"] for e in by_model]
        self.assertIn("gpt-5.4", model_ids,
                      f"gpt-5.4 not in token_usage.by_model: {model_ids}")
        entry = next(e for e in by_model if e["model_id"] == "gpt-5.4")
        self.assertEqual(entry["input"], 2000)
        self.assertEqual(entry["output"], 200)
        self.assertEqual(entry["cache_read"], 3000)


# ---------------------------------------------------------------------------
# 9. Cursor token_count → model-mix (A4)
# ---------------------------------------------------------------------------

class TestCursorTokenExtraction(unittest.TestCase):
    """_cursor_sqlite_events must extract bubble.tokenCount and emit a usage-bearing
    assistant event. Type-2 bubble with tokenCount → "cursor" row; zero tokens → no row.
    """

    def test_cursor_token_bearing_bubble_yields_usage_event(self):
        """A Cursor type-2 bubble with tokenCount.{inputTokens,outputTokens} must emit
        an assistant event with model:"cursor" and proper usage dict."""
        # We'll use the real fixture and verify the event stream directly.
        db_path = os.path.join(FIX, "cursor", "state.vscdb")
        # Since the fixture is real SQLite, _cursor_sqlite_events will read from it.
        # We expect a usage event for the cursor bubble with tokenCount.
        events = list(paxel._cursor_sqlite_events(db_path))
        # Filter for assistant events with model:"cursor" and usage
        usage_events = [e for e in events if e.get("type") == "assistant"
                        and e.get("message", {}).get("model") == "cursor"
                        and e.get("message", {}).get("usage")]
        # The fixture has a token-bearing type-2 bubble, so we must see at least one
        self.assertTrue(usage_events, "Expected at least one cursor usage event with tokenCount")
        ev = usage_events[0]
        usage = ev["message"]["usage"]
        # Verify it has the Claude-shape fields
        self.assertIn("input_tokens", usage)
        self.assertIn("output_tokens", usage)
        self.assertIn("cache_read_input_tokens", usage)
        self.assertIn("cache_creation_input_tokens", usage)
        # Values should be ints, and at least some should be non-zero
        self.assertIsInstance(usage["input_tokens"], int)
        self.assertIsInstance(usage["output_tokens"], int)
        self.assertEqual(usage["input_tokens"], 350, "Expected 350 input tokens from fixture")
        self.assertEqual(usage["output_tokens"], 150, "Expected 150 output tokens from fixture")

    def test_cursor_zero_tokens_does_not_emit_usage_event(self):
        """Type-2 bubbles with zero tokenCount or missing tokenCount should not produce
        a cursor model entry in the final statistics (guard prevents spurious rows)."""
        # Build a minimal fixture with just type-2 bubbles but NO tokenCount,
        # run paxel.main(), and verify no "cursor" entry appears in token_usage.
        out = tempfile.mkdtemp(prefix="paxel-cursor-zero-tok-")
        cursor_dir = os.path.join(FIX, "cursor", "projects")
        # Create a temporary database with only zero-token bubbles
        import tempfile as tf
        import shutil as sh
        temp_db = tf.NamedTemporaryFile(suffix=".vscdb", delete=False)
        temp_db.close()
        self.addCleanup(sh.rmtree, out, ignore_errors=True)
        self.addCleanup(lambda: os.unlink(temp_db.name) if os.path.exists(temp_db.name) else None)

        empty = tempfile.mkdtemp(prefix="paxel-cursor-zero-empty-")
        self.addCleanup(shutil.rmtree, empty, ignore_errors=True)

        # Create a minimal zero-token database for this test
        conn = sqlite3.connect(temp_db.name)
        conn.execute("CREATE TABLE cursorDiskKV (key TEXT PRIMARY KEY, value BLOB)")
        conn.execute("INSERT INTO cursorDiskKV VALUES (?, ?)",
                     ("composerData:zero-session",
                      json.dumps({"fullConversationHeadersOnly": [
                          {"bubbleId": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "type": 2}
                      ]})))
        conn.execute("INSERT INTO cursorDiskKV VALUES (?, ?)",
                     ("bubbleId:zero-session:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                      json.dumps({"type": 2, "createdAt": "2026-01-01T10:00:00.000Z",
                                  "text": "no tokens"})))
        conn.commit()
        conn.close()

        overrides = dict(
            BASE=empty,
            CODEX_DIR=empty,
            GEMINI_DIR=empty,
            ANTIGRAVITY_CLI_DIR=empty, ANTIGRAVITY_DB=os.path.join(empty, "nope.vscdb"),
            PI_DIR=empty,
            OPENCODE_DIR=empty,
            CURSOR_DIR=cursor_dir,
            CURSOR_DB=temp_db.name,
        )
        argv = ["paxel.py", "--no-open"]
        buf = io.StringIO()
        with mock.patch.multiple(paxel, OUT_DIR=out, **overrides), \
                mock.patch.object(sys, "argv", argv), \
                contextlib.redirect_stdout(buf):
            paxel.main()
        with open(os.path.join(out, "stats.json")) as fh:
            stats = json.load(fh)
        by_model = stats["token_usage"]["by_model"]
        model_ids = [e["model_id"] for e in by_model]
        # No cursor entry should appear when there are no tokens
        self.assertNotIn("cursor", model_ids,
                         f"cursor should not appear when tokens are zero; by_model: {model_ids}")

    def test_full_pipeline_cursor_model_in_token_usage(self):
        """Running paxel.main() with only the Cursor fixture must yield a "cursor"
        token row with the expected token counts."""
        out = tempfile.mkdtemp(prefix="paxel-cursor-tok-")
        cursor_dir = os.path.join(FIX, "cursor", "projects")
        cursor_db = os.path.join(FIX, "cursor", "state.vscdb")
        self.addCleanup(shutil.rmtree, out, ignore_errors=True)
        empty = tempfile.mkdtemp(prefix="paxel-cursor-empty-")
        self.addCleanup(shutil.rmtree, empty, ignore_errors=True)
        overrides = dict(
            BASE=empty,
            CODEX_DIR=empty,
            GEMINI_DIR=empty,
            ANTIGRAVITY_CLI_DIR=empty, ANTIGRAVITY_DB=os.path.join(empty, "nope.vscdb"),
            PI_DIR=empty,
            OPENCODE_DIR=empty,
            CURSOR_DIR=cursor_dir,
            CURSOR_DB=cursor_db,
        )
        argv = ["paxel.py", "--no-open"]
        buf = io.StringIO()
        with mock.patch.multiple(paxel, OUT_DIR=out, **overrides), \
                mock.patch.object(sys, "argv", argv), \
                contextlib.redirect_stdout(buf):
            paxel.main()
        with open(os.path.join(out, "stats.json")) as fh:
            stats = json.load(fh)
        by_model = stats["token_usage"]["by_model"]
        model_ids = [e["model_id"] for e in by_model]
        # The fixture has token-bearing type-2 bubbles, so "cursor" must be in the list
        self.assertIn("cursor", model_ids,
                      f"cursor not in token_usage.by_model: {model_ids}")
        entry = next(e for e in by_model if e["model_id"] == "cursor")
        # Verify the entry has the expected shape and values
        self.assertIn("model", entry)
        self.assertEqual(entry["model"], "Cursor")
        self.assertIn("input", entry)
        self.assertIn("output", entry)
        self.assertEqual(entry["input"], 350, "Expected 350 input tokens")
        self.assertEqual(entry["output"], 150, "Expected 150 output tokens")


# ---------------------------------------------------------------------------
# 10. Codex monthly token attribution — deltas split across calendar months
# ---------------------------------------------------------------------------

class TestCodexMonthlyTokenAttribution(unittest.TestCase):
    """A Codex thread that spans a month boundary must book each token delta in the
    calendar month it occurred — not all of it in the session's last month.

    token_count carries CUMULATIVE total_token_usage, so the per-month split is the
    delta between consecutive snapshots:

      Jan snapshot (cumulative): input=2000 cached=1000 output=50 reasoning=10
        Claude shape: input = 2000-1000 = 1000, cache_read = 1000, output = 50+10 = 60
      Feb snapshot (cumulative): input=5000 cached=3000 output=120 reasoning=80
        Feb delta:    input = 3000-2000 = 1000, cache_read = 2000, output = 70+70 = 140

    Window total (sum of months) must equal the single-emission total derived from the
    final cumulative snapshot: input=2000, output=200, cache_read=3000 — unchanged.
    """

    def _write_codex(self, codex_dir):
        os.makedirs(codex_dir, exist_ok=True)
        rows = [
            {"type": "session_meta", "timestamp": "2026-01-15T10:00:00Z",
             "payload": {"id": "codex-split-1", "cwd": "/repo"}},
            {"type": "turn_context", "timestamp": "2026-01-15T10:00:01Z",
             "payload": {"model": "gpt-5.4"}},
            {"type": "response_item", "timestamp": "2026-01-15T10:00:02Z",
             "payload": {"type": "message", "role": "user",
                         "content": [{"type": "input_text", "text": "do jan work"}]}},
            # January cumulative snapshot
            {"type": "event_msg", "timestamp": "2026-01-15T10:00:09Z",
             "payload": {"type": "token_count", "info": {"total_token_usage": {
                 "input_tokens": 2000, "cached_input_tokens": 1000,
                 "output_tokens": 50, "reasoning_output_tokens": 10,
                 "total_tokens": 2060}}}},
            # ...thread continues into February
            {"type": "response_item", "timestamp": "2026-02-12T11:00:00Z",
             "payload": {"type": "message", "role": "user",
                         "content": [{"type": "input_text", "text": "do feb work"}]}},
            # February cumulative snapshot (running total)
            {"type": "event_msg", "timestamp": "2026-02-12T11:00:09Z",
             "payload": {"type": "token_count", "info": {"total_token_usage": {
                 "input_tokens": 5000, "cached_input_tokens": 3000,
                 "output_tokens": 120, "reasoning_output_tokens": 80,
                 "total_tokens": 5200}}}},
        ]
        with open(os.path.join(codex_dir, "session-split.jsonl"), "w") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")

    def setUp(self):
        out = tempfile.mkdtemp(prefix="paxel-codex-split-out-")
        codex_dir = tempfile.mkdtemp(prefix="paxel-codex-split-")
        self._write_codex(codex_dir)
        self.addCleanup(shutil.rmtree, out, ignore_errors=True)
        self.addCleanup(shutil.rmtree, codex_dir, ignore_errors=True)
        empty = tempfile.mkdtemp(prefix="paxel-codex-split-empty-")
        self.addCleanup(shutil.rmtree, empty, ignore_errors=True)
        overrides = dict(
            BASE=empty,
            CODEX_DIR=codex_dir,
            GEMINI_DIR=empty,
            ANTIGRAVITY_CLI_DIR=empty, ANTIGRAVITY_DB=os.path.join(empty, "nope.vscdb"),
            PI_DIR=empty,
            OPENCODE_DIR=empty,
            CURSOR_DIR=empty,
            CURSOR_DB=os.path.join(empty, "nope.vscdb"),
        )
        argv = ["paxel.py", "--no-open"]
        buf = io.StringIO()
        with mock.patch.multiple(paxel, OUT_DIR=out, **overrides), \
                mock.patch.object(sys, "argv", argv), \
                contextlib.redirect_stdout(buf):
            paxel.main()
        with open(os.path.join(out, "stats.json")) as fh:
            self.stats = json.load(fh)

    def _month_entry(self, ym):
        for entry in self.stats["progression"]["monthly"]:
            if entry["month"] == ym:
                return entry
        return None

    def test_january_month_present(self):
        self.assertIsNotNone(self._month_entry("2026-01"),
                             "January must appear in progression.monthly")

    def test_january_tokens_split_not_zero(self):
        jan = self._month_entry("2026-01")
        # Jan delta: input 1000, output 60, cache_read 1000 -> total 2060
        self.assertEqual(jan["tokens_input"], 1000)
        self.assertEqual(jan["tokens_output"], 60)
        self.assertEqual(jan["tokens_cache_read"], 1000)

    def test_february_tokens_split(self):
        feb = self._month_entry("2026-02")
        self.assertIsNotNone(feb)
        # Feb delta: input 1000, output 140, cache_read 2000
        self.assertEqual(feb["tokens_input"], 1000)
        self.assertEqual(feb["tokens_output"], 140)
        self.assertEqual(feb["tokens_cache_read"], 2000)

    def test_tokens_not_all_in_last_month(self):
        """Regression: before the fix ALL tokens landed in February (last month)."""
        feb = self._month_entry("2026-02")
        # The buggy single-emission would have put input=2000 in Feb.
        self.assertNotEqual(feb["tokens_input"], 2000,
                            "February must not hold the whole thread's tokens")

    def test_window_total_unchanged(self):
        """Sum across months equals the single-emission total from final cumulative."""
        tu = self.stats["token_usage"]
        self.assertEqual(tu["total_input"], 2000)
        self.assertEqual(tu["total_output"], 200)
        self.assertEqual(tu["total_cache_read"], 3000)
        self.assertEqual(tu["total_cache_creation"], 0)

    def test_monthly_sum_matches_window(self):
        jan = self._month_entry("2026-01")
        feb = self._month_entry("2026-02")
        self.assertEqual(jan["tokens_input"] + feb["tokens_input"],
                         self.stats["token_usage"]["total_input"])
        self.assertEqual(jan["tokens_output"] + feb["tokens_output"],
                         self.stats["token_usage"]["total_output"])
        self.assertEqual(jan["tokens_cache_read"] + feb["tokens_cache_read"],
                         self.stats["token_usage"]["total_cache_read"])


if __name__ == "__main__":
    unittest.main()
