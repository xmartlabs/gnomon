"""The local profile's two-column diagnosis."""

import html
import re


CSS = """
.diagnosis-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 40px;
  min-width: 0;
}
.diagnosis-column {
  min-width: 0;
  padding-top: 16px;
  border-top: 1px solid var(--rule-strong);
}
.diagnosis-column h3 {
  margin: 0 0 20px;
  color: var(--text-primary);
  font-size: 24px;
  line-height: 1.15;
  letter-spacing: -0.015em;
}
.move,
.edge {
  min-width: 0;
  padding: 16px 0;
  border-top: 1px solid var(--rule-subtle);
}
.move:first-of-type,
.edge:first-of-type {
  border-top: 0;
  padding-top: 0;
}
.move-tag,
.edge-origin {
  display: block;
  margin-bottom: 6px;
  color: var(--text-secondary);
  font: 500 11px/1.2 var(--font-figure);
  letter-spacing: 0.1em;
  text-transform: uppercase;
}
.move-title,
.edge-title {
  margin: 0;
  color: var(--text-primary);
  font-size: 17px;
  line-height: 1.3;
  font-weight: 600;
}
.move-evidence,
.edge-advice {
  margin: 8px 0 0;
  color: var(--text-secondary);
  font-size: 14px;
  line-height: 1.5;
}
.move-evidence b,
.edge-advice b {
  color: var(--text-primary);
  font-weight: 600;
}
.move-evidence code,
.edge-advice code {
  color: var(--text-primary);
  font-family: var(--font-mono);
  font-size: 0.92em;
}
.edge-number {
  float: right;
  color: var(--text-decorative);
  font: 500 11px/1.2 var(--font-figure);
}
.diagnosis-column > .gn-empty {
  margin: 0;
  max-width: 42em;
  font-size: 14px;
}
@media (max-width: 760px) {
  .diagnosis-grid { grid-template-columns: 1fr; gap: 32px; }
}
"""


def _text(value):
    return html.escape(str(value), quote=True)


def _axis_pillar(ctx, axis):
    for pillar in (ctx.stats.get("agentic") or {}).get("pillars", []):
        for item in pillar.get("axes", []):
            if item.get("name") == axis:
                return pillar.get("name", "AQ")
    return "AQ"


def _edge_origin(ctx, edge):
    axis = edge.get("axis")
    if axis:
        return f"{_axis_pillar(ctx, axis)} · {axis}"
    return f"gstack · {edge.get('dimension') or 'Balanced'}"


def _display_advice(edge):
    """Avoid repeating the AQ origin tag in the advice body."""
    advice = edge.get("advice_html", "")
    return re.sub(r"^<b>[^<]+</b> is your thinnest AQ signal\.\s*", "", advice, count=1)


def _moves_empty(ctx):
    volume = ctx.stats.get("volume") or {}
    sessions = volume.get("total_sessions", 0)
    prompts = volume.get("total_prompts", 0)
    return ("No signature moves fired this month — none of the 8 patterns passed its gate on "
            f"{sessions} sessions and {prompts} prompts. They show up once a habit repeats "
            "often enough to count.")


def _render_moves(ctx):
    if not ctx.moves:
        return f'<p class="gn-empty">{_text(_moves_empty(ctx))}</p>'
    items = []
    for move in ctx.moves[:3]:
        items.append(
            '<div class="move">'
            f'<span class="move-tag">{_text(move.get("tag", ""))}</span>'
            f'<div class="move-title">{_text(move.get("title", ""))}</div>'
            f'<div class="move-evidence">{move.get("evidence_html", "")}</div>'
            '</div>'
        )
    return "".join(items)


def _render_edges(ctx):
    if not ctx.edges:
        return ('<p class="gn-empty">Nothing flagged to work on this month — no AQ axis or '
                'gstack dimension fell below its threshold.</p>')
    items = []
    for edge in ctx.edges[:3]:
        axis = edge.get("axis") or ""
        items.append(
            f'<div class="edge" data-n="{_text(edge.get("n", ""))}" '
            f'data-axis="{_text(axis)}">'
            f'<span class="edge-number">{_text(edge.get("n", ""))}</span>'
            f'<span class="edge-origin">{_text(_edge_origin(ctx, edge))}</span>'
            f'<div class="edge-title">{_text(edge.get("title", ""))}</div>'
            f'<div class="edge-advice">{_display_advice(edge)}</div>'
            '</div>'
        )
    return "".join(items)


def render(ctx) -> str:
    return ('<div class="diagnosis-grid">'
            '<div id="how-you-work" class="diagnosis-column">'
            '<h3>How you work</h3>'
            f'{_render_moves(ctx)}'
            '</div>'
            '<div id="what-to-work-on" class="diagnosis-column">'
            '<h3>What to work on</h3>'
            f'{_render_edges(ctx)}'
            '</div>'
            '</div>')
