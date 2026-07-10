from gnomon.config import _pretty_model
from gnomon.scoring.gstack import score_breakdown
from gnomon.scoring.archetype import pick_archetype
from gnomon.scoring.insights import (
    steering_reading, growth_edges_structured, signature_moves_structured,
)


def model_usage_from_models(models, tok_by_model=None):
    """Shape stack.models into the model_usage payload."""
    tok_by_model = tok_by_model or {}
    total = sum(n for _, n in models)
    if total <= 0:
        return []
    return [
        {
            "model_id": m,
            "model": _pretty_model(m),
            "count": int(n),
            "pct": round(n / total, 3),
            "tokens_input":          (tok_by_model.get(m) or {}).get("input", 0),
            "tokens_output":         (tok_by_model.get(m) or {}).get("output", 0),
            "tokens_cache_read":     (tok_by_model.get(m) or {}).get("cache_read", 0),
            "tokens_cache_creation": (tok_by_model.get(m) or {}).get("cache_creation", 0),
        }
        for m, n in models[:12]
    ]


def stats_from_scoring_block(block):
    """Turn a scoring-input block back into the stats shape scoring functions read."""
    s = {
        "corpus": {"sources": (block.get("corpus", {}).get("sources")
                               or ({block["source"]: {}} if block.get("source") else {}))},
        "volume": dict(block.get("volume") or {}),
        "velocity": dict(block.get("velocity") or {}),
        "behavior": dict(block.get("behavior") or {}),
        "stack": dict(block.get("stack") or {}),
        "tools": dict(block.get("tools") or {}),
    }
    s["volume"].setdefault("total_sessions", 0)
    s["volume"].setdefault("tool_calls_total", 0)
    s["token_usage"] = block.get("token_usage") or {"by_model": []}
    return s


def build_profile(stats, model_usage=None):
    """Assemble a profile dict from a stats/scoring block."""
    aq = stats.get("agentic", {})
    sb = score_breakdown(stats)
    arch_scores = {
        "Execution": sb["execution"]["value"],
        "Planning": sb["planning"]["value"],
        "Engineering": sb["engineering"]["value"],
    }
    # AQ-derived growth edges use the rolling blend. Identity/descriptive fields
    # remain explicitly full-window scoped so a short bucket cannot rewrite them.
    full_window_stats = stats
    if stats.get("_full_window_agentic"):
        full_window_stats = dict(stats)
        full_window_stats["agentic"] = stats["_full_window_agentic"]
    arch_title, arch_quote = pick_archetype(full_window_stats, arch_scores)
    if model_usage is None:
        all_models = (stats.get("stack") or {}).get("models") or []
        tok_by_model = {e["model_id"]: e for e in (stats.get("token_usage") or {}).get("by_model") or []}
        model_usage = model_usage_from_models(all_models, tok_by_model)
    return {
        "aq": aq,
        "archetype": {"title": arch_title, "quote": arch_quote},
        "scores": sb,
        "steering": steering_reading(full_window_stats),
        "growth_edges": growth_edges_structured(stats, arch_scores),
        "signature_moves": signature_moves_structured(full_window_stats),
        "model_usage": model_usage,
    }
