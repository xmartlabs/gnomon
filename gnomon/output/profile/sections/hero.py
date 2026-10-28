"""The local profile's diagnostic hero and share controls."""

import html
import json
from urllib.parse import quote

from gnomon.output.profile.ui import info_button
from gnomon.scoring.gstack import _evidence
from gnomon.scoring.trend import aq_delta


CSS = """
.hero-grid {
  display: flex;
  align-items: flex-end;
  gap: 40px;
  min-width: 0;
}
.hero-primary {
  flex: 1;
  min-width: 0;
  max-width: 560px;
}
.hero-period {
  margin: 0 0 16px;
  color: var(--text-tertiary);
  font: 500 12px/1.2 var(--font-figure);
  letter-spacing: .1em;
  text-transform: uppercase;
}
.hero-tier {
  margin: 0;
  color: var(--text-primary);
  font-size: 56px;
  font-weight: 600;
  line-height: 1.05;
  letter-spacing: -.02em;
}
.hero-sentence {
  margin: 20px 0 0;
  color: var(--text-secondary);
  font-size: 19px;
  font-style: italic;
  font-weight: 600;
  line-height: 1.35;
  text-wrap: pretty;
}
.hero-scores {
  display: flex;
  align-items: flex-end;
  gap: 32px;
  margin-left: auto;
  min-width: 0;
}
.hero-aq-block {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.hero-aq-line {
  display: flex;
  align-items: baseline;
  gap: 10px;
}
.hero-aq { color: var(--text-primary); }
.hero-aq-scale,
.hero-gstack-scale {
  color: var(--text-secondary);
  font: 400 13px/1.2 var(--font-figure);
}
.hero-gstack-scale {
  color: var(--text-tertiary);
  font-size: 11px;
  letter-spacing: 0;
}
.hero-delta,
#hero-delta.gn-empty {
  display: inline-flex;
  align-items: baseline;
  gap: 4px;
  color: var(--text-secondary);
  font: 500 16px/1.3 var(--font-figure);
  white-space: nowrap;
}
#hero-delta.gn-empty { color: var(--text-tertiary); }
#hero-delta.gn-empty::before { content: "\\2014"; }
.hero-delta[data-direction="up"] { color: var(--positive); }
.hero-delta[data-direction="down"] { color: var(--negative); }
.hero-delta[data-direction="flat"] { color: var(--text-secondary); }
.hero-delta-prev {
  color: var(--text-tertiary);
  font-weight: 400;
}
.hero-gstack {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
}
.hero-gstack-heading {
  display: flex;
  align-items: center;
  gap: 4px;
}
.hero-gstack-scores {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 24px;
}
.hero-gstack-score {
  display: grid;
  grid-template-columns: auto 1fr;
  align-items: baseline;
  column-gap: 2px;
  row-gap: 4px;
  min-width: 0;
  color: var(--text-primary);
}
.hero-gstack-label {
  grid-column: 1 / -1;
  color: var(--text-secondary);
  font: 400 13px/1.5 var(--font-ui);
  letter-spacing: 0;
  white-space: nowrap;
}
.hero-share {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 32px;
}
.hero-share-label { margin-right: 8px; }
.hero-share a,
.hero-share button {
  display: inline-flex;
  height: 32px;
  align-items: center;
  gap: 8px;
  padding: 0 12px;
  border: 1px solid var(--rule-strong);
  border-radius: 2px;
  background: var(--surface-raised);
  color: var(--text-primary);
  font: 500 13px/1 var(--font-ui);
  cursor: pointer;
}
.hero-share a:hover,
.hero-share button:hover {
  background: var(--surface-hover);
  color: var(--text-primary);
}
.hero-limited {
  display: grid;
  grid-template-columns: 160px minmax(0, 1fr);
  align-items: baseline;
  gap: 24px;
  margin-top: 40px;
  padding: 16px 0;
  border-top: 1px solid var(--rule-default);
  border-bottom: 1px solid var(--rule-default);
}
.hero-limited-badge {
  display: inline-flex;
  height: 22px;
  align-items: center;
  gap: 6px;
  justify-self: start;
  padding: 0 8px;
  border: 1px solid var(--warning);
  border-radius: 2px;
  color: var(--warning);
  font: 500 12px/1 var(--font-figure);
  white-space: nowrap;
}
.hero-limited p {
  margin: 0;
  color: var(--text-secondary);
  font-size: 15px;
  line-height: 1.5;
  text-wrap: pretty;
}
@media (max-width: 960px) {
  .hero-grid { flex-direction: column; align-items: stretch; gap: 40px; }
  .hero-scores { margin-left: 0; flex-wrap: wrap; }
}
@media (max-width: 560px) {
  .hero-tier { font-size: 40px; }
  .hero-scores { flex-direction: column; align-items: flex-start; }
  .hero-scores > .gn-vrule { display: none; }
  .hero-limited { grid-template-columns: 1fr; gap: 12px; }
}
"""


def _text(value):
    return html.escape(str(value), quote=True)


def _number(value, default="0"):
    """Format a score without exposing Python's implementation details in the DOM."""
    if value is None:
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number.is_integer():
        return str(int(number))
    return "{:.1f}".format(number)


def _score(scores, dimension):
    value = (scores or {}).get(dimension, 0)
    if isinstance(value, dict):
        value = value.get("value", value.get("score", 0))
    return _number(value)


def _aq(stats):
    return (stats or {}).get("agentic") or {}


def _evidence_level(stats):
    volume = dict((stats or {}).get("volume") or {})
    volume.setdefault("tool_calls_total", 0)
    safe_stats = dict(stats or {})
    safe_stats["volume"] = volume
    return _evidence(safe_stats)


def _delta_html(ctx):
    period = ctx.period
    if period.kind != "current_month":
        return ""
    delta = aq_delta(ctx.trend, period.month_key)
    if delta is None:
        return '<span id="hero-delta" class="gn-empty" data-delta="none">first month</span>'
    value = int(delta.get("value", 0))
    if value > 0:
        direction, glyph, signed = "up", "▲", "+{}".format(value)
    elif value < 0:
        direction, glyph, signed = "down", "▼", str(value)
    else:
        direction, glyph, signed = "flat", "=", "0"
    return ('<span id="hero-delta" class="hero-delta" data-delta="{value}" '
            'data-direction="{direction}"><span aria-hidden="true">{glyph}</span>'
            '<span>{signed}</span><span class="hero-delta-prev">vs {previous}</span></span>').format(
                value=_text(signed), direction=direction, glyph=glyph, signed=_text(signed),
                previous=_text(delta.get("prev_label", "previous month")))



_X_ICON = (
    '<svg viewBox="0 0 24 24" width="13" height="13" fill="currentColor" aria-hidden="true">'
    '<path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73'
    '-8.835L1.254 2.25H8.08l4.713 6.231 5.45-6.231Zm-1.161 17.52h1.833L7.084 4.126H5.117L17.083 '
    '19.77Z"></path></svg>'
)

_GSTACK_INFO = ("gstack scores how you build, 0 to 10. It is separate from the AQ, "
                "which scores how you operate agents.")


def _share_script(caption):
    # The caption is currently a constant, but escaping the script delimiter keeps this
    # renderer safe if the brand copy ever becomes configurable.
    encoded = json.dumps(caption, ensure_ascii=False).replace("<", "\\u003c")
    return """<script>
(function () {
  var caption = __CAPTION__;
  var x = document.getElementById("share-x");
  if (x) x.href = "https://x.com/intent/tweet?text=" + encodeURIComponent(caption);
  var copy = document.getElementById("share-copy");
  if (!copy) return;
  function copied() {
    var original = copy.textContent;
    copy.textContent = "✓ Copied";
    window.setTimeout(function () { copy.textContent = original; }, 1500);
  }
  function fallback() {
    var area = document.createElement("textarea");
    area.value = caption;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    try { document.execCommand("copy"); } catch (error) {}
    document.body.removeChild(area);
    copied();
  }
  copy.addEventListener("click", function () {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(caption).then(copied).catch(fallback);
    } else {
      fallback();
    }
  });
})();
</script>""".replace("__CAPTION__", encoded)


def render(ctx) -> str:
    """Render the AQ headline, gstack read, and local share controls."""
    stats = getattr(ctx, "stats", None) or {}
    aq = _aq(stats)
    period = ctx.period
    days = "" if period.days_elapsed is None else period.days_elapsed
    tier = aq.get("tier") or getattr(ctx, "archetype", "") or "Novice"
    caption = getattr(ctx, "caption", "") or ""
    limited = ""
    if _evidence_level(stats) < 0.5:
        volume = stats.get("volume") or {}
        limited = (
            '<div id="hero-limited" class="hero-limited" role="note">'
            '<span class="hero-limited-badge"><span aria-hidden="true">!</span>Limited data</span>'
            '<p>Just {sessions:,} sessions and {calls:,} tool calls here — not enough to read '
            'your habits with confidence, so these scores lean toward the middle. '
            'Run more and check back.</p></div>'
        ).format(sessions=int(volume.get("total_sessions") or 0),
                 calls=int(volume.get("tool_calls_total") or 0))

    dimensions = ("Execution", "Planning", "Engineering")
    gstack = "".join(
        '<span class="gn-fig-sm hero-gstack-score" data-dimension="{name}" '
        'aria-label="{name} score">{score}'
        '<span class="hero-gstack-scale">/10</span>'
        '<span class="hero-gstack-label">{name}</span>'
        '</span>'.format(name=_text(name), score=_text(_score(ctx.scores, name)))
        for name in dimensions
    )
    caption_attr = _text(caption)
    share = (
        '<div class="hero-share" data-caption="{caption}">'
        '<span class="gn-label hero-share-label">Share</span>'
        '<a id="share-x" href="https://x.com/intent/tweet?text={encoded}" '
        'target="_blank" rel="noopener">{x_icon}Post on X</a>'
        '<button id="share-copy" type="button">Copy caption</button>'
        '<button id="share-img" type="button">Download image</button>'
        '</div>'
    ).format(caption=caption_attr, encoded=quote(caption, safe=""), x_icon=_X_ICON)
    sentence = getattr(ctx, "quote", "") or ""
    sentence_html = (
        '<p id="hero-sentence" class="hero-sentence">\u201c{}\u201d</p>'.format(_text(sentence))
        if sentence else '<p id="hero-sentence" class="hero-sentence" hidden></p>')
    return (
        '<div class="hero-grid">'
        '<div class="hero-primary">'
        '<p id="hero-period" class="hero-period" data-period-kind="{kind}" '
        'data-days-elapsed="{days}">{period}</p>'
        '<h1 id="hero-tier" class="hero-tier">You\'re {tier}.</h1>'
        '{sentence}'
        '</div>'
        '<div class="hero-scores">'
        '<div class="hero-aq-block">'
        '<span class="gn-label">AQ</span>'
        '<div class="hero-aq-line">'
        '<span id="hero-aq" class="gn-fig-xl">{aq}</span>'
        '<span class="hero-aq-scale">/100</span>'
        '</div>{delta}'
        '</div>'
        '<div class="gn-vrule" aria-hidden="true"></div>'
        '<div id="hero-gstack" class="hero-gstack">'
        '<div class="hero-gstack-heading"><span class="gn-label">gstack · how you build</span>'
        '{info}</div>'
        '<div class="hero-gstack-scores">{gstack}</div>'
        '</div>'
        '</div>'
        '</div>{share}{limited}{script}'
    ).format(
        kind=_text(period.kind), days=_text(days), period=_text(period.label),
        tier=_text(tier),
        aq=_text(_number(aq.get("aq_0_100"))), delta=_delta_html(ctx),
        sentence=sentence_html, limited=limited, gstack=gstack,
        info=info_button(_GSTACK_INFO), share=share, script=_share_script(caption))
