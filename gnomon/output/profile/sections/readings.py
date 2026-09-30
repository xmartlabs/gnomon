"""Activity readings that are described, rather than graded."""

import html

from gnomon.scoring.insights import steering_reading


CSS = """
.readings {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 32px;
  margin-top: 40px;
}
.reading {
  min-width: 0;
  padding-top: 12px;
  border-top: 1px solid var(--rule-default);
}
.reading-title {
  margin: 0 0 16px;
  color: var(--text-primary);
  font-size: 14px;
  font-weight: 600;
}
.reading-value {
  margin: 0 0 4px;
  color: var(--text-primary);
  font-family: var(--font-figure);
  font-size: 24px;
  font-variant-numeric: tabular-nums;
}
.reading-gloss,
.reading-detail,
.reading-note {
  margin: 4px 0 0;
  color: var(--text-secondary);
  font-size: 13px;
}
.reading-detail,
.reading-note {
  color: var(--text-tertiary);
}
.reading-note b {
  color: var(--text-secondary);
  font-weight: 600;
}
.mcp-bar {
  display: flex;
  min-width: 0;
  height: 32px;
  margin: 8px 0 10px;
  overflow: hidden;
  background: var(--chart-track);
}
.mcp-segment {
  display: flex;
  min-width: 0;
  align-items: center;
  overflow: hidden;
  padding: 0 10px;
  color: var(--text-inverse);
  font-family: var(--font-mono);
  font-size: 11px;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.mcp-segment.cli { background: var(--chart-1); }
.mcp-segment.mcp { background: var(--chart-2); }
@media (max-width: 820px) {
  .readings { grid-template-columns: 1fr; gap: 24px; }
}
"""


def _text(value):
    return html.escape(str(value), quote=True)


def _count(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _number(value, default=0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _ratio(value):
    if value is None:
        return "n/a"
    number = _number(value, 0.0)
    if number.is_integer():
        return str(int(number))
    return str(value)


def _width(value):
    """Return a non-negative CSS percentage without unnecessary decimals."""
    value = max(0.0, min(100.0, value))
    if value.is_integer():
        return str(int(value)) + "%"
    return "%.2f%%" % value


def _steering_html(stats):
    try:
        reading = steering_reading(stats)
    except (KeyError, TypeError, ZeroDivisionError):
        return ""
    return (
        '<div class="reading" data-reading="steering" data-graded="false">'
        '<h3 class="reading-title">Steering · described, not graded</h3>'
        '<p class="reading-value">{label}</p>'
        '<p class="reading-gloss">{gloss}</p>'
        '<p class="reading-detail">{detail}</p>'
        '</div>'
    ).format(
        label=_text(reading["label"]),
        gloss=_text(reading["gloss"]),
        detail=_text(reading["detail"]),
    )


def _mcp_html(aq):
    reading = aq.get("mcp_vs_cli") or {}
    cli_calls = _count(reading.get("cli_calls"))
    cli_distinct = _count(reading.get("cli_distinct"))
    mcp_calls = _count(reading.get("mcp_calls"))
    mcp_distinct = _count(reading.get("mcp_distinct"))
    total = cli_calls + mcp_calls
    cli_pct = (cli_calls * 100.0 / total) if total else 0.0
    mcp_pct = (mcp_calls * 100.0 / total) if total else 0.0
    ratio = "all-CLI (no MCP)" if mcp_calls == 0 else _ratio(reading.get("ratio"))
    return (
        '<div class="reading" data-reading="mcp_vs_cli" data-graded="false">'
        '<h3 class="reading-title">MCP vs CLI · described, not graded</h3>'
        '<div class="mcp-bar" role="img" aria-label="CLI and MCP calls">'
        '<span class="mcp-segment cli" style="width:{cli_width}">'
        'CLI · {cli_calls} · {cli_distinct} tools</span>'
        '<span class="mcp-segment mcp" style="width:{mcp_width}">'
        'MCP · {mcp_calls} · {mcp_distinct} servers</span>'
        '</div>'
        '<p class="reading-note">Ratio <b>{ratio}</b> CLI-first. CLI is token-cheap '
        'and scriptable — you reach for it on repeatable work and reserve MCP for '
        'what CLI can\'t do (browser, design canvas, device control). Right instinct, '
        'not a gap.</p>'
        '</div>'
    ).format(
        cli_width=_width(cli_pct),
        mcp_width=_width(mcp_pct),
        cli_calls=_text("{:,}".format(cli_calls)),
        cli_distinct=_text("{:,}".format(cli_distinct)),
        mcp_calls=_text("{:,}".format(mcp_calls)),
        mcp_distinct=_text("{:,}".format(mcp_distinct)),
        ratio=_text(ratio),
    )


def _diversity_html(aq):
    reading = aq.get("tool_diversity") or {}
    distinct = _count(reading.get("distinct"))
    entropy = reading.get("entropy", 0)
    return (
        '<div class="reading" data-reading="tool_diversity" data-graded="false">'
        '<h3 class="reading-title">Tool diversity · described, not graded</h3>'
        '<p class="reading-value">{distinct} distinct tools</p>'
        '<p class="reading-detail">Entropy {entropy} · High range available, '
        'concentrated use. Not penalized.</p>'
        '</div>'
    ).format(distinct=_text("{:,}".format(distinct)), entropy=_text(entropy))


def render(ctx) -> str:
    """Render Steering, and AQ sidechain readings when AQ data is available."""
    stats = getattr(ctx, "stats", None) or {}
    steering = _steering_html(stats)
    if not steering:
        return ""
    readings = [steering]
    aq = stats.get("agentic")
    if aq:
        readings.extend((_mcp_html(aq), _diversity_html(aq)))
    return '<div class="readings">{}</div>'.format("".join(readings))
