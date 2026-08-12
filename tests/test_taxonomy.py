import unittest

from gnomon.taxonomy import (
    ASK_TOOLS, DELEGATE_TOOLS, DISCOVER_TOOLS, EXEC_TOOLS, ORCHESTRATION_TOOLS,
    FANOUT_BY_TRANSCRIPT_TOOLS,
    PLAN_MODE_TOOLS, PLAN_SIGNAL_TOOLS, PLAN_TOOLS, READ_TOOLS, SCHEDULE_TOOLS,
    SKILL_TOOLS, WRITE_TOOLS, classify_tool, is_substantive_tool,
    classify_change_target, is_plan_file_target, _is_compounding_path, _norm_path_seps,
    parse_workflow_agent_dispatch,
    MCP_INSPECT_HINTS, MCP_WRITE_HINTS, MCP_FETCH_ONLY_KNOWLEDGE_SERVERS,
    is_mcp_knowledge_write,
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

    def test_ephemeral_scratchpad_writes_are_not_code(self):
        # A scratchpad path is discardable by construction, so even a code extension there
        # must not make the input eligible for a code change. The location check must win
        # over the extension check. Covers every temp-root spelling, including the macOS
        # canonical /private/var/folders and Windows %TEMP% (backslashes normalized first).
        for path in (
            "/private/tmp/claude-12345/myproject/8f0c-uuid/scratchpad/foo.ts",
            "/tmp/claude-999/proj/abcd-uuid/scratchpad/bar.py",
            "/var/folders/xy/abcd/T/claude-1/proj/uuid/scratchpad/baz.go",
            "/private/var/folders/xy/abcd/T/claude-1/proj/uuid/scratchpad/baz.go",
            r"C:\Users\alice\AppData\Local\Temp\claude-123\proj\uuid\scratchpad\a.py",
            r"C:\Windows\Temp\claude-1\proj\uuid\scratchpad\b.py",
        ):
            self.assertEqual(classify_change_target(path), "other", path)

    def test_real_project_code_still_classifies_as_code(self):
        self.assertEqual(classify_change_target("/Users/dev/repo/src/app.py"), "code")

    def test_temp_root_without_scratchpad_is_not_excluded(self):
        # A legitimate checkout that merely lives under a temp root (no scratchpad segment)
        # must still count as code — excluding all of /tmp would hide real work.
        for path in ("/tmp/repo/src/app.py", "/var/folders/xy/T/repo/lib/util.ts"):
            self.assertEqual(classify_change_target(path), "code", path)

    def test_scratchpad_directly_under_temp_root_is_excluded(self):
        # OBS 3(a) — a scratchpad with NO intermediate path segment (directly under
        # the temp root) must still be excluded; the old `.*/scratchpad/` suffix
        # required an intermediate `/`, so this fell through to "code".
        self.assertEqual(classify_change_target("/tmp/scratchpad/foo.py"), "other")

    def test_windows_appdata_temp_requires_a_real_drive_rooted_path(self):
        # OBS 3(b) — the Windows AppData/Local/Temp alternative must not match a
        # legitimate (non-drive-rooted) path that merely CONTAINS that substring,
        # e.g. a project subfolder incidentally named appdata/local/temp.
        self.assertEqual(
            classify_change_target("/repo/vendor/appdata/local/temp/scratchpad/foo.py"),
            "code")


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


class TestOrchestrationToolsTaxonomy(unittest.TestCase):
    """WU4 (H1a/H1b/H6): ORCHESTRATION_TOOLS is the single named source of truth for
    the accumulator's orchestration-dispatch gate, superseding the literal
    `name == "Agent"` check. Task and Workflow are real dispatch tools and belong in
    the set; TaskCreate/TaskUpdate/TaskList/TaskGet are todo-bookkeeping (PLAN_TOOLS)
    and must stay excluded, or agents_per_session would be inflated by non-dispatch
    events."""

    def test_workflow_tool_classifies_as_delegate(self):
        self.assertEqual(classify_tool("Workflow"), "delegate")

    def test_workflow_is_added_to_delegate_tools(self):
        self.assertIn("Workflow", DELEGATE_TOOLS)

    def test_orchestration_tools_is_exactly_agent_task_workflow(self):
        self.assertEqual(ORCHESTRATION_TOOLS, {"Agent", "Task", "Workflow"})

    def test_orchestration_tools_excludes_todo_bookkeeping_task_variants(self):
        for tool in ("TaskCreate", "TaskUpdate", "TaskList", "TaskGet"):
            with self.subTest(tool=tool):
                self.assertNotIn(tool, ORCHESTRATION_TOOLS)


class TestWorkflowAgentDispatchPathParsing(unittest.TestCase):
    """Fix for Workflow fan-out under-credit: real dispatched-agent transcripts live
    at `.../subagents/workflows/wf_*/agent-*.jsonl`, one file per dispatched agent.
    `parse_workflow_agent_dispatch` recovers (parent_session_id, filename_agent_id)
    from that path so the accumulator can attribute the dispatch to the parent
    session instead of the per-Workflow-call count."""

    def test_matches_real_corpus_shaped_path(self):
        # Phase 5 (5.1) real-corpus confirmation: this exact path shape (parent sid,
        # `wf_<runId>` dir, `agent-<hash>.jsonl` filename) was found and inspected
        # live under a real `~/.claude/projects/**` corpus during apply (2026-08-06);
        # the parent sid / run id / agent hash below are copied verbatim from that
        # sample, not invented. `agentId` inside each such file's own events was also
        # confirmed to equal this same filename hash, while the file's `sessionId`
        # field carries the PARENT's session id, not a distinct child id -- see
        # parse_workflow_agent_dispatch's docstring and TestWorkflowFanoutTranscript
        # Attribution in tests/test_accumulator.py, which uses `agentId` accordingly.
        path = (
            "/Users/x/.claude/projects/-repo/c83998c6-540d-488b-8f79-fd6249316102/"
            "subagents/workflows/wf_6551bb5e-ac0/agent-a9cdfb752480e84ef.jsonl"
        )
        parent_sid, agent_id = parse_workflow_agent_dispatch(path)
        self.assertEqual(parent_sid, "c83998c6-540d-488b-8f79-fd6249316102")
        self.assertEqual(agent_id, "a9cdfb752480e84ef")

    def test_matches_with_backslash_separators(self):
        path = (
            r"C:\Users\x\.claude\projects\-repo\parent-sid"
            r"\subagents\workflows\wf_abc\agent-def123.jsonl"
        )
        parent_sid, agent_id = parse_workflow_agent_dispatch(path)
        self.assertEqual(parent_sid, "parent-sid")
        self.assertEqual(agent_id, "def123")

    def test_non_workflow_subagent_path_does_not_match(self):
        # Regular (non-Workflow) Agent/Task dispatch sidechain: one level shallower
        # (no /workflows/wf_*/ segment), and Agent/Task already count 1-call==1-agent
        # via the tool_use gate, so this path must NOT also earn transcript credit.
        path = "/base/proj/parent-sid/subagents/agent-abc123.jsonl"
        self.assertEqual(parse_workflow_agent_dispatch(path), (None, None))

    def test_root_transcript_path_does_not_match(self):
        path = "/base/proj/parent-sid.jsonl"
        self.assertEqual(parse_workflow_agent_dispatch(path), (None, None))

    def test_empty_path_does_not_match(self):
        self.assertEqual(parse_workflow_agent_dispatch(""), (None, None))
        self.assertEqual(parse_workflow_agent_dispatch(None), (None, None))

    def test_fanout_by_transcript_tools_is_exactly_workflow(self):
        # Agent/Task stay 1-call==1-agent (unchanged); only Workflow fans out
        # per-call to a variable number of real dispatched agents.
        self.assertEqual(FANOUT_BY_TRANSCRIPT_TOOLS, {"Workflow"})


class TestPowerShellIsAShell(unittest.TestCase):
    """Issue #72: `PowerShell` is the shell tool Claude Code emits on Windows, and it was
    unhandled everywhere `Bash` is handled. `classify_tool` fell through to `other`, which
    sits on NEITHER side of planning_ratio_explore_to_doing, so a Windows developer's shell
    work was invisible to Grounding, and `is_substantive_tool` excluded it from
    actions_per_prompt. It is the same category of action as Bash and must classify as one."""

    def test_powershell_classifies_as_execute(self):
        self.assertEqual(classify_tool("PowerShell"), "execute")

    def test_powershell_is_in_exec_tools(self):
        self.assertIn("PowerShell", EXEC_TOOLS)

    def test_powershell_is_substantive_work(self):
        self.assertTrue(is_substantive_tool("PowerShell"))

    def test_powershell_matches_bash_classification(self):
        # The point of the fix: the two shells are indistinguishable to the taxonomy.
        self.assertEqual(classify_tool("PowerShell"), classify_tool("Bash"))
        self.assertEqual(is_substantive_tool("PowerShell"), is_substantive_tool("Bash"))


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


class TestIsMcpKnowledgeWrite(unittest.TestCase):
    """Compounding credit for MCP knowledge-writes (contract 16:16:16): a MCP call
    credits the Compounding axis only when it is BOTH knowledge-subcategory AND a
    genuine persistence write, gated by an explicit positive write-verb predicate
    (NOT classify_tool=="produce", which over-selects and wrongly credits reads
    like context7 resolve-library-id / engram mem_context / mem0 delete_memory)."""

    def test_must_credit_mem0_add_memory(self):
        self.assertTrue(is_mcp_knowledge_write("mem0", "add_memory"))

    def test_must_credit_mem0_update_memory(self):
        self.assertTrue(is_mcp_knowledge_write("mem0", "update_memory"))

    def test_must_credit_engram_mem_save(self):
        self.assertTrue(is_mcp_knowledge_write("engram", "mem_save"))

    def test_must_credit_engram_mem_update(self):
        self.assertTrue(is_mcp_knowledge_write("engram", "mem_update"))

    def test_must_reject_context7_resolve_library_id(self):
        self.assertFalse(is_mcp_knowledge_write("context7", "resolve-library-id"))

    def test_must_reject_engram_mem_context(self):
        self.assertFalse(is_mcp_knowledge_write("engram", "mem_context"))

    def test_must_reject_engram_mem_current_project(self):
        self.assertFalse(is_mcp_knowledge_write("engram", "mem_current_project"))

    def test_must_reject_engram_mem_review(self):
        self.assertFalse(is_mcp_knowledge_write("engram", "mem_review"))

    def test_must_reject_mem0_search_memory(self):
        self.assertFalse(is_mcp_knowledge_write("mem0", "search_memory"))

    def test_must_reject_mem0_delete_memory(self):
        self.assertFalse(is_mcp_knowledge_write("mem0", "delete_memory"))

    def test_read_hint_precedence_rejects_hypothetical_get_or_create(self):
        # Read-hint match wins: "get_or_create" contains "get" (MCP_INSPECT_HINTS),
        # so it must NOT be treated as a write even though it also contains "create".
        self.assertFalse(is_mcp_knowledge_write("engram", "get_or_create"))

    def test_non_knowledge_server_never_credits_even_with_a_write_verb(self):
        # e.g. a "data"-subcategory server calling something named "add_record":
        # only knowledge-subcategory MCPs are eligible at all.
        self.assertFalse(is_mcp_knowledge_write("supabase", "add_record"))

    def test_write_and_inspect_hint_lists_are_disjoint(self):
        self.assertEqual(set(MCP_WRITE_HINTS) & set(MCP_INSPECT_HINTS), set())

    def test_fetch_only_knowledge_servers_present(self):
        self.assertIn("context7", MCP_FETCH_ONLY_KNOWLEDGE_SERVERS)


if __name__ == "__main__":
    unittest.main()
