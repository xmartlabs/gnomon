import unittest

from gnomon.taxonomy import classify_change_target, is_plan_file_target


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

    def test_matches_any_markdown_directly_in_plans_dir_at_any_depth(self):
        # superpowers writing-plans convention: filename need NOT contain "plan"
        for path in ("docs/superpowers/plans/2-stadium.md",
                     "docs/plans/roadmap.md",
                     "plans/2-feature.md",
                     ".claude/plans/foo.md",
                     ".context/session-plan.md"):
            self.assertTrue(is_plan_file_target(path), path)

    def test_rejects_unrelated_paths(self):
        for path in ("src/app.py", "README.md", "",
                     # segment must be exactly `plans`, not a suffix/prefix
                     "deployment-plans/notes.md", "plansomething/x.md",
                     # inside plans/ but not a markdown-ish file
                     "src/plans/config.json"):
            self.assertFalse(is_plan_file_target(path), path)


if __name__ == "__main__":
    unittest.main()
