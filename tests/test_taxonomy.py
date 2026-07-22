import unittest

from gnomon.taxonomy import (
    classify_change_target, is_plan_file_target, _is_compounding_path, _norm_path_seps,
)


class TestClassifyChangeTarget(unittest.TestCase):
    def test_classifies_common_code_extensions(self):
        for path in ("src/app.py", "lib/util.ts", "pkg/main.go", "app/Foo.java"):
            self.assertEqual(classify_change_target(path), "code", path)

    def test_classifies_test_files_by_name_pattern(self):
        for path in ("tests/test_foo.py", "src/foo_test.go", "src/foo.test.ts",
                     "src/foo.spec.tsx", "__tests__/bar.js"):
            self.assertEqual(classify_change_target(path), "test", path)

    def test_classifies_docs(self):
        for path in ("README.md", "docs/guide.mdx", "CHANGELOG.txt", "notes.rst"):
            self.assertEqual(classify_change_target(path), "doc", path)

    def test_classifies_config(self):
        for path in ("package.json", "config.yaml", "pyproject.toml", ".eslintrc.json",
                     "Dockerfile"):
            self.assertEqual(classify_change_target(path), "config", path)

    def test_classifies_lockfiles_even_when_json_extension(self):
        for path in ("package-lock.json", "yarn.lock", "pnpm-lock.yaml",
                     "Cargo.lock", "poetry.lock", "go.sum", "Gemfile.lock"):
            self.assertEqual(classify_change_target(path), "lockfile", path)

    def test_classifies_unknown_extension_as_other(self):
        self.assertEqual(classify_change_target("assets/logo.png"), "other")
        self.assertEqual(classify_change_target(""), "other")


class TestIsPlanFileTarget(unittest.TestCase):
    def test_matches_claude_plans_markdown(self):
        self.assertTrue(is_plan_file_target(".claude/plans/2026-01-01-feature.md"))

    def test_matches_cursor_plans_directory(self):
        self.assertTrue(is_plan_file_target(".cursor/plans/feature-plan.md"))

    def test_matches_context_plan_named_file(self):
        self.assertTrue(is_plan_file_target(".context/ordered-planning-redesign.md"))

    def test_matches_generic_plans_directory_with_plan_in_name(self):
        self.assertTrue(is_plan_file_target("docs/plans/rollout-plan.md"))

    def test_matches_any_markdown_in_a_plans_dir_regardless_of_filename(self):
        # superpowers writing-plans convention: docs/superpowers/plans/<n>-<name>.md
        for path in ("docs/superpowers/plans/2-stadium.md",
                     "docs/plans/notes.md",
                     "plans/2-feature.md"):
            self.assertTrue(is_plan_file_target(path), path)

    def test_rejects_unrelated_paths(self):
        # deployment-plans is not a `plans/` segment; non-md files in plans/ don't count
        for path in ("src/app.py", "README.md", "deployment-plans/notes.md",
                     "src/plans/config.json", "plansomething/x.md", ""):
            self.assertFalse(is_plan_file_target(path), path)


class TestBackslashPathsCountLikeForwardSlash(unittest.TestCase):
    """Windows transcripts record file_path with backslashes. The path classifiers only
    inspect the string (they never open the file), so a backslash path must be classified
    identically to its forward-slash form — otherwise Windows memory/ADR writes and native
    plan files are silently uncounted."""

    def test_compounding_memory_path(self):
        self.assertTrue(_is_compounding_path(
            r"C:\Users\d\.claude\projects\proj\memory\note.md"))

    def test_compounding_adr_path(self):
        self.assertTrue(_is_compounding_path(r"C:\repo\docs\adr\0003-thing.md"))

    def test_plan_file_native_claude_plans(self):
        self.assertTrue(is_plan_file_target(r"C:\Users\d\.claude\plans\hazy.md"))

    def test_plan_file_superpowers_convention(self):
        self.assertTrue(is_plan_file_target(
            r"C:\repo\docs\superpowers\plans\2-stadium.md"))

    def test_change_target_test_dir(self):
        self.assertEqual(classify_change_target(r"C:\repo\tests\helper.js"), "test")

    def test_normalization_is_identity_without_backslashes(self):
        """The Linux/Mac guarantee, stated as an invariant: normalization only ever
        rewrites a backslash, so any posix path is passed through byte-identical and
        every existing classification is unchanged by construction."""
        for path in ("/home/d/.claude/projects/p/memory/note.md", "src/app.py",
                     "docs/adr/0001-x.md", "package-lock.json", ""):
            self.assertEqual(_norm_path_seps(path), path, path)


if __name__ == "__main__":
    unittest.main()
