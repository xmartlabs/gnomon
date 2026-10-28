"""Data and browser code for the shareable local-profile poster."""

from typing import Dict, List, Optional

from gnomon.scoring.trend import aq_delta


# The poster is deliberately independent of the page theme. These are the v2 light
# tokens in their canvas-friendly form; one payload keeps the JS palette consistent.
_LIGHT_PALETTE = {
    "page": "#FFFFFF",
    "text": "#141616",
    "secondary": "#6A6E6E",
    "tertiary": "#6E7272",
    "rule_strong": "#141616",
    "rule": "#D5D7D7",
    "rule_subtle": "#E9EAEA",
    "accent": "#1F60B0",
    "mark": "#2A78D6",
    "mark_shadow": "#9EC2EF",
    "positive": "#15734A",
    "negative": "#A23B2A",
    "chart": "#2A78D6",
    "track": "#E9EAEA",
}


def _rounded(value, default=0):
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return default


def _poster_period(ctx) -> str:
    period = getattr(ctx, "period", None)
    label = getattr(period, "label", "All history") or "All history"
    if getattr(period, "kind", None) == "current_month":
        # The page label includes elapsed days; the poster header has room for the
        # month and state, but not the redundant day count.
        return " · ".join(label.split(" · ")[:2])
    return label


def _delta(ctx) -> Optional[dict]:
    period = getattr(ctx, "period", None)
    if getattr(period, "kind", None) != "current_month":
        return None
    change = aq_delta(getattr(ctx, "trend", None), getattr(period, "month_key", None))
    if not change:
        return None
    return {
        "value": change.get("value", 0),
        "label": "vs {}".format(change.get("prev_label", "previous month")),
    }


def _pillars(ctx) -> List[dict]:
    stats = getattr(ctx, "stats", None) or {}
    aq = stats.get("agentic") or {}
    return [
        {"name": pillar.get("name", ""), "score": _rounded(pillar.get("score"))}
        for pillar in (aq.get("pillars") or [])[:4]
    ]


def _moves(ctx) -> List[dict]:
    return [
        {"tag": move.get("tag", ""), "title": move.get("title", "")}
        for move in (getattr(ctx, "moves", None) or [])[:3]
    ]


def _quote(ctx) -> Optional[dict]:
    voice = getattr(ctx, "voice", None) or {}
    cryptics = voice.get("cryptics") or []
    if not cryptics:
        return None
    return {"live": "cuff", "text": str(cryptics[0])}


def poster_data(ctx) -> Dict[str, object]:
    """Return the JSON-safe, light-theme data consumed by ``POSTER_JS``."""
    stats = getattr(ctx, "stats", None) or {}
    aq = stats.get("agentic") or {}
    delta = _delta(ctx)
    period = getattr(ctx, "period", None)
    is_current_month = getattr(period, "kind", None) == "current_month"
    return {
        "theme": "light",
        "period": _poster_period(ctx),
        "tier": aq.get("tier", "Novice"),
        "aq": _rounded(aq.get("aq_0_100")),
        "delta": delta,
        "delta_empty": "first month" if is_current_month and delta is None else None,
        "pillars": _pillars(ctx),
        "moves": _moves(ctx),
        "quote": _quote(ctx),
        "palette": dict(_LIGHT_PALETTE),
        "fonts": {"ui": "Archivo", "mono": "IBM Plex Mono"},
        "repo": "github.com/xmartlabs/gnomon",
    }


POSTER_JS = r'''<script>
(function () {
  var WIDTH = 1200;
  var HEIGHT = 1320;
  var button = document.getElementById("share-img");
  if (!button) return;

  function readyForFonts() {
    if (!document.fonts || typeof document.fonts.load !== "function") {
      return Promise.resolve();
    }
    return Promise.all([
      document.fonts.load("600 1em Archivo"),
      document.fonts.load("italic 600 1em Archivo"),
      document.fonts.load("400 1em IBM Plex Mono"),
      document.fonts.load("500 1em IBM Plex Mono")
    ]);
  }

  // Text helpers. Tracking uses the canvas letterSpacing property where the browser has
  // it and falls back to drawing glyph by glyph, so labels keep the v2 0.1em tracking.
  function setFont(ctx, font, tracking) {
    ctx.font = font;
    ctx.__tracking = tracking || 0;
    if ("letterSpacing" in ctx) ctx.letterSpacing = (tracking || 0) + "px";
  }

  function textWidth(ctx, text) {
    var tracking = ctx.__tracking || 0;
    if ("letterSpacing" in ctx || !tracking) return ctx.measureText(text).width;
    return ctx.measureText(text).width + tracking * Math.max(0, text.length - 1);
  }

  function drawText(ctx, text, x, y, align) {
    text = String(text || "");
    var width = textWidth(ctx, text);
    var left = align === "right" ? x - width : x;
    var tracking = ctx.__tracking || 0;
    ctx.textAlign = "left";
    if ("letterSpacing" in ctx || !tracking) {
      ctx.fillText(text, left, y);
    } else {
      for (var i = 0; i < text.length; i += 1) {
        ctx.fillText(text[i], left, y);
        left += ctx.measureText(text[i]).width + tracking;
      }
    }
    return width;
  }

  function wrap(ctx, value, maxWidth) {
    var words = String(value || "").split(/\s+/);
    var lines = [];
    var line = "";
    var pieces = [];
    words.forEach(function (word) {
      // A single token wider than the column (a URL, a path) is split by characters.
      while (word && textWidth(ctx, word) > maxWidth) {
        var cut = word.length - 1;
        while (cut > 1 && textWidth(ctx, word.slice(0, cut)) > maxWidth) cut -= 1;
        pieces.push(word.slice(0, cut));
        word = word.slice(cut);
      }
      pieces.push(word);
    });
    pieces.forEach(function (word) {
      if (!word) return;
      var next = line ? line + " " + word : word;
      if (line && textWidth(ctx, next) > maxWidth) {
        lines.push(line);
        line = word;
      } else {
        line = next;
      }
    });
    if (line) lines.push(line);
    return lines.length ? lines : [""];
  }

  function rule(ctx, color, x, y, width, height) {
    ctx.fillStyle = color;
    ctx.fillRect(x, y, width, height || 1);
  }

  function liveQuote() {
    var element = document.getElementById("q-cuff");
    var visible = element && element.textContent ? element.textContent.trim() : "";
    if (visible) return visible.replace(/^[“\"]|[”\"]$/g, "");
    return CARD.quote ? CARD.quote.text : "";
  }

  // Geometry follows the hi-fi Poster artboard: 1200x1320, 72px top/bottom and 80px
  // side padding, header / hero / pillars / moves+quote / footer.
  function drawPoster(quote) {
    var canvas = document.createElement("canvas");
    var scale = 3;
    var maxArea = 16777216;
    while (WIDTH * HEIGHT * scale * scale > maxArea && scale > 1) scale -= 1;
    canvas.width = WIDTH * scale;
    canvas.height = HEIGHT * scale;
    canvas.style.width = WIDTH + "px";
    canvas.style.height = HEIGHT + "px";
    var ctx = canvas.getContext("2d");
    ctx.scale(scale, scale);

    // P is the fixed light palette; page styles are not consulted here.
    var P = CARD.palette;
    var UI = '"' + CARD.fonts.ui + '", "Helvetica Neue", Helvetica, Arial, sans-serif';
    var MONO = '"' + CARD.fonts.mono + '", ui-monospace, Menlo, monospace';
    var LEFT = 80;
    var RIGHT = WIDTH - 80;
    var INNER = RIGHT - LEFT;
    ctx.fillStyle = P.page;
    ctx.fillRect(0, 0, WIDTH, HEIGHT);
    ctx.textBaseline = "alphabetic";

    // Header: the gnomon mark (64-unit glyph drawn at 36px), wordmark, period label.
    var k = 36 / 64;
    ctx.fillStyle = P.mark_shadow;
    ctx.beginPath();
    ctx.moveTo(LEFT + 32 * k, 72 + 8 * k);
    ctx.lineTo(LEFT + 32 * k, 72 + 52 * k);
    ctx.lineTo(LEFT + 8 * k, 72 + 52 * k);
    ctx.closePath();
    ctx.fill();
    ctx.fillStyle = P.mark;
    ctx.beginPath();
    ctx.moveTo(LEFT + 32 * k, 72 + 8 * k);
    ctx.lineTo(LEFT + 44 * k, 72 + 52 * k);
    ctx.lineTo(LEFT + 32 * k, 72 + 52 * k);
    ctx.closePath();
    ctx.fill();
    ctx.fillStyle = P.text;
    setFont(ctx, "600 32px " + UI, -0.96);
    drawText(ctx, "gnomon", 128, 101);
    ctx.fillStyle = P.tertiary;
    setFont(ctx, "500 15px " + MONO, 1.5);
    drawText(ctx, ("Local profile · " + CARD.period).toUpperCase(), RIGHT, 96, "right");
    rule(ctx, P.rule_strong, LEFT, 128, INNER, 1);

    // Hero: tier on the left, AQ and delta bottom-aligned on the right.
    var heroBottom = 368;
    var aqBaseline = heroBottom - 51;
    var change = CARD.delta ? Number(CARD.delta.value || 0) : null;
    var blockWidth = 0;
    if (change !== null || CARD.delta_empty) {
      var parts;
      if (change !== null) {
        var glyph = change > 0 ? "▲" : (change < 0 ? "▼" : "=");
        var signed = change > 0 ? "+" + change : String(change);
        var tone = change > 0 ? P.positive : (change < 0 ? P.negative : P.secondary);
        parts = [[glyph, "500", tone], [signed, "500", tone], [CARD.delta.label, "400", P.tertiary]];
      } else {
        parts = [["—", "500", P.tertiary], [CARD.delta_empty, "500", P.tertiary]];
      }
      var x = RIGHT;
      for (var i = parts.length - 1; i >= 0; i -= 1) {
        ctx.fillStyle = parts[i][2];
        setFont(ctx, parts[i][1] + " 22px " + MONO, 0);
        x -= drawText(ctx, parts[i][0], x, heroBottom - 7, "right");
        if (i) x -= 6;
      }
      blockWidth = RIGHT - x;
    } else {
      aqBaseline = heroBottom - 10;
    }
    ctx.fillStyle = P.secondary;
    setFont(ctx, "400 20px " + MONO, 0);
    var scaleWidth = drawText(ctx, "/100 AQ", RIGHT, aqBaseline, "right");
    ctx.fillStyle = P.text;
    setFont(ctx, "500 152px " + MONO, -4.56);
    var aqWidth = drawText(ctx, String(CARD.aq), RIGHT - scaleWidth - 12, aqBaseline, "right");
    blockWidth = Math.max(blockWidth, aqWidth + 12 + scaleWidth);

    var tier = "You're " + CARD.tier + ".";
    var room = INNER - blockWidth - 48;
    var size = 80;
    setFont(ctx, "600 " + size + "px " + UI, -0.025 * size);
    while (size > 56 && textWidth(ctx, tier) > room) {
      size -= 4;
      setFont(ctx, "600 " + size + "px " + UI, -0.025 * size);
    }
    var tierLines = wrap(ctx, tier, room);
    ctx.fillStyle = P.text;
    tierLines.forEach(function (line, index) {
      var fromBottom = tierLines.length - 1 - index;
      drawText(ctx, line, LEFT, heroBottom - Math.round(size * 0.166) - fromBottom * size);
    });

    // Pillars: four equal columns, 2px top rule, name and score on one baseline, 10px bar.
    var pillarTop = heroBottom + 64;
    var columnWidth = (INNER - 3 * 40) / 4;
    (CARD.pillars || []).forEach(function (pillar, index) {
      var px = LEFT + index * (columnWidth + 40);
      var score = Math.max(0, Math.min(100, Number(pillar.score || 0)));
      rule(ctx, P.rule_strong, px, pillarTop, columnWidth, 2);
      ctx.fillStyle = P.text;
      setFont(ctx, "600 22px " + UI, 0);
      drawText(ctx, pillar.name, px, pillarTop + 48);
      setFont(ctx, "500 40px " + MONO, -1);
      drawText(ctx, String(pillar.score), px + columnWidth, pillarTop + 48, "right");
      rule(ctx, P.track, px, pillarTop + 67, columnWidth, 10);
      rule(ctx, P.chart, px, pillarTop + 67, columnWidth * score / 100, 10);
    });

    // How you work | Off the cuff, on a 1.35fr auto 1fr grid with 48px gaps.
    var lowerTop = pillarTop + 77 + 72;
    var leftWidth = (INNER - 96 - 1) * 1.35 / 2.35;
    var ruleX = LEFT + leftWidth + 48;
    var rightX = ruleX + 1 + 48;
    var rightWidth = RIGHT - rightX;
    var listTop = lowerTop + 26;
    function eyebrow(text, x) {
      ctx.fillStyle = P.secondary;
      setFont(ctx, "500 14px " + MONO, 1.4);
      drawText(ctx, text.toUpperCase(), x, lowerTop + 14);
    }

    eyebrow("How you work", LEFT);
    var y = listTop;
    var moves = (CARD.moves || []).slice(0, 3);
    if (!moves.length) {
      rule(ctx, P.rule_subtle, LEFT, y, leftWidth, 1);
      ctx.fillStyle = P.tertiary;
      setFont(ctx, "400 20px " + UI, 0);
      drawText(ctx, "No signature moves this month", LEFT, y + 42);
      y += 1 + 18 + 30 + 18;
    }
    moves.forEach(function (move) {
      rule(ctx, P.rule_subtle, LEFT, y, leftWidth, 1);
      ctx.fillStyle = P.tertiary;
      setFont(ctx, "500 13px " + MONO, 1.3);
      var tagLines = wrap(ctx, String(move.tag || "").toUpperCase(), 150);
      tagLines.forEach(function (line, index) {
        drawText(ctx, line, LEFT, y + 42 + index * 17);
      });
      ctx.fillStyle = P.text;
      setFont(ctx, "600 24px " + UI, 0);
      var titleLines = wrap(ctx, move.title || "", leftWidth - 166).slice(0, 2);
      titleLines.forEach(function (line, index) {
        drawText(ctx, line, LEFT + 166, y + 42 + index * 30);
      });
      y += 1 + 18 + 30 * titleLines.length + 18;
    });
    var leftBottom = y;

    eyebrow("Off the cuff", rightX);
    rule(ctx, P.rule_subtle, rightX, listTop, rightWidth, 1);
    var rightBottom;
    if (quote) {
      ctx.fillStyle = P.text;
      setFont(ctx, "italic 600 32px " + UI, 0);
      var quoteLines = wrap(ctx, "“" + quote + "”", rightWidth).slice(0, 6);
      quoteLines.forEach(function (line, index) {
        drawText(ctx, line, rightX, listTop + 50 + index * 41.6);
      });
      rightBottom = listTop + 19 + quoteLines.length * 41.6;
    } else {
      ctx.fillStyle = P.tertiary;
      setFont(ctx, "400 20px " + UI, 0);
      drawText(ctx, "No off-the-cuff line this month", rightX, listTop + 42);
      rightBottom = listTop + 19 + 30;
    }
    rule(ctx, P.rule, ruleX, lowerTop, 1, Math.max(leftBottom, rightBottom) - lowerTop);

    // Footer: lock, privacy line, repository.
    var footerTop = HEIGHT - 72 - 44;
    rule(ctx, P.rule, LEFT, footerTop, INNER, 1);
    ctx.strokeStyle = P.secondary;
    ctx.lineWidth = 1.125;
    ctx.lineCap = "round";
    ctx.beginPath();
    ctx.rect(LEFT + 3.75, footerTop + 32.25, 10.5, 7.5);
    ctx.moveTo(LEFT + 6, footerTop + 32.25);
    ctx.lineTo(LEFT + 6, footerTop + 29.25);
    ctx.arc(LEFT + 9, footerTop + 29.25, 3, Math.PI, 0);
    ctx.lineTo(LEFT + 12, footerTop + 32.25);
    ctx.stroke();
    ctx.fillStyle = P.secondary;
    setFont(ctx, "500 14px " + MONO, 1.4);
    drawText(ctx, "GENERATED ON THIS MACHINE · NOTHING UPLOADED", LEFT + 30, footerTop + 38);
    ctx.fillStyle = P.accent;
    setFont(ctx, "500 18px " + MONO, 0);
    drawText(ctx, CARD.repo, RIGHT, footerTop + 39, "right");
    return canvas;
  }

  function showError() {
    if (typeof alert === "function") alert("Could not create the profile image. Please try again.");
  }

  function downloadCanvas(canvas) {
    try {
      if (typeof canvas.toBlob === "function") {
        canvas.toBlob(function (blob) {
          if (!blob || typeof URL === "undefined" || !URL.createObjectURL) {
            showError();
            return;
          }
          var link = document.createElement("a");
          link.download = "gnomon-profile.png";
          link.href = URL.createObjectURL(blob);
          link.click();
          if (URL.revokeObjectURL) setTimeout(function () { URL.revokeObjectURL(link.href); }, 0);
        }, "image/png");
      } else {
        // Older iOS Safari has no toBlob; the data URL path is the compatible fallback.
        var fallback = document.createElement("a");
        fallback.download = "gnomon-profile.png";
        fallback.href = canvas.toDataURL("image/png");
        fallback.click();
      }
    } catch (error) {
      showError();
    }
  }

  button.addEventListener("click", function () {
    var quote = liveQuote();
    readyForFonts().then(function () {
      downloadCanvas(drawPoster(quote));
    }).catch(showError);
  });
}());
</script>'''
