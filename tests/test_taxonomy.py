import unittest

from gnomon.taxonomy import (
    ASK_TOOLS, DELEGATE_TOOLS, DISCOVER_TOOLS, EXEC_TOOLS, PLAN_MODE_TOOLS,
    PLAN_SIGNAL_TOOLS, PLAN_TOOLS, READ_TOOLS, SCHEDULE_TOOLS, SKILL_TOOLS,
    WRITE_TOOLS, classify_tool, is_substantive_tool,
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


class TestClassifyToolPlanCategory(unittest.TestCase):
    """Planning ceremony is neither exploring nor building, so it belongs on neither side
    of planning_ratio_explore_to_doing. It used to classify as `explore`, which meant plan
    mode raised that ratio's numerator AND — now that plan mode is a qualified planning
    signal — the separate Planning practice term: one action paid twice inside one axis.
    Its own category keeps it neutral."""

    def test_every_plan_tool_is_its_own_category(self):
        for tool in sorted(PLAN_TOOLS):
            with self.subTest(tool=tool):
                self.assertEqual(classify_tool(tool), "plan")

    def test_plan_category_is_neither_explore_nor_a_doing_class(self):
        # The ratio reads explore against produce+execute+delegate; "plan" is in none of them.
        for tool in sorted(PLAN_TOOLS):
            with self.subTest(tool=tool):
                self.assertNotIn(
                    classify_tool(tool), {"explore", "produce", "execute", "delegate"})

    def test_plan_tools_remain_non_substantive(self):
        # Containment proof: is_substantive_tool short-circuits on
        # _NONSUBSTANTIVE_WORK_TOOLS before classify_tool is consulted, so change
        # eligibility and orchestration counting are untouched by the category change.
        for tool in sorted(PLAN_TOOLS):
            with self.subTest(tool=tool):
                self.assertFalse(is_substantive_tool(tool))

    def test_plan_mode_and_signal_sets_nest_inside_plan_tools(self):
        self.assertTrue(PLAN_MODE_TOOLS <= PLAN_TOOLS)
        self.assertTrue(PLAN_SIGNAL_TOOLS <= PLAN_TOOLS)
        self.assertTrue(PLAN_MODE_TOOLS <= PLAN_SIGNAL_TOOLS)

    def test_todo_write_is_a_plan_signal_but_not_plan_mode(self):
        self.assertIn("TodoWrite", PLAN_SIGNAL_TOOLS)
        self.assertNotIn("TodoWrite", PLAN_MODE_TOOLS)


class TestClassifyToolOtherCategoriesUnchanged(unittest.TestCase):
    """Guard: carving `plan` out of the explore branch must not shift anything else."""

    def test_write_read_exec_delegate_skill_ask_are_stable(self):
        expected = {
            "Edit": "produce", "Write": "produce", "MultiEdit": "produce",
            "Read": "explore", "Grep": "explore", "Glob": "explore",
            "WebSearch": "explore", "WebFetch": "explore", "ToolSearch": "explore",
            "Bash": "execute", "BashOutput": "execute", "KillShell": "execute",
            "Agent": "delegate", "Task": "delegate",
            "Skill": "execute",
            "CronCreate": "execute", "Monitor": "execute",
            "AskUserQuestion": "ask",
        }
        for tool, category in expected.items():
            with self.subTest(tool=tool):
                self.assertEqual(classify_tool(tool), category)

    def test_mcp_tools_still_split_by_inspect_hint(self):
        self.assertEqual(classify_tool("mcp__linear__search_issues"), "explore")
        self.assertEqual(classify_tool("mcp__acme__create_thing"), "produce")

    def test_unknown_tool_is_other(self):
        self.assertEqual(classify_tool("TotallyMadeUpTool"), "other")

    def test_category_sets_stay_disjoint_from_plan_tools(self):
        # classify_tool's precedence order is only unambiguous while these stay disjoint.
        for other in (WRITE_TOOLS, READ_TOOLS, DISCOVER_TOOLS, EXEC_TOOLS,
                      DELEGATE_TOOLS, SKILL_TOOLS, SCHEDULE_TOOLS, ASK_TOOLS):
            with self.subTest(other=sorted(other)):
                self.assertEqual(PLAN_TOOLS & other, set())


if __name__ == "__main__":
    unittest.main()
