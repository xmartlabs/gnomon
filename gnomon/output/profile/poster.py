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
      document.fonts.load("500 1em IBM Plex Mono")
    ]);
  }

  function textLines(value, limit) {
    var words = String(value || "").split(/\s+/);
    var lines = [];
    var line = "";
    words.forEach(function (word) {
      if (!word) return;
      if (line && (line.length + word.length + 1) > limit) {
        lines.push(line);
        line = word;
      } else {
        line = line ? line + " " + word : word;
      }
    });
    if (line) lines.push(line);
    return lines;
  }

  function writeLines(ctx, value, x, y, lineHeight, limit) {
    var lines = textLines(value, limit);
    lines.forEach(function (line, index) {
      ctx.fillText(line, x, y + index * lineHeight);
    });
    return y + Math.max(1, lines.length) * lineHeight;
  }

  function liveQuote() {
    var element = document.getElementById("q-cuff");
    var visible = element && element.textContent ? element.textContent.trim() : "";
    if (visible) return visible.replace(/^[\u201c\"]|[\u201d\"]$/g, "");
    return CARD.quote ? CARD.quote.text : "";
  }

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
    var UI = CARD.fonts.ui;
    var MONO = CARD.fonts.mono;
    ctx.fillStyle = P.page;
    ctx.fillRect(0, 0, WIDTH, HEIGHT);
    ctx.textBaseline = "alphabetic";

    // Header mark and identity.
    ctx.fillStyle = P.mark_shadow;
    ctx.beginPath();
    ctx.moveTo(72, 74);
    ctx.lineTo(92, 38);
    ctx.lineTo(112, 74);
    ctx.closePath();
    ctx.fill();
    ctx.fillStyle = P.mark;
    ctx.beginPath();
    ctx.moveTo(86, 74);
    ctx.lineTo(106, 38);
    ctx.lineTo(126, 74);
    ctx.closePath();
    ctx.fill();
    ctx.fillStyle = P.text;
    ctx.font = "600 30px " + UI;
    ctx.fillText("gnomon", 144, 68);
    ctx.fillStyle = P.secondary;
    ctx.font = "400 18px " + UI;
    ctx.fillText("Local profile · " + CARD.period, 72, 112);
    ctx.fillStyle = P.rule;
    ctx.fillRect(72, 144, 1056, 1);

    // AQ is the central signal; the poster intentionally has no competing metric.
    ctx.fillStyle = P.secondary;
    ctx.font = "500 18px " + MONO;
    ctx.fillText("YOUR LEVEL", 72, 204);
    ctx.fillStyle = P.text;
    ctx.font = "600 56px " + UI;
    ctx.fillText("You're " + CARD.tier + ".", 72, 270);
    ctx.fillStyle = P.accent;
    ctx.font = "500 120px " + MONO;
    ctx.fillText(String(CARD.aq), 72, 414);
    ctx.fillStyle = P.secondary;
    ctx.font = "400 18px " + UI;
    ctx.fillText("agentic quotient · 0–100", 80, 448);
    if (CARD.delta) {
      var change = Number(CARD.delta.value || 0);
      ctx.fillStyle = change > 0 ? P.positive : (change < 0 ? P.negative : P.secondary);
      ctx.font = "500 22px " + MONO;
      ctx.fillText((change > 0 ? "▲ +" : change < 0 ? "▼ " : "= ") + change + "  " + CARD.delta.label, 72, 492);
    } else if (CARD.delta_empty) {
      ctx.fillStyle = P.tertiary;
      ctx.font = "400 18px " + UI;
      ctx.fillText(CARD.delta_empty, 72, 492);
    }

    // Four equal columns keep the AQ evidence legible at a glance.
    var pillarTop = 562;
    var pillarWidth = 246;
    ctx.fillStyle = P.text;
    ctx.font = "600 20px " + UI;
    ctx.fillText("AQ pillars", 72, 538);
    (CARD.pillars || []).forEach(function (pillar, index) {
      var x = 72 + index * 264;
      var score = Number(pillar.score || 0);
      ctx.fillStyle = P.secondary;
      ctx.font = "500 15px " + MONO;
      ctx.fillText(String(pillar.name || ""), x, pillarTop);
      ctx.fillStyle = P.text;
      ctx.font = "500 32px " + MONO;
      ctx.fillText(String(pillar.score), x, pillarTop + 44);
      ctx.fillStyle = P.track;
      ctx.fillRect(x, pillarTop + 64, pillarWidth, 8);
      ctx.fillStyle = P.chart;
      ctx.fillRect(x, pillarTop + 64, pillarWidth * Math.max(0, Math.min(100, score)) / 100, 8);
    });

    ctx.fillStyle = P.rule;
    ctx.fillRect(72, 700, 1056, 1);
    var moves = CARD.moves || [];
    if (moves.length) {
      ctx.fillStyle = P.text;
      ctx.font = "600 24px " + UI;
      ctx.fillText("How you work", 72, 760);
      moves.forEach(function (move, index) {
        var y = 812 + index * 68;
        ctx.fillStyle = P.accent;
        ctx.font = "500 14px " + MONO;
        ctx.fillText(String(move.tag || "").toUpperCase(), 72, y);
        ctx.fillStyle = P.text;
        ctx.font = "400 22px " + UI;
        writeLines(ctx, move.title || "", 196, y, 27, 54);
      });
    }

    var quoteTop = moves.length ? 1050 : 780;
    ctx.fillStyle = P.text;
    ctx.font = "600 24px " + UI;
    ctx.fillText("Off the cuff", 72, quoteTop);
    if (quote) {
      ctx.fillStyle = P.secondary;
      ctx.font = "400 22px " + UI;
      writeLines(ctx, "“" + quote + "”", 72, quoteTop + 48, 30, 82);
    } else {
      ctx.fillStyle = P.tertiary;
      ctx.font = "400 18px " + UI;
      ctx.fillText("No off-the-cuff line this month", 72, quoteTop + 48);
    }

    ctx.fillStyle = P.rule;
    ctx.fillRect(72, 1222, 1056, 1);
    ctx.fillStyle = P.secondary;
    ctx.font = "400 17px " + UI;
    ctx.fillText("▣  Generated on this machine · nothing uploaded", 72, 1260);
    ctx.fillStyle = P.accent;
    ctx.font = "500 17px " + MONO;
    ctx.fillText(CARD.repo, 72, 1292);
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
