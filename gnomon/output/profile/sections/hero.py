"""The local profile's diagnostic hero and share controls."""

import html
import json
from urllib.parse import quote

from gnomon.scoring.gstack import _evidence
from gnomon.scoring.trend import aq_delta


CSS = """
#hero {
  padding: 64px 0 48px;
  border-bottom: 1px solid var(--rule-default);
}
.hero-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(240px, .8fr);
  gap: 48px;
  min-width: 0;
}
.hero-primary,
.hero-secondary,
.hero-gstack,
.hero-gstack-score {
  min-width: 0;
}
.hero-period {
  margin: 0 0 20px;
  color: var(--text-secondary);
  font-size: 13px;
}
.hero-tier {
  max-width: 12em;
  margin: 0;
  color: var(--text-primary);
  font-size: clamp(36px, 5vw, 56px);
  line-height: 1.02;
  letter-spacing: -.025em;
}
.hero-score-label {
  margin: 36px 0 8px;
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: .1em;
  text-transform: uppercase;
}
.hero-aq-line {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 20px;
  min-width: 0;
}
.hero-aq {
  color: var(--text-primary);
}
.hero-delta {
  color: var(--text-secondary);
  font: 500 14px/1.3 var(--font-figure);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.hero-delta[data-direction="up"] { color: var(--positive); }
.hero-delta[data-direction="down"] { color: var(--negative); }
.hero-delta[data-direction="flat"] { color: var(--text-secondary); }
.hero-sentence {
  max-width: 42em;
  margin: 24px 0 0;
  color: var(--text-secondary);
  font-size: 17px;
  line-height: 1.5;
}
.hero-secondary {
  align-self: end;
}
.hero-gstack {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--rule-strong);
}
.hero-gstack-heading {
  grid-column: 1 / -1;
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 20px;
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: .1em;
  text-transform: uppercase;
}
.hero-gstack-info {
  display: inline-grid;
  width: 16px;
  height: 16px;
  place-items: center;
  border: 1px solid var(--rule-default);
  border-radius: 50%;
  color: var(--text-tertiary);
  font: 500 11px/1 var(--font-figure);
  letter-spacing: 0;
  cursor: help;
}
.hero-gstack-score {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.hero-gstack-score .gn-fig-sm {
  color: var(--text-primary);
}
.hero-gstack-label {
  color: var(--text-secondary);
  font-size: 12px;
  overflow-wrap: anywhere;
}
.hero-limited {
  margin: 24px 0 0;
  color: var(--text-tertiary);
  font-size: 13px;
}
.hero-limited strong {
  color: var(--text-secondary);
  font-weight: 600;
}
.hero-share {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 40px;
  padding-top: 20px;
  border-top: 1px solid var(--rule-subtle);
}
.hero-share-label {
  margin-right: 4px;
  color: var(--text-tertiary);
  font-size: 13px;
}
.hero-share a,
.hero-share button {
  display: inline-flex;
  min-height: 34px;
  align-items: center;
  justify-content: center;
  padding: 7px 12px;
  border: 1px solid var(--rule-default);
  border-radius: 2px;
  background: var(--surface-page);
  color: var(--text-primary);
  font: 500 13px/1.2 var(--font-ui);
  cursor: pointer;
}
.hero-share a:hover,
.hero-share button:hover {
  border-color: var(--accent);
  color: var(--accent);
  text-decoration: none;
}
@media (max-width: 760px) {
  .hero-grid { grid-template-columns: 1fr; gap: 40px; }
  .hero-secondary { align-self: auto; }
}
@media (max-width: 420px) {
  .hero-gstack { grid-template-columns: 1fr; gap: 20px; }
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
            'data-direction="{direction}">{glyph} {signed} vs {previous}</span>').format(
                value=_text(signed), direction=direction, glyph=glyph, signed=_text(signed),
                previous=_text(delta.get("prev_label", "previous month")))


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
        limited = ('<p id="hero-limited" class="hero-limited"><strong>Limited data.</strong> '
                   'The read is directional until there is enough activity to judge habits.</p>')

    dimensions = ("Execution", "Planning", "Engineering")
    gstack = "".join(
        '<span class="gn-fig-sm hero-gstack-score" data-dimension="{name}" '
        'aria-label="{name} score">{score}'
        '<span class="hero-gstack-label">{name}</span>'
        '</span>'.format(name=_text(name), score=_text(_score(ctx.scores, name)))
        for name in dimensions
    )
    caption_attr = _text(caption)
    share = (
        '<div class="hero-share" data-caption="{caption}">'
        '<span class="hero-share-label">Share</span>'
        '<a id="share-x" href="https://x.com/intent/tweet?text={encoded}" '
        'target="_blank" rel="noopener">Post on X</a>'
        '<button id="share-copy" type="button">Copy caption</button>'
        '<button id="share-img" type="button">Download image</button>'
        '</div>'
    ).format(caption=caption_attr, encoded=quote(caption, safe=""))
    return (
        '<div class="hero-grid">'
        '<div class="hero-primary">'
        '<p id="hero-period" class="hero-period" data-period-kind="{kind}" '
        'data-days-elapsed="{days}">{period}</p>'
        '<h1 id="hero-tier" class="hero-tier">You\'re {tier}.</h1>'
        '<p class="hero-score-label">Agentic Quotient</p>'
        '<div class="hero-aq-line">'
        '<span id="hero-aq" class="gn-fig-xl">{aq}</span>{delta}'
        '</div>'
        '<p id="hero-sentence" class="hero-sentence">{sentence}</p>'
        '{limited}'
        '</div>'
        '<div class="hero-secondary">'
        '<div id="hero-gstack" class="hero-gstack">'
        '<p class="hero-gstack-heading">gstack <span class="hero-gstack-info" '
        'title="A 0–10 read on how you build, separate from AQ." aria-label="About gstack scores">i</span></p>'
        '{gstack}'
        '</div>'
        '</div>'
        '</div>{share}{script}'
    ).format(
        kind=_text(period.kind), days=_text(days), period=_text(period.label),
        tier=_text(tier), aq=_text(_number(aq.get("aq_0_100"))), delta=_delta_html(ctx),
        sentence=_text(getattr(ctx, "quote", "") or ""), limited=limited, gstack=gstack,
        share=share, script=_share_script(caption))
