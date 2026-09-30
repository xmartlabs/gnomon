"""The local profile's monthly AQ trend."""

import html


_CHART_HEIGHT = 120
_TREND_NOTE = "Monthly AQ, calculated from the activity in each month."


CSS = """
#trend {
  margin-top: 64px;
}
.trend-heading {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 24px;
  min-width: 0;
  margin-bottom: 8px;
}
.trend-heading h2 {
  min-width: 0;
  margin: 0;
  color: var(--text-primary);
  font-size: 24px;
  line-height: 1.2;
}
.trend-note {
  min-width: 0;
  margin: 0;
  color: var(--text-tertiary);
  font-size: 13px;
  text-align: right;
}
.trend-chart {
  display: flex;
  align-items: flex-end;
  gap: var(--space-5);
  min-width: 0;
  height: 176px;
  padding: 20px 0 0;
  border-bottom: 1px solid var(--rule-strong);
}
.trend-col {
  display: flex;
  flex: 1 1 0;
  min-width: 0;
  height: 100%;
  flex-direction: column;
  align-items: center;
  justify-content: flex-end;
  gap: var(--space-3);
}
.trend-value {
  min-width: 0;
  color: var(--text-secondary);
  font-family: var(--font-figure);
  font-size: 13px;
  font-variant-numeric: tabular-nums;
  line-height: 1.2;
  white-space: nowrap;
}
.trend-bar {
  width: 100%;
  min-height: 2px;
  background: var(--chart-4);
}
.trend-col[data-in-progress="true"] .trend-value {
  color: var(--text-primary);
}
.trend-col[data-in-progress="true"] .trend-bar {
  background: var(--chart-1);
}
.trend-label,
.trend-progress {
  min-width: 0;
  overflow-wrap: anywhere;
  color: var(--text-tertiary);
  font-family: var(--font-figure);
  font-size: 11px;
  letter-spacing: 0.1em;
  line-height: 1.2;
  text-align: center;
  text-transform: uppercase;
}
.trend-progress {
  min-height: 13px;
  color: var(--text-primary);
  font-family: var(--font-ui);
  font-size: 12px;
  letter-spacing: 0;
  text-transform: none;
}
.trend-approx-note {
  margin: 12px 0 0;
  padding-top: 8px;
  border-top: 1px solid var(--rule-default);
  color: var(--text-tertiary);
  font-size: 13px;
}
.trend-approx-mark {
  font-family: var(--font-figure);
}
@media (max-width: 680px) {
  .trend-heading { display: block; }
  .trend-note { margin-top: 8px; text-align: left; }
  .trend-chart { gap: var(--space-2); }
}
"""


def _text(value):
    return html.escape(str(value), quote=True)


def _approx_mark(point, value):
    """Prefix an approximate monthly value without changing its numeric value."""
    if point.get("approximate"):
        return "≈" + value
    return value


def _number(value, default=0):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number.is_integer():
        return int(number)
    return number


def _number_text(value):
    number = _number(value)
    if isinstance(number, float):
        return "{:g}".format(number)
    return str(number)


def _bar_height(value):
    score = max(0.0, min(100.0, float(_number(value))))
    return max(2, round(score / 100.0 * _CHART_HEIGHT))


def _aria_label(points):
    values = []
    for point in points:
        value = _number_text(point.get("aq", 0))
        prefix = "approximate " if point.get("approximate") else ""
        progress = " in progress" if point.get("in_progress") else ""
        values.append("{} {}AQ {}{}".format(
            point.get("label", point.get("month", "")), prefix, value, progress))
    return "AQ by month: " + ", ".join(values)


def _column(point):
    value = _number_text(point.get("aq", 0))
    display_value = _approx_mark(point, value)
    progress = "in progress" if point.get("in_progress") else ""
    return (
        '<div class="trend-col" data-month="{month}" data-aq="{aq}" '
        'data-in-progress="{in_progress}" data-approximate="{approximate}">'
        '<span class="trend-value">{display_value}</span>'
        '<div class="trend-bar" style="height:{height}px" aria-hidden="true"></div>'
        '<span class="trend-progress">{progress}</span>'
        '<span class="trend-label">{label}</span>'
        '</div>'
    ).format(
        month=_text(point.get("month", "")),
        aq=_text(value),
        in_progress="true" if point.get("in_progress") else "false",
        approximate="true" if point.get("approximate") else "false",
        display_value=_text(display_value),
        height=_bar_height(point.get("aq", 0)),
        progress=_text(progress),
        label=_text(point.get("label", point.get("month", ""))),
    )


def render(ctx) -> str:
    """Render the sparse, oldest-first monthly AQ trend."""
    trend = getattr(ctx, "trend", None) or {}
    points = trend.get("points") or []
    if not points:
        return '<p class="gn-empty">No months with activity yet.</p>'

    count = len(points)
    month_word = "month" if count == 1 else "months"
    approximate = any(point.get("approximate") for point in points)
    note = (
        '<p class="trend-approx-note"><span class="trend-approx-mark">≈</span> '
        'Approximate values combine multiple sources.</p>'
        if approximate else ""
    )
    return (
        '<div class="trend-heading">'
        '<h2>AQ by month · {count} {month_word}</h2>'
        '<p class="trend-note">{trend_note}</p>'
        '</div>'
        '<div class="trend-chart" role="img" aria-label="{aria_label}">{columns}</div>'
        '{note}'
    ).format(
        count=count,
        month_word=month_word,
        trend_note=_text(_TREND_NOTE),
        aria_label=_text(_aria_label(points)),
        columns="".join(_column(point) for point in points),
        note=note,
    )
