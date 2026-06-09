import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import paxel


class TestExtractClis(unittest.TestCase):
    def test_single_known_cli(self):
        self.assertEqual(paxel._extract_clis("git status"), ["git"])

    def test_chained_commands(self):
        self.assertEqual(paxel._extract_clis("cd /x && pnpm install | grep foo"),
                         ["pnpm", "grep"])

    def test_skips_env_assignment(self):
        self.assertEqual(paxel._extract_clis("FOO=bar python3 run.py"), ["python3"])

    def test_path_prefixed_binary(self):
        self.assertEqual(paxel._extract_clis("/usr/bin/node app.js"), ["node"])

    def test_unknown_command_ignored(self):
        self.assertEqual(paxel._extract_clis("frobnicate --x"), [])

    def test_empty(self):
        self.assertEqual(paxel._extract_clis(""), [])


class TestCodexInjected(unittest.TestCase):
    def test_environment_context(self):
        self.assertTrue(paxel._codex_is_injected(
            "<environment_context>\n  <cwd>/x</cwd>\n  <shell>zsh</shell>\n</environment_context>"))

    def test_user_instructions(self):
        self.assertTrue(paxel._codex_is_injected("  <user_instructions>be concise</user_instructions>"))

    def test_real_prompt_kept(self):
        self.assertFalse(paxel._codex_is_injected("fix the auth bug in middleware"))

    def test_empty(self):
        self.assertFalse(paxel._codex_is_injected(""))


if __name__ == "__main__":
    unittest.main()
