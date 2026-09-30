"""Contract tests for the T2 profile shell."""

import json
import os
import tempfile
import unittest
from unittest import mock

from gnomon.cli.period import Period
from gnomon.output.profile import brand, poster, tokens
from gnomon.output.profile.context import ProfileContext
from gnomon.output.profile.page import render_page
from gnomon.output.profile_html import write_profile_html


class TestProfileShell(unittest.TestCase):
    def _context(self):
        return ProfileContext(
            stats={}, archetype="", quote="", scores={}, voice={},
            period=Period("all_history", None, None, None, "All history", None, None),
            trend=None, moves=[], edges=[], caption=brand.CAPTION)

    def test_brand_and_shell_contract(self):
        page = render_page(self._context())
        self.assertIn('<title>gnomon · Local profile</title>', page)
        self.assertIn('class="gn-masthead"', page)
        self.assertIn('href="https://github.com/xmartlabs/gnomon"', page)
        self.assertIn("Generated on this machine by gnomon", page)
        self.assertIn(brand.CAPTION, page)
        card = json.loads(page.split("var CARD=", 1)[1].split(";", 1)[0])
        self.assertEqual(card["theme"], "light")   # the poster is always light (ADR 13)
        for old in ("Roadmap", "paxel", "Max Schilling", "Merriweather", "Josefin Sans"):
            self.assertNotIn(old, page)

    def test_empty_rule_is_tertiary_not_negative(self):
        self.assertIn(".gn-empty { color: var(--text-tertiary); }", tokens.BASE_CSS)
        self.assertNotIn(".gn-empty { color: var(--negative)", tokens.BASE_CSS)

    def test_write_overwrites_only_profile(self):
        with tempfile.TemporaryDirectory() as output_dir:
            profile = os.path.join(output_dir, "profile.html")
            sentinel = os.path.join(output_dir, "keep.txt")
            with open(profile, "w", encoding="utf-8") as handle:
                handle.write("old")
            with open(sentinel, "w", encoding="utf-8") as handle:
                handle.write("keep")
            with mock.patch("gnomon.output.profile_html.build_context",
                            return_value=self._context()):
                write_profile_html({}, "", "", {}, output_dir=output_dir,
                                   period=self._context().period)
            with open(profile, encoding="utf-8") as handle:
                self.assertIn("gnomon · Local profile", handle.read())
            with open(sentinel, encoding="utf-8") as handle:
                self.assertEqual(handle.read(), "keep")


if __name__ == "__main__":
    unittest.main()
