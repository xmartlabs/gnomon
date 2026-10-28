"""MCP vs CLI and tool diversity: readings that are described, rather than graded."""

import html


CSS = """
.readings {
  display: flex;
  min-width: 0;
  flex-direction: column;
}
.reading {
  min-width: 0;
  padding: 20px 0;
  border-top: 1px solid var(--rule-subtle);
}
.reading:first-child {
  padding-top: 0;
  border-top: 0;
}
.reading:last-child {
  padding-bottom: 0;
}
.reading-title {
  margin: 0 0 12px;
}
.reading-note {
  margin: 10px 0 0;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.5;
  text-wrap: pretty;
}
.reading-note b {
  font-weight: inherit;
}
.mcp-bar {
  display: flex;
  gap: 2px;
  height: 8px;
  min-width: 0;
}
.mcp-segment {
  flex: 0 1 auto;
  min-width: 0;
}
.mcp-segment.cli { background: var(--chart-1); }
.mcp-segment.mcp { background: var(--chart-3); }
.mcp-labels {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-top: 8px;
  color: var(--text-primary);
  font: 400 12px/1.4 var(--font-figure);
}
.mcp-labels span + span {
  color: var(--text-secondary);
  text-align: right;
}
.diversity-figures {
  display: flex;
  gap: 32px;
}
.diversity-value {
  color: var(--text-primary);
  font: 500 28px/1.15 var(--font-figure);
}
.diversity-label {
  color: var(--text-secondary);
  font-size: 13px;
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


def _mcp_html(aq):
    reading = aq.get("mcp_vs_cli") or {}
    cli_calls = _count(reading.get("cli_calls"))
    cli_distinct = _count(reading.get("cli_distinct"))
    mcp_calls = _count(reading.get("mcp_calls"))
    mcp_distinct = _count(reading.get("mcp_distinct"))
    total = cli_calls + mcp_calls
    cli_pct = (cli_calls * 100.0 / total) if total else 0.0
    mcp_pct = (mcp_calls * 100.0 / total) if total else 0.0
    ratio = "all-CLI (no MCP)" if mcp_calls == 0 else _ratio(reading.get("ratio")) + ":1"
    if mcp_calls > cli_calls:
        note = ("Ratio <b>{ratio}</b> — MCP carries more of your tool traffic this month."
                .format(ratio=_text(ratio)))
    else:
        note = ("Ratio <b>{ratio}</b> CLI-first. CLI is token-cheap and scriptable — you reach "
                "for it on repeatable work and reserve MCP for what CLI can't do (browser, "
                "design canvas, device control)."
                .format(ratio=_text(ratio)))
    return (
        '<div class="reading" data-reading="mcp_vs_cli" data-graded="false">'
        '<h3 class="gn-label reading-title">MCP vs CLI · described, not graded</h3>'
        '<div class="mcp-bar" role="img" aria-label="CLI {cli_calls} calls, MCP {mcp_calls} calls">'
        '<span class="mcp-segment cli" style="width:{cli_width}"></span>'
        '<span class="mcp-segment mcp" style="width:{mcp_width}"></span>'
        '</div>'
        '<div class="mcp-labels">'
        '<span>CLI · {cli_calls} calls · {cli_distinct} {cli_noun}</span>'
        '<span>MCP · {mcp_calls} · {mcp_distinct} {mcp_noun}</span>'
        '</div>'
        '<p class="reading-note">{note}</p>'
        '</div>'
    ).format(
        cli_width=_width(cli_pct),
        mcp_width=_width(mcp_pct),
        cli_calls=_text("{:,}".format(cli_calls)),
        cli_distinct=_text("{:,}".format(cli_distinct)),
        cli_noun="tool" if cli_distinct == 1 else "tools",
        mcp_calls=_text("{:,}".format(mcp_calls)),
        mcp_distinct=_text("{:,}".format(mcp_distinct)),
        mcp_noun="server" if mcp_distinct == 1 else "servers",
        note=note,
    )


def _diversity_html(aq):
    reading = aq.get("tool_diversity") or {}
    distinct = _count(reading.get("distinct"))
    entropy = reading.get("entropy", 0)
    return (
        '<div class="reading" data-reading="tool_diversity" data-graded="false">'
        '<h3 class="gn-label reading-title">Tool diversity · described, not graded</h3>'
        '<div class="diversity-figures">'
        '<div><div class="diversity-value">{distinct}</div>'
        '<div class="diversity-label">distinct tools</div></div>'
        '<div><div class="diversity-value">{entropy}</div>'
        '<div class="diversity-label">entropy</div></div>'
        '</div>'
        '<p class="reading-note">High range available, concentrated use. Not penalized.</p>'
        '</div>'
    ).format(distinct=_text("{:,}".format(distinct)), entropy=_text(_entropy(entropy)))


def _entropy(value):
    try:
        return "{:.2f}".format(float(value))
    except (TypeError, ValueError):
        return str(value)


def render(ctx) -> str:
    """Render MCP vs CLI above tool diversity; both are described, not graded."""
    stats = getattr(ctx, "stats", None) or {}
    aq = stats.get("agentic")
    if not aq:
        return ""
    return '<div class="readings">{}{}</div>'.format(_mcp_html(aq), _diversity_html(aq))
