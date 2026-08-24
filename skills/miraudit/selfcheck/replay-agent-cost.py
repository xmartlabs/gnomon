"""agent-cost.py: derives run_cost.agent from a subagent transcript, and emit-gate.py's
rule for the field once it lands in a payload.

Real transcript paths are NOT embedded here on purpose, even though two are named in the
task that produced this file: this suite ships with the skill and a real transcript path is
a real user's home directory plus a real session id, which is exactly what
`scripts/scan-leaks.py` exists to keep out of a public repo. The two real files were used to
verify `measure()` by hand once (tool_uses 47/66, duration_ms within ~0.1s of 766960/1162592,
output_tokens_total 28558/47410, context_peak 131780/163821, all reported in the task's own
write-up) and everything below is a synthetic, hand-computable stand-in for that shape.
"""
import contextlib
import io
import json
import os
import harness

NEEDS = ()

ac = harness.load("agent-cost.py")
gate = harness.load("emit-gate.py")


def _write(root, name, lines):
    """Write raw text lines (already JSON-encoded, or deliberately not) as one .jsonl file."""
    path = os.path.join(root, name)
    with open(path, "w") as fh:
        for line in lines:
            fh.write(line + "\n")
    return path


def _assistant(ts, tool_use_count, output_tokens=None, extra_usage=None):
    blocks = [{"type": "tool_use", "name": "Bash", "input": {"command": "true"}}
              for _ in range(tool_use_count)]
    body = {"type": "assistant", "sessionId": "s1", "timestamp": ts,
            "message": {"role": "assistant", "content": blocks}}
    if output_tokens is not None:
        usage = {"output_tokens": output_tokens}
        usage.update(extra_usage or {})
        body["message"]["usage"] = usage
    return json.dumps(body)


def _user(ts):
    return json.dumps({"type": "user", "sessionId": "s1", "timestamp": ts,
                       "message": {"role": "user", "content": "go"}})


# ---- measure() against a hand-computable fixture ------------------------------------------
# T0 (user, first timestamp) .. T3 (assistant, last timestamp) spans exactly 60000ms.
# tool_uses: 3 (msg1) + 2 (msg2) + 0 (msg3) = 5, deliberately NOT equal to the message count
# (3): a fixture where those two numbers coincide cannot tell "count tool_use blocks" apart
# from "count assistant messages", which is exactly the mutation this suite has to catch.
# output_tokens_total: 100 + 50 + 25 = 175.
# context_peak is read from msg3's usage ONLY (the last one), never summed: 5+1000+200+25=1230.
T0 = "2026-08-21T00:00:00.000Z"
T1 = "2026-08-21T00:00:10.000Z"
T2 = "2026-08-21T00:00:20.000Z"
T3 = "2026-08-21T00:01:00.000Z"


def _hand_computable_fixture(root):
    return _write(root, "fixture.jsonl", [
        _user(T0),
        _assistant(T1, 3, output_tokens=100),
        _assistant(T2, 2, output_tokens=50),
        _assistant(T3, 0, output_tokens=25,
                   extra_usage={"input_tokens": 5, "cache_read_input_tokens": 1000,
                                "cache_creation_input_tokens": 200}),
    ])


def check_hand_computable_fixture_reproduces_exactly(t):
    with harness.tmpdir() as d:
        path = _hand_computable_fixture(d)
        result, skipped, lines_seen = ac.measure(path)
        t.equal(skipped, 0, "no malformed lines in this fixture")
        t.equal(lines_seen, 4, "all four lines counted")
        t.equal(result["tool_uses"], 5, "3 + 2 + 0 tool_use blocks across three messages")
        t.equal(result["duration_ms"], 60000, "T3 - T0, hand-computed to the millisecond")
        t.equal(result["output_tokens_total"], 175, "100 + 50 + 25, summed across messages")
        t.equal(result["context_peak"], 1230,
                "5 + 25 + 1000 + 200 from the LAST usage block only, not a sum across all three")


def check_malformed_lines_are_skipped_and_counted_not_fatal(t):
    with harness.tmpdir() as d:
        path = _write(d, "fixture.jsonl", [
            _user(T0),
            "{not even close to json",
            _assistant(T1, 3, output_tokens=10),
            "42",  # valid JSON, but not an object -- also not usable and must be skipped
            _assistant(T2, 2, output_tokens=20),
        ])
        result, skipped, lines_seen = t.completes(lambda: ac.measure(path),
                                                   "a file with garbage lines does not raise")
        if result is None:
            return
        t.equal(lines_seen, 5, "every non-blank line is counted as seen")
        t.equal(skipped, 2, "the unparseable line AND the bare-42 line are both skipped")
        t.equal(result["tool_uses"], 5,
                "3 + 2 tool_use blocks from the two valid messages, not a count of 2 messages")


def check_zero_tool_use_blocks_reports_zero_not_something_else(t):
    # CONTROL for the count above: a transcript with real assistant messages and NO tool_use
    # blocks at all must report tool_uses: 0, not None, not skip the field, not crash.
    with harness.tmpdir() as d:
        path = _write(d, "fixture.jsonl", [
            _user(T0),
            _assistant(T1, 0, output_tokens=5),
            _assistant(T2, 0, output_tokens=5),
        ])
        result, skipped, _ = ac.measure(path)
        t.equal(result["tool_uses"], 0, "zero tool_use blocks is a real zero, not a null")
        t.equal(skipped, 0, "nothing here is malformed")


def check_no_assistant_usage_at_all_yields_null_not_a_fabricated_zero(t):
    # If NOTHING carried a usage block, there is nothing to sum -- reporting 0 would look like
    # a measurement. Mirrors run_cost.wall's own "null, not 0" rule for the same reason.
    with harness.tmpdir() as d:
        path = _write(d, "fixture.jsonl", [_user(T0), _assistant(T1, 1)])
        result, _, _ = ac.measure(path)
        t.equal(result["tool_uses"], 1, "the tool_use block is still counted")
        t.equal(result["output_tokens_total"], None, "nothing to sum, so null rather than 0")
        t.equal(result["context_peak"], None, "same: no usage block seen at all")


def check_a_single_timestamp_yields_a_zero_duration_not_none(t):
    # Distinguishes "we saw one instant" (0ms, a real measurement) from "we saw nothing at
    # all" (None). new-run.py's run_cost.wall makes exactly this distinction for the same
    # reason: a single artifact spans no time, and 0 there would be a fabricated measurement --
    # but here there IS one timestamp, and 0 IS the honest span between it and itself.
    with harness.tmpdir() as d:
        path = _write(d, "fixture.jsonl", [_assistant(T1, 1, output_tokens=1)])
        result, _, _ = ac.measure(path)
        t.equal(result["duration_ms"], 0, "one timestamp spans zero ms, not null")


def check_empty_file_yields_all_nulls_and_zero_tool_uses(t):
    with harness.tmpdir() as d:
        path = _write(d, "fixture.jsonl", [])
        result, skipped, lines_seen = ac.measure(path)
        t.equal(lines_seen, 0, "nothing to read")
        t.equal(skipped, 0, "nothing to skip either")
        t.equal(result["tool_uses"], 0, "no messages, no tool_use blocks")
        t.equal(result["duration_ms"], None, "no timestamps at all to span")


def check_missing_file_is_an_oserror_not_a_silent_empty_result(t):
    exc = t.raises(OSError, lambda: ac.measure("/no/such/path/fixture.jsonl"),
                   "a transcript that does not exist is an error, not a zeroed report")
    if exc:
        t.contains(str(exc), "No such file", "and names what went wrong")


# ---- the CLI: --emit writes the documented shape -------------------------------------------

def _run_cli(root, path, emit_name="out.json"):
    emit_path = os.path.join(root, emit_name)
    buf = io.StringIO()
    with harness.quiet():
        with contextlib.redirect_stdout(buf):
            rc = ac.main([path, "--emit", emit_path])
    return rc, buf.getvalue(), emit_path


def check_emit_writes_well_formed_json_with_the_documented_keys(t):
    with harness.tmpdir() as d:
        path = _hand_computable_fixture(d)
        rc, _out, emit_path = _run_cli(d, path)
        t.equal(rc, 0, "a normal fixture exits clean")
        t.equal(os.path.exists(emit_path), True, "the --emit path was written")
        with open(emit_path) as fh:
            doc = t.completes(lambda: json.load(fh), "the emitted file is well-formed JSON")
        if doc is not None:
            t.equal(sorted(doc), ["context_peak", "duration_ms", "output_tokens_total",
                                  "tool_uses"],
                    "exactly the four documented run_cost.agent keys, nothing extra")
            t.equal(doc["tool_uses"], 5, "the CLI path reproduces the direct measure() call")


def check_a_missing_file_exits_2_and_writes_nothing(t):
    with harness.tmpdir() as d:
        emit_path = os.path.join(d, "out.json")
        buf = io.StringIO()
        with harness.quiet():
            with contextlib.redirect_stdout(buf):
                rc = ac.main(["/no/such/path.jsonl", "--emit", emit_path])
        t.equal(rc, 2, "a missing transcript is exit code 2, per the docstring's own contract")
        t.equal(os.path.exists(emit_path), False, "and nothing is written on that path")


# ---- offline-tier only: this module never imports gnomon.* -------------------------------

def check_agent_cost_is_offline_never_imports_gnomon(t):
    import inspect
    src = inspect.getsource(ac)
    t.absent(src, "import gnomon", "agent-cost.py must stay offline tier: no gnomon.* import")
    t.absent(src, "from gnomon", "same check, the other import spelling")
    t.absent(src, "--checkout", "and it must never require a checkout to run")


# ---- emit-gate.py's run_cost.agent rule ----------------------------------------------------
# Mirrors the shape of check_run_cost_is_optional_but_typed_when_present in
# replay-emit-gate-gating.py (checks/arms/adhoc_checks), one level down at .agent.

def _where(bad, prefix):
    return [v for v in bad if v.startswith(prefix)]


def check_run_cost_agent_absent_entirely_is_clean(t):
    with harness.tmpdir() as flags:
        bad = gate.check(harness.payload(), doc_path=None, flags_dir=flags)
        t.equal(_where(bad, "run_cost.agent"), [],
                "CONTROL: no run_cost.agent at all is clean -- most runs are not dispatched "
                "as a subagent, and that is the normal case, not a hole")


def check_run_cost_agent_valid_shape_passes(t):
    with harness.tmpdir() as flags:
        good = {"agent": {"tool_uses": 47, "duration_ms": 766887,
                          "output_tokens_total": 28558, "context_peak": 131780}}
        bad = gate.check(harness.payload(run_cost=good), doc_path=None, flags_dir=flags)
        t.equal(_where(bad, "run_cost.agent"), [], "the documented shape passes clean")


def check_run_cost_agent_optional_fields_may_be_null(t):
    with harness.tmpdir() as flags:
        minimal = {"agent": {"tool_uses": 0, "duration_ms": None,
                             "output_tokens_total": None, "context_peak": None}}
        bad = gate.check(harness.payload(run_cost=minimal), doc_path=None, flags_dir=flags)
        t.equal(_where(bad, "run_cost.agent"), [],
                "tool_uses is the only field this rule requires structurally; the rest may "
                "be null")


def check_run_cost_agent_optional_fields_need_not_be_present_at_all(t):
    # Distinct from the null case above: this object never mentions duration_ms /
    # output_tokens_total / context_peak at all, which the "for key in (...): if key not in
    # agent_cost: continue" branch has to accept, not just the explicit-null branch.
    with harness.tmpdir() as flags:
        bare = {"agent": {"tool_uses": 5}}
        bad = gate.check(harness.payload(run_cost=bare), doc_path=None, flags_dir=flags)
        t.equal(_where(bad, "run_cost.agent"), [],
                "the object does not have to carry every optional subfield, only tool_uses")


def check_run_cost_agent_requires_tool_uses_as_a_nonneg_int(t):
    with harness.tmpdir() as flags:
        for value, why in (
            (None, "tool_uses absent-as-null defeats the one field agent-cost.py always "
                   "derives deterministically"),
            (-1, "a negative count cannot come from counting blocks"),
            (3.5, "a fraction of a tool call is not a count"),
            (True, "a bool is not a count, even though bool is an int subclass"),
            ("47", "a string is not the structured form"),
        ):
            entry = {"agent": {"tool_uses": value}}
            bad = gate.check(harness.payload(run_cost=entry), doc_path=None, flags_dir=flags)
            t.equal(bool(_where(bad, "run_cost.agent")), True,
                    "tool_uses=%r rejected: %s" % (value, why))


def check_run_cost_agent_optional_numbers_reject_negative_and_bad_type(t):
    with harness.tmpdir() as flags:
        for key in ("duration_ms", "output_tokens_total", "context_peak"):
            for value, why in (
                (-1, "a negative %s cannot be real" % key),
                (True, "a bool is not a number"),
                ("47", "a string is not the structured form"),
            ):
                entry = {"agent": {"tool_uses": 0, key: value}}
                bad = gate.check(harness.payload(run_cost=entry), doc_path=None,
                                 flags_dir=flags)
                t.equal(bool(_where(bad, "run_cost.agent")), True,
                        "%s=%r rejected: %s" % (key, value, why))
