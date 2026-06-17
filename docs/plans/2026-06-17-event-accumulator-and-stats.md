# EventAccumulator + Stats Deepening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deepen `paxel.py`'s accumulation stage into an `EventAccumulator` module behind a tiny interface, and give the cross-stage `stats` dict a declared `Stats` dataclass contract — without changing any output.

**Architecture:** A behavior-preserving refactor guarded by a golden `stats.json`. First freeze current output over the test fixtures. Then declare `Stats` dataclasses (output stays byte-identical via `asdict`). Then lift the 40 loose accumulators and the ~290-line event loop out of `main()` into `EventAccumulator.consume_file()` / `finalize(churn)`, leaving `main()` as a thin feed. `git_churn` is injected into `finalize` so the accumulator is testable with synthetic events. Verbatim voice samples move to a separate `voice_samples()` accessor, off `stats.json`. Everything stays **in `paxel.py`** (ADR-0001: single-file curl distribution).

**Tech Stack:** Python 3.8+ stdlib only (`dataclasses`, `unittest`). No new dependencies.

**Reference:** `CONTEXT.md` (terms), `docs/adr/0001-paxel-stays-single-file.md`.

**Test runner:** this project has NO pytest — it is stdlib `unittest`. Use `python3 -m unittest tests.<module>` for one module and `python3 -m unittest discover -s tests` for the full suite. (Plan steps below that say `pytest` mean the unittest equivalent.)

---

### Task 0: Freeze the golden stats.json

The whole refactor is behavior-preserving. Establish the tripwire first.

**Files:**
- Create: `tests/test_golden_stats.py`
- Create: `tests/fixtures/golden/stats.json` (generated, then committed)

- [ ] **Step 1: Write a helper that runs paxel over fixtures and returns the stats dict**

VERIFIED idiom — reuse `test_smoke.py`'s hermetic harness exactly: `mock.patch.multiple(paxel, OUT_DIR=out, **SRC_DIRS)` redirects both the output dir and every source-discovery global at `tests/fixtures/`. Do NOT use `--<source>-dir=` argv (the smoke tests don't, and `SRC_DIRS` covers Cursor's two paths that flags can't).

```python
# tests/test_golden_stats.py
import os, sys, io, json, shutil, tempfile, contextlib, unittest
from unittest import mock
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import paxel

FIX = os.path.join(HERE, "fixtures")
GOLDEN = os.path.join(FIX, "golden", "stats.json")

# Copy verbatim from tests/test_smoke.py (keep in sync if fixtures move).
SRC_DIRS = dict(
    BASE=os.path.join(FIX, "claude"),
    CODEX_DIR=os.path.join(FIX, "codex"),
    GEMINI_DIR=os.path.join(FIX, "gemini"),
    PI_DIR=os.path.join(FIX, "pi"),
    OPENCODE_DIR=os.path.join(FIX, "opencode"),
    CURSOR_DIR=os.path.join(FIX, "cursor", "projects"),
    CURSOR_DB=os.path.join(FIX, "cursor", "state.vscdb"),
)


def run_paxel_stats():
    """Run main() hermetically over the fixtures; return parsed stats.json."""
    out = tempfile.mkdtemp(prefix="paxel-golden-")
    try:
        argv = ["paxel.py", "--no-open"]
        with mock.patch.multiple(paxel, OUT_DIR=out, **SRC_DIRS), \
                mock.patch.object(sys, "argv", argv), \
                contextlib.redirect_stdout(io.StringIO()):
            paxel.main()
        with open(os.path.join(out, "stats.json")) as f:
            return json.load(f)
    finally:
        shutil.rmtree(out, ignore_errors=True)
```

- [ ] **Step 2: Generate the golden file once and commit it**

Run a throwaway generation (not a test assertion yet):

```bash
mkdir -p tests/fixtures/golden
python3 -c "import json; from tests.test_golden_stats import run_paxel_stats; \
open('tests/fixtures/golden/stats.json','w').write(json.dumps(run_paxel_stats(), indent=2, sort_keys=True, default=str))"
```

Expected: `tests/fixtures/golden/stats.json` exists and is non-empty.

- [ ] **Step 3: Write the golden assertion test**

```python
class TestGoldenStats(unittest.TestCase):
    def test_stats_match_golden(self):
        with open(GOLDEN) as f:
            golden = json.load(f)
        actual = run_paxel_stats()
        self.assertEqual(
            json.dumps(actual, sort_keys=True, default=str),
            json.dumps(golden, sort_keys=True, default=str),
        )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 4: Run it to confirm it passes against current code**

Run: `python3 -m pytest tests/test_golden_stats.py -v`
Expected: PASS (golden was just generated from this same code).

- [ ] **Step 5: Commit**

```bash
git add tests/test_golden_stats.py tests/fixtures/golden/stats.json
git commit -m "test: freeze golden stats.json before accumulator refactor"
```

---

### Task 1: Declare the Stats dataclasses

Give the cross-stage dict a typed contract. `asdict()` must reproduce today's JSON exactly.

**Files:**
- Modify: `paxel.py` (add dataclass block near the top, after imports; modify `main()` assembly at `paxel.py:2019–2174`)
- Test: `tests/test_stats_shape.py` (create)

- [ ] **Step 1: Add nested dataclasses describing the stats shape**

Place after the existing imports. Field names and nesting mirror the dict built at `paxel.py:2019–2174` exactly (verify each key against that block). Use `field(default_factory=...)` for mutable defaults.

```python
from dataclasses import dataclass, field, asdict

@dataclass
class Corpus:
    sources: dict = field(default_factory=dict)
    files_parsed: int = 0
    lines_total: int = 0
    lines_unparseable: int = 0
    date_range: list = field(default_factory=list)
    window: dict = None
    span_days: int = 0
    active_days: int = 0
    timezone: str = ""
    antigravity_experimental: dict = None

@dataclass
class Volume:
    total_sessions: int = 0
    total_prompts: int = 0
    command_invocations: int = 0
    avg_prompt_length_chars: float = 0.0
    median_prompt_length_chars: float = 0.0
    assistant_turns: int = 0
    tool_calls_total: int = 0
    thinking_blocks: int = 0

# ... Tools, Velocity, Behavior, Rhythm, Progression, Stack, Autonomy, TokenUsage ...
# One dataclass per top-level block in paxel.py:2019–2174. Copy every key verbatim.

@dataclass
class Stats:
    scope: str = ""
    generated_local_only: bool = True
    corpus: Corpus = field(default_factory=Corpus)
    volume: Volume = field(default_factory=Volume)
    tools: "Tools" = field(default_factory=lambda: Tools())
    velocity: "Velocity" = field(default_factory=lambda: Velocity())
    behavior: "Behavior" = field(default_factory=lambda: Behavior())
    rhythm: "Rhythm" = field(default_factory=lambda: Rhythm())
    progression: "Progression" = field(default_factory=lambda: Progression())
    stack: "Stack" = field(default_factory=lambda: Stack())
    autonomy: "Autonomy" = field(default_factory=lambda: Autonomy())
    token_usage: "TokenUsage" = field(default_factory=lambda: TokenUsage())
    agentic: dict = field(default_factory=dict)  # filled by compute_aq in the score stage
```

The complete field list per block is the dict literal at `paxel.py:2019–2174` — transcribe it; do not invent fields. `agentic` stays a plain `dict` (it is produced by `compute_aq`, not event-derived).

- [ ] **Step 2: Write a test that asdict(Stats) round-trips through json identically to a dict literal**

```python
# tests/test_stats_shape.py
import os, sys, json, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import paxel
from dataclasses import asdict

class TestStatsShape(unittest.TestCase):
    def test_empty_stats_has_all_blocks(self):
        s = asdict(paxel.Stats())
        for key in ("corpus","volume","tools","velocity","behavior","rhythm",
                    "progression","stack","autonomy","token_usage","agentic"):
            self.assertIn(key, s)

    def test_asdict_is_json_serializable(self):
        json.dumps(asdict(paxel.Stats()), default=str)  # must not raise
```

- [ ] **Step 3: Run it to verify it fails (dataclasses not yet present), then passes after Step 1**

Run: `python3 -m pytest tests/test_stats_shape.py -v`
Expected: PASS once Step 1 dataclasses exist.

- [ ] **Step 4: Have main() assemble a Stats instance instead of a bare dict, then asdict() at write time**

In `main()` replace the `stats = {...}` dict assembly (`paxel.py:2019–2174`) with a `Stats(...)` construction using the same values. At each write site (`paxel.py:2176` `json.dump(stats, ...)`), wrap with `asdict`:

```python
stats = Stats(scope=..., corpus=Corpus(...), volume=Volume(...), ...)
stats.agentic = compute_aq(stats_dict_view(stats))   # see note
...
with open(os.path.join(OUT_DIR, "stats.json"), "w") as f:
    json.dump(asdict(stats), f, indent=2, default=str)
```

Note: downstream readers (`compute_scores`, `write_report`, etc.) currently index `stats["volume"]["x"]`. To keep this task small and the golden green, pass them `asdict(stats)` for now (a dict view). Converting readers to attribute access is out of scope for this task.

- [ ] **Step 5: Run the golden test — output must be byte-identical**

Run: `python3 -m pytest tests/test_golden_stats.py tests/test_stats_shape.py -v`
Expected: PASS. If the golden diff fails, a dataclass field name/order/default diverges from the original dict — fix the field, not the golden.

- [ ] **Step 6: Run the full suite**

Run: `python3 -m pytest -q`
Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add paxel.py tests/test_stats_shape.py
git commit -m "refactor: declare Stats dataclass contract for cross-stage shape"
```

---

### Task 2: Extract EventAccumulator (consume_file + finalize)

Lift the 40 accumulators and the event loop out of `main()` into one deep module.

**Files:**
- Modify: `paxel.py` (new `EventAccumulator` class; gut the loop body from `main()`, `paxel.py:1498–2016`)
- Test: `tests/test_event_accumulator.py` (create)

- [ ] **Step 1: Create the EventAccumulator class skeleton with the target interface**

```python
class EventAccumulator:
    def __init__(self, window=(None, None)):
        self._since, self._until = window
        # MOVE every accumulator declared at paxel.py:1499–1583 here as self._<name>.
        # (prompts_count, tool_counter, model_tokens, hour_hist, file_edit_run, ...)

    def consume_file(self, source, events):
        """Fold one transcript file's events. Owns per-file reset state and the
        codex empty-seed skip (paxel.py:1599-1618). Drops out-of-window events."""
        events = list(events)
        # MOVE the codex empty-seed skip (paxel.py:1610-1618) here.
        # MOVE the per-file reset (pending_error, file_edit_run; paxel.py:1599-1600) here.
        for ev in events:
            # MOVE the per-event body (paxel.py:1619-1893) here verbatim,
            # replacing local var writes with self._<name>.
            ...

    def cwds(self):
        """Project cwds seen — input to git_churn (kept out of the accumulator)."""
        return list(self._project_activity.keys())

    def window(self):
        """(since_iso, until_iso) for git_churn, derived from observed event dates."""
        ...

    def finalize(self, churn):
        """Pure derivation. MOVE paxel.py:1895-2016 + the Stats assembly
        (paxel.py:2019-2174) here. `churn` is the injected git_churn result."""
        ...
        return Stats(...)

    def voice_samples(self):
        """Verbatim go-to / cryptic / crash-out — LOCAL ONLY, never on stats.json.
        MOVE the goto/cryptic/crashout selection from paxel.py:2185-2206 here."""
        ...
```

This is a mechanical lift: each former local variable becomes `self._<name>`; the loop body and derivation move verbatim. The golden test is the proof of equivalence.

- [ ] **Step 2: Run the golden test — it should still pass because main() is unchanged yet**

Run: `python3 -m pytest tests/test_golden_stats.py -v`
Expected: PASS (class added, not yet wired in).

- [ ] **Step 3: Write a synthetic-event unit test (the payoff — no git, no fixtures)**

```python
# tests/test_event_accumulator.py
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import paxel

def _user(text, sid="s1", ts="2026-06-01T10:00:00Z"):
    return {"type": "user", "sessionId": sid, "timestamp": ts,
            "message": {"content": text}}

def _tool(name, sid="s1", ts="2026-06-01T10:01:00Z"):
    return {"type": "assistant", "sessionId": sid, "timestamp": ts,
            "message": {"content": [{"type": "tool_use", "name": name, "input": {}}]}}

class TestEventAccumulator(unittest.TestCase):
    def test_counts_prompts_and_tools_without_git_or_fixtures(self):
        acc = paxel.EventAccumulator()
        acc.consume_file("claude", [_user("fix the bug"), _tool("Read"), _tool("Edit")])
        stats = acc.finalize(churn=None)  # no git needed
        self.assertEqual(stats.volume.total_prompts, 1)
        self.assertEqual(stats.volume.tool_calls_total, 2)

    def test_window_drops_out_of_range_events(self):
        acc = paxel.EventAccumulator(window=(paxel.parse_ts("2026-06-01T00:00:00Z"), None))
        acc.consume_file("claude", [_user("old", ts="2026-01-01T00:00:00Z"),
                                    _user("new", ts="2026-06-02T00:00:00Z")])
        stats = acc.finalize(churn=None)
        self.assertEqual(stats.volume.total_prompts, 1)
```

Adjust event dict shapes to match what `iter_events` actually yields (inspect `paxel.py:656-686`). `finalize(churn=None)` must tolerate absent churn (treat as zero velocity).

- [ ] **Step 4: Run the unit test to verify it fails (finalize not implemented)**

Run: `python3 -m pytest tests/test_event_accumulator.py -v`
Expected: FAIL (skeleton `...` bodies) — drives the verbatim move in Step 5.

- [ ] **Step 5: Complete the verbatim move into consume_file/finalize**

Cut `paxel.py:1499–1583` (accumulators) → `__init__` fields. Cut `paxel.py:1599–1893` (per-file reset + event loop) → `consume_file`. Cut `paxel.py:1895–2174` (derivation + Stats assembly) → `finalize`. Replace every bare local name with `self._<name>`. `git_churn` reads `churn` arg instead of calling git.

- [ ] **Step 6: Run both the golden and the unit test**

Run: `python3 -m pytest tests/test_event_accumulator.py -v`
Expected: PASS. (main() still has the old loop at this point — that's fine; the class is independently exercised.)

- [ ] **Step 7: Commit**

```bash
git add paxel.py tests/test_event_accumulator.py
git commit -m "refactor: lift accumulation into EventAccumulator (consume_file/finalize)"
```

---

### Task 3: Rewire main() as a thin feed

Replace the in-`main()` loop with the accumulator. Voice samples via the new accessor.

**Files:**
- Modify: `paxel.py` (`main()` body, `paxel.py:1498–2206`)

- [ ] **Step 1: Replace the loop and derivation in main() with the accumulator calls**

```python
acc = EventAccumulator(window=(since_dt, until_dt))
for cur_src, fp, fmt in sources:
    if since_dt is not None and _mtime_before(fp, since_dt):   # I/O skip stays in feed
        continue
    acc.consume_file(cur_src, iter_events(fp, fmt, cursor_twins=cursor_twins))
churn = git_churn(acc.cwds(), *acc.window())
stats = acc.finalize(churn)
stats.agentic = compute_aq(asdict(stats))
voice = acc.voice_samples()
```

`_mtime_before` is the extracted form of the mtime check at `paxel.py:1588–1593`. Delete the now-dead accumulator declarations and loop that Task 2 copied out.

- [ ] **Step 2: Pass voice samples to the renderers explicitly**

`write_narrative_input` and `write_profile_html` currently take `opening_prompts`/`longest_prompts`/`voice` from `main()` locals. Route them from `voice` / `acc` accessors instead. Keep signatures otherwise unchanged.

- [ ] **Step 3: Run the golden test — output must still be byte-identical**

Run: `python3 -m pytest tests/test_golden_stats.py -v`
Expected: PASS. This is the real proof the feed rewrite preserved behavior.

- [ ] **Step 4: Run the full suite**

Run: `python3 -m pytest -q`
Expected: all green.

- [ ] **Step 5: Manual smoke — generate a real profile and eyeball it**

Run: `python3 paxel.py --no-open` (in a dir with real transcripts, or with `--claude-dir=`)
Expected: writes stats.json/report.md/narrative_input.md/profile.html; voice cards present on the local HTML.

- [ ] **Step 6: Commit**

```bash
git add paxel.py
git commit -m "refactor: main() becomes a thin feed over EventAccumulator"
```

---

## Self-Review notes

- **Spec coverage:** Task 1 = candidate 2 (Stats contract). Tasks 2–3 = candidate 1 (EventAccumulator). Task 0 = the golden safety net both depend on.
- **ADR-0001:** every change stays in `paxel.py`. No new importable modules. ✔
- **Forks honored:** A2 (`consume_file`), window owned by accumulator, C1 (`git_churn` injected into `finalize`), D1 (`voice_samples()` separate, off `stats.json`).
- **Type consistency:** `consume_file(source, events)`, `finalize(churn) -> Stats`, `cwds()`, `window()`, `voice_samples()` used identically across Tasks 2 and 3.
- **Open verification: CLOSED.** Golden run reuses `test_smoke.py`'s `mock.patch.multiple(paxel, OUT_DIR=out, **SRC_DIRS)` harness (verified `paxel.py:61` defines `OUT_DIR`, `test_smoke.py:24-61` defines `SRC_DIRS` + the run helper).
