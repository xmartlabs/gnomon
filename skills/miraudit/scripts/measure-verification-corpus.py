"""Measure, over the REAL corpus, whether delegating sinks the Verification axis.

    python3 measure-verification-corpus.py [path-to-checkout]

Per session: tool calls and test runs, separating those in top-level transcripts
from those in agents dispatched by Workflow. Read-only.
Uses the package's own `bash_runs_tests`, so any checkout works.
"""
import collections
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parse, header  # noqa: E402

args, WINDOW = parse(__doc__.strip().splitlines()[0])
REPO, ROOT = args.checkout, args.corpus
from gnomon.taxonomy import bash_runs_tests  # noqa: E402

WF_RX = re.compile(r'(?:^|/)([^/]+)/subagents/workflows/wf_[^/]+/agent-([^/]+)\.jsonl$')
SUB_RX = re.compile(r'(?:^|/)([^/]+)/subagents/agent-([^/]+)\.jsonl$')

# sid -> counters
top_calls = collections.Counter()
wf_calls = collections.Counter()
sub_calls = collections.Counter()
top_tests = collections.Counter()
wf_tests = collections.Counter()
sub_tests = collections.Counter()
edits = collections.Counter()
wf_dispatches = collections.Counter()

CODE_RX = re.compile(r'\.(ts|tsx|js|jsx|prisma|py|go|rb|java)$', re.I)

for p in glob.glob(os.path.join(ROOT, "**", "*.jsonl"), recursive=True):
    mwf, msub = WF_RX.search(p), SUB_RX.search(p)
    kind = "wf" if mwf else ("sub" if msub else "top")
    if mwf:
        wf_dispatches[mwf.group(1)] += 1
    try:
        f = open(p)
    except OSError:
        continue
    with f:
        for line in f:
            if '"tool_use"' not in line:
                continue
            try:
                e = json.loads(line)
            except ValueError:
                continue
            sid = e.get("sessionId")
            if not sid:
                continue
            c = (e.get("message") or {}).get("content")
            if not isinstance(c, list):
                continue
            for b in c:
                if not isinstance(b, dict) or b.get("type") != "tool_use":
                    continue
                name = b.get("name", "")
                inp = b.get("input") or {}
                (top_calls if kind == "top" else
                 wf_calls if kind == "wf" else sub_calls)[sid] += 1
                if name == "Bash" and bash_runs_tests(str(inp.get("command", ""))):
                    (top_tests if kind == "top" else
                     wf_tests if kind == "wf" else sub_tests)[sid] += 1
                if name in ("Edit", "Write", "MultiEdit") and CODE_RX.search(
                        str(inp.get("file_path", ""))):
                    edits[sid] += 1

TARGET = 0.025
sessions = set(top_calls) | set(wf_calls) | set(sub_calls)
coding = [s for s in sessions if edits[s] > 0]

deleg = [s for s in coding if wf_dispatches[s] > 0]
inline = [s for s in coding if wf_dispatches[s] == 0]


def block(label, sids):
    tc = sum(top_calls[s] + wf_calls[s] + sub_calls[s] for s in sids)
    tr = sum(top_tests[s] + wf_tests[s] + sub_tests[s] for s in sids)
    tested = sum(1 for s in sids if top_tests[s] + wf_tests[s] + sub_tests[s] > 0)
    ed = sum(edits[s] for s in sids)
    rate = min(1.0, (tr / tc) / TARGET) if tc else 0.0
    print(f"{label:<34}{len(sids):>8}{tested:>9}{100*tested//max(1,len(sids)):>7}%"
          f"{ed:>9}{tr:>8}{tc:>10}{rate:>9.3f}")


print(f"repo: {REPO}\n")
print("Sessions that EDITED code, split by whether they used Workflow.\n")
print(f"{'group':<34}{'sessions':>8}{'w/tests':>9}{'cover':>8}"
      f"{'edits':>9}{'tests':>8}{'toolcalls':>10}{'rate':>9}")
print("-" * 95)
block("delegated to Workflow", deleg)
block("inline work", inline)
block("ALL", coding)

print("\nWhere each part of the ratio comes from (whole corpus):")
tot_tc = sum(top_calls.values()) + sum(wf_calls.values()) + sum(sub_calls.values())
tot_tr = sum(top_tests.values()) + sum(wf_tests.values()) + sum(sub_tests.values())
for label, calls, tests in [("top-level", top_calls, top_tests),
                            ("Workflow agents", wf_calls, wf_tests),
                            ("Agent sidechains", sub_calls, sub_tests)]:
    c, t = sum(calls.values()), sum(tests.values())
    print(f"  {label:<22} denominator {c:>7} ({100*c/tot_tc:>4.1f}%)   "
          f"numerator {t:>4} ({100*t/max(1,tot_tr):>4.1f}%)")

print("\nCounterfactual: what if the delegators tested EXACTLY like the ones "
      "that did not?")
in_tc = sum(top_calls[s] + wf_calls[s] + sub_calls[s] for s in inline)
in_tr = sum(top_tests[s] + wf_tests[s] + sub_tests[s] for s in inline)
in_ed = sum(edits[s] for s in inline)
de_tc = sum(top_calls[s] + wf_calls[s] + sub_calls[s] for s in deleg)
de_ed = sum(edits[s] for s in deleg)
per_edit = in_tr / in_ed
cf_tests = per_edit * de_ed
cf_rate = min(1.0, (cf_tests / de_tc) / TARGET)
in_rate = min(1.0, (in_tr / in_tc) / TARGET)
print(f"  inline discipline: {per_edit:.3f} test runs per code edit")
print(f"  applied to the {de_ed} edits of the delegators -> {cf_tests:.0f} tests")
print(f"  counterfactual rate = ({cf_tests:.0f} / {de_tc}) / {TARGET} = {cf_rate:.3f}")
print(f"  real inline rate                                     = {in_rate:.3f}")
print(f"  SAME testing discipline, {in_rate/max(cf_rate,1e-9):.1f}x worse for delegating.")

print("\nTop 8 sessions by Workflow dispatches:")
print(f"  {'session':<12}{'dispatches':>10}{'edits':>7}{'tests':>7}"
      f"{'toolcalls':>11}{'rate':>8}")
for s, n in wf_dispatches.most_common(8):
    tc = top_calls[s] + wf_calls[s] + sub_calls[s]
    tr = top_tests[s] + wf_tests[s] + sub_tests[s]
    r = min(1.0, (tr / tc) / TARGET) if tc else 0.0
    print(f"  {s[:8]:<12}{n:>10}{edits[s]:>7}{tr:>7}{tc:>11}{r:>8.3f}")
