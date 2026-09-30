import re
import unittest
from types import SimpleNamespace

from gnomon.output.profile.sections import portrait


def _ctx(**overrides):
    stats = {
        "volume": {
            "total_prompts": 100,
            "avg_prompt_length_chars": 300,
            "median_prompt_length_chars": 100,
        },
        "behavior": {
            "polite_prompts": 12,
            "questions_asked": 0,
            "longest_run_minutes": 125,
        },
        "rhythm": {
            "peak_hours_local": [23],
            "weekday_histogram": {
                "Mon": 10, "Tue": 10, "Wed": 10, "Thu": 10, "Fri": 10,
                "Sat": 6, "Sun": 6,
            },
            "preferred_days": ["Tue"],
        },
    }
    for block, values in overrides.items():
        stats[block].update(values)
    return SimpleNamespace(stats=stats, period=SimpleNamespace(label="Jun 2026"))


class TestProfilePortrait(unittest.TestCase):
    def test_renders_heading_and_six_traits(self):
        page = portrait.render(_ctx())

        self.assertIn("<h2>Portrait</h2>", page)
        self.assertIn("Traits and quotes from Jun 2026. Not scored, and not part of your AQ.", page)
        self.assertIn("<h3>{}</h3>".format(portrait.TRAITS_LABEL), page)
        self.assertEqual(
            re.findall(r'<div class="trait" data-trait="([^"]+)">', page),
            ["best_time", "weekends", "prompt_length", "teammate", "politeness", "longest_run"],
        )
        self.assertEqual(page.count('class="trait-question"'), 6)
        self.assertEqual(page.count('class="trait-answer"'), 6)
        self.assertEqual(page.count('class="trait-detail"'), 6)

    def test_month_hint_uses_calendar_month_only(self):
        ctx = _ctx()
        ctx.period = SimpleNamespace(
            month_key="2026-06", label="Jun 2026 · in progress · 30 days")

        page = portrait.render(ctx)

        self.assertIn("Traits and quotes from Jun 2026. Not scored", page)
        self.assertNotIn("in progress", page)

    def test_uses_legacy_trait_copy(self):
        page = portrait.render(_ctx())

        for text in (
            "Night owl",
            "You do your heaviest work around 11pm.",
            "No days off",
            "Short, with the odd essay",
            "Like a teammate",
            "You say thanks a lot",
            "2h 5m",
        ):
            self.assertIn(text, page)

    def test_politeness_and_teammate_thresholds(self):
        enough = portrait.render(_ctx(behavior={"polite_prompts": 4, "questions_asked": 0}))
        self.assertIn("Polite enough", enough)
        self.assertIn("Like a tool", enough)

        questions = portrait.render(_ctx(behavior={"polite_prompts": 0, "questions_asked": 4}))
        self.assertIn("All business", questions)
        self.assertIn("Like a teammate", questions)

        thanks = portrait.render(_ctx(behavior={"polite_prompts": 12, "questions_asked": 0}))
        self.assertIn("You say thanks a lot", thanks)

    def test_css_uses_tokens_instead_of_hex_colors(self):
        self.assertNotRegex(portrait.CSS, r"#[0-9a-fA-F]{3,8}")
        self.assertIn("var(--text-secondary)", portrait.CSS)
        self.assertIn("var(--surface-raised)", portrait.CSS)


if __name__ == "__main__":
    unittest.main()
