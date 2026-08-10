# Known state — gnomon / xl-ai-insights

**This file expires.** It pins what was true at one commit. Phase 0 compares the installed
version against it; if they differ, every finding below is a hypothesis again and the
fixtures in `scripts/` have to be re-run before anyone quotes them.

- **Validated against:** `3148a96` on `main` (contract `16:16:16`), 2026-08-07.
- **Known to be moving:** contracts `17:17:17` and `18:18:18` are in open upstream PRs. See
  "Incoming" below before trusting anything here.

## How to refresh this file

The pin going stale is expected. The file going stale *silently* is the failure. Whoever
notices the drift does this, in order:

1. Resolve the installed ref and the contract string in the scoring output. **The contract
   is the gate, the ref is a hint.** A different contract means the calibration or the axis
   set moved and everything below is a hypothesis again. A different ref with the same
   contract is common and usually harmless: read the diff, and if it touches none of
   `scoring/`, `taxonomy.py` or `cli/accumulator.py`, record that and treat the pin as
   holding. Say which of the two you checked — a run once had to invent this rule because
   the file only said "if they differ".
2. Re-run every fixture in `scripts/` against the new checkout. A fixture that dies on an
   `ImportError` is doing its job: it depended on a symbol that no longer exists.
3. For each entry below, decide one of three things and write it down: still true, now
   fixed (move it to "Confirmed and fixed" with how it was verified), or **obsolete because
   the axis it describes no longer exists**.
4. Delete the fixtures whose subject is gone. A fixture that demonstrates pre-fix behaviour
   prints a confident conclusion its own numbers contradict once the fix lands. This has
   already happened once, to `verify-compounding-mcp.py`, which is deleted on purpose.
5. Update the pin and the date at the top.

## Running the tool (Phase 0 operations)

`python3 xl_ai_insights.py` is an import shim with no `__main__` guard. It exits 0, prints
nothing, writes nothing, and looks like success. Use the module entry point on the
throwaway copy instead:

```bash
uv run --project <copy> -- python -m gnomon.cli.insights \
    --local --console --no-open \
    --since=YYYY-MM-DD --until=YYYY-MM-DD --output-dir=<dir>
```

`--output-dir` warns "unknown flag" and then honours it. That is an upstream quirk, not a
sign the command is wrong.

Pass the report's own boundaries, never `--last=30d`: a rolling window ends now, drifts
daily, and includes the audit session itself. The published reports this file was built
against ran `--since=2026-07-07 --until=2026-08-06`.

## Incoming — three PRs, all responses to findings below

Reported by us, accepted upstream, open at the time of writing. When they merge, the two
"Open" entries move to "Confirmed and fixed" and the fixtures that demonstrate them expire.

| PR | What it does | What it invalidates here |
|---|---|---|
| #62 | Stops crediting harness-imposed activity in eligibility and ToolSearch: scratchpad writes (`/private/tmp`, `/tmp`, `/var/folders`) no longer count as code changes | The denominator note below |
| #63 | Drops the ToolSearch rate term from both axes entirely. Contract `17:17:17` | The ToolSearch entry, and section D of `fidelity-audit.py` |
| #65 | Replaces Verification's density term with per-session coverage, drops the task-tool term. Contract `18:18:18`. Stacked on #63 | The Verification entry, and `verify-verification-axis.py` in full |

## Confirmed and fixed

Both were reported by us, implemented upstream, and verified here.

| What | Verified how |
|---|---|
| `Workflow` fan-out sourced from dispatched-agent transcripts instead of one-per-call | Ten injection fixtures, each with a control: parent attribution, dedup, `agentId` fallback, out-of-window zero, and no double-count with `Agent`/`Task` sidechains. All ten pass. |
| Compounding credits MCP knowledge-writes, not only filesystem paths | No false positives across the corpus: only `add_memory` and `update_memory` credit; `search_memories`, `delete_memory`, `get_*` and doc-fetch servers do not. **Fixed does not mean exact — see the caveat below.** |

**Caveat on Compounding.** It credits the right calls and undercounts them by 63%. Writes are
deduplicated by a key built from the call's arguments, and `add_memory` carries none of the
fields that key looks for, so every such call in a session collapses onto one bucket:
441 knowledge-writes earn 165 credits. The axis is saturated, so correcting it moves the total
by nothing — which is why this reads as fixed unless you measure it. Do not cite this row as
evidence that the counter is accurate.

Three-point A/B at the published window reproduced 88 → 89 → 91, attributing +1 to the
fan-out fix and +2 to the compounding fix.

## Open

**Verification measures density, not coverage.** `rate(shell_test_runs, target)` normalises
by total tool calls, so the same testing discipline scores worse the more non-test work a
session contains. Two proofs, both holding the numerator fixed:

- Counterfactual on a real corpus: fixing the inline group's tests-per-edit ratio and
  applying it to the delegating group still leaves the delegating group 4.3× lower.
- Synthetic, with a control: 100% coverage scores 0.198, 20% coverage scores 0.714.

Reported, corrected once (see `refutation.md`, `invented-denominator`), **accepted — PR #65**.

**ToolSearch credits mandatory tool loading, in two pillars.** 577 of 603 calls are
`select:` — loading tools by exact name — and 419 of those loads are core built-in tools.
The counter feeds both a Breadth axis and a Savvy axis. Removing the forced calls costs
5.03 AQ, which is an upper bound. **Reported and accepted — PRs #62 and #63.**

**Two more, found by cold runs and not yet reported.** Both are named here with their
magnitude only. **Do not paste their diagnosis into this file.** A later cold run reported
that reading it during Phase 0 anchored its investigation before a single measurement — in a
skill whose `design-rationale.md` argues at length that one agent checking another shares its
blind spot. Keep the count and the size; leave the mechanism to be re-derived.

| id | magnitude | status |
|---|---|---|
| `model-mix-drops-routing-outside-wsum` | ~1 AQ, worst case 2 | measured twice, with controls |
| `aq-is-mostly-ceiling` | 52% of the total sits on saturated axes | measured, with controls |

**A previous version of this file called the first one
`routing-term-dropped-by-workflow-children`. That name is wrong** and is recorded here so it
is not restored. Workflow-dispatched children are 97.3% of the leftover, which is what made
the name plausible, but 197 invalid `Agent`/`Task` attempts trip the same gate independently:
removing the Workflow children would not restore the measured state. A run that trusted the
name would have shipped a mis-attributed finding to the tool's authors.

## Reviewed and dismissed — do not re-open

Each has the fact that killed it. Full write-ups in `refutation.md`.

| Candidate | Killed by |
|---|---|
| Recovery is tautological | Properly paired measurement gives 90.2% against the 96.7% reported. Loose definition, nearly right number. |
| Context Intelligence is boilerplate from a config rule | Only 26% of grounded sessions armed in the first three tool calls; 25 of 42 armed after position 10. |
| ToolSearch appeared with a harness rollout | Its start date is the corpus start date. Retention, not rollout. |
| `Workflow` and `Agent` double-count fan-out | `Agent` sidechains live one level up and the path pattern excludes them. |
| `bash_runs_tests` counts a bare `cd` as a test run | It does not. The command was truncated to 70 characters by the display in the comparison script that "found" it. Confirmed by running the predicate on the exact string: `False`. |

**Below the reporting bar, recorded so it is not rediscovered:** `bash_runs_tests` matches a
runner name inside a quoted argument, so `grep -iE "tsc|npm run|vitest"` counts as running
tests. Real and verified, twice in the whole corpus. Not worth a report.

## Denominator note

`eligible_change_sessions` counts writes to the harness-assigned ephemeral scratchpad
(`/private/tmp/claude-<pid>/<project>/<session-uuid>/scratchpad/`). Four of 50 code-editing
sessions qualify only through that, and C2 eligibility moves from 34 to 40.

It costs nothing today — both consumers are saturated with margin — but it biases any
diagnostic built on that counter by about 15%. Reported as context; **PR #62 addresses it.**
