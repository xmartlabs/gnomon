# paxel-XL (gnomon) — AQ + Codex fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a native Agentic Quotient (AQ) metric and fix the Codex transcript parser in the local `paxel.py` fork (gnomon).

**Architecture:** Edit the single-file `paxel.py` in place. Add two pure helpers (`_extract_clis`, `_codex_is_injected`), wire new aggregate fields into the existing tool-counting loop, add a `compute_aq(stats)` function mirroring `compute_scores`, attach `stats["agentic"]` before the JSON dump, and render an AQ section into `report.md` and `profile.html`. Codex fix drops injected `<environment_context>`/`<user_instructions>` user messages so they stop counting as human prompts.

**Tech Stack:** Python 3 stdlib only (`re`, `collections.Counter`, `json`, `unittest`). No new dependencies. Tests via stdlib `unittest`.

**Paths (all absolute under repo root `/Users/xmartlabs/Desktop/development/personal/claude-workshop/gnomon`):**
- Modify: `paxel.py`
- Create: `tests/test_gnomon.py`

---

## File Structure

- `paxel.py` — single-file tool (existing pattern; do NOT split). New code lives next to its siblings:
  - module constants near top (`KNOWN_CLIS`, after `ASK_TOOLS` at line 64)
  - `_extract_clis`, `_codex_is_injected` as module-level helpers (near other `_`-helpers)
  - `compute_aq(stats)` right after `compute_scores` (~line 1610)
  - aggregation wiring inside the assistant tool-use loop (~960–1026) and the Codex parser (~428)
  - `stats["agentic"]` assignment before `json.dump` (~1226)
  - render blocks in `write_report` (~1371) and `write_profile_html` (~2094)
- `tests/test_gnomon.py` — stdlib `unittest` covering the three pure units (`_extract_clis`, `_codex_is_injected`, `compute_aq`). Importing `paxel` is safe: it is guarded by `if __name__ == "__main__"`.

---

### Task 1: CLI extraction helper

**Files:**
- Modify: `paxel.py` (add constant after line 64; add helper near other helpers, e.g. after `bash_runs_tests`)
- Test: `tests/test_gnomon.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_gnomon.py`:

```python
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import paxel


class TestExtractClis(unittest.TestCase):
    def test_single_known_cli(self):
        self.assertEqual(paxel._extract_clis("git status"), ["git"])

    def test_chained_commands(self):
        self.assertEqual(paxel._extract_clis("cd /x && pnpm install | grep foo"),
                         ["pnpm", "grep"])

    def test_skips_env_assignment(self):
        self.assertEqual(paxel._extract_clis("FOO=bar python3 run.py"), ["python3"])

    def test_path_prefixed_binary(self):
        self.assertEqual(paxel._extract_clis("/usr/bin/node app.js"), ["node"])

    def test_unknown_command_ignored(self):
        self.assertEqual(paxel._extract_clis("frobnicate --x"), [])

    def test_empty(self):
        self.assertEqual(paxel._extract_clis(""), [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/xmartlabs/Desktop/development/personal/claude-workshop/gnomon && python3 -m unittest tests.test_gnomon.TestExtractClis -v`
Expected: FAIL — `AttributeError: module 'paxel' has no attribute '_extract_clis'`

- [ ] **Step 3: Add the constant and helper**

After line 64 (`ASK_TOOLS = {"AskUserQuestion"}`) add:

```python
KNOWN_CLIS = {
    "git", "gh", "npm", "npx", "yarn", "pnpm", "bun", "python", "python3", "pip",
    "pip3", "node", "deno", "cargo", "go", "rg", "grep", "sed", "awk", "find",
    "curl", "wget", "jq", "docker", "kubectl", "make", "xcodebuild", "pod", "expo",
    "eas", "supabase", "vercel", "psql", "sqlite3", "open", "cp", "mv", "rm",
    "mkdir", "ls", "cat", "chmod", "ssh", "brew", "tsc", "eslint", "prettier",
    "vitest", "jest", "pytest", "ruby", "swift", "ffmpeg",
}
_CLI_SPLIT = re.compile(r"&&|\|\||\||;|\bthen\b|\bdo\b")
```

After the `bash_runs_tests` function definition add:

```python
def _extract_clis(command):
    """Return the known-CLI heads invoked in a shell command (one per &&/|/;-separated part)."""
    found = []
    for part in _CLI_SPLIT.split(command or ""):
        toks = part.strip().split()
        i = 0
        while i < len(toks) and ("=" in toks[i] and not toks[i].startswith("-")):
            i += 1  # skip leading VAR=val env assignments
        if i < len(toks):
            head = toks[i].split("/")[-1]
            if head in KNOWN_CLIS:
                found.append(head)
    return found
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/xmartlabs/Desktop/development/personal/claude-workshop/gnomon && python3 -m unittest tests.test_gnomon.TestExtractClis -v`
Expected: PASS (6 tests OK)

- [ ] **Step 5: Commit**

```bash
cd /Users/xmartlabs/Desktop/development/personal/claude-workshop/gnomon
git add paxel.py tests/test_gnomon.py
git commit -m "feat: add _extract_clis helper + KNOWN_CLIS"
```

---

### Task 2: Codex injected-message filter

**Files:**
- Modify: `paxel.py` (add `_codex_is_injected` near `_codex_events`; wire into `_codex_events` ~428)
- Test: `tests/test_gnomon.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_gnomon.py` (before the `if __name__` block):

```python
class TestCodexInjected(unittest.TestCase):
    def test_environment_context(self):
        self.assertTrue(paxel._codex_is_injected(
            "<environment_context>\n  <cwd>/x</cwd>\n  <shell>zsh</shell>\n</environment_context>"))

    def test_user_instructions(self):
        self.assertTrue(paxel._codex_is_injected("  <user_instructions>be concise</user_instructions>"))

    def test_real_prompt_kept(self):
        self.assertFalse(paxel._codex_is_injected("fix the auth bug in middleware"))

    def test_empty(self):
        self.assertFalse(paxel._codex_is_injected(""))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/xmartlabs/Desktop/development/personal/claude-workshop/gnomon && python3 -m unittest tests.test_gnomon.TestCodexInjected -v`
Expected: FAIL — `AttributeError: module 'paxel' has no attribute '_codex_is_injected'`

- [ ] **Step 3: Add the helper**

Immediately before `def _codex_events(fp):` (line 391) add:

```python
def _codex_is_injected(text):
    """True for Codex tooling wrappers (environment context / user instructions) that are
    sent as `user` messages but are NOT human prompts."""
    if not text:
        return False
    s = text.lstrip()
    return s.startswith("<environment_context") or s.startswith("<user_instructions")
```

- [ ] **Step 4: Wire it into `_codex_events`**

In `_codex_events`, change the user-message branch (currently lines 428–430):

```python
            if role == "user" and text:
                yield {**base, "type": "user", "timestamp": ts,
                       "message": {"role": "user", "content": text}}
```

to:

```python
            if role == "user" and text and not _codex_is_injected(text):
                yield {**base, "type": "user", "timestamp": ts,
                       "message": {"role": "user", "content": text}}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd /Users/xmartlabs/Desktop/development/personal/claude-workshop/gnomon && python3 -m unittest tests.test_gnomon.TestCodexInjected -v`
Expected: PASS (4 tests OK)

- [ ] **Step 6: Commit**

```bash
cd /Users/xmartlabs/Desktop/development/personal/claude-workshop/gnomon
git add paxel.py tests/test_gnomon.py
git commit -m "fix: drop injected Codex env/user_instructions messages from prompt counts"
```

---

### Task 3: Collect agentic aggregates into stats

**Files:**
- Modify: `paxel.py` (counters init ~776–784; tool-use loop ~966 and ~1018; stats dict ~1150 and ~1209)

No new unit test — verified by the integration run in Task 8 and consumed by Task 4.

- [ ] **Step 1: Add counters**

After line 784 (`subagent_counter = Counter()`) add:

```python
    mcp_server_counter = Counter()   # mcp server name -> calls
    cli_counter = Counter()          # known CLI head -> calls (from Bash commands)
```

- [ ] **Step 2: Capture MCP server on every mcp__ tool**

Change lines 966–967:

```python
                                if name.startswith("mcp__"):
                                    mcp_calls += 1
```

to:

```python
                                if name.startswith("mcp__"):
                                    mcp_calls += 1
                                    parts = name.split("__")
                                    if len(parts) > 1 and parts[1]:
                                        mcp_server_counter[parts[1]] += 1
```

- [ ] **Step 3: Capture CLIs in the Bash branch**

In the `elif name == "Bash":` block, right after line 1019 (`cmd = inp.get("command", "") or ""`) add:

```python
                                    for _cli in _extract_clis(cmd):
                                        cli_counter[_cli] += 1
```

- [ ] **Step 4: Add fields to `stats["tools"]`**

Inside the `"tools": { ... }` dict, after the `"category_breakdown"` line (1157) add:

```python
            "mcp_servers": mcp_server_counter.most_common(),
            "mcp_servers_distinct": len(mcp_server_counter),
            "clis": cli_counter.most_common(),
            "clis_distinct": len(cli_counter),
            "cli_calls": sum(cli_counter.values()),
            "toolsearch_calls": tool_counter.get("ToolSearch", 0),
            "task_tool_calls": tool_counter.get("TaskCreate", 0) + tool_counter.get("TaskUpdate", 0),
            "agent_calls": tool_counter.get("Agent", 0),
```

- [ ] **Step 5: Add fields to `stats["stack"]`**

Inside the `"stack": { ... }` dict, after the `"top_skills"` line (1211) add:

```python
            "skills_distinct": len(skill_counter),
            "skills_total": sum(skill_counter.values()),
            "subagent_types_distinct": len(subagent_counter),
```

- [ ] **Step 6: Smoke-check it parses and runs**

Run: `cd /Users/xmartlabs/Desktop/development/personal/claude-workshop/gnomon && python3 paxel.py claude --no-open 2>&1 | tail -3`
Expected: runs to completion, prints the "Wrote stats.json…" summary line, no traceback.

- [ ] **Step 7: Confirm new fields exist**

Run: `cd /Users/xmartlabs/Desktop/development/personal/claude-workshop/gnomon && python3 -c "import json;d=json.load(open('stats.json'));print(d['tools']['clis_distinct'], d['tools']['mcp_servers_distinct'], d['tools']['toolsearch_calls'], d['stack']['skills_distinct'])"`
Expected: prints four integers, e.g. `41 12 308 39`

- [ ] **Step 8: Commit**

```bash
cd /Users/xmartlabs/Desktop/development/personal/claude-workshop/gnomon
git add paxel.py
git commit -m "feat: collect MCP-server/CLI/skill aggregates into stats"
```

---

### Task 4: compute_aq function

**Files:**
- Modify: `paxel.py` (add `compute_aq` after `compute_scores`, ~line 1610)
- Test: `tests/test_gnomon.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_gnomon.py` (before the `if __name__` block):

```python
def _sample_stats():
    return {
        "tools": {
            "tool_diversity": 111, "tool_entropy_normalized": 0.435,
            "mcp_calls": 1984, "mcp_servers_distinct": 12,
            "clis_distinct": 41, "cli_calls": 9194,
            "toolsearch_calls": 308, "task_tool_calls": 1166, "agent_calls": 416,
        },
        "stack": {
            "skills_distinct": 39, "skills_total": 8000,
            "subagent_types_distinct": 9,
            "subagent_types": [("general-purpose", 250), ("harness-generator", 29)],
            "top_skills": [("simplify", 1832), ("superpowers:writing-plans", 1752),
                           ("cerberus", 774)],
        },
        "behavior": {"background_tasks": 187, "scheduled_actions": 11},
    }


class TestComputeAq(unittest.TestCase):
    def setUp(self):
        self.aq = paxel.compute_aq(_sample_stats())

    def test_score_and_tier(self):
        self.assertEqual(self.aq["aq_0_100"], 95)
        self.assertEqual(self.aq["tier"], "Systems Builder")

    def test_four_axes(self):
        names = [a["name"] for a in self.aq["axes"]]
        self.assertEqual(names, ["Multi-agent orchestration", "Skill fluency",
                                 "Tool command (MCP + CLI)", "Orchestration discipline"])

    def test_mcp_vs_cli(self):
        self.assertEqual(self.aq["mcp_vs_cli"]["ratio"], 4.6)
        self.assertEqual(self.aq["mcp_vs_cli"]["cli_distinct"], 41)

    def test_tool_diversity_passthrough(self):
        self.assertEqual(self.aq["tool_diversity"]["distinct"], 111)

    def test_tier_floor(self):
        empty = {"tools": {}, "stack": {}, "behavior": {}}
        self.assertLess(paxel.compute_aq(empty)["aq_0_100"], 60)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/xmartlabs/Desktop/development/personal/claude-workshop/gnomon && python3 -m unittest tests.test_gnomon.TestComputeAq -v`
Expected: FAIL — `AttributeError: module 'paxel' has no attribute 'compute_aq'`

- [ ] **Step 3: Implement compute_aq**

After the end of `compute_scores` (before `def pick_archetype`, ~line 1612) add:

```python
def compute_aq(stats):
    """Agentic Quotient (0-100): how well the builder wields the agentic stack.
    Four graded axes (weights 33/22/28/17). MCP-vs-CLI and tool diversity are
    DESCRIPTIVE (not graded), mirroring how Steering is described, not scored."""
    t, st, b = stats.get("tools", {}), stats.get("stack", {}), stats.get("behavior", {})

    def sat(x, target):
        return min(1.0, x / target) if target else 0.0

    def has_skill(needles):
        return any(any(nd in str(k).lower() for nd in needles)
                   for k, _ in st.get("top_skills", []))

    def has_harness():
        rx = re.compile(r"harness|trisel", re.I)
        return any(rx.search(str(k)) for k, _ in st.get("subagent_types", [])) or has_skill(["trisel"])

    agent_runs = t.get("agent_calls", 0)
    bg, sched = b.get("background_tasks", 0), b.get("scheduled_actions", 0)

    vol = sat(agent_runs, 400)
    div = sat(st.get("subagent_types_distinct", 0), 8)
    harness = 1.0 if has_harness() else 0.6
    asy = sat(bg + sched, 200)
    ax1 = .30 * vol + .25 * div + .20 * harness + .25 * asy

    sk_distinct = sat(st.get("skills_distinct", 0), 40)
    sk_volume = sat(st.get("skills_total", 0), 1500)
    sk_meta = 1.0 if has_skill(["subagent-driven", "brainstorm", "writing-plans",
                                "cerberus", "systematic-debugging"]) else 0.6
    ax2 = .40 * sk_distinct + .30 * sk_volume + .30 * sk_meta

    mcp = sat(t.get("mcp_servers_distinct", 0), 15)
    cli = sat(t.get("clis_distinct", 0), 40)
    tss = sat(t.get("toolsearch_calls", 0), 300)
    ax3 = .40 * mcp + .40 * cli + .20 * tss

    tasks = sat(t.get("task_tool_calls", 0), 1500)
    plan = 1.0 if has_skill(["writing-plans", "autoplan", "plan"]) else 0.6
    ax4 = .60 * tasks + .40 * plan

    axes = [
        ("Multi-agent orchestration", 33, ax1,
         {"agent_runs": agent_runs, "subagent_types": st.get("subagent_types_distinct", 0),
          "background": bg, "scheduled": sched}),
        ("Skill fluency", 22, ax2,
         {"skills_distinct": st.get("skills_distinct", 0), "skills_total": st.get("skills_total", 0)}),
        ("Tool command (MCP + CLI)", 28, ax3,
         {"mcp_servers": t.get("mcp_servers_distinct", 0), "clis": t.get("clis_distinct", 0),
          "toolsearch": t.get("toolsearch_calls", 0)}),
        ("Orchestration discipline", 17, ax4,
         {"task_tool_calls": t.get("task_tool_calls", 0)}),
    ]
    total = round(sum(w * s for _, w, s, _ in axes))
    tier = ("Systems Builder" if total >= 80 else "Orchestrator" if total >= 60
            else "Power User" if total >= 40 else "Operator")
    cli_calls, mcp_calls = t.get("cli_calls", 0), t.get("mcp_calls", 0)
    return {
        "aq_0_100": total,
        "tier": tier,
        "axes": [{"name": n, "weight": w, "score": round(w * s, 1), "signals": sig}
                 for n, w, s, sig in axes],
        "mcp_vs_cli": {
            "cli_calls": cli_calls, "cli_distinct": t.get("clis_distinct", 0),
            "mcp_calls": mcp_calls, "mcp_distinct": t.get("mcp_servers_distinct", 0),
            "ratio": round(cli_calls / mcp_calls, 1) if mcp_calls else None,
        },
        "tool_diversity": {"distinct": t.get("tool_diversity", 0),
                           "entropy": t.get("tool_entropy_normalized", 0)},
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/xmartlabs/Desktop/development/personal/claude-workshop/gnomon && python3 -m unittest tests.test_gnomon.TestComputeAq -v`
Expected: PASS (5 tests OK). If `aq_0_100` differs from 95, the formula above is the source of truth — update the spec's "expected ≈95" note rather than fudging the formula.

- [ ] **Step 5: Commit**

```bash
cd /Users/xmartlabs/Desktop/development/personal/claude-workshop/gnomon
git add paxel.py tests/test_gnomon.py
git commit -m "feat: add compute_aq (Agentic Quotient) with 4 graded axes"
```

---

### Task 5: Attach stats["agentic"] before JSON dump

**Files:**
- Modify: `paxel.py` (~line 1226, right after the `stats = { ... }` literal closes and before `json.dump`)

- [ ] **Step 1: Insert the assignment**

Between the close of the `stats` dict (line 1225, `    }`) and the `with open(...stats.json...)` block (line 1227) add:

```python
    stats["agentic"] = compute_aq(stats)
```

- [ ] **Step 2: Run and confirm the block lands in stats.json**

Run: `cd /Users/xmartlabs/Desktop/development/personal/claude-workshop/gnomon && python3 paxel.py claude --no-open >/dev/null 2>&1 && python3 -c "import json;a=json.load(open('stats.json'))['agentic'];print(a['aq_0_100'], a['tier'], len(a['axes']), a['mcp_vs_cli']['ratio'])"`
Expected: prints e.g. `95 Systems Builder 4 4.6`

- [ ] **Step 3: Commit**

```bash
cd /Users/xmartlabs/Desktop/development/personal/claude-workshop/gnomon
git add paxel.py
git commit -m "feat: attach agentic block to stats output"
```

---

### Task 6: Render AQ block in report.md

**Files:**
- Modify: `paxel.py` — `write_report` (after the Autonomy block, ~line 1371, before the file write at 1372)

- [ ] **Step 1: Insert the report block**

After line 1371 (`A(f"- Components: {au['components']}")`) and before `with open(os.path.join(OUT_DIR, "report.md"), "w") as f:` add:

```python
    aq = s.get("agentic")
    if aq:
        A("\n## Agentic Quotient (AQ)")
        A(f"- **AQ: {aq['aq_0_100']}/100 — {aq['tier']}** "
          "_(custom metric, not from paxel; multi-agents · skills · MCP+CLI · orchestration)_")
        for ax in aq["axes"]:
            sig = ", ".join(f"{k}={v}" for k, v in ax["signals"].items())
            A(f"  - {ax['name']}: **{ax['score']}/{ax['weight']}** ({sig})")
        mv = aq["mcp_vs_cli"]
        A(f"- MCP vs CLI _(described, not graded)_: **CLI** {mv['cli_calls']:,} calls / "
          f"{mv['cli_distinct']} tools · **MCP** {mv['mcp_calls']:,} calls / {mv['mcp_distinct']} servers "
          f"· ratio {mv['ratio']}:1 CLI-first")
        td = aq["tool_diversity"]
        A(f"- Tool diversity _(described)_: {td['distinct']} distinct tools, entropy {td['entropy']}")
```

Note: `write_report`'s parameter is named `s` and `au = s["autonomy"]` is already bound earlier in the function — confirm by reading the function head; use `s` to read `s.get("agentic")`.

- [ ] **Step 2: Run and confirm the block renders**

Run: `cd /Users/xmartlabs/Desktop/development/personal/claude-workshop/gnomon && python3 paxel.py claude --no-open >/dev/null 2>&1 && grep -A1 "## Agentic Quotient" report.md`
Expected: shows the `## Agentic Quotient (AQ)` heading followed by the AQ/100 line.

- [ ] **Step 3: Commit**

```bash
cd /Users/xmartlabs/Desktop/development/personal/claude-workshop/gnomon
git add paxel.py
git commit -m "feat: render AQ block in report.md"
```

---

### Task 7: Render AQ section in profile.html

**Files:**
- Modify: `paxel.py` — CSS (in the `<style>` block, before its closing `</style>` at line 1866) and the body assembly in `write_profile_html` (after the Steering `steerread` block, line 2094)

- [ ] **Step 1: Add CSS for the AQ section**

Immediately before `</style>` (line 1866) add (reuses existing `--beak`/`--line` vars; light theme to match the profile):

```python
  .aq-head{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap;margin:0 0 6px}
  .aq-big{font-family:var(--serif);font-size:46px;font-weight:800;color:var(--beak-deep);line-height:1}
  .aq-tier{font-size:12px;letter-spacing:.1em;text-transform:uppercase;color:var(--beak-deep);border:1px solid var(--beak);border-radius:999px;padding:4px 11px}
  .aq-axis{display:grid;grid-template-columns:200px 1fr 56px;align-items:center;gap:14px;margin:0 0 12px}
  .aq-axis .nm{font-weight:600;font-size:14px} .aq-axis .vl{font-weight:800;text-align:right}
  .aq-split{margin-top:18px;background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:15px 16px}
  .aq-split .bar{display:flex;height:28px;border-radius:6px;overflow:hidden;font-size:11.5px;font-weight:700;margin:8px 0}
  .aq-split .cli{background:var(--beak-deep);color:#fff;display:flex;align-items:center;padding:0 12px}
  .aq-split .mcp{background:var(--beak);color:#fff;display:flex;align-items:center;justify-content:flex-end;padding:0 12px}
  .aq-split .meta{font-size:12.5px;color:var(--muted);margin:6px 0 0;line-height:1.5} .aq-split .meta b{color:var(--text)}
```

(If `--panel`/`--muted`/`--serif`/`--beak`/`--beak-deep`/`--line`/`--text` are not all defined, read the `:root{}` block near line 1820 and substitute the closest existing var — do not invent new vars.)

- [ ] **Step 2: Build and emit the AQ section**

After line 2094 (the closing of the `steerread` `P(...)` call) add:

```python
    aq = stats.get("agentic")
    if aq:
        P('<h2 class="section">Agentic Quotient</h2>')
        P('<div class="disclaimer"><b>How well you wield the agentic stack</b> — multi-agents, skills, '
          'MCP + CLI, orchestration. A custom metric (not part of paxel). MCP-vs-CLI and tool diversity '
          'below are <b>described, not graded</b> — like Steering.</div>')
        P(f'<div class="aq-head"><span class="aq-big">{aq["aq_0_100"]}</span>'
          f'<span class="aq-tier">{_h.escape(aq["tier"])}</span></div>')
        for ax in aq["axes"]:
            pct = (ax["score"] / ax["weight"] * 100) if ax["weight"] else 0
            P(f'<div class="aq-axis"><span class="nm">{_h.escape(ax["name"])}</span>'
              f'<span class="track"><span class="fill" style="width:{pct:.0f}%"></span></span>'
              f'<span class="vl mono">{ax["score"]:.0f}/{ax["weight"]}</span></div>')
        mv = aq["mcp_vs_cli"]
        cli_calls, mcp_calls = mv["cli_calls"], mv["mcp_calls"]
        tot = (cli_calls + mcp_calls) or 1
        cli_pct = max(8, round(cli_calls / tot * 100))
        P('<div class="aq-split"><b>MCP vs CLI</b> — described, not graded'
          f'<div class="bar"><span class="cli" style="flex:{cli_pct}">CLI · {cli_calls:,} · {mv["cli_distinct"]} tools</span>'
          f'<span class="mcp" style="flex:{100-cli_pct}">MCP · {mcp_calls:,} · {mv["mcp_distinct"]}</span></div>'
          f'<p class="meta">Ratio <b>{mv["ratio"]}:1</b> CLI-first. CLI is token-cheap and scriptable — '
          'you reach for it on repeatable work and reserve MCP for what CLI can\'t do (browser, design canvas, '
          'device control). Right instinct, not a gap.</p>'
          f'<p class="meta"><b>Tool diversity</b> · {aq["tool_diversity"]["distinct"]} distinct tools, '
          f'entropy {aq["tool_diversity"]["entropy"]} — high range available, concentrated use. Not penalized.</p>'
          '</div>')
```

(`_h` is the `html` module already imported at the top of `write_profile_html` as `import html as _h`.)

- [ ] **Step 3: Run and confirm the section renders**

Run: `cd /Users/xmartlabs/Desktop/development/personal/claude-workshop/gnomon && python3 paxel.py claude --no-open >/dev/null 2>&1 && grep -c "Agentic Quotient\|aq-big\|aq-axis" profile.html`
Expected: prints a count ≥ 3 (heading + big number + at least one axis row).

- [ ] **Step 4: Visual check**

Run: `cd /Users/xmartlabs/Desktop/development/personal/claude-workshop/gnomon && open profile.html`
Expected: the profile opens; an "Agentic Quotient" section appears below Steering with the big number, tier chip, 4 bars, and the MCP-vs-CLI split.

- [ ] **Step 5: Commit**

```bash
cd /Users/xmartlabs/Desktop/development/personal/claude-workshop/gnomon
git add paxel.py
git commit -m "feat: render Agentic Quotient section in profile.html"
```

---

### Task 8: Integration verification (no-regression + Codex fix)

**Files:** none modified — verification only.

- [ ] **Step 1: Full unit suite green**

Run: `cd /Users/xmartlabs/Desktop/development/personal/claude-workshop/gnomon && python3 -m unittest discover -s tests -v`
Expected: all tests PASS (Task 1, 2, 4 suites).

- [ ] **Step 2: Claude-only no-regression**

Run: `cd /Users/xmartlabs/Desktop/development/personal/claude-workshop/gnomon && python3 paxel.py claude --no-open 2>&1 | grep -E "scores|sessions="`
Expected: `Execution: 10.0, Planning: 10.0, Engineering: 8.8` (or the same values as the pre-change baseline) and `sessions=221 prompts=1655` unchanged. The AQ addition must not move the three gstack scores or the corpus counts.

- [ ] **Step 3: Codex fix — env_context no longer a top prompt**

Run: `cd /Users/xmartlabs/Desktop/development/personal/claude-workshop/gnomon && python3 paxel.py --no-open 2>&1 | tail -8`
Then: `cd /Users/xmartlabs/Desktop/development/personal/claude-workshop/gnomon && python3 -c "import re;h=open('profile.html').read();import sys;print('environment_context' in (re.search(r'most-repeated prompt.{0,120}', h) or [''])[0] if re.search(r'most-repeated prompt', h) else 'n/a')"`
Expected: the all-sources run completes; the "most-repeated prompt" is NOT `environment_context`. Also eyeball the printed summary: `total_prompts` for codex should drop sharply versus the pre-fix 113,673, and the codex archetype/scores should move toward the claude-only profile.

- [ ] **Step 4: Final commit (if any uncommitted changes remain)**

```bash
cd /Users/xmartlabs/Desktop/development/personal/claude-workshop/gnomon
git add -A
git commit -m "test: integration verification for AQ + Codex fix" || echo "nothing to commit"
```

---

## Self-Review

**Spec coverage:**
- AQ metric (4 axes, own section) → Tasks 4, 5, 6, 7 ✓
- Data collection (mcp_servers, clis, toolsearch, skills_distinct) → Task 3 ✓
- compute_aq with stated formula/weights → Task 4 ✓
- MCP-vs-CLI + tool diversity descriptive → rendered in Tasks 6, 7; computed in Task 4 ✓
- Codex fix (`_codex_is_injected`) → Task 2 ✓
- Render in all 3 outputs (stats.json / report.md / profile.html) → Tasks 5, 6, 7 ✓
- Verification (no-regression, codex fix, field presence) → Tasks 3, 8 ✓

**Placeholder scan:** No TBD/TODO. Every code step shows full code. CSS-var substitution caveat in Task 7 Step 1 is a guarded conditional, not a placeholder.

**Type/name consistency:** `_extract_clis` (Task 1) used in Task 3 Step 3. `_codex_is_injected` (Task 2) used in Task 2 Step 4. `compute_aq` (Task 4) used in Tasks 5, 6, 7. stats fields written in Task 3 (`mcp_servers_distinct`, `clis_distinct`, `cli_calls`, `toolsearch_calls`, `task_tool_calls`, `agent_calls`, `skills_distinct`, `skills_total`, `subagent_types_distinct`) are exactly the keys read by `compute_aq` in Task 4. The `agentic` block keys (`aq_0_100`, `tier`, `axes`, `mcp_vs_cli`, `tool_diversity`) match across Tasks 4/6/7.

**Open risk:** the expected AQ value (95) is computed from the formula; if a real run yields a different number, the formula is the source of truth — reconcile the spec note and the hand-built `claude-workshop/paxel-onepager.*` (which used 90), don't fudge weights.
