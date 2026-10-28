"""Monthly AQ trend helpers for the local profile."""

import calendar
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple


TREND_MONTHS = 6


def _month_number(month_key: str) -> Tuple[int, int]:
    try:
        parsed = datetime.strptime(month_key + "-01", "%Y-%m-%d")
    except (TypeError, ValueError):
        raise ValueError("month_key must be YYYY-MM")
    return parsed.year, parsed.month


def _add_months(year: int, month: int, offset: int) -> Tuple[int, int]:
    absolute = year * 12 + month - 1 + offset
    return absolute // 12, absolute % 12 + 1


def trend_months(end_month: str, months: int = TREND_MONTHS) -> List[str]:
    """Return the trailing calendar months ending at ``end_month``."""
    if months < 1:
        return []
    year, month = _month_number(end_month)
    return [
        "%04d-%02d" % _add_months(year, month, offset)
        for offset in range(-(months - 1), 1)
    ]


def month_bounds(month_key: str) -> Tuple[datetime, datetime]:
    """Return the timezone-aware local half-open bounds for a calendar month."""
    year, month = _month_number(month_key)
    tzinfo = datetime.now().astimezone().tzinfo
    since = datetime(year, month, 1, tzinfo=tzinfo)
    next_year, next_month = _add_months(year, month, 1)
    until = datetime(next_year, next_month, 1, tzinfo=tzinfo)
    return since, until


def _month_label(month_key: str) -> str:
    year, month = _month_number(month_key)
    return calendar.month_abbr[month]


def _active_sources(stats: dict) -> List[str]:
    source_stats = (stats.get("corpus", {}).get("sources", {}) or {})
    return sorted(
        source for source, values in source_stats.items()
        if (values or {}).get("sessions", 0) > 0
    )


def _point_result(value: dict) -> Tuple[Optional[dict], List[str], Optional[int]]:
    """Normalize a scored month result accepted by ``build_aq_trend``."""
    stats = value.get("stats") if isinstance(value, dict) else None
    score = value.get("aq") if isinstance(value, dict) else None
    if score is None and isinstance(value, dict) and "aq_0_100" in value:
        score = value
    if score is None and isinstance(value, dict):
        score = value.get("agentic")
    if score is None and isinstance(stats, dict):
        score = stats.get("agentic")
    if not isinstance(score, dict):
        return None, [], None

    sources = value.get("sources") if isinstance(value, dict) else None
    if sources is None and isinstance(stats, dict):
        sources = _active_sources(stats)
    sources = sorted(set(sources or []))

    sessions = value.get("total_sessions") if isinstance(value, dict) else None
    if sessions is None and isinstance(stats, dict):
        sessions = (stats.get("volume", {}) or {}).get("total_sessions")
    return score, sources, sessions


def build_aq_trend(end_month: str, month_stats: Dict[str, dict],
                   current_month: Optional[str] = None,
                   current_stats: Optional[dict] = None,
                   now: Optional[datetime] = None) -> dict:
    """Build an oldest-first, sparse six-month AQ trend.

    ``month_stats`` maps month keys to scored results.  A result may be an AQ dict
    directly, or ``{"aq": aq_dict, "sources": [...], "stats": raw_stats}``.
    ``current_stats`` replaces the current-month result when the local period is the
    calendar month; this is how the titular AQ is kept identical to the hero score.
    """
    current_now = (now if now is not None else datetime.now().astimezone()).astimezone()
    in_progress_month = current_now.strftime("%Y-%m")
    results = dict(month_stats or {})
    if current_month is not None and current_stats is not None:
        results[current_month] = {
            "aq": current_stats.get("agentic", current_stats),
            "stats": current_stats,
            "sources": _active_sources(current_stats),
        }

    points = []
    for month in trend_months(end_month):
        value = results.get(month)
        if value is None:
            continue
        score, sources, sessions = _point_result(value)
        if score is None or (sessions is not None and sessions <= 0):
            continue
        is_current_point = current_month is not None and month == current_month
        points.append({
            "month": month,
            "label": _month_label(month),
            "aq": score.get("aq_0_100", 0),
            "tier": score.get("tier", "Novice"),
            "in_progress": month == in_progress_month,
            "approximate": False if is_current_point else len(sources) > 1,
            "sources": sources,
        })
    return {"end_month": end_month, "points": points}


def aq_delta(trend: Optional[dict], month_key: Optional[str]) -> Optional[dict]:
    """Return the change from the immediately preceding calendar month."""
    if not trend or not month_key:
        return None
    year, month = _month_number(month_key)
    previous_year, previous_month = _add_months(year, month, -1)
    previous_key = "%04d-%02d" % (previous_year, previous_month)
    points = {point.get("month"): point for point in trend.get("points", [])}
    current = points.get(month_key)
    previous = points.get(previous_key)
    if current is None or previous is None:
        return None
    return {
        "value": current.get("aq", 0) - previous.get("aq", 0),
        "prev_month": previous_key,
        "prev_label": previous.get("label", _month_label(previous_key)),
    }
