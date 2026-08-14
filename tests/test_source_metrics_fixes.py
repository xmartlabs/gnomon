import os, sys, json, io, sqlite3, tempfile, shutil, contextlib, unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import paxel
from gnomon.cli.accumulator import (
    Accumulator, aggregate_ordered, derive_session_ordered_facts,
)
from gnomon.sources import iter_events
from gnomon.sources import discovery
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
        conn.execute("INSERT INTO message VALUES (?, ?, ?, ?)",
                     ("m2", "session", 1782900001000,
                      json.dumps({"id": "m2", "role": "assistant",
                                  "time": {"created": 1782900001000}})))
        conn.execute("INSERT INTO part VALUES (?, ?, ?, ?, ?)",
                     ("p1", "session", "m2", 1782900001000,
                      json.dumps({"id": "p1", "type": "tool", "tool": "bash",
                                  "state": {"status": "completed", "input": {}}})))
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

    def test_opencode_coexistence_counts_shared_session_once(self):
        root = tempfile.mkdtemp(prefix="opencode-coexist-")
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        db = self._opencode_db(with_parent_column=True)
        shutil.move(db, os.path.join(root, "opencode.db"))
        session_dir = os.path.join(root, "storage", "session", "project")
        message_dir = os.path.join(root, "storage", "message", "session")
        part_dir = os.path.join(root, "storage", "part", "m2")
        os.makedirs(session_dir)
        os.makedirs(message_dir)
        os.makedirs(part_dir)
        for sid in ("session", "legacy-only"):
            with open(os.path.join(session_dir, f"{sid}.json"), "w") as handle:
                json.dump({"id": sid, "directory": "/x"}, handle)
        with open(os.path.join(message_dir, "m1.json"), "w") as handle:
            json.dump({"id": "m1", "role": "user", "time": {"created": 1782900000000},
                       "summary": {"title": "plan"}}, handle)
        with open(os.path.join(message_dir, "m2.json"), "w") as handle:
            json.dump({"id": "m2", "role": "assistant", "time": {"created": 1782900001000}}, handle)
        with open(os.path.join(part_dir, "p1.json"), "w") as handle:
            json.dump({"id": "p1", "type": "tool", "tool": "bash",
                       "state": {"status": "completed", "input": {}}}, handle)
        acc = Accumulator()
        with mock.patch.object(discovery, "OPENCODE_DIR", root):
            sources = discovery.discover_sources(["opencode"])
            self.assertIn(("opencode", os.path.join(session_dir, "legacy-only.json"), "opencode"), sources)
            for source, path, fmt in sources:
                acc.begin_file(source, path)
                for event in iter_events(path, fmt):
                    acc.observe(event, None, None)
                acc.end_file()
        volume = acc.to_source_stats("opencode", None, None)["volume"]
        self.assertEqual((volume["total_sessions"], volume["total_prompts"],
                          volume["assistant_turns"], volume["tool_calls_total"]), (1, 1, 1, 1))

    def test_opencode_degraded_sqlite_keeps_legacy_session(self):
        root = tempfile.mkdtemp(prefix="opencode-partial-")
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        db = self._opencode_db(with_parent_column=True)
        with sqlite3.connect(db) as conn:
            conn.execute("DROP TABLE part")
        shutil.move(db, os.path.join(root, "opencode.db"))
        session_dir = os.path.join(root, "storage", "session", "project")
        os.makedirs(session_dir)
        legacy = os.path.join(session_dir, "session.json")
        with open(legacy, "w") as handle:
            json.dump({"id": "session", "directory": "/x"}, handle)
        with mock.patch.object(discovery, "OPENCODE_DIR", root):
            self.assertIn(("opencode", legacy, "opencode"),
                          discovery.discover_sources(["opencode"]))

    def test_opencode_missing_session_table_keeps_legacy_session(self):
        root = tempfile.mkdtemp(prefix="opencode-no-session-")
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        db = self._opencode_db(with_parent_column=True)
        with sqlite3.connect(db) as conn:
            conn.execute("DROP TABLE session")
        shutil.move(db, os.path.join(root, "opencode.db"))
        session_dir = os.path.join(root, "storage", "session", "project")
        os.makedirs(session_dir)
        legacy = os.path.join(session_dir, "session.json")
        with open(legacy, "w") as handle:
            json.dump({"id": "session", "directory": "/x"}, handle)
        with mock.patch.object(discovery, "OPENCODE_DIR", root):
            self.assertIn(("opencode", legacy, "opencode"),
                          discovery.discover_sources(["opencode"]))

    def test_opencode_incompatible_sqlite_columns_keep_legacy_session(self):
        root = tempfile.mkdtemp(prefix="opencode-incompatible-")
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        db = os.path.join(root, "opencode.db")
        with sqlite3.connect(db) as conn:
            conn.execute(
                "CREATE TABLE session "
                "(id TEXT, directory TEXT, time_created INTEGER)")
            conn.execute(
                "CREATE TABLE message "
                "(id TEXT, session_id TEXT, time_created INTEGER)")
            conn.execute(
                "CREATE TABLE part "
                "(id TEXT, session_id TEXT, message_id TEXT, "
                "time_created INTEGER, data TEXT)")
            conn.execute("INSERT INTO session VALUES (?, ?, ?)",
                         ("session", "/x", 1782900000000))
            conn.execute("INSERT INTO message VALUES (?, ?, ?)",
                         ("m1", "session", 1782900000000))

        session_dir = os.path.join(root, "storage", "session", "project")
        os.makedirs(session_dir)
        legacy = os.path.join(session_dir, "session.json")
        with open(legacy, "w") as handle:
            json.dump({"id": "session", "directory": "/x"}, handle)

        self.assertEqual(list(_opencode_sqlite_events(db)), [])
        with mock.patch.object(discovery, "OPENCODE_DIR", root):
            self.assertIn(("opencode", legacy, "opencode"),
                          discovery.discover_sources(["opencode"]))

    def test_opencode_undecodable_sqlite_session_keeps_legacy_copy(self):
        root = tempfile.mkdtemp(prefix="opencode-undecodable-")
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        db = self._opencode_db(with_parent_column=True)
        with sqlite3.connect(db) as conn:
            conn.execute("UPDATE message SET data = 'not-json'")
        shutil.move(db, os.path.join(root, "opencode.db"))

        session_dir = os.path.join(root, "storage", "session", "project")
        os.makedirs(session_dir)
        legacy = os.path.join(session_dir, "session.json")
        with open(legacy, "w") as handle:
            json.dump({"id": "session", "directory": "/x"}, handle)

        self.assertEqual(
            list(_opencode_sqlite_events(os.path.join(root, "opencode.db"))),
            [],
        )
        with mock.patch.object(discovery, "OPENCODE_DIR", root):
            self.assertIn(("opencode", legacy, "opencode"),
                          discovery.discover_sources(["opencode"]))


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
        argv = ["paxel.py", "--include-low-volume", "--no-open",
                "--since=2026-03-01", "--until=2026-03-31"]
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
# BLOCKER 1 — Codex tool events must thread `call_id` as the correlation id
# (`id` on tool_use, `tool_use_id` on tool_result) so F7's corpus-lifetime,
# source/session-scoped success map (`Accumulator._tool_result_is_error`) can resolve a Codex shell
# test's outcome, the same way it already does for Claude's `id`/`tool_use_id`.
# ---------------------------------------------------------------------------

class TestCodexVerificationCoverageBlocker1(unittest.TestCase):
    def _session_rows(self, test_success, as_string=False, raw_output=None,
                      session_id="codex-s1", call_id="test-1"):
        _out = (raw_output if raw_output is not None
                else (json.dumps({"success": test_success}) if as_string
                      else {"success": test_success}))
        return [
            {"type": "session_meta", "timestamp": "2026-01-01T00:00:00Z",
             "payload": {"id": session_id, "cwd": "/repo"}},
            {"type": "turn_context", "timestamp": "2026-01-01T00:00:01Z",
             "payload": {"model": "gpt-5.4"}},
            {"type": "response_item", "timestamp": "2026-01-01T00:00:02Z",
             "payload": {"type": "custom_tool_call", "name": "apply_patch",
                         "call_id": "patch-1",
                         "input": ("*** Begin Patch\n*** Update File: src/a.py\n"
                                   "@@\n-x = 1\n+x = 2\n*** End Patch")}},
            {"type": "response_item", "timestamp": "2026-01-01T00:00:03Z",
             "payload": {"type": "custom_tool_call", "name": "apply_patch",
                         "call_id": "patch-2",
                         "input": ("*** Begin Patch\n*** Update File: src/b.py\n"
                                   "@@\n-y = 1\n+y = 2\n*** End Patch")}},
            {"type": "response_item", "timestamp": "2026-01-01T00:00:04Z",
             "payload": {"type": "function_call", "name": "shell", "call_id": call_id,
                         "arguments": json.dumps({"command": "pytest"})}},
            {"type": "response_item", "timestamp": "2026-01-01T00:00:05Z",
             "payload": {"type": "function_call_output", "call_id": call_id,
                         "output": _out}},
        ]

    def _run(self, test_success, as_string=False, raw_output=None):
        path = _write_jsonl(self._session_rows(test_success, as_string, raw_output))
        try:
            events = list(_codex_events(path))
        finally:
            os.unlink(path)
        acc = Accumulator()
        acc.begin_file("codex", path)
        for ev in events:
            acc.observe(ev, None, None)
        from gnomon.cli.accumulator import aggregate_ordered
        facts = None
        for (src, sid), f in acc.session_ordered_tools.items():
            if src == "codex" and sid == "codex-s1":
                facts = f
        self.assertIsNotNone(facts, "codex session facts not recorded")
        return aggregate_ordered([facts], acc._tool_result_is_error)

    def test_successful_codex_shell_test_is_covered(self):
        agg = self._run(test_success=True)
        self.assertEqual(agg["eligible"], 1)
        self.assertEqual(agg["test_covered"], 1)

    def test_failing_codex_shell_test_is_not_covered(self):
        agg = self._run(test_success=False)
        self.assertEqual(agg["eligible"], 1)
        self.assertEqual(agg["test_covered"], 0)

    def test_reused_codex_call_id_is_scoped_within_the_corpus(self):
        acc = Accumulator()
        for session_id, test_success in (("codex-a", False), ("codex-b", True)):
            path = _write_jsonl(self._session_rows(
                test_success, session_id=session_id, call_id="reused-call-id"))
            try:
                events = list(_codex_events(path))
                acc.begin_file("codex", path)
                for ev in events:
                    acc.observe(ev, None, None)
            finally:
                os.unlink(path)

        facts_a = acc.session_ordered_tools[("codex", "codex-a")]
        facts_b = acc.session_ordered_tools[("codex", "codex-b")]
        aggregate = aggregate_ordered([facts_a, facts_b], acc._tool_result_is_error)

        self.assertFalse(derive_session_ordered_facts(
            facts_a, acc._tool_result_is_error)["ran_test"])
        self.assertTrue(derive_session_ordered_facts(
            facts_b, acc._tool_result_is_error)["ran_test"])
        self.assertEqual(aggregate["eligible"], 2)
        self.assertEqual(aggregate["test_covered"], 1)

    def test_json_string_output_success_is_covered(self):
        # Codex records function_call_output.output as a dict OR a JSON string.
        agg = self._run(test_success=True, as_string=True)
        self.assertEqual(agg["eligible"], 1)
        self.assertEqual(agg["test_covered"], 1)

    def test_json_string_output_failure_is_not_covered(self):
        # Regression: a string `{"success": false}` must be parsed as a failure,
        # not read as no-error, or a FAILED Codex test would inflate coverage.
        agg = self._run(test_success=False, as_string=True)
        self.assertEqual(agg["eligible"], 1)
        self.assertEqual(agg["test_covered"], 0)

    def test_not_json_output_is_not_covered(self):
        """Malformed Codex output has no determinate success state."""
        agg = self._run(test_success=True, raw_output="not-json")
        self.assertEqual(agg["eligible"], 1)
        self.assertEqual(agg["test_covered"], 0)


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
        argv = ["paxel.py", "--include-low-volume", "--no-open"]
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
