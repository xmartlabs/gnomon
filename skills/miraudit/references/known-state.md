# Known state — gnomon / xl-ai-insights

**This file expires.** It pins what was true at one commit. Phase 0 compares the installed
version against it; if they differ, every finding below is a hypothesis again and the
fixtures in `scripts/` have to be re-run before anyone quotes them.

- **Validated against:** `3148a96` on `main` (contract `16:16:16`), 2026-08-07.
- **How to check yours:** resolve the installed ref, then compare the contract string in
  the scoring output. A different contract means the calibration or the axis set moved.

## Confirmed and fixed

Both were reported by us, implemented upstream, and verified here.

| What | Verified how |
|---|---|
| `Workflow` fan-out sourced from dispatched-agent transcripts instead of one-per-call | Ten injection fixtures, each with a control: parent attribution, dedup, `agentId` fallback, out-of-window zero, and no double-count with `Agent`/`Task` sidechains. All ten pass. |
| Compounding credits MCP knowledge-writes, not only filesystem paths | No false positives across the corpus: only `add_memory` and `update_memory` credit; `search_memories`, `delete_memory`, `get_*` and doc-fetch servers do not. |

Three-point A/B at the published window reproduced 88 → 89 → 91, attributing +1 to the
fan-out fix and +2 to the compounding fix.

## Open

**Verification measures density, not coverage.** `rate(shell_test_runs, target)` normalises
by total tool calls, so the same testing discipline scores worse the more non-test work a
session contains. Two proofs, both holding the numerator fixed:

- Counterfactual on a real corpus: fixing the inline group's tests-per-edit ratio and
  applying it to the delegating group still leaves the delegating group 4.3× lower.
- Synthetic, with a control: 100% coverage scores 0.198, 20% coverage scores 0.714.

Reported once, corrected once (see `refutation.md`, `invented-denominator`), unanswered.

**ToolSearch credits mandatory tool loading, in two pillars.** 577 of 603 calls are
`select:` — loading tools by exact name — and 419 of those loads are core built-in tools.
The counter feeds both a Breadth axis and a Savvy axis. Removing the forced calls costs
5.03 AQ, which is an upper bound. Not yet reported.

## Reviewed and dismissed — do not re-open

Each has the fact that killed it. Full write-ups in `refutation.md`.

| Candidate | Killed by |
|---|---|
| Recovery is tautological | Properly paired measurement gives 90.2% against the 96.7% reported. Loose definition, nearly right number. |
| Context Intelligence is boilerplate from a config rule | Only 26% of grounded sessions armed in the first three tool calls; 25 of 42 armed after position 10. |
| ToolSearch appeared with a harness rollout | Its start date is the corpus start date. Retention, not rollout. |
| `Workflow` and `Agent` double-count fan-out | `Agent` sidechains live one level up and the path pattern excludes them. |

## Denominator note

`eligible_change_sessions` counts writes to the harness-assigned ephemeral scratchpad
(`/private/tmp/claude-<pid>/<project>/<session-uuid>/scratchpad/`). Four of 50 code-editing
sessions qualify only through that, and C2 eligibility moves from 34 to 40.

It costs nothing today — both consumers are saturated with margin — but it biases any
diagnostic built on that counter by about 15%. Report it as context, not as a finding.
