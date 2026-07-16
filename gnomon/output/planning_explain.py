"""Per-session Ordered Planning diagnostic (local `--explain-planning`).

Read-only: for the user's OWN logs it lists every eligible ordered-planning
session, whether it was detected PLANNED (and via which signal), and for the
non-planned ones the near-misses + inline planning signals — so a low score
can be told apart from a detector blindspot. Nothing here is uploaded.

The per-session `planned` verdict is derived from the SAME cross-session
consume-once credit (`apply_cross_session_credit`) the scored aggregate uses,
and the summary carries a `reconciles` flag asserting summed eligible/planned
equals `aggregate_ordered` over the same sessions.
"""

import datetime
import os
from collections import Counter

from gnomon.cli.accumulator import (
    session_ordered_detail, aggregate_ordered, apply_cross_session_credit,
)


def _short_sid(sid):
    sid = str(sid or "")
    return sid[:8] if len(sid) > 8 else sid


def _row_date(facts):
    """Session date from the latest fact order (a unix timestamp). Falls back to
    empty when unmeasurable (no datable facts)."""
    orders = [f.get("order") for f in facts
              if isinstance(f.get("order"), (int, float)) and f.get("order") != float("inf")]
    if not orders:
        return ""
    try:
        return datetime.datetime.fromtimestamp(
            max(orders), datetime.timezone.utc).date().isoformat()
    except (OverflowError, OSError, ValueError):
        return ""


def build_planning_explain(session_ordered_tools, session_thinking_blocks,
                           session_first_prompt):
    """Return {"summary": {...}, "rows": [...]} for the local diagnostic.

    `session_ordered_tools` maps (source, sid) -> list of ordered facts (exactly
    the accumulator's structure). `session_thinking_blocks` is a Counter keyed
    the same way; `session_first_prompt` maps the same key -> prompt snippet.
    """
    keys = list(session_ordered_tools.keys())
    details = [session_ordered_detail(session_ordered_tools[k]) for k in keys]
    # Same consume-once credit as the scored aggregate; mutates details in place,
    # order preserved so we can zip back to the session keys.
    apply_cross_session_credit(details)

    rows = []
    for key, detail in zip(keys, details):
        source, sid = key
        facts = session_ordered_tools[key]
        planned_intra = detail["planned_intra"]
        cross_session = bool(detail.get("planned_final") and not planned_intra)
        planned = bool(planned_intra or cross_session)
        rows.append({
            "session": _short_sid(sid),
            "source": source,
            "date": _row_date(facts),
            "cwd": os.path.basename(str(detail.get("cwd") or "").rstrip("/")),
            "eligible": detail["eligible"],
            "reason": detail["reason"],
            "planned": planned,
            "signals": list(detail["signals"]),
            "cross_session": cross_session,
            # near-miss fields
            "todo_steps_max": detail["todo_steps_max"],
            "plan_file_locs": detail["plan_file_locs"],
            "plan_mode_present": detail["plan_mode_present"],
            "plan_skill_present": detail["plan_skill_present"],
            "evidence_reads_before_write": detail["evidence_reads_before_write"],
            "n_code_files": detail["n_code_files"],
            "code_churn": detail["code_churn"],
            "substantive": detail["substantive"],
            "thinking_blocks": int(session_thinking_blocks.get(key, 0)),
            "prompt": session_first_prompt.get(key, ""),
        })

    eligible_rows = [r for r in rows if r["eligible"]]
    planned_rows = [r for r in eligible_rows if r["planned"]]
    n_eligible = len(eligible_rows)
    n_planned = len(planned_rows)

    ineligible_reasons = Counter(r["reason"] for r in rows if not r["eligible"])
    planned_signals = Counter()
    for r in planned_rows:
        for sig in r["signals"]:
            planned_signals[sig] += 1
        if r["cross_session"]:
            planned_signals["cross-session"] += 1

    # Reconciliation: summed eligible/planned MUST equal the scored aggregate.
    agg = aggregate_ordered(session_ordered_tools.values())
    reconciles = (n_eligible == agg["eligible"] and n_planned == agg["planned"])

    summary = {
        "total_sessions": len(rows),
        "eligible": n_eligible,
        "planned": n_planned,
        "coverage": round(n_planned / n_eligible, 4) if n_eligible else 0.0,
        "ineligible_reasons": dict(ineligible_reasons),
        "planned_signals": dict(planned_signals),
        "reconciles": reconciles,
        "aggregate": agg,
    }
    return {"summary": summary, "rows": rows}
