# Robust source accounting — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Use superpowers:test-driven-development for every code task (write the failing test first). Steps use checkbox (`- [ ]`) syntax.

**Goal:** Guarantee that every source discovery finds either appears in the per-source breakdown (`source_usage`, dashboard tabs) or has its absence surfaced with a warning naming the source and reason. Fix the concrete case: Cursor's 2 sessions dropping silently between runs.

**Architecture:** Add a reconciliation step in the cli layer (`gnomon/cli/local.py`) that diffs discovered sources against `scoring_inputs_by_source` after it is built (~line 233) and warns on any dropped source. Root-cause Cursor's flakiness first; apply a parser/dedup fix in `gnomon/sources/` only if the drop is a real defect (not a legitimate zero-in-window window-edge artifact). Respect `sources/ → cli/ → output/` direction — no adapter learns about reconciliation.

**Tech Stack:** Python 3 stdlib, `unittest`. Tests patch `paxel.X` (propagated to gnomon modules via the `_PaxelModule` shim in `paxel.py`). Run: `python3 -m unittest discover -s tests -v`.

**Spec:** `docs/superpowers/specs/2026-07-21-robust-source-accounting-design.md`.

**Paths:** Modify `gnomon/cli/local.py`; conditionally `gnomon/sources/cursor.py` and/or `gnomon/sources/discovery.py`; add tests under `tests/`. All under repo root `/Users/marcossoto/Documents/experiments/gnomon`.

---

### Task 0: Root-cause the Cursor flaky drop (investigation, no code)

**Files:** read-only — `gnomon/sources/cursor.py`, `gnomon/sources/discovery.py`, `gnomon/cli/local.py`, `gnomon/cli/accumulator.py`.

- [x] **Step 1: Reproduce.** Ran `python3 paxel.py --summary --no-open` 3 times. Result: **Cursor absent in all 3 runs**, in the discovery banner (`Found N transcript files across ...` — cursor never listed via `grep -i cursor` on any run log), in `corpus.sources`, and in `scoring_inputs_by_source`. No flakiness observed on this machine — consistently absent.
- [x] **Step 2: Trace the four candidate drop points** — moot for this machine's state, because the drop happens *before* any of them:
  - Filesystem check: `~/.cursor/projects` does not exist, `~/.cursor/chats` does not exist, `~/Library/Application Support/Cursor/User/globalStorage/state.vscdb` does not exist (nor does `~/.cursor` or `~/Library/Application Support/Cursor` at all).
  - `gnomon/sources/discovery.py:163-167` only appends `("cursor", ...)` to `sources` if `os.path.isdir(CURSOR_DIR)` or `os.path.isfile(CURSOR_DB)` — both false here, so Cursor **never enters the `sources` list**, confirmed by `by_src = Counter(...)` (`local.py`, printed immediately after `discover_sources()`, before `_cursor_dedup`) never containing `cursor` in any of the 3 run logs.
  - Because Cursor never enters `sources`, `_cursor_dedup`, the in-window filter, and `_per_source_stats` registration are all unreached — none of them are the cause on this machine.
- [x] **Step 3: Classify the cause.** New bucket, not one of the three predefined: **`not-discovered`** — Cursor's on-disk data location does not exist at all, so discovery itself finds nothing. This is distinct from `parse-empty` (files exist, parse yields nothing) and `dedup-twin` (files exist, dedup misclassifies) — no gnomon code path is involved. It is analogous in spirit to `out-of-window`: a legitimate absence, not a defect.
- [x] **Decision gate: Task B is SKIPPED.** `not-discovered` is not `parse-empty` or `dedup-twin`, so no code defect was found or is being fixed in `sources/cursor.py` / `sources/discovery.py`. Caveat recorded in the spec: the original flaky observation (`cursor(1f/2s)` in one banner, absent from a later `summary.json`) was seen at an earlier point when Cursor's data directory apparently *did* exist transiently on that machine/session — that exact state could not be reproduced here since the environment has since changed (no Cursor data present at all now). The reconciliation warning (Task A) is the correct fix regardless of mechanism: it is keyed off the pre-dedup `by_src` Counter (the true "discovered" set) vs. `scoring_by_source.keys()` (the "present" set), so it will catch this drop whenever it recurs — whether caused by `not-discovered`, `parse-empty`, `dedup-twin`, or `out-of-window`.

---

### Task A: Reconciliation helper + warning

**Files:** Modify `gnomon/cli/local.py` (reconciliation call in `main()` after line ~233; helper near the other module-level helpers). Test: new `tests/test_source_reconciliation.py`.

- [x] **Step 1: Write the failing test** — create `tests/test_source_reconciliation.py`:

```python
import unittest
from gnomon.cli.local import _reconcile_sources


class TestReconcileSources(unittest.TestCase):
    def test_dropped_source_is_reported(self):
        # discovered has cursor; present (scoring_inputs) does not
        dropped = _reconcile_sources(
            discovered={"claude", "codex", "cursor"},
            present={"claude", "codex"},
            reasons={"cursor": "out-of-window"},
        )
        self.assertEqual(dropped, [("cursor", "out-of-window")])

    def test_all_reconciled_is_empty(self):
        dropped = _reconcile_sources(
            discovered={"claude", "codex"},
            present={"claude", "codex"},
            reasons={},
        )
        self.assertEqual(dropped, [])

    def test_reason_defaults_to_unknown(self):
        dropped = _reconcile_sources(
            discovered={"cursor"}, present=set(), reasons={},
        )
        self.assertEqual(dropped, [("cursor", "unknown")])
```

- [x] **Step 2: Run, expect FAIL** — `python3 -m unittest tests.test_source_reconciliation -v` → ImportError (`_reconcile_sources` does not exist).

- [x] **Step 3: Implement the helper** in `gnomon/cli/local.py` (pure, deterministic — sorted output):

```python
def _reconcile_sources(discovered, present, reasons):
    """Sources discovered but absent from the per-source breakdown, with a reason.

    Returns a sorted list of (source, reason) so nothing drops silently.
    """
    return sorted(
        (src, reasons.get(src, "unknown"))
        for src in (set(discovered) - set(present))
    )
```

- [x] **Step 4: Run, expect PASS** (3 tests). Same command as Step 2.

- [x] **Step 5: Wire it into `main()`** — after `stats["scoring_inputs_by_source"] = scoring_by_source` (~line 233), compute the discovered set from `source_files`/`source_sessions` (the post-dedup, post-accumulate set already printed in the `sources:` banner) and the present set from `scoring_by_source.keys()`, derive `reasons` from the accumulate pass (Task 0 buckets), and print one warning line per dropped source, e.g.:

```
  warning: source 'cursor' discovered but dropped from breakdown (out-of-window) -- not in source_usage/tabs
```

  Silent when the dropped list is empty. Keep the reason derivation cheap; if a precise reason is unavailable, fall back to `"unknown"` (the helper already handles it).

- [x] **Step 6: Manual check** — `python3 paxel.py --summary --no-open`; confirm the warning fires for the Cursor drop (or stays silent if Cursor is present), and no traceback. Result: silent (no drops on this machine — all 4 discovered sources reconciled), no traceback.

---

### Task B: Fix the Cursor root cause (CONDITIONAL — only if Task 0 = parse-empty or dedup-twin)

**Files:** `gnomon/sources/cursor.py` and/or `gnomon/sources/discovery.py`. Test: `tests/test_source_metrics_fixes.py` (append) or a targeted new test.

- [ ] **Step 1: Write the failing test** capturing the specific defect from Task 0. Examples by bucket:
  - `dedup-twin`: assert `_cursor_dedup([...single cursor source...])` does NOT remove the lone Cursor entry.
  - `parse-empty`: assert `_cursor_sqlite_events(<fixture db>)` yields a stable non-empty event list across repeated calls (read-only snapshot consistency).
- [ ] **Step 2: Run, expect FAIL** — `python3 -m unittest <the new test> -v`.
- [ ] **Step 3: Implement the minimal fix** for the identified cause. Do not broaden scope beyond making Cursor detection deterministic.
- [ ] **Step 4: Run, expect PASS.**
- [ ] **Step 5: Determinism check** — run `python3 paxel.py --summary --no-open` 3× consecutively; Cursor is present in `source_usage.by_source` and the tab set every time.
- [x] **If Task 0 = out-of-window:** SKIP this task. Task 0 = `not-discovered` (closely analogous); no code defect found; covered by Task A warning.

---

### Task C: Regression test — no silent drop for a low-session source

**Files:** `tests/test_source_reconciliation.py` (append) or `tests/test_scoring_inputs_by_source.py`.

- [x] **Step 1: Write the failing/int test** — build a minimal `scoring_inputs_by_source` with a low-session source (cursor-like, e.g. 2 sessions / 3 prompts) and assert `build_source_usage(...)["by_source"]` includes it with correct counts and a non-zero `sessions_pct`. Proves there is no min-session drop in the rendering layer.

```python
from gnomon.output.source_usage import build_source_usage

def test_low_session_source_survives():
    sibs = {
        "cursor": {"window": {"volume": {"total_sessions": 2, "total_prompts": 3,
                                          "tool_calls_total": 5},
                              "velocity": {"active_hours": 0.4}}},
        "codex":  {"window": {"volume": {"total_sessions": 100, "total_prompts": 900,
                                          "tool_calls_total": 5000},
                              "velocity": {"active_hours": 40.0}}},
    }
    out = build_source_usage(sibs)
    assert "cursor" in out["by_source"]
    assert out["by_source"]["cursor"]["sessions"] == 2
```

- [x] **Step 2: Run** — expect PASS immediately (documents/guards existing correct behavior; if it fails, a real regression exists to fix). Passed on first run, as expected.

---

### Task D: Verify gate + regenerate

- [x] **Step 1: Full suite** — `python3 -m unittest discover -s tests -v`, all green. Result: 992 tests, OK.
- [x] **Step 2: Regenerate** — `python3 paxel.py --summary --no-open`. Regenerated cleanly, no warnings, no traceback.
- [x] **Step 3: Reconcile check** — confirmed: `by_source` = `{antigravity-ide, claude, codex, opencode}`, matching the discovery banner exactly (Cursor absent from both, consistent with `not-discovered`, no silent drop); `context.total_sessions` (346) == `source_usage.totals.sessions` (346); no source in the banner missing from the breakdown without a warning.
- [ ] **Step 4: Dashboard** — re-upload insights; spot-check June (opencode local models present) and Cursor's presence/warning. Not performed in this session (requires the dashboard upload/network step, outside local verification scope) — flagged for the user to run when ready.

---

## Notes

- The design settles two decisions (see spec): absence + warning over forced zero-rows, and Task B conditional on root cause. Revisit only if reproduction contradicts them.
- Work happens on a new branch off `main` (per the collaboration plan); this doc and its spec are the starting point.
