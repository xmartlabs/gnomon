"""The AQ breakdown: pillars, axes, and measured-data disclosure."""

import html

from gnomon.scoring.gstack import (
    AQ_AXIS_NOTES,
    AQ_PILLAR_NOTES,
    savvy_cursor_model_mix_note,
)


# Keep this order in step with the axis lists assembled by compute_aq().  A dropped axis is
# absent from ``pillar["axes"]``, so the renderer needs the source order to put it back in its
# intended position beside the measured axes.
_CANONICAL_AXES = {
    "Breadth": ("Orchestration", "Skill fluency", "Tool command (MCP + CLI)", "Discipline"),
    "Craft": ("Verification", "Grounding", "Context Intelligence", "Compounding"),
    "Efficiency": ("Steering leverage", "Recovery"),
    "Savvy": ("Model mix", "Token economy"),
}


CSS = """
#aq-breakdown {
  margin-top: 64px;
}
.aq-breakdown-heading {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 32px;
}
.aq-breakdown-heading h2 {
  margin: 0;
  color: var(--text-primary);
  font-size: 24px;
  line-height: 1.2;
}
.aq-breakdown-hint {
  margin: 0;
  color: var(--text-tertiary);
  font-size: 13px;
}
.aq-pillars {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 48px 40px;
}
.aq-pillar {
  min-width: 0;
  padding-top: 16px;
  border-top: 1px solid var(--rule-strong);
}
.aq-pillar-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 16px;
  min-width: 0;
  margin-bottom: 20px;
}
.aq-pillar-name {
  min-width: 0;
  overflow-wrap: anywhere;
  color: var(--text-primary);
  font-size: 18px;
  font-weight: 600;
}
.aq-pillar-score {
  flex: 0 0 auto;
  color: var(--text-primary);
  font-family: var(--font-figure);
  font-size: 20px;
  font-variant-numeric: tabular-nums;
}
.aq-axis {
  min-width: 0;
  padding: 12px 0;
  border-top: 1px solid var(--rule-subtle);
}
.aq-axis-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 16px;
  min-width: 0;
}
.aq-axis-name {
  min-width: 0;
  overflow-wrap: anywhere;
  color: var(--text-secondary);
  font-size: 13px;
}
.aq-axis-value {
  flex: 0 0 auto;
  color: var(--text-primary);
  font-family: var(--font-figure);
  font-size: 14px;
  font-variant-numeric: tabular-nums;
}
.aq-axis[data-edge="01"],
.aq-axis[data-edge="02"],
.aq-axis[data-edge="03"] {
  border-left: 3px solid var(--accent);
  padding-left: 12px;
}
.aq-axis-edge {
  display: inline-block;
  margin-left: 8px;
  color: var(--accent);
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: .04em;
  text-transform: uppercase;
}
.gn-bar {
  height: 6px;
  margin-top: 8px;
  overflow: hidden;
  background: var(--chart-track);
}
.gn-bar-fill {
  display: block;
  height: 100%;
  background: var(--chart-1);
}
.aq-axis-unmeasured {
  margin: 8px 0 0;
  font-size: 13px;
}
.aq-pillar-note {
  margin: 16px 0 0;
  color: var(--text-tertiary);
  font-size: 13px;
}
.aq-pillar-note strong {
  color: var(--text-secondary);
  font-weight: 600;
}
@media (max-width: 760px) {
  .aq-pillars { grid-template-columns: 1fr; gap: 32px; }
  .aq-breakdown-heading { display: block; }
  .aq-breakdown-hint { margin-top: 8px; }
}
"""


def _text(value):
    return html.escape(str(value), quote=True)


def _axis_value(axis) -> str:
    """Return the measured axis value on the public 0–100 display scale."""
    try:
        normalized = float(axis.get("normalized_score"))
    except (AttributeError, TypeError, ValueError):
        return ""
    normalized = max(0.0, min(1.0, normalized))
    return str(round(normalized * 100))


def _axis_order(pillar):
    """Yield measured and dropped axes in compute_aq's canonical order."""
    measured = {axis.get("name"): axis for axis in (pillar.get("axes") or [])}
    dropped = set(pillar.get("not_applicable") or [])
    names = list(_CANONICAL_AXES.get(pillar.get("name"), ()))
    names.extend(name for name in measured if name not in names)
    names.extend(name for name in dropped if name not in names)
    for name in names:
        if name in measured:
            yield name, measured[name], True
        elif name in dropped:
            yield name, None, False


def _edge_numbers(ctx):
    return {
        edge.get("axis"): edge.get("n", "")
        for edge in (getattr(ctx, "edges", None) or [])
        if edge.get("axis")
    }


def _axis_html(name, axis, measured, edge_number):
    attrs = ' class="aq-axis" data-axis="{name}" data-measured="{measured}" data-edge="{edge}"'.format(
        name=_text(name), measured="true" if measured else "false", edge=_text(edge_number))
    title = _text(AQ_AXIS_NOTES.get(name, ""))
    label = '<span class="aq-axis-name" title="{title}">{name}</span>'.format(
        title=title, name=_text(name))
    edge = ('<span class="aq-axis-edge">EDGE {}</span>'.format(_text(edge_number))
            if edge_number else "")
    if not measured:
        body = '<span class="gn-empty aq-axis-unmeasured">not measured for this source</span>'
    else:
        value = _axis_value(axis)
        try:
            width = max(0, min(100, int(value)))
        except ValueError:
            width = 0
        body = (
            '<span class="aq-axis-value">{value}</span>'
            '<div class="gn-bar" role="progressbar" aria-valuemin="0" '
            'aria-valuemax="100" aria-valuenow="{value}">'
            '<span class="gn-bar-fill" style="width:{width}%"></span></div>'
        ).format(value=_text(value), width=width)
    return '<div{attrs}><div class="aq-axis-header">{label}{edge}</div>{body}</div>'.format(
        attrs=attrs, label=label, edge=edge, body=body)


def _pillar_html(ctx, pillar, edges):
    name = pillar.get("name", "")
    axes = "".join(_axis_html(axis_name, axis, measured, edges.get(axis_name, ""))
                    for axis_name, axis, measured in _axis_order(pillar))
    note = ""
    if name == "Savvy":
        aq = (getattr(ctx, "stats", None) or {}).get("agentic") or {}
        cursor_note = savvy_cursor_model_mix_note(getattr(ctx, "stats", None) or {}, aq)
        if cursor_note:
            note = '<p class="aq-pillar-note"><strong>{}</strong> {}</p>'.format(
                _text(cursor_note[0]), _text(cursor_note[1]))
    return (
        '<div class="aq-pillar" data-pillar="{name}" title="{title}">'
        '<div class="aq-pillar-header">'
        '<span class="aq-pillar-name">{name}</span>'
        '<span class="aq-pillar-score">{score} / 100</span>'
        '</div>{axes}{note}</div>'
    ).format(
        name=_text(name), title=_text(AQ_PILLAR_NOTES.get(name, "")),
        score=_text(pillar.get("score", "")), axes=axes, note=note)


def render(ctx) -> str:
    """Render all four AQ pillars, including axes a source cannot measure."""
    stats = getattr(ctx, "stats", None) or {}
    aq = stats.get("agentic") or {}
    pillars = aq.get("pillars") or []
    if not pillars:
        return ""
    edges = _edge_numbers(ctx)
    rendered = "".join(_pillar_html(ctx, pillar, edges) for pillar in pillars)
    return (
        '<div class="aq-breakdown-heading">'
        '<h2>AQ breakdown</h2>'
        '<p class="aq-breakdown-hint">Axes shown on a 0–100 scale.</p>'
        '</div><div class="aq-pillars">{}</div>'
    ).format(rendered)
