"""Contract tests for the bundled local-profile fonts."""

import base64
import fnmatch
import os
import re
import unittest

from gnomon.output.profile.fonts import font_face_css


ROOT = os.path.dirname(os.path.dirname(__file__))
FONT_DIR = os.path.join(ROOT, "gnomon", "output", "profile", "fonts")
PYPROJECT = os.path.join(ROOT, "pyproject.toml")


class TestProfileFonts(unittest.TestCase):
    def test_font_face_css_embeds_all_font_files(self):
        css = font_face_css()

        self.assertEqual(css.count("@font-face"), 3)
        self.assertIn('font-family: "Archivo";', css)
        self.assertIn("font-weight: 400 600;", css)
        self.assertEqual(css.count('font-family: "IBM Plex Mono";'), 2)
        self.assertIn("font-weight: 400;", css)
        self.assertIn("font-weight: 500;", css)
        self.assertEqual(css.count("font-display: swap;"), 3)
        self.assertNotIn("fonts.googleapis.com", css)
        self.assertNotIn("fonts.gstatic.com", css)

        data_urls = re.findall(
            r"src:url\(data:font/woff2;base64,([A-Za-z0-9+/=]+)\) "
            r'format\("woff2"\);',
            css,
        )
        self.assertEqual(len(data_urls), 3)
        expected = []
        for filename in (
            "Archivo-latin-wght.woff2",
            "IBMPlexMono-400-latin.woff2",
            "IBMPlexMono-500-latin.woff2",
        ):
            with open(os.path.join(FONT_DIR, filename), "rb") as font_file:
                expected.append(base64.b64encode(font_file.read()).decode("ascii"))
        self.assertEqual(data_urls, expected)

    def test_package_data_covers_every_font_asset(self):
        with open(PYPROJECT, encoding="utf-8") as project_file:
            project = project_file.read()

        self.assertIn('[tool.setuptools.package-data]', project)
        self.assertIn('"gnomon.output.profile" = ["fonts/*.woff2", "fonts/OFL.txt"]', project)
        patterns = ("fonts/*.woff2", "fonts/OFL.txt")
        for filename in os.listdir(FONT_DIR):
            relative = os.path.join("fonts", filename)
            self.assertTrue(
                any(fnmatch.fnmatch(relative, pattern) for pattern in patterns),
                "package-data does not cover %s" % relative,
            )

    def test_woff2_assets_fit_profile_budget(self):
        total = sum(
            os.path.getsize(os.path.join(FONT_DIR, filename))
            for filename in (
                "Archivo-latin-wght.woff2",
                "IBMPlexMono-400-latin.woff2",
                "IBMPlexMono-500-latin.woff2",
            )
        )
        self.assertLessEqual(total, 150 * 1024)


if __name__ == "__main__":
    unittest.main()
