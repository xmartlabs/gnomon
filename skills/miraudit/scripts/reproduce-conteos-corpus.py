#!/usr/bin/env python3
"""Reproduce the gnomon audit figures over a Claude Code corpus.

Usage:
    python3 gnomon-audit-reproduce.py [CORPUS_DIR]

CORPUS_DIR default: ~/.claude/projects
Window: [2026-07-07T03:00Z, 2026-08-06T03:00Z)  == 2026-07-07 -> 2026-08-06 at -03:00

Prints a corpus FINGERPRINT first. If the fingerprint does not match between two
runs, the figures are not comparable and discussing the counts is pointless.
"""
import glob
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone

WIN_START = datetime(2026, 7, 7, 3, 0, tzinfo=timezone.utc)
WIN_END = datetime(2026, 8, 6, 3, 0, tzinfo=timezone.utc)

root = os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else "~/.claude/projects")
if not os.path.isdir(root):
    sys.exit(f"does not exist: {root}")

files = glob.glob(os.path.join(root, "**", "*.jsonl"), recursive=True)

tools = Counter()
wf_by_session = Counter()
agent_by_session = Counter()
lines = 0
tool_calls = 0
sidechain_calls = 0

for fp in files:
    with open(fp, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            lines += 1
            try:
                ev = json.loads(line)
            except Exception:
                continue
            if not isinstance(ev, dict):
                continue
            ts = ev.get("timestamp")
            if not ts:
                continue
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except Exception:
                continue
            if not (WIN_START <= dt < WIN_END):
                continue
            msg = ev.get("message")
            if not isinstance(msg, dict):
                continue
            content = msg.get("content")
            if not isinstance(content, list):
                continue
            sid = ev.get("sessionId")
            for blk in content:
                if not (isinstance(blk, dict) and blk.get("type") == "tool_use"):
                    continue
                name = blk.get("name")
                tools[name] += 1
                tool_calls += 1
                if ev.get("isSidechain"):
                    sidechain_calls += 1
                if name == "Workflow" and sid:
                    wf_by_session[sid] += 1
                elif name == "Agent" and sid:
                    agent_by_session[sid] += 1

wf_runs = glob.glob(os.path.join(root, "*", "*", "subagents", "workflows", "wf_*"))
wf_agents = glob.glob(
    os.path.join(root, "*", "*", "subagents", "workflows", "wf_*", "agent-*.jsonl")
)

print("=" * 62)
print("CORPUS FINGERPRINT  (must match to compare figures)")
print("=" * 62)
print(f"  root                  {root}")
print(f"  .jsonl files          {len(files):,}")
print(f"  total lines           {lines:,}")
print(f"  tool calls in window  {tool_calls:,}")
print(f"  sidechain share       {100 * sidechain_calls / max(tool_calls, 1):.1f}%")
print()
print("=" * 62)
print("AUDIT CLAIMS")
print("=" * 62)
print(f"  Workflow (calls)                  {tools.get('Workflow', 0):,}   [audit: 106]")
print(f"  Workflow (sessions)               {len(wf_by_session):,}   [audit: 33]")
print(f"  Agent (calls)                     {tools.get('Agent', 0):,}   [audit: 478]")
print(f"  StructuredOutput                  {tools.get('StructuredOutput', 0):,}   [audit: 2023]")
print(f"  wf_* runs on disk                 {len(wf_runs):,}   [audit: 100]")
print(f"  agent-*.jsonl under wf_*          {len(wf_agents):,}   [audit: 2273]")

only_wf = set(wf_by_session) - set(agent_by_session)
print(f"  sessions w/ Workflow and 0 Agent  {len(only_wf):,}   [audit: 14]")

print()
print("WITNESS SESSION 740551c5-f601-48b2-a027-d22b821c8926")
witness = "740551c5-f601-48b2-a027-d22b821c8926"
hits = [f for f in files if witness in f]
if not hits:
    print("  NOT FOUND in this corpus -> you are looking at another machine/user.")
else:
    print(f"  found: {len(hits)} file(s)")
    print(f"  Workflow in session:   {wf_by_session.get(witness, 0)}   [audit: 25]")
    print(f"  Agent in session:      {agent_by_session.get(witness, 0)}   [audit: 0]")
    wr = glob.glob(os.path.join(root, "*", witness, "subagents", "workflows", "wf_*"))
    wa = glob.glob(
        os.path.join(root, "*", witness, "subagents", "workflows", "wf_*", "agent-*.jsonl")
    )
    print(f"  own wf_* runs:         {len(wr)}")
    print(f"  agents dispatched:     {len(wa)}")

print()
print("TOP 20 TOOLS IN WINDOW")
for name, n in tools.most_common(20):
    print(f"  {n:>7,}  {name}")
