"""The local profile's monthly AQ trend."""

import html

from gnomon.scoring.aq import TIER_FLOORS


_CHART_HEIGHT = 110


CSS = """
.trend-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) auto minmax(0, 1fr);
  align-items: start;
  gap: 40px;
  min-width: 0;
}
.trend-next {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
}
.trend-next-figure {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-top: 12px;
}
.trend-next-points {
  font: 500 40px/.88 var(--font-figure);
  letter-spacing: -.025em;
  color: var(--text-primary);
}
.trend-next-unit {
  color: var(--text-secondary);
  font-size: 15px;
}
.trend-next-bar {
  position: relative;
  height: 8px;
  margin-top: 12px;
  background: var(--chart-track);
}
.trend-next-fill {
  position: absolute;
  top: 0;
  bottom: 0;
  left: 0;
  background: var(--chart-1);
}
.trend-next-scale {
  display: flex;
  justify-content: space-between;
  color: var(--text-tertiary);
  font: 400 11px/1.3 var(--font-figure);
  letter-spacing: .1em;
  text-transform: uppercase;
}
.trend-next-note {
  margin: 4px 0 0;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.5;
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
@media (max-width: 760px) {
  .trend-grid { grid-template-columns: 1fr; gap: 24px; }
  .trend-grid > .gn-vrule { display: none; }
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


def _next_level_html(ctx):
    """How many AQ points separate the headline score from the next tier."""
    aq = ((getattr(ctx, "stats", None) or {}).get("agentic") or {})
    score = aq.get("aq_0_100")
    if score is None:
        return ""
    score = _number(score)
    floors = list(reversed(TIER_FLOORS))          # lowest tier first
    index = max(i for i, (_, floor) in enumerate(floors) if score >= floor)
    tier, floor = floors[index]
    head = '<span class="gn-label">Next level</span>'
    if index == len(floors) - 1:
        return (
            '<div class="trend-next" data-next-tier="">{head}'
            '<p class="trend-next-note">{tier} is the top level. Keep it there: the AQ is '
            'scored month by month.</p></div>'
        ).format(head=head, tier=_text(tier))
    next_tier, next_floor = floors[index + 1]
    missing = next_floor - score
    progress = (score - floor) * 100.0 / (next_floor - floor)
    return (
        '<div class="trend-next" data-next-tier="{next_tier}" data-points="{missing}">{head}'
        '<div class="trend-next-figure"><span class="trend-next-points">{missing}</span>'
        '<span class="trend-next-unit">{unit} to {next_tier}</span></div>'
        '<div class="trend-next-bar" role="img" aria-label="{score} of {next_floor} for '
        '{next_tier}"><span class="trend-next-fill" style="width:{width:.0f}%"></span></div>'
        '<div class="trend-next-scale"><span>{tier} · {floor}</span>'
        '<span>{next_tier} · {next_floor}</span></div>'
        '<p class="trend-next-note">Your AQ is {score}. {next_tier} starts at {next_floor}.</p>'
        '</div>'
    ).format(head=head, missing=_number_text(missing),
             unit="point" if missing == 1 else "points", next_tier=_text(next_tier),
             next_floor=next_floor, tier=_text(tier), floor=floor,
             score=_number_text(score), width=max(0.0, min(100.0, progress)))


def render(ctx) -> str:
    """Render the monthly AQ trend, with the distance to the next tier beside it."""
    trend = getattr(ctx, "trend", None) or {}
    points = trend.get("points") or []
    chart = (
        '<div class="trend-chart" role="img" aria-label="{aria_label}">{columns}</div>'.format(
            aria_label=_text(_aria_label(points)),
            columns="".join(_column(point) for point in points))
        if points else '<p class="gn-empty">No months with activity yet.</p>')
    return (
        '<div class="trend-grid">'
        '<div class="trend-main">'
        '<div class="gn-section-head trend-heading"><h2>AQ evolution by month</h2></div>'
        '{chart}'
        '</div>'
        '<div class="gn-vrule" aria-hidden="true"></div>'
        '{next_level}'
        '</div>'
    ).format(chart=chart, next_level=_next_level_html(ctx))
