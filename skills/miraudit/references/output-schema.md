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
  "tool":   { "name": "xl-ai-insights", "ref": "3148a96", "contract": "16:16:16" },
  "corpus": { "files": 3059, "lines": 287670, "tool_calls": 41983,
              "window": "30d", "sources": ["claude", "codex", "cursor"] },
  "anchor": { "published": 91, "reproduced": 91, "ok": true },
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
      "not_checked": ["whether other harnesses treat ToolSearch as discovery"]
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
      "cost": "one wasted run" }
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

## Rendering the markdown

Order: verdict, then what was confirmed, then what was dismissed. The dismissed section is
not filler — it is the evidence that what survived went through a filter, and it is what
keeps a reader from re-opening settled ground.

An empty `findings` with a populated `dismissed` renders as a normal, useful report. Say so
plainly rather than padding it.
