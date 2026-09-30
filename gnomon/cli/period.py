"""Period selection for local profile runs."""

import calendar
from datetime import datetime, timedelta
from typing import List, NamedTuple, Optional

from gnomon.sources.discovery import parse_window


DEFAULT_PERIOD: str = "current_month"


class Period(NamedTuple):
    kind: str
    since: Optional[datetime]
    until: Optional[datetime]
    month_key: Optional[str]
    label: str
    days_elapsed: Optional[int]
    days_in_month: Optional[int]


def now_local() -> datetime:
    """Return the current timezone-aware local datetime."""
    return datetime.now().astimezone()


def _custom_label(since: Optional[datetime], until: Optional[datetime]) -> str:
    start = since.date().isoformat() if since is not None else "…"
    end = (until - timedelta(days=1)).date().isoformat() if until is not None else "today"
    return f"{start} → {end}"


def _current_month(now: datetime) -> Period:
    local_now = now.astimezone()
    since = local_now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_key = since.strftime("%Y-%m")
    days_in_month = calendar.monthrange(local_now.year, local_now.month)[1]
    days_elapsed = local_now.day
    day_word = "day" if days_elapsed == 1 else "days"
    label = f"{local_now.strftime('%b %Y')} · in progress · {days_elapsed} {day_word}"
    return Period("current_month", since, None, month_key, label,
                  days_elapsed, days_in_month)


def resolve_period(argv: List[str], now: Optional[datetime] = None) -> Period:
    """Resolve window flags or the configured default local-profile period."""
    effective_now = (now if now is not None else now_local()).astimezone()
    since, until = parse_window(argv, now=effective_now)
    if since is not None or until is not None:
        return Period("custom", since, until, None,
                      _custom_label(since, until), None, None)
    if DEFAULT_PERIOD == "current_month":
        return _current_month(effective_now)
    return Period("all_history", None, None, None, "All history", None, None)
