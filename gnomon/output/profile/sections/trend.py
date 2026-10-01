"""The local profile's monthly AQ trend."""

import html


_CHART_HEIGHT = 110


CSS = """
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
@media (max-width: 760px) {
  .trend-chart { gap: 8px; }
}
"""


def _text(value):
    return html.escape(str(value), quote=True)


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
        progress = " in progress" if point.get("in_progress") else ""
        values.append("{} AQ {}{}".format(
            point.get("label", point.get("month", "")), value, progress))
    return "AQ by month: " + ", ".join(values)


def _column(point):
    value = _number_text(point.get("aq", 0))
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
        display_value=_text(value),
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
    return (
        '<div class="gn-section-head trend-heading">'
        '<h2>AQ evolution by month</h2>'
        '</div>'
        '<div class="trend-chart" role="img" aria-label="{aria_label}">{columns}</div>'
    ).format(
        aria_label=_text(_aria_label(points)),
        columns="".join(_column(point) for point in points),
    )
