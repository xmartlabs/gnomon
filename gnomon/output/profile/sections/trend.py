"""The local profile's monthly AQ trend."""

import html


_CHART_HEIGHT = 110
_MONTH_DAYS_NOTE = ("Each column is that month's AQ, scored on that month's sessions only.")


CSS = """
.trend-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) auto minmax(0, 1fr);
  align-items: end;
  gap: 40px;
  min-width: 0;
}
.trend-heading {
  margin-bottom: 20px;
}
.trend-chart {
  display: flex;
  align-items: flex-end;
  gap: 16px;
  min-width: 0;
  height: 176px;
}
.trend-col {
  display: flex;
  flex: 1 1 0;
  max-width: 88px;
  min-width: 0;
  flex-direction: column;
  align-items: center;
  gap: 6px;
}
.trend-value {
  color: var(--text-secondary);
  font: 500 13px/1.3 var(--font-figure);
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
.trend-label {
  color: var(--text-tertiary);
  font: 400 11px/1.3 var(--font-figure);
  letter-spacing: .1em;
  text-transform: uppercase;
}
.trend-progress {
  height: 14px;
  color: var(--text-secondary);
  font: 400 11px/14px var(--font-figure);
  white-space: nowrap;
}
.trend-aside {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding-bottom: 20px;
}
.trend-note {
  margin: 0;
  color: var(--text-secondary);
  font-size: 15px;
  line-height: 1.5;
  text-wrap: pretty;
}
.trend-approx-note {
  margin: 16px 0 0;
  padding-top: 8px;
  border-top: 1px solid var(--rule-default);
  color: var(--text-tertiary);
  font-size: 13px;
}
.trend-approx-mark {
  font-family: var(--font-figure);
}
@media (max-width: 760px) {
  .trend-grid { grid-template-columns: 1fr; gap: 24px; }
  .trend-grid > .gn-vrule { display: none; }
  .trend-chart { gap: 8px; }
  .trend-aside { padding-bottom: 0; }
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
        '<span class="trend-label">{label}</span>'
        '<span class="trend-progress">{progress}</span>'
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


def _aside(ctx, points):
    """Return the label and note shown beside the chart."""
    period = getattr(ctx, "period", None)
    last = points[-1]
    label = str(last.get("label", last.get("month", "")))
    if last.get("in_progress"):
        days = getattr(period, "days_elapsed", None)
        total = getattr(period, "days_in_month", None)
        if days and total:
            covers = "{} covers {} of {} days".format(label, days, total)
        else:
            covers = "{} is still in progress".format(label)
        if len(points) == 1:
            note = ("{}. It's your first month on record, so there is no delta yet — the "
                    "trend adds a column as each month closes.").format(covers)
        else:
            note = "{} and keeps moving until the month closes. {}".format(
                covers, _MONTH_DAYS_NOTE)
        return "{} · in progress".format(label), note
    return "AQ per month", _MONTH_DAYS_NOTE


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
    aside_label, aside_note = _aside(ctx, points)
    return (
        '<div class="trend-grid">'
        '<div class="trend-main">'
        '<div class="gn-section-head trend-heading">'
        '<h2>AQ by month · {count} {month_word}</h2>'
        '</div>'
        '<div class="trend-chart" role="img" aria-label="{aria_label}">{columns}</div>'
        '{note}'
        '</div>'
        '<div class="gn-vrule" aria-hidden="true"></div>'
        '<div class="trend-aside">'
        '<span class="gn-label">{aside_label}</span>'
        '<p class="trend-note">{aside_note}</p>'
        '</div>'
        '</div>'
    ).format(
        count=count,
        month_word=month_word,
        aria_label=_text(_aria_label(points)),
        columns="".join(_column(point) for point in points),
        note=note,
        aside_label=_text(aside_label),
        aside_note=_text(aside_note),
    )
