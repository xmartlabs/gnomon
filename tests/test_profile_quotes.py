"""Contract tests for the T12 profile quote cards."""

import unittest

from gnomon.cli.period import Period
from gnomon.output.profile.brand import CAPTION
from gnomon.output.profile.context import ProfileContext
from gnomon.output.profile.sections.quotes import render


class TestProfileQuotes(unittest.TestCase):
    def _context(self, voice):
        return ProfileContext(
            stats={"volume": {"total_prompts": 17}}, archetype="", quote="", scores={},
            voice=voice,
            period=Period("all_history", None, None, None, "All history", None, None),
            trend=None, moves=[], edges=[], caption=CAPTION)

    def test_three_cards_and_rerolls(self):
        page = render(self._context({
            "goto": ("ship it", 4, 2),
            "crashouts": ["NO, STOP!", "why is this broken"],
            "cryptics": ["ok ship it", "pls fix"],
        }))

        self.assertEqual(page.count('class="quote-card"'), 3)
        self.assertIn('id="q-goto">&ldquo;ship it&rdquo;', page)
        self.assertIn("4 times across 2 sessions", page)
        self.assertIn('id="q-crashout">&ldquo;NO, STOP!&rdquo;', page)
        self.assertIn('id="q-cuff">&ldquo;ok ship it&rdquo;', page)
        self.assertEqual(page.count('class="reroll"'), 2)
        self.assertIn('data-target="crashout"', page)
        self.assertIn('data-target="cuff"', page)
        self.assertNotIn('data-target="goto"', page)
        self.assertIn("var QUOTES", page)
        self.assertIn("document.getElementById(\"q-\" + target)", page)

    def test_empty_cards_explain_missing_candidates(self):
        page = render(self._context({
            "goto": None, "crashouts": [], "cryptics": [],
        }))

        self.assertEqual(page.count('class="quote-card"'), 3)
        self.assertEqual(page.count('class="gn-empty"'), 3)
        self.assertIn(
            "No go-to prompt this month — nothing you typed repeated 3+ times "
            "across 2+ sessions.", page)
        self.assertIn(
            "No crash-out this month — none of your 17 prompts read as heated. "
            "It shows up once one does.", page)
        self.assertIn(
            "No off-the-cuff line this month — none of your 17 prompts made it "
            "through the secrets/PII filter as a short, unfiltered ask.", page)

    def test_quotes_are_escaped_in_html_and_script_json(self):
        page = render(self._context({
            "goto": ('</script><img src=x onerror="pwn()">', 3, 2),
            "crashouts": [],
            "cryptics": [],
        }))

        self.assertIn(
            "&lt;/script&gt;&lt;img src=x onerror=&quot;pwn()&quot;&gt;", page)
        self.assertIn(r'\u003c/script\u003e\u003cimg src=x onerror=\"pwn()\"\u003e', page)
        script_json = page.split("var QUOTES = ", 1)[1].split(";", 1)[0]
        self.assertNotIn("</script><img", script_json)


if __name__ == "__main__":
    unittest.main()
