"""The local profile's two-column diagnosis."""

import html
import re

from gnomon.output.profile.ui import info_button


CSS = """
.diagnosis-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1.25fr);
  align-items: start;
  gap: 40px;
  min-width: 0;
}
.diagnosis-column {
  min-width: 0;
}
.move {
  display: grid;
  grid-template-columns: 104px minmax(0, 1fr);
  gap: 16px;
  min-width: 0;
  padding: 16px 0;
  border-top: 1px solid var(--rule-subtle);
}
.edge {
  display: grid;
  grid-template-columns: 32px minmax(0, 1fr);
  gap: 12px;
  min-width: 0;
  padding: 16px 0;
  border-top: 1px solid var(--rule-subtle);
}
.move-tag {
  padding-top: 5px;
  overflow-wrap: anywhere;
}
.edge-number {
  padding-top: 1px;
  color: var(--accent);
  font: 500 13px/1.3 var(--font-figure);
}
.edge-origin {
  display: block;
  margin-bottom: 6px;
  color: var(--text-secondary);
}
.move-title,
.edge-title {
  margin: 0;
  color: var(--text-primary);
  font-size: 19px;
  font-weight: 600;
  line-height: 1.3;
  text-wrap: pretty;
}
.move-evidence,
.edge-advice {
  margin: 4px 0 0;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.5;
  text-wrap: pretty;
}
.edge-advice { margin-top: 6px; }
.move-evidence b,
.edge-advice b {
  color: inherit;
  font-weight: inherit;
}
.move-evidence code,
.edge-advice code {
  font-family: var(--font-mono);
  font-size: 0.92em;
}
.diagnosis-empty {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 16px 0;
  border-top: 1px solid var(--rule-subtle);
}
.diagnosis-empty .gn-empty {
  margin: 0;
  color: var(--text-secondary);
  font-size: 15px;
  line-height: 1.5;
  text-wrap: pretty;
}
@media (max-width: 760px) {
  .diagnosis-grid { grid-template-columns: 1fr; gap: 32px; }
  .diagnosis-grid > .gn-vrule { display: none; }
  .move { grid-template-columns: 1fr; gap: 6px; }
  .move-tag { padding-top: 0; }
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
        return ('<div class="diagnosis-empty">'
                '<span class="gn-label">— No moves this month</span>'
                f'<p class="gn-empty">{_text(_moves_empty(ctx))}</p></div>')
    items = []
    for move in ctx.moves[:3]:
        items.append(
            '<div class="move">'
            f'<span class="gn-label move-tag">{_text(move.get("tag", ""))}</span>'
            '<div>'
            f'<div class="move-title">{_text(move.get("title", ""))}</div>'
            f'<div class="move-evidence">{move.get("evidence_html", "")}</div>'
            '</div></div>'
        )
    return "".join(items)


def _render_edges(ctx):
    if not ctx.edges:
        return ('<div class="diagnosis-empty">'
                '<span class="gn-label">— Nothing flagged this month</span>'
                '<p class="gn-empty">Nothing flagged to work on this month — no AQ axis or '
                'gstack dimension fell below its threshold.</p></div>')
    items = []
    for edge in ctx.edges[:3]:
        axis = edge.get("axis") or ""
        items.append(
            f'<div class="edge" data-n="{_text(edge.get("n", ""))}" '
            f'data-axis="{_text(axis)}">'
            f'<span class="edge-number">{_text(edge.get("n", ""))}</span>'
            '<div>'
            f'<span class="gn-label edge-origin">{_text(_edge_origin(ctx, edge))}</span>'
            f'<div class="edge-title">{_text(edge.get("title", ""))}</div>'
            f'<div class="edge-advice">{_display_advice(edge)}</div>'
            '</div></div>'
        )
    return "".join(items)


_MOVES_INFO = ("Signature moves: patterns in how you direct agents, each detected by a gate "
               "on this month's numbers. Style, not a grade.")
_EDGES_INFO = ("Growth edges: up to three, most urgent first. Each one comes from an AQ axis "
               "(marked in the breakdown below) or from gstack.")


def render(ctx) -> str:
    return ('<div class="diagnosis-grid">'
            '<div id="how-you-work" class="diagnosis-column">'
            '<div class="gn-section-head"><h2 id="moves-h">How you work</h2>'
            f'{info_button(_MOVES_INFO)}</div>'
            '<p class="gn-section-hint">Patterns in how you direct agents. The tag is the '
            'gstack stage each one maps to.</p>'
            f'{_render_moves(ctx)}'
            '</div>'
            '<div class="gn-vrule" aria-hidden="true"></div>'
            '<div id="what-to-work-on" class="diagnosis-column">'
            '<div class="gn-section-head"><h2 id="edges-h">What to work on</h2>'
            f'{info_button(_EDGES_INFO)}</div>'
            '<p class="gn-section-hint">Most urgent first. The tag says where each one '
            'comes from.</p>'
            f'{_render_edges(ctx)}'
            '</div>'
            '</div>')
