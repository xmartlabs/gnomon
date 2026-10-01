"""The local profile's verbatim prompt quotes."""

import html

from gnomon.scoring.gstack import _js


CSS = """\
.quotes-column {
  grid-column: 3;
  grid-row: 2;
  min-width: 0;
}
.quotes-column h3 {
  margin: 0 0 6px;
  color: var(--text-tertiary);
  font: 500 11px/1.2 var(--font-figure);
  letter-spacing: 0.1em;
  text-transform: uppercase;
}
.quotes-hint {
  margin: 0 0 16px;
  color: var(--text-tertiary);
  font-size: 13px;
  line-height: 1.5;
  text-wrap: pretty;
}
.quote-card {
  min-width: 0;
  padding: 16px 0 20px;
  border-top: 1px solid var(--rule-subtle);
}
.quote-head {
  display: flex;
  min-height: 24px;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.quote-label {
  margin: 0;
  color: var(--text-tertiary);
  font: 500 11px/1.2 var(--font-figure);
  letter-spacing: 0.1em;
  text-transform: uppercase;
}
.quote-text {
  min-width: 0;
  margin: 0;
  overflow-wrap: anywhere;
  color: var(--text-primary);
  font-size: 19px;
  font-style: italic;
  font-weight: 600;
  line-height: 1.35;
  text-wrap: pretty;
}
.quote-detail {
  margin: 6px 0 0;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.5;
  text-wrap: pretty;
}
.quote-card .gn-empty {
  margin: 0;
  color: var(--text-secondary);
  font-size: 15px;
  line-height: 1.5;
  text-wrap: pretty;
}
.quote-card .gn-empty::before {
  content: "\\2014\\00a0";
  color: var(--text-tertiary);
  font-family: var(--font-mono);
}
.reroll {
  height: 24px;
  margin-left: auto;
  padding: 0 8px;
  border: 1px solid var(--rule-default);
  border-radius: 2px;
  background: transparent;
  color: var(--accent);
  font: 400 11px/1 var(--font-figure);
  cursor: pointer;
}
.reroll:hover {
  background: var(--surface-hover);
}
@media (max-width: 760px) {
  .quotes-column { grid-column: 1; grid-row: auto; margin-top: 32px; }
}
"""


def _prompts(ctx):
    stats = getattr(ctx, "stats", {}) or {}
    volume = stats.get("volume", {}) or {}
    return volume.get("total_prompts", 0) or 0


def _pool(value):
    """Return a safe, deterministic list for a quote pool."""
    if not value:
        return []
    return [quote for quote in value if isinstance(quote, str) and quote]


def _empty(target, prompts):
    messages = {
        "goto": "No go-to prompt this month — nothing you typed repeated 3+ times "
                 "across 2+ sessions.",
        "crashout": "No crash-out this month — none of your {:,} prompts read as heated. "
                    "It shows up once one does.",
        "cuff": "No off-the-cuff line this month — none of your {:,} prompts made it "
                "through the secrets/PII filter as a short, unfiltered ask.",
    }
    message = messages[target]
    return message.format(prompts) if target != "goto" else message


def _quote_card(label, target, quote, pool, empty_text, detail=None, quote_js=None):
    """Render one quote card, keeping transcript text out of raw HTML and JS."""
    if pool is not None and quote_js is not None:
        quote_js[target] = list(pool)

    if quote:
        reroll = (
            '<button type="button" class="reroll" data-target="{0}" '
            'aria-label="Show another {1} quote">&#8635; another</button>'.format(
                target, {"crashout": "crash-out", "cuff": "off-the-cuff"}.get(target, target))
            if len(pool) > 1 else ""
        )
        body = (
            '<p class="quote-text" id="q-{0}">&ldquo;{1}&rdquo;</p>'
            '<p class="quote-detail">{2}</p>'.format(
                target, html.escape(quote), detail or "")
        )
    else:
        reroll = ""
        body = '<p class="gn-empty">{}</p>'.format(html.escape(empty_text))

    return (
        '<div class="quote-card" data-quote="{target}">'
        '<div class="quote-head"><p class="quote-label">{label}</p>{reroll}</div>'
        '{body}</div>'.format(
            target=target, label=label, reroll=reroll, body=body)
    )


def _source_phrase(ctx):
    period = getattr(ctx, "period", None)
    kind = getattr(period, "kind", None)
    if kind == "current_month" or getattr(period, "month_key", None):
        return "this month's prompts"
    if kind == "custom":
        return "this window's prompts"
    return "your prompts"


def _goto_data(value):
    if not value or len(value) != 3:
        return None
    text, count, sessions = value
    if not isinstance(text, str) or not text:
        return None
    return text, count, sessions


def render(ctx) -> str:
    """Render all three quote cards and the client-side reroll behavior."""
    voice = getattr(ctx, "voice", None) or {}
    prompts = _prompts(ctx)
    goto = _goto_data(voice.get("goto"))
    crashouts = _pool(voice.get("crashouts"))
    cryptics = _pool(voice.get("cryptics"))
    quote_js = {}

    if goto:
        goto_text, count, sessions = goto
        goto_detail = "Your most-repeated prompt — {:,} times across {} sessions.".format(
            count, sessions)
    else:
        goto_text = None
        goto_detail = None

    # Keep every displayed quote in the JSON payload as well.  The go-to prompt has no
    # reroll control, but using the same escaped payload prevents a transcript quote from
    # ever becoming executable script if the card contract grows later.
    quote_js["goto"] = [goto_text] if goto_text else []

    cards = [
        _quote_card(
            "What's your go-to prompt?", "goto", goto_text,
            [goto_text] if goto_text else [],
            _empty("goto", prompts), goto_detail, quote_js),
        _quote_card(
            "Your biggest crash-out?", "crashout", crashouts[0] if crashouts else None,
            crashouts, _empty("crashout", prompts),
            "One of your most heated prompts. We&rsquo;ve all been there.", quote_js),
        _quote_card(
            "Off the cuff?", "cuff", cryptics[0] if cryptics else None,
            cryptics, _empty("cuff", prompts),
            "One of your more unfiltered asks — straight from the keyboard, unedited.",
            quote_js),
    ]

    script = """<script>
(function () {
  var QUOTES = %s;
  var QIDX = {};
  document.querySelectorAll(".reroll").forEach(function (button) {
    button.addEventListener("click", function () {
      var target = button.getAttribute("data-target");
      var pool = QUOTES[target];
      if (!pool || pool.length < 2) return;
      QIDX[target] = ((QIDX[target] || 0) + 1) %% pool.length;
      var quote = document.getElementById("q-" + target);
      if (quote) quote.textContent = "\\u201c" + pool[QIDX[target]] + "\\u201d";
    });
  });
}());
</script>""" % _js(quote_js)

    return (
        '<div class="quotes-column">'
        '<h3>In your own words</h3>'
        '<p class="quotes-hint">Verbatim from {}, filtered for secrets and PII. '
        'The off-the-cuff line goes on the shared image — reroll until you like it.</p>'
        '{}'
        '</div>{}'.format(_source_phrase(ctx), "".join(cards), script)
    )
