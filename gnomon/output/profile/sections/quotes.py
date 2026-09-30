"""The local profile's verbatim prompt quotes."""

import html

from gnomon.scoring.gstack import _js


CSS = """\
.quotes-column {
  margin-top: 40px;
  min-width: 0;
}
.quotes-column h3 {
  margin: 0;
  font-size: 24px;
  line-height: 1.15;
  letter-spacing: -0.015em;
}
.quotes-hint {
  max-width: 720px;
  margin: 8px 0 20px;
  color: var(--text-secondary);
}
.quote-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
  min-width: 0;
}
.quote-card {
  min-width: 0;
  padding: 20px;
  border: 1px solid var(--rule-default);
  background: var(--surface-raised);
}
.quote-label {
  margin: 0 0 12px;
  color: var(--text-secondary);
  font: 500 11px/1.2 var(--font-figure);
  letter-spacing: 0.1em;
  text-transform: uppercase;
}
.quote-text {
  min-width: 0;
  margin: 0 0 12px;
  overflow-wrap: anywhere;
  color: var(--text-primary);
  font-size: 18px;
  line-height: 1.4;
}
.quote-detail {
  margin: 0;
  color: var(--text-secondary);
  font-size: 13px;
}
.quote-card .gn-empty {
  margin: 0;
  font-size: 14px;
}
.reroll {
  margin-left: 8px;
  padding: 2px 7px;
  border: 1px solid var(--rule-default);
  background: var(--surface-raised);
  color: var(--text-accent);
  font: 500 11px/1.2 var(--font-ui);
  cursor: pointer;
}
.reroll:hover {
  background: var(--surface-hover);
}
@media (max-width: 760px) {
  .quote-grid {
    grid-template-columns: 1fr;
  }
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
            ' <button type="button" class="reroll" data-target="{}">'
            '&#8635; another</button>'.format(target)
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
        '<p class="quote-label">{label}{reroll}</p>{body}</div>'.format(
            target=target, label=label, reroll=reroll, body=body)
    )


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
        '<p class="quotes-hint">Pulled verbatim from your real prompts '
        '(filtered for secrets &amp; PII). Hit &#8635; another to reroll.</p>'
        '<div class="quote-grid">{}</div>'
        '</div>{}'.format("".join(cards), script)
    )
