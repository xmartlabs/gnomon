import os, sys, json, io, tempfile, shutil, contextlib, unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import paxel


def _write_jsonl(rows):
    f = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False)
    f.write("\n".join(json.dumps(r) for r in rows))
    f.close()
    return f.name


# ---------------------------------------------------------------------------
# FIX 1 — synthetic Codex Agent fan-out event must carry a timestamp so it is
# not dropped by windowed runs (--since/--until, --last, monthly uploads).
# ---------------------------------------------------------------------------

class TestCodexFanoutTimestamp(unittest.TestCase):
    def _child_rows(self):
        return [
            {"type": "session_meta", "timestamp": "2026-03-10T12:00:00Z",
             "payload": {"id": "child-1", "cwd": "/x",
                         "source": {"subagent": {"thread_spawn": {
                             "parent_thread_id": "parent-1"}}}}},
            {"type": "turn_context", "timestamp": "2026-03-10T12:00:01Z",
             "payload": {"model": "gpt-5.4"}},
            {"type": "response_item", "timestamp": "2026-03-10T12:00:02Z",
             "payload": {"type": "message", "role": "user",
                         "content": [{"type": "input_text", "text": "do the work"}]}},
        ]

    def test_synthetic_agent_event_has_timestamp(self):
        path = _write_jsonl(self._child_rows())
        try:
            evs = list(paxel._codex_events(path))
        finally:
            os.unlink(path)
        agent = [e for e in evs if e.get("sessionId") == "parent-1"]
        self.assertTrue(agent, "no synthetic Agent event keyed to the parent session")
        self.assertIsNotNone(agent[0].get("timestamp"),
                             "synthetic Agent event must carry a timestamp")
        # must parse to a datetime inside the child's window
        dt = paxel.parse_ts(agent[0]["timestamp"])
        self.assertIsNotNone(dt)
        self.assertEqual(dt.strftime("%Y-%m"), "2026-03-10"[:7])

    def test_fanout_counted_in_bounded_window(self):
        """A parent Codex session whose fan-out happens inside the window must have
        its delegate/Agent event counted, not dropped as undated."""
        codex_dir = tempfile.mkdtemp(prefix="paxel-fanout-")
        self.addCleanup(shutil.rmtree, codex_dir, ignore_errors=True)
        empty = tempfile.mkdtemp(prefix="paxel-fanout-empty-")
        self.addCleanup(shutil.rmtree, empty, ignore_errors=True)
        # child session that spawns the synthetic Agent on the parent
        child = self._child_rows()
        with open(os.path.join(codex_dir, "child.jsonl"), "w") as fh:
            fh.write("\n".join(json.dumps(r) for r in child))
        # a genuine parent session in-window (so it survives the codex empty-seed skip)
        parent = [
            {"type": "session_meta", "timestamp": "2026-03-10T11:00:00Z",
             "payload": {"id": "parent-1", "cwd": "/x"}},
            {"type": "turn_context", "timestamp": "2026-03-10T11:00:01Z",
             "payload": {"model": "gpt-5.4"}},
            {"type": "response_item", "timestamp": "2026-03-10T11:00:02Z",
             "payload": {"type": "message", "role": "user",
                         "content": [{"type": "input_text", "text": "orchestrate this"}]}},
        ]
        with open(os.path.join(codex_dir, "parent.jsonl"), "w") as fh:
            fh.write("\n".join(json.dumps(r) for r in parent))

        out = tempfile.mkdtemp(prefix="paxel-fanout-out-")
        self.addCleanup(shutil.rmtree, out, ignore_errors=True)
        overrides = dict(
            BASE=empty, CODEX_DIR=codex_dir, GEMINI_DIR=empty, PI_DIR=empty,
            OPENCODE_DIR=empty, CURSOR_DIR=empty,
            CURSOR_DB=os.path.join(empty, "nope.vscdb"),
        )
        argv = ["paxel.py", "--no-open", "--since=2026-03-01", "--until=2026-03-31"]
        buf = io.StringIO()
        with mock.patch.multiple(paxel, OUT_DIR=out, **overrides), \
                mock.patch.object(sys, "argv", argv), \
                contextlib.redirect_stdout(buf):
            paxel.main()
        with open(os.path.join(out, "stats.json")) as fh:
            stats = json.load(fh)
        agent_runs = next((c for n, c in stats["stack"].get("subagent_types", [])
                           if n == "codex-subagent"), 0)
        self.assertGreaterEqual(agent_runs, 1,
                                "fan-out Agent event was dropped in the bounded window")


# ---------------------------------------------------------------------------
# FIX 2 — synthetic Codex usage events must NOT count as assistant turns or
# inflate the model mix, but MUST still contribute their tokens.
# ---------------------------------------------------------------------------

class TestCodexUsageNotAssistantTurn(unittest.TestCase):
    def _session_rows(self):
        # one real assistant turn + multiple token_count snapshots in the same month
        return [
            {"type": "session_meta", "timestamp": "2026-04-01T10:00:00Z",
             "payload": {"id": "usage-1", "cwd": "/x"}},
            {"type": "turn_context", "timestamp": "2026-04-01T10:00:01Z",
             "payload": {"model": "gpt-5.4"}},
            {"type": "response_item", "timestamp": "2026-04-01T10:00:02Z",
             "payload": {"type": "message", "role": "user",
                         "content": [{"type": "input_text", "text": "run the build"}]}},
            {"type": "response_item", "timestamp": "2026-04-01T10:00:03Z",
             "payload": {"type": "message", "role": "assistant",
                         "content": [{"type": "output_text", "text": "on it"}]}},
            {"type": "event_msg", "timestamp": "2026-04-01T10:00:04Z",
             "payload": {"type": "token_count", "info": {"total_token_usage": {
                 "input_tokens": 1000, "cached_input_tokens": 0,
                 "output_tokens": 50, "reasoning_output_tokens": 0,
                 "total_tokens": 1050}}}},
            {"type": "event_msg", "timestamp": "2026-04-01T10:00:05Z",
             "payload": {"type": "token_count", "info": {"total_token_usage": {
                 "input_tokens": 2000, "cached_input_tokens": 0,
                 "output_tokens": 100, "reasoning_output_tokens": 0,
                 "total_tokens": 2100}}}},
        ]

    def _run(self):
        codex_dir = tempfile.mkdtemp(prefix="paxel-usage-")
        self.addCleanup(shutil.rmtree, codex_dir, ignore_errors=True)
        with open(os.path.join(codex_dir, "s.jsonl"), "w") as fh:
            fh.write("\n".join(json.dumps(r) for r in self._session_rows()))
        empty = tempfile.mkdtemp(prefix="paxel-usage-empty-")
        self.addCleanup(shutil.rmtree, empty, ignore_errors=True)
        out = tempfile.mkdtemp(prefix="paxel-usage-out-")
        self.addCleanup(shutil.rmtree, out, ignore_errors=True)
        overrides = dict(
            BASE=empty, CODEX_DIR=codex_dir, GEMINI_DIR=empty, PI_DIR=empty,
            OPENCODE_DIR=empty, CURSOR_DIR=empty,
            CURSOR_DB=os.path.join(empty, "nope.vscdb"),
        )
        argv = ["paxel.py", "--no-open"]
        buf = io.StringIO()
        with mock.patch.multiple(paxel, OUT_DIR=out, **overrides), \
                mock.patch.object(sys, "argv", argv), \
                contextlib.redirect_stdout(buf):
            paxel.main()
        with open(os.path.join(out, "stats.json")) as fh:
            return json.load(fh)

    def test_assistant_turns_excludes_synthetic_usage(self):
        stats = self._run()
        # one genuine assistant message turn; the two usage snapshots must not count
        self.assertEqual(stats["volume"]["assistant_turns"], 1)

    def test_model_mix_not_inflated_by_usage(self):
        stats = self._run()
        models = dict(stats["stack"]["models"])
        # gpt-5.4 appears once (the real assistant turn), not per usage snapshot
        self.assertEqual(models.get("gpt-5.4"), 1)

    def test_tokens_still_attributed(self):
        stats = self._run()
        by_model = stats["token_usage"]["by_model"]
        entry = next((e for e in by_model if e["model_id"] == "gpt-5.4"), None)
        self.assertIsNotNone(entry, "gpt-5.4 token row missing")
        self.assertEqual(entry["input"], 2000)
        self.assertEqual(entry["output"], 100)

    def test_month_models_not_inflated_by_usage(self):
        stats = self._run()
        monthly = {m["month"]: m for m in stats["progression"]["monthly"]}
        apr = monthly.get("2026-04")
        self.assertIsNotNone(apr, "2026-04 month missing from progression")
        # month_models must reflect the single real assistant turn, not the snapshots
        self.assertEqual(dict(apr["models"]).get("gpt-5.4"), 1)
        # per-month token attribution must remain intact
        self.assertEqual(apr["tokens_input"], 2000)
        self.assertEqual(apr["tokens_output"], 100)


# ---------------------------------------------------------------------------
# FIX 3 — apply_patch "*** Move to:" must re-attribute churn to the new path.
# ---------------------------------------------------------------------------

class TestApplyPatchMoveTo(unittest.TestCase):
    def test_move_to_reattributes_path(self):
        patch = (
            "*** Begin Patch\n"
            "*** Update File: old/path.py\n"
            "*** Move to: new/path.py\n"
            "@@\n"
            "-old line\n"
            "+new line\n"
            "*** End Patch"
        )
        files = paxel._patch_files(patch)
        self.assertEqual(len(files), 1)
        new_s, old_s, fpath = files[0]
        self.assertEqual(fpath, "new/path.py")
        self.assertEqual(new_s, "new line\n")
        self.assertEqual(old_s, "old line\n")


if __name__ == "__main__":
    unittest.main()
