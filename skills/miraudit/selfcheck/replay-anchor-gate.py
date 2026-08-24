"""anchor.py's gate(): the final "PHASE 0 RESULT" print, which crashed on the normal
--published + --expect-contract path and nothing here caught it before a live run did.

Two independent defects lived in that one block. `stats = load_stats(stats_path)` at the
top of gate() already shadows `stats` with a parsed dict; the old code called
`load_stats(stats)` again near the end, on the dict instead of the path -- a dict has no
open()-able form, so that raised. Separately, the old print referenced `ref` and `measured`,
names that exist only in main()'s local scope, not gate()'s -- NameError, unconditionally,
on every call. Because gate() runs strictly before anchor.json gets written (main() calls it,
then writes the payload), the crash discarded a full pipeline run -- minutes of real work --
down to a bare traceback. Fixed same day by reading `aq` (a real local, set earlier via
find_key) and os.path.dirname(stats_path) (the parameter, not the shadowed name).

Offline: gate() only reads a stats.json-shaped dict, no checkout, no corpus, no subprocess.
"""
import contextlib
import io
import json
import os
import harness

NEEDS = ()

anchor = harness.load("anchor.py")


def _stats(root, aq=91, tier="Ascending", contract="19:19:19"):
    """A stats.json small enough to be built by hand, real enough for find_key to resolve
    every field gate() reads: aq_0_100, tier, score_contract_id."""
    path = os.path.join(root, "stats.json")
    with open(path, "w") as fh:
        json.dump({"aq_0_100": aq, "tier": tier, "score_contract_id": contract}, fh)
    return path


def _gate(stats_path, published, expect):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = anchor.gate(stats_path, published, expect)
    return rc, buf.getvalue()


def check_gate_prints_its_final_summary_without_crashing_on_a_clean_match(t):
    """The primary regression test. Under the old code this exact call raised before ever
    reaching a `return` -- t.completes turns that into a named failure instead of taking the
    whole runner down, which is the point: gate() cannot pass this by accident."""
    with harness.tmpdir() as d:
        stats_path = _stats(d, aq=91)
        result = t.completes(lambda: _gate(stats_path, "91", "19:19:19"),
                             "gate() returns instead of raising on a clean match")
        if not result:
            return
        rc, out = result
        t.equal(rc, 0, "a matching published number and contract is not a gate failure")
        t.contains(out, "PHASE 0 RESULT", "the final summary line is reached at all")
        t.contains(out, "AQ 91", "and it prints the fixture's real AQ, not a placeholder")


def check_gate_still_prints_its_final_summary_when_published_and_expect_are_both_omitted(t):
    """The old bug lived in code reached regardless of whether --published or
    --expect-contract were passed -- the crash did not need either flag to fire."""
    with harness.tmpdir() as d:
        stats_path = _stats(d, aq=77)
        result = t.completes(lambda: _gate(stats_path, None, None),
                             "gate() returns even with nothing to compare against")
        if not result:
            return
        rc, out = result
        t.equal(rc, 0, "no published number and no contract means nothing CAN fail")
        t.contains(out, "PHASE 0 RESULT", "the final block still prints")
        t.contains(out, "was not gated", "and says so for the missing --published")


def check_gate_refuses_cleanly_on_a_real_mismatch_without_hitting_the_broken_line(t):
    """A contrast case, not a duplicate of the success path: a real mismatch returns from
    the EARLY refusal, before gate() ever reaches the block that used to crash. This is why
    the mismatch path stayed green in the wild while the clean-match path was throwing --
    the fix did not need to be reached for this case to already work."""
    with harness.tmpdir() as d:
        stats_path = _stats(d, aq=91)
        result = t.completes(lambda: _gate(stats_path, "999", "19:19:19"),
                             "a mismatch is a refusal, not an exception")
        if not result:
            return
        rc, out = result
        t.equal(rc, 1, "a published number that does not match the run fails the gate")
        t.contains(out, "DOES NOT MATCH", "and says which comparison failed")
        t.absent(out, "PHASE 0 RESULT",
                 "the early refusal returns before the final summary block -- the one "
                 "line that carried both original bugs -- is ever reached")
