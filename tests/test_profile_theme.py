"""Contract tests for the T13 profile theme controls."""

import re
import shutil
import subprocess
import tempfile
import unittest

from gnomon.output.profile import theme


class TestProfileTheme(unittest.TestCase):
    def test_head_script_is_prepaint_safe_and_uses_system_fallback(self):
        self.assertIn('localStorage.getItem("gn-theme")', theme.HEAD_SCRIPT)
        self.assertIn('window.matchMedia("(prefers-color-scheme: dark)")', theme.HEAD_SCRIPT)
        self.assertIn('document.documentElement.dataset.theme = theme', theme.HEAD_SCRIPT)
        self.assertRegex(theme.HEAD_SCRIPT, r"(?s)try \{.*localStorage\.getItem.*\} catch \(e\) \{\}")

    def test_dark_tokens_match_the_v2_dark_selector(self):
        with open("docs/design/design-system-v2/design_system/tokens/colors.css",
                  encoding="utf-8") as handle:
            colors = handle.read()
        start = colors.index('[data-theme="dark"]')
        expected = colors[start:colors.index("\n}", start) + 2]
        self.assertEqual(theme.DARK_CSS, expected)

    def test_toggle_has_accessible_icons_and_safe_persistence(self):
        toggle = theme.render_toggle()
        self.assertIn('id="gn-theme-toggle"', toggle)
        self.assertIn('aria-label="Switch to dark theme"', toggle)
        self.assertIn('data-theme-icon="sun"', toggle)
        self.assertIn('data-theme-icon="moon"', toggle)
        self.assertIn('localStorage.setItem("gn-theme", next)', toggle)
        self.assertRegex(toggle, r"(?s)try \{.*localStorage\.setItem.*\} catch \(e\) \{\}")

    @unittest.skipUnless(shutil.which("node"), "node not installed (CI installs it)")
    def test_head_script_follows_system_when_storage_throws(self):
        script = re.search(r"<script>(.*?)</script>", theme.HEAD_SCRIPT, re.S).group(1)
        source = """
var document = {documentElement: {dataset: {}}};
var window = {matchMedia: function () { return {matches: true}; }};
var localStorage = {getItem: function () { throw new Error("blocked"); }};
%s
if (document.documentElement.dataset.theme !== "dark") process.exit(1);
""" % script
        self._run_node(source)

    @unittest.skipUnless(shutil.which("node"), "node not installed (CI installs it)")
    def test_toggle_persists_and_head_script_reads_saved_theme(self):
        head = re.search(r"<script>(.*?)</script>", theme.HEAD_SCRIPT, re.S).group(1)
        toggle = re.findall(r"<script>(.*?)</script>", theme.render_toggle(), re.S)[0]
        source = """
var listeners = {};
var button = {
  attrs: {},
  hidden: false,
  setAttribute: function (name, value) { this.attrs[name] = value; },
  addEventListener: function (name, fn) { listeners[name] = fn; },
  querySelector: function (selector) {
    return selector.indexOf("sun") !== -1 ? {hidden: true} : {hidden: false};
  }
};
var document = {
  documentElement: {dataset: {theme: "light"}},
  getElementById: function () { return button; }
};
var window = {matchMedia: function () { return {matches: false}; }};
var saved = {};
var localStorage = {
  getItem: function (key) { return saved[key] || null; },
  setItem: function (key, value) { saved[key] = value; }
};
%s
%s
listeners.click();
if (saved["gn-theme"] !== "dark") process.exit(1);
document.documentElement.dataset.theme = "light";
%s
if (document.documentElement.dataset.theme !== "dark") process.exit(1);
""" % (head, toggle, head)
        self._run_node(source)

    @staticmethod
    def _run_node(source):
        with tempfile.NamedTemporaryFile("w", suffix=".js", encoding="utf-8") as handle:
            handle.write(source)
            handle.flush()
            result = subprocess.run(
                [shutil.which("node"), handle.name],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
            )
        if result.returncode:
            raise AssertionError(result.stderr or "node script failed")


if __name__ == "__main__":
    unittest.main()
