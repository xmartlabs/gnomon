"""The local profile's six personality traits."""

import html
from datetime import datetime


TRAITS_LABEL = "Curiosities"


CSS = """\
.portrait-heading {
  margin: 64px 0 32px;
}
.portrait-heading h2 {
  margin: 0;
  font-size: 32px;
  line-height: 1.1;
  letter-spacing: -0.02em;
}
.portrait-hint {
  max-width: 720px;
  margin: 8px 0 0;
  color: var(--text-secondary);
}
.traits-column {
  min-width: 0;
}
.traits-column h3 {
  margin: 0;
  font-size: 24px;
  line-height: 1.15;
  letter-spacing: -0.015em;
}
.trait-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
  min-width: 0;
}
.trait {
  min-width: 0;
  padding: 20px;
  border: 1px solid var(--rule-default);
  background: var(--surface-raised);
}
.trait-question {
  margin: 0 0 10px;
  color: var(--text-secondary);
  font: 500 11px/1.2 var(--font-figure);
  letter-spacing: 0.1em;
  text-transform: uppercase;
}
.trait-answer {
  min-width: 0;
  margin: 0 0 8px;
  overflow-wrap: anywhere;
  color: var(--text-primary);
  font-size: 20px;
  line-height: 1.25;
}
.trait-detail {
  margin: 0;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.45;
}
@media (max-width: 900px) {
  .trait-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 560px) {
  .trait-grid {
    grid-template-columns: 1fr;
  }
}
"""


_DAYFULL = {
    "Mon": "Monday", "Tue": "Tuesday", "Wed": "Wednesday", "Thu": "Thursday",
    "Fri": "Friday", "Sat": "Saturday", "Sun": "Sunday",
}


def _trait_values(ctx):
    """Return the six legacy trait values in their display order."""
    stats = getattr(ctx, "stats", {}) or {}
    volume = stats.get("volume", {}) or {}
    behavior = stats.get("behavior", {}) or {}
    rhythm = stats.get("rhythm", {}) or {}

    peak = (rhythm.get("peak_hours_local") or [12])[0]
    tod = ("Night owl" if (peak >= 22 or peak <= 4) else
           "Morning person" if peak <= 11 else
           "Afternoon" if peak <= 16 else "Evening")
    h12 = "{}{}".format((peak - 1) % 12 + 1, "am" if peak < 12 else "pm")

    weekday_histogram = rhythm.get("weekday_histogram", {}) or {}
    weekend_count = weekday_histogram.get("Sat", 0) + weekday_histogram.get("Sun", 0)
    weekday_average = (sum(weekday_histogram.get(day, 0)
                           for day in ("Mon", "Tue", "Wed", "Thu", "Fri")) / 5 or 1)
    weekend_answer = ("No days off" if weekend_count / 2 >= weekday_average * 0.6
                      else "Weekday warrior")
    preferred_days = rhythm.get("preferred_days") or ["—"]
    busy_day = _DAYFULL.get(preferred_days[0], preferred_days[0])
    weekend_detail = (
        "Your busiest day is {} — and you logged time most days, weekends included."
        if weekend_answer == "No days off" else
        "Your busiest day is {}; weekends stay quiet."
    ).format(html.escape(str(busy_day)))

    average_length = volume.get("avg_prompt_length_chars", 0)
    median_length = volume.get("median_prompt_length_chars", 0)
    two_gears = average_length > median_length * 2
    prompt_answer = "Short, with the odd essay" if two_gears else "Consistent length"
    prompt_detail = (
        "Half run under {:,.0f} characters — quick commands — but the average is {:,.0f}."
        if two_gears else
        "Median {:,.0f} characters, average {:,.0f} — pretty steady."
    ).format(median_length, average_length)

    total_prompts = volume.get("total_prompts", 0) or 0
    prompts_for_rates = max(total_prompts, 1)
    polite_count = behavior.get("polite_prompts", 0) or 0
    polite_rate = polite_count / prompts_for_rates
    polite_answer = ("You say thanks a lot" if polite_rate >= 0.12 else
                     "Polite enough" if polite_rate >= 0.04 else "All business")
    polite_detail = (
        "You said please or thank-you in <b>{:,}</b> of your {:,} prompts ({:.0f}%).{}"
    ).format(
        polite_count, total_prompts, polite_rate * 100,
        " When the robots take over, they'll remember." if polite_rate >= 0.12 else "",
    )

    question_rate = (behavior.get("questions_asked", 0) or 0) / prompts_for_rates
    teammate = polite_rate >= 0.05 or question_rate >= 0.04
    teammate_answer = "Like a teammate" if teammate else "Like a tool"
    teammate_detail = (
        "You bounce ideas off it and ask for pushback — more collaborator than command line."
        if teammate else
        "You hand it work and check the result — more command line than collaborator."
    )

    longest_run = behavior.get("longest_run_minutes", 0) or 0
    run_hours, run_minutes = int(longest_run // 60), int(longest_run % 60)
    longest_run_answer = ("{}h {}m".format(run_hours, run_minutes)
                          if run_hours else "{}m".format(run_minutes))

    return [
        ("best_time", "When do you do your best work?", tod,
         "You do your heaviest work around {}.".format(h12)),
        ("weekends", "Do you take weekends off?", weekend_answer, weekend_detail),
        ("prompt_length", "How long are your prompts?", prompt_answer, prompt_detail),
        ("teammate", "How do you see your agent?", teammate_answer, teammate_detail),
        ("politeness", "How polite are you to it?", polite_answer, polite_detail),
        ("longest_run", "What's your longest run?", longest_run_answer,
         "Your longest unbroken stretch of active work in a single session."),
    ]


def _trait_html(key, question, answer, detail):
    return (
        '<div class="trait" data-trait="{}">'
        '<p class="trait-question">{}</p>'
        '<p class="trait-answer">{}</p>'
        '<p class="trait-detail">{}</p>'
        '</div>'
    ).format(
        html.escape(key, quote=True),
        html.escape(question),
        html.escape(str(answer)),
        detail,
    )


def render(ctx) -> str:
    """Render the Portrait traits column using the legacy derivations."""
    traits = "".join(_trait_html(*trait) for trait in _trait_values(ctx))
    return (
        '<div class="portrait-heading">'
        '<h2>Portrait</h2>'
        '<p class="portrait-hint">Traits and quotes from {}. Not scored, and not part of your AQ.</p>'
        '</div>'
        '<div class="traits-column">'
        '<h3>{}</h3>'
        '<div class="trait-grid">{}</div>'
        '</div>'
    ).format(html.escape(_period_label(ctx)), TRAITS_LABEL, traits)


def _period_label(ctx):
    period = getattr(ctx, "period", None)
    month_key = getattr(period, "month_key", None)
    if month_key:
        try:
            return datetime.strptime(month_key, "%Y-%m").strftime("%b %Y")
        except (TypeError, ValueError):
            pass
    label = getattr(period, "label", None)
    return str(label).split(" · ", 1)[0] if label else "this month"
