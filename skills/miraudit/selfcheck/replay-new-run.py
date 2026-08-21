"""new-run.py: the skeleton, and the guard that stops it landing on an earlier run.

The plan for this tier deferred the anti-clobber guard, on the grounds that it cannot be
exercised without walking the corpus and that an AST check for "the exists() test dominates
the open()" is too clever to trust. Both halves were wrong in the useful direction: new-run
imports `_common` and nothing from gnomon, so an EMPTY corpus directory satisfies it and the
script runs end to end offline in well under a second. The guard is checked by running it.

That matters more here than elsewhere. What the guard protects is somebody else's completed
run -- the evidence -- and the failure is silent and total: the file is opened "w", so a
broken guard does not corrupt the earlier payload, it empties it.

Everything else here is a MIRROR between the two ends of the audit. new-run writes the
skeleton and emit-gate refuses it; if either side moves alone, a run starts from a file its
own gate no longer recognises as unfilled. Both ends are the shipped ones.
"""
import json
import os
import subprocess
import sys
import harness

NEEDS = ()

_gate = harness.load("emit-gate.py")


def _emit(root, checkout, out=None, stats=None, extra=()):
    """Run new-run.py against an empty corpus. Returns (completed_process, out_path)."""
    empty = os.path.join(root, "empty-corpus")
    os.makedirs(empty, exist_ok=True)
    out = out or os.path.join(root, "skeleton.json")
    if stats is None:
        stats = os.path.join(root, "stats.json")
        if not os.path.exists(stats):
            with open(stats, "w") as fh:
                json.dump({}, fh)
    cmd = [sys.executable, os.path.join(harness.SCRIPTS, "new-run.py"),
           "--checkout", checkout, "--corpus", empty, "--stats", stats,
           "--since", "2026-07-13", "--until", "2026-08-12", "--out", out]
    return subprocess.run(cmd + list(extra), capture_output=True, text=True,
                          timeout=120), out


def check_an_earlier_run_is_not_overwritten(t):
    # The guard's whole value is that the earlier payload is evidence. Note what is asserted:
    # not that the second run failed, but that the FILE still holds the first run's bytes.
    # An exit code says what the script decided; only the bytes say what it did.
    with harness.tmpdir() as d, harness.fake_checkout() as ck:
        out = os.path.join(d, "miraudit-2026-08-12.json")
        with open(out, "w") as fh:
            fh.write('{"findings": ["a whole audit somebody already did"]}')
        proc, _ = _emit(d, ck, out=out)
        t.equal(open(out).read(), '{"findings": ["a whole audit somebody already did"]}',
                "the earlier run survives byte for byte")
        t.equal(proc.returncode != 0, True, "and the second run exits non-zero")
        t.contains(proc.stderr + proc.stdout, "exists",
                   "saying the file was already there rather than failing obscurely")


def check_it_writes_a_skeleton_when_the_path_is_free(t):
    # CONTROL for the guard above. A script that refused unconditionally would satisfy every
    # assertion in that check while being useless.
    with harness.tmpdir() as d, harness.fake_checkout() as ck:
        proc, out = _emit(d, ck)
        t.equal(proc.returncode, 0, "CONTROL: a free path is written, not refused")
        t.equal(os.path.exists(out), True, "and the skeleton is on disk")


def check_the_skeleton_is_what_the_gate_calls_unfilled(t):
    # The mirror. new-run produces and emit-gate consumes, and the gate's refusal of an empty
    # payload keys on all five buckets being empty at once. If new-run started prefilling one
    # of them, or the gate's signature changed, a skeleton would sail through as a clean
    # audit -- which is the exact defect that rule was added for.
    with harness.tmpdir() as d, harness.fake_checkout() as ck:
        proc, out = _emit(d, ck)
        if proc.returncode != 0:
            t.failures.append("new-run.py did not write: " + (proc.stderr or "")[-200:])
            return
        doc = json.load(open(out))
        violations = _gate.check(doc, flags_dir=d)
        t.equal(bool(violations), True, "the shipped gate refuses the fresh skeleton")
        t.contains(" ".join(violations), "bucket",
                   "and refuses it as unfilled rather than for some unrelated reason")


def check_every_bucket_the_gate_knows_about_is_in_the_skeleton(t):
    # Second half of the same mirror, in the other direction: a bucket the gate reasons about
    # but new-run never emits is a slot nobody will fill, because nothing puts it in the file.
    with harness.tmpdir() as d, harness.fake_checkout() as ck:
        proc, out = _emit(d, ck)
        if proc.returncode != 0:
            return
        doc = json.load(open(out))
        for bucket in _gate.BUCKETS:
            t.equal(bucket in doc, True, f"the skeleton carries `{bucket}`")


def check_the_refutation_rows_are_printed_from_the_gate(t):
    # JSON holds no comments, so the eight questions cannot sit in the file without reading
    # as answers. They are printed instead, at the moment somebody is about to answer them.
    #
    # Asserting against the SHIPPED ROWS is what makes a ninth row covered the day it lands:
    # this check needs no edit, and it goes red if new-run ever copies the questions into its
    # own source and the two drift.
    with harness.tmpdir() as d, harness.fake_checkout() as ck:
        proc, out = _emit(d, ck)
        for key, question in _gate.ROWS.items():
            t.contains(proc.stdout, key, f"row `{key}` is named")
            t.contains(proc.stdout, question, f"row `{key}` asks its question in full")
        for key in _gate.NOT_RAISED_KEYS:
            t.contains(proc.stdout, key, f"a not_raised entry's `{key}` is announced")
        t.absent(open(out).read(), sorted(_gate.ROWS.values())[0],
                 "and no question is written into the JSON, where it would look answered")


def check_the_other_buckets_announce_what_the_gate_will_demand(t):
    # Same mechanism as the eight rows, extended to the fields a cold run actually got
    # refused on. Asserted against the SHIPPED constants so a key added to the gate arrives
    # in the printout without anyone remembering to, and so the printout cannot drift into a
    # private copy of a list the gate owns.
    with harness.tmpdir() as d, harness.fake_checkout() as ck:
        proc, out = _emit(d, ck)
        # Matched on the bucket's OWN LINE, not anywhere in stdout. The first version of this
        # asserted `key in stdout` and passed against a printout carrying a stale private
        # copy of the list -- because "state" is a substring of "unstated: the payload
        # carries no per-source block", which the same output already contained. A short key
        # and a whole-document haystack is an assertion that cannot fail.
        lines = {b: next((ln for ln in proc.stdout.splitlines() if ln.strip().startswith(b)),
                         "") for b in ("reported[]", "dismissed[]", "process_friction[]")}
        for bucket, keys in (("reported[]", _gate.REPORTED_KEYS),
                             ("dismissed[]", _gate.DISMISSED_KEYS),
                             ("process_friction[]", _gate.FRICTION_KEYS)):
            t.equal(bool(lines[bucket]), True, f"`{bucket}` gets its own announced line")
            for key in keys:
                t.contains(lines[bucket], key,
                           f"`{bucket}{key}` is named on that line, not merely somewhere")


def check_the_sources_come_from_the_payload_not_from_a_fallback(t):
    # This read `event["source"]`, a key no transcript carries, so the set came out empty
    # every time and a `["claude"]` fallback was the only branch that ever ran. It wrote
    # `["claude"]` over a window whose payload said claude AND codex, and sources is the
    # field the cross-machine protocol leans on hardest.
    with harness.tmpdir() as d, harness.fake_checkout() as ck:
        stats = os.path.join(d, "stats.json")
        with open(stats, "w") as fh:
            json.dump({"scoring_inputs_by_source": {"codex": 12, "claude": 30}}, fh)
        proc, out = _emit(d, ck, stats=stats)
        if proc.returncode != 0:
            return
        t.equal(json.load(open(out))["corpus"]["sources"], ["claude", "codex"],
                "both scored sources reach the payload")


def check_an_absent_source_block_says_so_instead_of_guessing(t):
    # CONTROL for the check above, and the reason the fallback was removed rather than
    # corrected: with no per-source block there is no honest default, so the field has to
    # carry its own absence. A silent `["claude"]` here is a claim nobody measured.
    with harness.tmpdir() as d, harness.fake_checkout() as ck:
        proc, out = _emit(d, ck)
        if proc.returncode != 0:
            return
        sources = json.load(open(out))["corpus"]["sources"]
        t.equal(len(sources), 1, "CONTROL: one entry, and it is not a source name")
        t.contains(sources[0], "unstated", "the absence is stated in the field itself")
