_SOURCE_USAGE_METRICS = ("sessions", "prompts", "tool_calls", "active_hours")


def _usage_raw_from_block(block):
    vol = (block or {}).get("volume") or {}
    vel = (block or {}).get("velocity") or {}
    return {
        "sessions": vol.get("total_sessions", 0) or 0,
        "prompts": vol.get("total_prompts", 0) or 0,
        "tool_calls": vol.get("tool_calls_total", 0) or 0,
        "active_hours": vel.get("active_hours", 0) or 0,
    }


def _source_usage_share(raw_by_source):
    totals = {m: sum(r.get(m, 0) or 0 for r in raw_by_source.values()) for m in _SOURCE_USAGE_METRICS}
    by_source = {}
    for src, r in raw_by_source.items():
        entry = {m: (r.get(m, 0) or 0) for m in _SOURCE_USAGE_METRICS}
        for m in _SOURCE_USAGE_METRICS:
            entry[f"{m}_pct"] = round(entry[m] / totals[m], 3) if totals[m] else 0
        by_source[src] = entry
    return {"by_source": by_source, "totals": totals, "primary_metric": "prompts"}


def build_source_usage(scoring_inputs_by_source):
    raw = {src: _usage_raw_from_block(b.get("window"))
           for src, b in (scoring_inputs_by_source or {}).items()}
    return _source_usage_share(raw)


def build_source_usage_monthly(scoring_inputs_by_source):
    months = {}
    for src, b in (scoring_inputs_by_source or {}).items():
        for entry in (b.get("monthly") or []):
            mk = entry.get("month")
            if mk:
                months.setdefault(mk, {})[src] = _usage_raw_from_block(entry)
    out = []
    for mk in sorted(months):
        block = _source_usage_share(months[mk])
        block["month"] = mk
        out.append(block)
    return out
