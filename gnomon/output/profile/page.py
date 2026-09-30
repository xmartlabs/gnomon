"""Document shell and section composition for the local profile."""

import html
import json

from gnomon.output.profile import brand, fonts, poster, theme, tokens
from gnomon.output.profile.sections import activity, breakdown, diagnosis, hero, portrait, quotes, readings, trend


def _section_css():
    return "".join(module.CSS for module in (
        hero, trend, diagnosis, breakdown, activity, readings, portrait, quotes))


def render_page(ctx) -> str:
    """Render the shell in the fixed v2 section order."""
    caption = html.escape(ctx.caption)
    card = json.dumps(poster.poster_data(ctx), separators=(",", ":"))
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>gnomon · Local profile</title>
  {head_script}
  <style>{font_css}{light_css}{base_css}{dark_css}{section_css}</style>
</head>
<body>
  <div class="gn-shell">
    <header class="gn-masthead">
      <a class="gn-brand" href="{repo_url}">{mark}<span>gnomon</span></a>
      <span class="gn-masthead-label">Local profile</span>
      <span class="gn-masthead-note">Generated on this machine · nothing uploaded</span>
      {toggle}
    </header>
    <main class="gn-main">
      <section id="hero" class="gn-section">{hero_html}</section>
      <section id="trend" class="gn-section">{trend_html}</section>
      <section id="diagnosis" class="gn-section">{diagnosis_html}</section>
      <section id="aq-breakdown" class="gn-section">{breakdown_html}</section>
      <section id="activity" class="gn-section">{activity_html}{readings_html}</section>
      <section id="portrait" class="gn-section">{portrait_html}{quotes_html}</section>
    </main>
    <footer class="gn-footer">
      <p>Generated on this machine by gnomon · stats.json · <a href="{repo_url}">{repo_label}</a></p>
      <p class="gn-caption">{caption}</p>
    </footer>
  </div>
  <script>
  var CARD={card};
  </script>
  {poster_js}
</body>
</html>
""".format(
        head_script=theme.HEAD_SCRIPT,
        font_css=fonts.font_face_css(),
        light_css=tokens.LIGHT_CSS,
        base_css=tokens.BASE_CSS,
        dark_css=theme.DARK_CSS,
        section_css=_section_css(),
        repo_url=brand.REPO_URL,
        repo_label=html.escape(brand.REPO_LABEL),
        mark=brand.MARK_SVG,
        toggle=theme.render_toggle(),
        hero_html=hero.render(ctx),
        trend_html=trend.render(ctx),
        diagnosis_html=diagnosis.render(ctx),
        breakdown_html=breakdown.render(ctx),
        activity_html=activity.render(ctx),
        readings_html=readings.render(ctx),
        portrait_html=portrait.render(ctx),
        quotes_html=quotes.render(ctx),
        caption=caption,
        card=card,
        poster_js=poster.POSTER_JS,
    )
