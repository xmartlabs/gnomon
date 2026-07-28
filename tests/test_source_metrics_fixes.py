import os, sys, json, io, sqlite3, tempfile, shutil, contextlib, unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import paxel
from gnomon.cli.accumulator import Accumulator
from gnomon.sources.codex import _codex_events
from gnomon.sources.opencode import _opencode_events, _opencode_sqlite_events


def _write_jsonl(rows):
    f = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False)
    f.write("\n".join(json.dumps(r) for r in rows))
    f.close()
    return f.name


class TestPlanningSessionIdentity(unittest.TestCase):
    @staticmethod
    def _codex_rows(source):
        return [
            {"type": "session_meta", "timestamp": "2026-07-01T10:00:00Z",
             "payload": {"id": "codex-session", "cwd": "/x", "source": source}},
            {"type": "response_item", "timestamp": "2026-07-01T10:00:01Z",
             "payload": {"type": "message", "role": "user",
                         "content": [{"type": "input_text", "text": "plan this"}]}},
        ]

    def test_codex_guardian_is_authoritative_child_and_unknown_subagent_fails_closed(self):
        cases = (
            ({"subagent": {"other": "guardian"}}, True),
            ({"subagent": {"thread_spawn": {"parent_thread_id": "parent"}}}, True),
            ({"subagent": {"other": "unknown"}}, None),
            ({"subagent": {}}, None),
        )
        for source, expected in cases:
            with self.subTest(source=source):
                path = _write_jsonl(self._codex_rows(source))
                self.addCleanup(lambda p=path: os.path.exists(p) and os.unlink(p))
                event = next(e for e in _codex_events(path) if e.get("type") == "user")
                self.assertIs(event["isSidechain"], expected)

    def _opencode_json_events(self, session, *, planning_marker=False):
        root = tempfile.mkdtemp(prefix="opencode-json-")
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        sid = session["id"]
        session_path = os.path.join(root, f"{sid}.json")
        with open(session_path, "w") as handle:
            json.dump(session, handle)
        message_dir = os.path.join(root, "storage", "message", sid)
        os.makedirs(message_dir)
        with open(os.path.join(message_dir, "m1.json"), "w") as handle:
            json.dump({"id": "m1", "role": "assistant" if planning_marker else "user",
                       "time": {"created": 1782900000000},
                       "summary": {"title": "plan"}}, handle)
        if planning_marker:
            part_dir = os.path.join(root, "storage", "part", "m1")
            os.makedirs(part_dir)
            with open(os.path.join(part_dir, "p1.json"), "w") as handle:
                json.dump({
                    "id": "p1", "type": "tool", "tool": "bash",
                    "time": {"start": 1782900001000},
                    "state": {
                        "status": "completed",
                        "input": {
                            "command": "cat /x/skills/writing-plans/SKILL.md",
                        },
                    },
                }, handle)
        with mock.patch("gnomon.sources.opencode.discovery.OPENCODE_DIR", root):
            return list(_opencode_events(session_path))

    def test_opencode_json_parent_metadata_matrix(self):
        cases = (
            ({"id": "root", "directory": "/x", "parentID": None}, False),
            ({"id": "child", "directory": "/x", "parentID": "parent"}, True),
            ({"id": "missing", "directory": "/x"}, False),
            ({"id": "malformed", "directory": "/x", "parentID": 42}, None),
        )
        for session, expected in cases:
            with self.subTest(session=session["id"]):
                events = self._opencode_json_events(session)
                self.assertTrue(events)
                self.assertTrue(all(e["isSidechain"] is expected for e in events))

    def test_opencode_legacy_json_roots_contribute_planning_scope(self):
        cases = (
            (False, (0, 1, 0)),
            (True, (1, 1, 0)),
        )
        for planning_marker, expected in cases:
            with self.subTest(planning_marker=planning_marker):
                events = self._opencode_json_events(
                    {"id": f"legacy-{planning_marker}", "directory": "/x"},
                    planning_marker=planning_marker,
                )
                acc = Accumulator()
                acc.begin_file("opencode", "legacy-session.json")
                for event in events:
                    acc.observe(event, None, None)
                acc.end_file()
                behavior = acc.to_source_stats("opencode", None, None)["behavior"]
                self.assertEqual((
                    behavior["planning_skill_sessions"],
                    behavior["planning_skill_eligible_sessions"],
                    behavior["planning_skill_unmeasured_sessions"],
                ), expected)

    @staticmethod
    def _opencode_db(*, with_parent_column, parent_value=None):
        fd, path = tempfile.mkstemp(prefix="opencode-", suffix=".db")
        os.close(fd)
        conn = sqlite3.connect(path)
        parent_sql = ", parent_id" if with_parent_column else ""
        conn.execute(
            "CREATE TABLE session (id TEXT, directory TEXT, time_created INTEGER"
            + (", parent_id" if with_parent_column else "") + ")")
        conn.execute("CREATE TABLE message "
                     "(id TEXT, session_id TEXT, time_created INTEGER, data TEXT)")
        conn.execute("CREATE TABLE part "
                     "(id TEXT, session_id TEXT, message_id TEXT, time_created INTEGER, data TEXT)")
        columns = "id, directory, time_created" + parent_sql
        placeholders = "?, ?, ?" + (", ?" if with_parent_column else "")
        values = ["session", "/x", 1782900000000]
        if with_parent_column:
            values.append(parent_value)
        conn.execute(f"INSERT INTO session ({columns}) VALUES ({placeholders})", values)
        conn.execute("INSERT INTO message VALUES (?, ?, ?, ?)",
                     ("m1", "session", 1782900000000,
                      json.dumps({"id": "m1", "role": "user",
                                  "time": {"created": 1782900000000},
                                  "summary": {"title": "plan"}})))
        conn.commit()
        conn.close()
        return path

    def test_opencode_sqlite_parent_metadata_matrix(self):
        cases = (
            (True, None, False),
            (True, "parent", True),
            (True, 42, None),
            (False, None, None),
        )
        for with_parent, value, expected in cases:
            with self.subTest(with_parent=with_parent, value=value):
                path = self._opencode_db(
                    with_parent_column=with_parent, parent_value=value)
                self.addCleanup(lambda p=path: os.path.exists(p) and os.unlink(p))
                events = list(_opencode_sqlite_events(path))
                self.assertTrue(events)
                self.assertTrue(all(e["isSidechain"] is expected for e in events))


# ---------------------------------------------------------------------------
# FIX 1 — real Codex Agent calls are authoritative and remain windowed.
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

    def test_child_metadata_does_not_synthesize_parent_agent(self):
        path = _write_jsonl(self._child_rows())
        try:
            evs = list(paxel._codex_events(path))
        finally:
            os.unlink(path)
        agent = [e for e in evs if e.get("sessionId") == "parent-1"]
        self.assertEqual(agent, [])

    def test_fanout_counted_in_bounded_window(self):
        """A parent Codex session whose fan-out happens inside the window must have
        its delegate/Agent event counted, not dropped as undated."""
        codex_dir = tempfile.mkdtemp(prefix="paxel-fanout-")
        self.addCleanup(shutil.rmtree, codex_dir, ignore_errors=True)
        empty = tempfile.mkdtemp(prefix="paxel-fanout-empty-")
        self.addCleanup(shutil.rmtree, empty, ignore_errors=True)
        # Child metadata links routing but must not create another fan-out event.
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
            {"type": "response_item", "timestamp": "2026-03-10T11:00:03Z",
             "payload": {"type": "function_call", "name": "spawn_agent",
                         "call_id": "spawn-1", "arguments": json.dumps({
                             "task_name": "worker", "subagent_type": "codex-subagent"})}},
            {"type": "response_item", "timestamp": "2026-03-10T11:00:04Z",
             "payload": {"type": "function_call_output", "call_id": "spawn-1",
                         "output": json.dumps({"agent_id": "child-1"})}},
        ]
        with open(os.path.join(codex_dir, "parent.jsonl"), "w") as fh:
            fh.write("\n".join(json.dumps(r) for r in parent))

        out = tempfile.mkdtemp(prefix="paxel-fanout-out-")
        self.addCleanup(shutil.rmtree, out, ignore_errors=True)
        overrides = dict(
            BASE=empty, CODEX_DIR=codex_dir, GEMINI_DIR=empty, PI_DIR=empty,
            ANTIGRAVITY_CLI_DIR=empty, ANTIGRAVITY_IDE_DIR=empty, ANTIGRAVITY_DB=os.path.join(empty, "nope.vscdb"),
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
        self.assertEqual(stats["tools"]["agent_calls"], 1,
                         "real fan-out Agent event was dropped or duplicated")


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
            ANTIGRAVITY_CLI_DIR=empty, ANTIGRAVITY_IDE_DIR=empty, ANTIGRAVITY_DB=os.path.join(empty, "nope.vscdb"),
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
