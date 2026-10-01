"""The AQ breakdown: pillars, axes, and measured-data disclosure."""

import html

from gnomon.output.profile.ui import info_button
from gnomon.scoring.gstack import savvy_cursor_model_mix_note


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
.aq-breakdown-hint {
  margin-bottom: 28px;
}
.aq-pillars {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 40px;
}
.aq-pillar {
  min-width: 0;
  padding-top: 12px;
}
.aq-pillar-header {
  display: flex;
  align-items: baseline;
  gap: 8px;
  min-width: 0;
  margin-bottom: 20px;
}
.aq-pillar-name {
  min-width: 0;
  overflow-wrap: anywhere;
  color: var(--text-primary);
  font-size: 19px;
  font-weight: 600;
}
.aq-pillar-score {
  margin-left: auto;
  color: var(--text-primary);
  font: 500 28px/1.15 var(--font-figure);
  letter-spacing: -.025em;
}
.aq-pillar-scale {
  color: var(--text-tertiary);
  font: 400 11px/1.2 var(--font-figure);
}
.aq-axes {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.aq-axis {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}
.aq-axis-header {
  display: flex;
  align-items: baseline;
  gap: 8px;
  min-width: 0;
}
.aq-axis-name {
  min-width: 0;
  overflow-wrap: anywhere;
  color: var(--text-primary);
  font-size: 13px;
  line-height: 1.3;
}
.aq-axis[data-measured="false"] .aq-axis-name {
  color: var(--text-tertiary);
}
.aq-axis-value {
  margin-left: auto;
  flex: none;
  color: var(--text-primary);
  font: 500 15px/1.3 var(--font-figure);
}
.aq-axis-edge {
  display: inline-flex;
  height: 18px;
  flex: none;
  align-items: center;
  padding: 0 5px;
  border: 1px solid var(--accent);
  border-radius: 2px;
  color: var(--accent);
  font: 500 10px/1 var(--font-mono);
  letter-spacing: .08em;
}
.gn-bar {
  position: relative;
  height: 6px;
  background: var(--chart-track);
}
.gn-bar-fill {
  position: absolute;
  top: 0;
  bottom: 0;
  left: 0;
  background: var(--chart-1);
}
.aq-axis-unmeasured {
  color: var(--text-tertiary);
  font: 400 11px/1.3 var(--font-figure);
  letter-spacing: .04em;
}
.aq-axis-unmeasured::before {
  content: "\\2014\\00a0";
}
.aq-pillar-note {
  margin: 16px 0 0;
  padding-top: 12px;
  border-top: 1px solid var(--rule-subtle);
  color: var(--text-tertiary);
  font-size: 13px;
  line-height: 1.5;
  text-wrap: pretty;
}
.aq-pillar-note strong {
  color: var(--text-secondary);
  font-weight: 500;
}
@media (max-width: 960px) {
  .aq-pillars { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 40px; }
}
@media (max-width: 560px) {
  .aq-pillars { grid-template-columns: 1fr; gap: 32px; }
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
    label = '<span class="aq-axis-name">{name}</span>'.format(name=_text(name))
    edge = ('<span class="aq-axis-edge">EDGE {}</span>'.format(_text(edge_number))
            if edge_number else "")
    if not measured:
        value = ""
        body = '<span class="gn-empty aq-axis-unmeasured">not measured for this source</span>'
    else:
        shown = _axis_value(axis)
        try:
            width = max(0, min(100, int(shown)))
        except ValueError:
            width = 0
        value = '<span class="aq-axis-value">{}</span>'.format(_text(shown))
        body = (
            '<div class="gn-bar" role="progressbar" aria-label="{name}" aria-valuemin="0" '
            'aria-valuemax="100" aria-valuenow="{value}">'
            '<span class="gn-bar-fill" style="width:{width}%"></span></div>'
        ).format(name=_text(name), value=_text(shown), width=width)
    return '<div{attrs}><div class="aq-axis-header">{label}{edge}{value}</div>{body}</div>'.format(
        attrs=attrs, label=label, edge=edge, value=value, body=body)


def _pillar_score(value):
    try:
        return str(int(round(float(value))))
    except (TypeError, ValueError):
        return ""


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
        '<div class="aq-pillar" data-pillar="{name}">'
        '<div class="aq-pillar-header">'
        '<span class="aq-pillar-name">{name}</span>'
        '<span class="aq-pillar-score">{score}</span>'
        '<span class="aq-pillar-scale">/100</span>'
        '</div><div class="aq-axes">{axes}</div>{note}</div>'
    ).format(
        name=_text(name), score=_text(_pillar_score(pillar.get("score"))), axes=axes,
        note=note)


_PILLARS_INFO = ("Breadth: how much machinery you move. Craft: how well. Efficiency: the "
                 "return on each intervention. Savvy: judgment.")


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
        '<div class="gn-section-head"><h2 id="aq-h">Agentic Quotient · 4 pillars</h2>'
        '{info}</div>'
        '<div class="aq-pillars">{pillars}</div>'
    ).format(info=info_button(_PILLARS_INFO), pillars=rendered)
