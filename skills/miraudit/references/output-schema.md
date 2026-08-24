# Output schema

One run writes `miraudit-<date>.json`, then renders `miraudit-<date>.md` **from it**. Never
write the two by hand: they drift, and a report that has drifted from its evidence is the
defect this skill exists to catch.

**A real one is in `example-run/miraudit-2026-08-10.json`** — a full run against `c6401cc`
on contract `17:17:17`, with two file paths from a private repository redacted and nothing
else changed. Read that for the current shape. The sketch below illustrates the field rules
one at a time and is **older than the contract**: it shows `3148a96` / `16:16:16`, a signal
(`test_runs_per_call`) the tool no longer computes, and a `findings[]` entry that has since
been accepted upstream and belongs in `reported`. Kept because each field is annotated;
not kept as an example of a current payload.

**Where.** Into a directory you name at the start of the run and state in the report, never
the working directory. Two runs on one day otherwise overwrite each other silently, and the
second one looks like the only one there ever was. If a name collides, do not overwrite:
the earlier run is evidence, and comparing two runs of the same day is sometimes the point.

The JSON is what makes cross-machine comparison possible. One person's corpus is an
anecdote; the same gap in five corpora is a defect in the axis.

```json
{
  "schema_version": "1",
  "tool":   { "name": "xl-ai-insights", "ref": "3148a96", "measured_ref": "3148a96",
              "contract": "16:16:16" },
  "corpus": { "files": 3059, "lines": 287670, "tool_calls": 41983,
              "window": "30d", "sources": ["claude", "codex", "cursor"] },
  "anchor": { "published": 91, "reproduced": 91, "ok": true },
  "run_cost": {
    "wall": { "started": "2026-08-10T18:11:02+00:00", "ended": "2026-08-10T18:30:26+00:00",
              "seconds": 1164,
              "derived_from": "mtimes of the output directory, excluding checkout/anchor/.git/__pycache__. NOT a self-report: an agent's own clock has been wrong by 2.3x." },
    "checks": { "unit": "seconds", "value": 66.1 }, "arms": null, "adhoc_checks": null,
    "agent": null, "gate_retries": { "unit": "count", "value": 0 },
    "phases": { "0_anchor": 214.7, "4_synthesis": 949.3 } },
  "axes": [
    { "name": "Verification", "score": 20.1, "max": 35,
      "declared": { "test_runs_per_call": 0.004168, "target": 0.025 },
      "remeasured": { "sessions_editing_code": 50, "of_those_ran_tests": 17 },
      "direction": "overestimates",
      "evidence": { "command": "…", "control": "…", "output": "…" },
      "confidence": "fact",
      "not_checked": ["whether the target is calibrated against a real population"] }
  ],
  "findings": [
    {
      "id": "toolsearch-forced-load",
      "shape": "signal-not-attributable-to-person",
      "axes": ["Tool command", "Token economy"],
      "direction": "overestimates",
      "magnitude": { "unit": "AQ", "value": -5.03, "bound": "upper" },
      "confidence": "fact",
      "evidence": {
        "command": "…",
        "control": "…",
        "output": "…"
      },
      "not_checked": [
        {"kind": "population", "term": "toolsearch_calls",
         "note": "whether other harnesses treat ToolSearch as discovery"}
      ],
      "what_would_close_it": "a run where ToolSearch is disabled and the axis does not move",
      "refuted": {
        "window_or_corpus":           { "verdict": "pass", "note": "Reproduces on the fixed window and on --last=30d." },
        "denominator_theirs":         { "verdict": "pass", "note": "tool_calls_total, their field, unchanged." },
        "fairest_operationalization": { "verdict": "pass", "note": "Scored their way, not ours; the flattering read was worse for us." },
        "already_conceded":           { "verdict": "pass", "note": "We conceded shrinking the denominator, and this does not." },
        "paths_and_refs_exist":       { "verdict": "pass", "note": "taxonomy.py:37 resolved against the pinned ref." },
        "control_present":            { "verdict": "pass", "note": "A fixture that MUST score non-zero does." },
        "tooling_reshaped_evidence":  { "verdict": "pass", "note": "Measured before our own runs entered the window." },
        "one_condition_neutralized":  { "verdict": "pass", "note": "Neutralizing discovery alone still moves the axis." }
      }
    }
  ],
  "not_raised": [
    {
      "id": "steering-leverage-retained",
      "shape": "withheld-from-the-person",
      "axes": ["Steering leverage"],
      "direction": "underestimates",
      "confidence": "hypothesis",
      "evidence": { "command": "…", "control": "…", "output": "…" },
      "not_checked": ["whether the dashboard renders it server-side"],
      "refuted": {
        "window_or_corpus":           { "verdict": "pass", "note": "Present in two corpora." },
        "denominator_theirs":         { "verdict": "n/a",  "note": "No denominator; this is a presence claim." },
        "fairest_operationalization": { "verdict": "pass", "note": "Read their renderer, not our expectation of it." },
        "already_conceded":           { "verdict": "fail", "note": "They called the mechanism intended in #72." },
        "paths_and_refs_exist":       { "verdict": "pass", "note": "Resolved against the pinned ref." },
        "control_present":            { "verdict": "pass", "note": "A field that IS rendered was checked alongside." },
        "tooling_reshaped_evidence":  { "verdict": "pass", "note": "Read from their payload, not ours." },
        "one_condition_neutralized":  { "verdict": "n/a",  "note": "Single condition." }
      },
      "why_not": "Ceiling is 0.29 AQ and half of it was already conceded upstream as intended, so it would spend attention we need for the routing term.",
      "reconsider_if": "the dashboard starts rendering the field, or anything begins scoring with it"
    }
  ],
  "reported": [
    { "id": "verification-measures-density",
      "confirmed_by": "Counterfactual on the real corpus plus a synthetic case with a control.",
      "state": "accepted upstream, carried by PR #66" }
  ],
  "dismissed": [
    { "id": "recovery-tautological",
      "killed_by": "Paired tool_use/tool_result and looked for a later successful retry of the same tool: 90.2% vs the 96.7% reported. Definition is loose, number is nearly right." }
  ],
  "process_friction": [
    { "phase": "0",
      "what": "The published number could not be reproduced until the module entry point was used; the documented script is an import shim that exits 0 silently.",
      "cost": "one wasted run",
      "cost_units": { "unit": "runs", "value": 1 } }
  ]
}
```

## Field rules

Each of these exists because a run got it wrong.

**`corpus`** — mandatory, emitted before any other number. Without a fingerprint, counts
compared across machines mean nothing. The one substantive disagreement with the tool's
authors was explained entirely by the two sides measuring different corpora.

**`anchor.ok`** — `false` means every finding in the file is unsafe to read. Phase 0 is a
gate: if the base run does not reproduce the published number, the method is wrong before
any finding is.

**`null` is the common case and it needs `anchor.note`.** Most runs have no published figure
at the pinned contract to compare against, and `second-corpus.md` treats a null as usable for
composition and shape while only a `false` disqualifies. So `emit-gate.py` does not demand a
pass; it demands a reason, and refuses a file whose `ok` is not `true` while `findings[]` is
non-empty and `note` is blank. Requiring `true` instead was tried and measured: it rejects
every run this skill can currently produce and it ends the contributor path, which emits with
`ok` null by design.

`anchor.py` leaves an `anchor.json` beside `stats.json` carrying `ref`, `contract`,
`published`, `reproduced`, `ok` and the probe result, and `new-run.py` reads it. That file is
a record, not a gate: nothing requires it to exist in order to run a check. It exists so the
skeleton stops re-deriving what Phase 0 already resolved, which is how `tool.ref` came out
`null` on a `git archive` tree that has no `.git` for `git rev-parse` to read.

**`corpus.sources`** — the sources gnomon actually SCORED, read from
`scoring_inputs_by_source` in the payload. Not from the transcripts: this was built from an
`event["source"]` key that no Claude Code transcript carries, so the set came out empty every
time and a `["claude"]` fallback was the only branch that ever ran. It wrote `claude` on a
window whose payload said claude and codex, and this is the field the cross-machine
comparison leans on hardest.

**`shape`** — one of the Phase 2 keys, never a tool-specific axis name. This is what lets
the schema survive the tool renaming, splitting, or adding axes. Axis names go in `axes`,
which is free text.

**A Phase 1 gap does not need a shape.** Some gaps are a plain counting error in one axis and
map to none of the five structural shapes. Those belong in `axes[]`, which carries the same
`evidence` / `confidence` / `not_checked` fields as a finding for exactly this reason. A run
hit this with a source-confirmed 63% undercount and had to choose between mislabelling the
shape and extending the entry unsanctioned; it is sanctioned now. If a gap has a shape it is
a finding; if the axis is simply counting wrong, it is an axis entry.

**`direction`** — `overestimates` | `underestimates` | `faithful`. Stating the size of a
gap without its direction is how a report ends up arguing the opposite of what the data
shows. Both directions matter: an axis that flatters you is as unfaithful as one that
punishes you, and easier to miss.

**`magnitude.bound`** — `upper`, `lower`, or absent when the estimate is a point. A bound
reported as a point estimate is a specific, repeatable mistake: the −5.03 is an upper bound
because it removes every forced call, and 90.2% is a lower bound because switching approach
is also recovery.

**`confidence`** — `fact` or `hypothesis`, and nothing else. Anything that could vary with
the corpus, the version, or the reader's usage is a hypothesis. Facts are things this run
measured. A run challenged on a finding once wrote a sentence here — "fact for the mechanism
in the fixture; hypothesis for whether it fires on any real corpus" — which reads as
precision and is a hedge: the finding had failed a Phase 3 row and belonged in `dismissed`.
`emit-gate.py` rejects anything outside the two words.

**`refuted`** — mandatory on every finding, one entry per Phase 3 row, each
`{"verdict": "pass" | "fail" | "n/a", "note": "the fact behind the verdict"}`. A `fail`
means the finding did not survive, and `emit-gate.py` rejects the file rather than letting
it render: what did not survive goes to `dismissed`. A verdict without a note is rejected
too — it is the same unchecked claim in a smaller box. The gate cannot judge whether a note
is honest; it insists the row was answered, which is where the failure actually happened.

**`evidence.control`** — mandatory for any finding backed by a synthetic fixture. Name the
case that must come out non-zero and show that it did. Without it, a zero may be a broken
fixture rather than a real absence.

**`not_checked`** — mandatory, non-empty. A finding that claims complete coverage without
naming its blind spots is the failure mode to avoid. If nothing was left out, say which
question you did not ask.

**`dismissed[].killed_by`** — the fact that killed it, not the verdict. This is what stops a
dismissed finding from being rediscovered and re-argued next month.

**`reported`** — findings that are true, reproduced, and already in the hands of the people
who own the audited tool. Without this state a confirmed finding has nowhere to go but
`dismissed`, and a run really did file one there annotated "Not dismissed as false". That is
the schema forcing a lie. `findings` is what this run is raising; `reported` is what is
already raised, so the next reader neither re-argues it nor re-sends it.

**`measured_ref`** — the ref the pipeline actually ran against, which is not the same thing
as `ref` and used to be conflated with it. `ref` comes from the ```pin block, so a payload
built by `anchor.py` had the pin on both sides of `emit-gate.py`'s ref comparison: a check
advertised as catching "a pipeline pointed at the wrong directory" was equal by construction
and could not fail. A cold run measured the read-only reference clone twelve commits behind
the pin, the payload read the pin, and the gate passed clean.

It is allowed to be absent: a `git archive` copy has no `.git` and cannot report a ref, and
every payload written before the field existed carries none. What is not allowed is a
mismatch nobody discloses. When it differs from the pin, `anchor.note` has to name it, the
same four-word bar the `ref` rule sets, because a deliberate run at another ref and an
accident read identically in the file.

**`kind`** — the optional companion on a `not_checked` entry, and the thing that lets two
runs declaring one hole be counted as one hole. An entry may stay a bare string forever; 29
payloads on record are, including the example run above. When it is an object, `kind` comes
from the closed vocabulary in `emit-gate.py` (`BLIND_SPOT_KINDS`) and `term` names the signal
or constant it is about. The identity is then DERIVED as `<axis>/<kind>/<term>` — nobody types
an id, because across the saved runs one hole carries sixteen wordings and one finding carries
five different hand-typed ids, so neither the prose nor the `id` field could ever key them.

Same call the schema already made for `process_friction[].cost`: the prose stays and a
comparable companion is added beside it, rather than the prose being replaced by a code.

The comparison against `references/blind-spots.json` happens at Phase 4 and nowhere earlier.
That registry carries keys and no sentences, and `scripts/blind-spots.py` has no browse mode:
you can ask it what your finished payload missed, and you cannot ask it what the known holes
are. A cold run that read a list of holes during Phase 0 reported that it anchored the whole
investigation before a single measurement existed.

One real entry from that registry, so the shape does not have to be reconstructed with
`python3 -c "import json; ..."` a fourth time (a cold run did this, once per bucket):

```json
{
  "id": "Model mix/not-localized/linked_model_routing_state",
  "anchor": "Model mix",
  "kind": "not-localized",
  "term": "linked_model_routing_state",
  "runs": 13,
  "first_seen": "2026-08-10",
  "last_seen": "2026-08-20",
  "reopens_when": null
}
```

`id` is the derived `<axis>/<kind>/<term>` from the rule above, not typed by hand.
`reopens_when` is `null` until it carries a structured condition, e.g.
`{"kind": "signal_below_threshold", "signal": "skills_distinct", "threshold": "SKILLS_TOTAL_PER_CALL_TARGET"}`
for another entry in the same registry, not free text.

**`what_would_close_it`** — the observation that would settle a finding either way, concrete
enough for the reader to go and get it. Optional here and required by `render-issue.py`,
because the split is deliberate: this schema governs the audit artifact, where a finding kept
for your own records owes nobody a closing condition, while the message that goes out does.
A claim that cannot be closed produces three replies instead of one. Present but empty is
rejected: leave the field out or write it.

**`not_raised`** — true, survived Phase 3, and deliberately not sent. This is the third
state the `reported` note above predicted: a run confirmed the Steering leverage disclosure
gap on two corpora, and the owner judged it too slight to spend a maintainer's attention on.
Filing that in `dismissed` would say something killed it and filing it in `findings` would
say the run is raising it — both false, and `dismissed` is the exact lie `reported` exists to
prevent. Entries keep their `refuted` block, because deciding not to send something is not a
reason to skip proving it, and add two fields:

- **`why_not`** — the judgement, in the owner's terms. "Too small to send alone" is a
  complete reason; padding it into a technical objection it is not would misrepresent a
  scoping call as evidence.
- **`reconsider_if`** — the condition that would change the answer, concrete enough to
  evaluate without re-litigating. Without it this list becomes a graveyard that the next run
  re-derives from scratch, which is the cost the whole state exists to avoid.

`emit-gate.py` requires both, and requires the `refuted` block: a finding nobody proved has
not earned the right to be remembered as true.

**`process_friction`** — what the audit cost you that the audit's subject did not cause: a
phase that hung, a command that failed silently, a flag that was accepted and ignored. A
cold run invented this key because it had nowhere to put the four defects it had just found
in the skill itself, and those were the most valuable output of the run. It is part of the
contract now. Findings improve the audited tool; this improves the auditor.

`cost` is prose and stays prose: across the saved runs it holds 74 distinct values, and the
specific ones are the valuable ones -- *"three separate polls of the background log that
showed nothing new"* is worth more than any number. What prose cannot do is let two runs be
compared, so there is an **optional** companion:

```json
  { "phase": "0", "what": "...", "cost": "four re-runs",
    "cost_units": { "unit": "runs", "value": 4 } }
```

`unit` is one of `runs`, `renders`, `minutes`, `seconds`, `none`, and `value` is a number.
`emit-gate.py` validates it when present and ignores it when absent -- omitting it is always
allowed, because inventing a number for a cost nobody measured is worse than having none.
`none` is in the vocabulary on purpose: an entry recorded so the next run does not rediscover
something, at no cost, is a real and common case.

**`run_cost`** — what the audit cost, in units. `process_friction[].cost` is the only other
place cost appears and it holds prose (`"four re-runs"`, `"unknown number of past runs"`),
which cannot be compared between two runs.

```json
  "run_cost": {
    "wall":    {"started": "...", "ended": "...", "seconds": 900, "derived_from": "..."},
    "checks":  {"unit": "seconds", "value": 66.1},
    "arms":    null,
    "adhoc_checks": null,
    "gate_retries": {"unit": "count", "value": 0},
    "phases":  {"0_anchor": 214.7, "4_synthesis": 685.3}
  }
```

`wall` is **derived**, never reported. `new-run.py` takes it from the mtimes of the run's own
output directory, which is the one source here without an opinion: a cold run's self-reported
clock came in inflated **2.3x both times** anyone compared it against reality, saying 45
minutes for runs that took 19.4 and 19.9. `derived_from` says so in the payload so a reader
does not mistake it for a self-report.

Since 2026-08-24 that is not always a single directory. `anchor.py`'s own work directory (the
one `--stats` points at, and `anchor.json` is read from) can be a completely separate tree
from `--out` -- exactly how this project's own convention stages a fresh checkout copy apart
from where a run's artifacts land, and exactly how a dispatched cold run was invoked that day.
`new-run.py` used to walk only `dirname(--out)`, so anchor.json's mtime (15:04:44) was
structurally invisible to a span that only ever saw the earliest file in `--out`'s own
directory (15:07:17, 153 seconds later) -- not excluded by `EXCLUDE_FROM_SPAN`, just never
walked at all. With `4_synthesis = wall.seconds - 0_anchor` that shipped `-34.0`, a
structurally impossible negative duration, into a rendered report undetected. `wall` is now
the union of both roots (`_combine_spans` in `new-run.py`), and `derived_from` says plainly
which case it is: "mtimes of the output directory" when `--stats` lands beside the payload
(the common case, and a no-op for every run before this fix), or "mtimes of TWO directories"
when it does not.

The walk excludes `checkout/` (and `anchor/`, `.git/`, `__pycache__`, see `EXCLUDE_FROM_SPAN`
in `new-run.py`), and that is load-bearing rather than tidy: `checkout/` is where `anchor.py`
writes its copy of the audited checkout, and those files carry the date `git archive` stamped
on them, not the date the run touched them. One real run's raw directory span read **47
hours** because of it. `selfcheck/replay-run-cost.py` builds that exact trap and fails
without the exclusion. The exclusion applies inside EACH root when there are two, not just
the output directory's own.

`null` is the honest answer when there is nothing to span -- a single artifact spans no time,
and reporting `0` would be a measurement. `checks`, `arms` and `adhoc_checks` are filled from
the wall-clock lines `run-checks.py` and `run-arms.py` already print, or from a count of what
ran, and each carries its unit rather than a bare number: two saved runs wrote this same field
with two different meanings under it, `13` meaning a **count** of checks in one run and
`101.3` meaning **seconds** of wall clock in the next. Nothing in the field told them apart.
The shape is `{"unit": "seconds"|"count", "value": N}`, `emit-gate.py` refuses a bare number
or an unknown unit, and `null` stays legal for "not measured" (the common case: no A/B ran, so
`arms` is `null`). Report the mechanism's own counter beside the money number, never the money
number alone.

**`run_cost.gate_retries`** -- how many times the REAL submission gate already failed for this
run before it passed, counted from an append-only log `render-report.py` writes beside the
payload (`<run>.gate-log.jsonl`, one line per invocation) rather than typed by whoever ran it.
It counts only calls through `render-report.py`'s own `gate = subprocess.run(...)` -- a
standalone `emit-gate.py` invocation run for diagnosis (a saved transcript shows one run doing
exactly this, twice, from two different working directories, on purpose, to compare behaviour)
is not a submission attempt and never touches the log. This is fully automatic: unlike
`run_cost.agent`, nobody has to fill it in, and a run that never touches `render-report.py`
carries no `gate_retries` at all.

`0` is a normal and meaningful value -- first-try success, not "nothing to report" -- and is
written whenever the log has no `fail` entries yet, which is the common case. It is distinct
from two other states: **absent**, meaning this payload never went through the logging code at
all (an old payload, or one hand-assembled without `render-report.py`), and **null**, meaning
the log file exists next to the payload but could not be read cleanly -- a hand-truncated or
corrupted log degrades to `null` rather than a fabricated `0` or a crash, the same precedent
`emit-gate.py`'s own `pinned_ref()` sets for an input it cannot resolve.

**`run_cost.phases`** — where `wall` went, split into the one phase that has its own timer
and everything else. `anchor.py` was the only large script in this skill with zero internal
timing: two saved cold runs measured the orchestrating session at 767s and 1163s total, while
`wall` (mtimes of the output directory) only covered 578s and 933s of that. The missing
190-230s both times was `anchor.py`'s shell-out to the external scoring pipeline, and nothing
recorded it. `0_anchor` is that shell-out's own `time.monotonic()` span, written into
`anchor.json` as `pipeline_seconds` and read back from there -- `null`, not `0`, on a run made
with an `anchor.json` from before this field existed (most saved runs). `4_synthesis` is
**derived, not measured**: `wall.seconds - 0_anchor`, the residual covering Phases 1-5 (per-
axis checks through send). There is no artifact that marks a boundary inside that span to
measure it directly -- `render-report.py` overwrites the same payload file on every synthesis
pass, so the file's own mtime span between "skeleton created" and "final write" collapses to
zero by construction, not because synthesis took no time. `4_synthesis` is `null` whenever
either `wall` or `0_anchor` is `null`, and never a fabricated `0`.

It is meant to never be negative either, and until 2026-08-24 that was only an intent: `wall`
missing the anchor-work root (see above) made the subtraction go negative in a real payload,
`-34.0`, and nothing refused it. `wall` unioning both roots closes the cause that produced
that number, but the residual is still a subtraction against whatever mtimes happen to exist,
not a value with a hard floor -- so `emit-gate.py` now refuses a negative `4_synthesis`
outright, as a backstop for whatever the next way to get it wrong turns out to be, rather than
leaving the guarantee resting on `new-run.py` alone.

Filling `checks`/`adhoc_checks`/`arms` by hand from the printed lines never actually happened
across the saved runs, so it is automated now instead of documented as a manual step nobody
took. `run-checks.py --emit <path>` and `run-arms.py --emit <path>` write the same wall/serial
numbers as JSON, the same handoff shape `axis-terms.py --emit` already uses for
`axis-coverage.py --terms`. `render-report.py` looks for two fixed paths next to the run
directory that holds the payload it is rendering:

  - `<run>/checks/run-checks-emit.json` -- point `run-checks.py --emit` here
  - `<run>/run-arms-emit.json` -- point `run-arms.py --emit` here

and patches `run_cost.checks`, `run_cost.adhoc_checks` and `run_cost.arms` from whichever of
the two exist, writing the patched payload back to `src` **before** gating it, then gating
that version, and only rendering the `.md` once the gate agrees. Neither file existing is a
no-op: `render-report.py` does not touch `run_cost` at all in that case, so a run that never
called `--emit` renders exactly as it did before this automation existed. `--check` mode does
none of this patching -- its contract is comparing the report against its source with zero
side effects, and reading an `--emit` file from disk would be one.

**`run_cost.agent`** — what dispatching THIS RUN as a subagent cost, filled from the
completion notification the harness writes when it does. **Entirely absent is the normal
case**: most runs are not dispatched as a subagent, and the field is absent (not a
null-filled object) then, the same convention `anchor` and `corpus` already use for "nothing
to say" versus "measured and empty".

```json
  "run_cost": {
    "agent": {"tool_uses": 47, "duration_ms": 766887,
              "output_tokens_total": 28558, "context_peak": 131780}
  }
```

Filled **only by whatever dispatches miraudit**, never by anything under `scripts/`: a
script running inside the corpus-walk pipeline has no access to its own dispatch transcript,
so `new-run.py`, `render-report.py` and `anchor.py` neither write this field nor assume it
exists. An orchestrator can copy it straight off the harness's `<usage>` block, or run
`scripts/agent-cost.py <the subagent's own transcript path>` to derive the same numbers from
disk instead of hand-copying them off a notification that is not saved anywhere once read.

`tool_uses` and `duration_ms` are the trustworthy fields here, the way `run_cost.wall` above
is already derived rather than reported because a self-reported clock came in inflated 2.3x
both times anyone checked it: `tool_uses` is a plain count of `tool_use` blocks and
`duration_ms` a delta between two transcript timestamps, both near-deterministic
reconstructions rather than something a model estimates. `output_tokens_total` and
`context_peak` are read the same mechanical way but are noisier and turn-shape dependent --
informational, not meant for cross-run comparison. And `context_peak` is deliberately not
named `subagent_tokens` or "tokens used": checked against two real runs, the harness
notification's own `subagent_tokens` field (130010 / 160998) turned out to be close to the
LAST message's input+output+cache_read+cache_creation total, i.e. a final-context snapshot,
while the real cumulative `output_tokens` summed to 28558 / 47410 over the same two runs.
Reporting a snapshot as "tokens used" is exactly the kind of mislabeled metric this skill
exists to catch in other tools' dashboards, so `agent-cost.py` never emits that name.

## Rendering the markdown

`render-report.py`'s own order, upstream of the document's: patch `run_cost` from any
`--emit` files (see above), gate the patched result, and only then render. Gating a payload
this script never wrote meant nothing gated ever inspected what a later patch would add;
gating after the patch means whatever ships in `run_cost` was validated by the same gate as
every other field. The patch is written to a `src + ".partial"` temp file and gated there
first, so a gate failure -- for any reason, not necessarily one the patch caused -- leaves
`src` untouched rather than half-applied.

Order within the document: verdict, then what was confirmed, then what was dismissed. The
dismissed section is not filler — it is the evidence that what survived went through a
filter, and it is what keeps a reader from re-opening settled ground.

An empty `findings` with a populated `dismissed` renders as a normal, useful report. Say so
plainly rather than padding it.
