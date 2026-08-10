# Known state — gnomon / xl-ai-insights

**This file expires.** It pins what was true at one commit. Phase 0 compares the installed
version against it; if they differ, every finding below is a hypothesis again and the
fixtures in `scripts/` have to be re-run before anyone quotes them.

- **Validated against:** `c6401cc` on `main` (contract `17:17:17`), 2026-08-10.
- **Known to be moving:** nothing pending upstream. #66 and #67 merged on 2026-08-10; see
  "What v17 changed" below for what that invalidated here.

## How to refresh this file

The pin going stale is expected. The file going stale *silently* is the failure. Whoever
notices the drift does this, in order:

0. **Re-check the upstream PR states with `gh`, every time.** Never carry them from a
   conversation, a plan, or an earlier version of this file. On 2026-08-10 this section
   named three PRs as open that had been closed the day before. It costs one command:
   `gh pr list --repo <upstream> --state all --limit 10`.
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

Pass the report's own boundaries. `--last=30d` is a valid flag — an earlier draft of this
file was about to claim it had been removed — but it is a rolling window that ends now,
drifts daily, and includes the audit session itself. **Passing no window flag at all is
worse than a rolling one:** it scores the entire corpus, and on a corpus wide enough,
`ordered_facts_state` flips to `unmeasured`, which drops the coverage terms and deletes
Context Intelligence from the report. Measured on one corpus, same code, same day:

| window | AQ | Context Intelligence |
|---|---:|---|
| `--since=2026-07-07 --until=2026-08-06` | 92 | 20.0 |
| `--last=30d` | 91 | 20.0 |
| no flag (314 sessions) | 88 | **absent** |

Verification reads *higher* in the last row — 28.8 against 23.2 — because its coverage term
was dropped and the weight renormalized, not because anything was tested more. Reading an
axis that went up as an axis that improved is the exact mistake this skill exists to catch.

**Never omit `--output-dir`.** Without it this entry point writes `stats.json`, `report.md`,
`summary.json`, `narrative_input.md` and `profile.html` into the project directory — which,
run against a checkout, means writing inside the audited repo. All five are in gnomon's
`.gitignore`, so `git status` stays clean and the write is invisible to the check most
people would use to catch it. Verify with `ls`, not `git status`. This happened during a
run of this skill.

**What the dashboard shows is not what this code computes.** Without `--local`, the CLI
uploads and opens the mirdash deployment, which is a separate service that lags the
contract: a run whose local output was AQ 91 on `17:17:17` displayed 97, in an older
layout, with fewer Craft axes. Numbers from the web page are not comparable to numbers
from the CLI, and gnomon's own `COMPARISON_POLICY = "same_score_contract_id_only"` is the
reason. Audit the local output.

## What v17 changed — #66 and #67, both merged 2026-08-10

**Verified with `gh` and by running the merged code, not carried from conversation.**
#62, #63 and #65 were closed unmerged on 2026-08-09 and superseded by **#66**
(`c6401cc`), which merged on 2026-08-10 alongside **#67** (`23aeb4b`).

An earlier version of this section listed those three PRs as open, a day after they closed.
That error is the one this file exists to prevent, and it was avoidable: the run that wrote
it had already flagged "did not verify whether those PRs are still open" as a gap and the
claim went in anyway. Hence the first step of the refresh procedure above.

**#66 removed three targets, not two.** This file said "both" and named two;
`TASK_CALLS_PER_CALL_TARGET` went with them. The count came from grepping the merged
checkout, not from reading the PR description.

| Gone in v17 | Consequence here |
|---|---|
| `TEST_RUNS_PER_CALL_TARGET` | `verify-verification-axis.py` **deleted** — it demonstrated a fixed bug. `measure-verification-corpus.py` exits loudly through `require()`, as designed |
| `TOOLSEARCH_PER_CALL_TARGET` | Section D of `fidelity-audit.py` **deleted**. `toolsearch_calls` survives as a published diagnostic no term reads, so the `signal-reused` shape it showed is gone |
| `TASK_CALLS_PER_CALL_TARGET` | Dropped from the saturation arm's pairings |

**#67 filters low-volume sources** (`LOW_VOLUME_SESSION_THRESHOLD = 10` sessions, in
`cli/local.py`). It drops whole sources from scoring — on the corpus here, codex, cursor
and opencode — and `--include-low-volume` restores them. It sounds decisive and is not:
measured as an A/B on the same window, it moves AQ by **0**, and the only axis that moves
at all is Discipline, by −0.1, because the restored source adds 25 tool calls to a
denominator. Do not attribute a score change to it without running that A/B.

**The Verification finding was implemented.** `accumulator.py` now emits
`test_covered_change_sessions` as C2 eligibility crossed with per-session test runs, and
`aq.py` scores `0.5 · coverage + 0.5 · rate(review_skills)`. Upstream went further than the
proposal, which kept density as a third term at 1/3 weight: they deleted density outright
and scored coverage against the raw ratio. On this corpus the axis went 20.1 → 23.2 —
**up**, not down as the proposal predicted, because the coverage ratio (0.3673) beats the
density term it replaced (0.170).

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

Reported, corrected once (see `refutation.md`, `invented-denominator`), **accepted upstream and
MERGED in `c6401cc`**, which removes the density target outright and replaces it with the
coverage term. Fixed; do not re-send.

**ToolSearch credits mandatory tool loading, in two pillars.** 577 of 603 calls are
`select:` — loading tools by exact name — and 419 of those loads are core built-in tools.
The counter feeds both a Breadth axis and a Savvy axis. Removing the forced calls costs
5.03 AQ, which is an upper bound. **Reported, accepted upstream, and MERGED in `c6401cc`:** `toolsearch_calls` is now a
published diagnostic that no term scores. Fixed; do not re-send.

**Two more, found by cold runs. One is now reported, one is not.** Both are named here with
their magnitude only. **Do not paste their diagnosis into this file.** A later cold run reported
that reading it during Phase 0 anchored its investigation before a single measurement — in a
skill whose `design-rationale.md` argues at length that one agent checking another shares its
blind spot. Keep the count and the size; leave the mechanism to be re-derived.

Both were re-checked against `c6401cc` and both survive v17 unchanged. State only — the
diagnosis stays out of this file on purpose.

| id | magnitude | status |
|---|---|---|
| `model-mix-drops-routing-outside-wsum` | 1 AQ (92 -> 91), axis 50.0 -> 43.1 | **reported: issue #68, 2026-08-10** |
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
diagnostic built on that counter by about 15%. Reported as context; the eligibility fix
merged in `c6401cc`.
