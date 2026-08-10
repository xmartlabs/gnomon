# Output schema

One run writes `miraudit-<date>.json`, then renders `miraudit-<date>.md` **from it**. Never
write the two by hand: they drift, and a report that has drifted from its evidence is the
defect this skill exists to catch.

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
      "state": "accepted upstream, PR #65" }
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

**`confidence`** — `fact` or `hypothesis`. Anything that could vary with the corpus, the
version, or the reader's usage is a hypothesis. Facts are things this run measured.

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
