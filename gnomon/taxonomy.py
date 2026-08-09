import os
import re

WRITE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
READ_TOOLS = {"Read", "Grep", "Glob", "NotebookRead"}
DISCOVER_TOOLS = {"WebSearch", "WebFetch", "ToolSearch"}
EXEC_TOOLS = {"Bash", "BashOutput", "KillShell"}
DELEGATE_TOOLS = {"Agent", "Task", "Workflow"}
PLAN_TOOLS = {"TodoWrite", "TodoRead", "ExitPlanMode", "EnterPlanMode", "EnterWorktree",
              "ExitWorktree", "TaskCreate", "TaskUpdate", "TaskList", "TaskGet"}
# Real dispatch tools -- the accumulator's orchestration-counting gate
# (agents_per_session / _delegated_orchestratable / o_frequency) is driven by
# membership in this set, not a literal `name == "Agent"` check. TaskCreate/
# TaskUpdate/TaskList/TaskGet are todo-bookkeeping (PLAN_TOOLS above), not dispatch,
# and are deliberately EXCLUDED: admitting them would inflate agents_per_session with
# non-dispatch events (most sessions carry a TaskCreate at least once).
ORCHESTRATION_TOOLS = {"Agent", "Task", "Workflow"}
# Membership in ORCHESTRATION_TOOLS drives the delegation/frequency signal
# (agents_per_session > 0, _fanouts, delegating_sessions, o_frequency); this
# narrower set names which of those tools additionally fan out to MULTIPLE real
# dispatched agents per single tool_use call. Agent/Task stay 1-call==1-agent
# (unchanged): the accumulator gate still increments agents_per_session/
# month_fanouts directly for them. Workflow can dispatch anywhere from one to
# dozens of agents per call, so its fan-out is instead sourced from the real
# `.../subagents/workflows/wf_*/agent-*.jsonl` transcripts the walker already
# visits -- see parse_workflow_agent_dispatch below and accumulator.py's
# begin_file/observe handling of _pending_fanout_credit.
FANOUT_BY_TRANSCRIPT_TOOLS = {"Workflow"}
# Explicit plan-mode ceremony: the human chose to plan and a plan was produced before any
# code. EnterPlanMode = Cursor create_plan / switch_mode(plan); ExitPlanMode = Claude Code
# native plan mode (shift+tab -> present plan -> approve). These carry the same construct as
# a planning Skill, so they feed the QUALIFIED planning numerator too, not just the legacy
# union. TodoWrite deliberately does NOT: see PLAN_SIGNAL_TOOLS below.
PLAN_MODE_TOOLS = {"EnterPlanMode", "ExitPlanMode"}
# Plan-ceremony signal tools (a subset of PLAN_TOOLS): a plan was produced/tracked. Adds
# TodoWrite = Codex update_plan / Antigravity manage_task / Cursor todos — execution
# bookkeeping the agent maintains on its own, which earns "Ordered planning readiness" via
# the PLAN_MIN_STEPS distinct-step gate instead. TodoRead and the Task*/Worktree tools are
# reads/bookkeeping, not planning acts. Derived from PLAN_MODE_TOOLS so the two can't drift.
PLAN_SIGNAL_TOOLS = PLAN_MODE_TOOLS | {"TodoWrite"}
# Substrings that mark a Skill invocation as a planning skill (shared by the accumulator's
# per-session plan detection and scoring). Keep in sync with the planning intent.
PLAN_SKILL_NEEDLES = ("brainstorm", "writing-plan", "plan", "spec", "office-hours",
                      "autoplan", "grill", "ceo-review", "eng-review", "design-review",
                      # SDD planning phases run as Agent subagent_types (sdd-spec already
                      # matches "spec"); explore is grounding, not planning, so it's excluded.
                      "sdd-propose", "sdd-design", "sdd-tasks")
# Extend (never replace) the built-in needles from the environment, so custom planning-skill
# names are detectable without a code change. Comma-separated, e.g.
# GNOMON_PLAN_SKILL_NEEDLES="roadmap,my-planner". Mirrors config.py's env-var convention.
_extra_plan_needles = os.environ.get("GNOMON_PLAN_SKILL_NEEDLES", "")
if _extra_plan_needles:
    PLAN_SKILL_NEEDLES = PLAN_SKILL_NEEDLES + tuple(
        n.strip().lower() for n in _extra_plan_needles.split(",") if n.strip())
KNOWLEDGE_SKILL_NEEDLES = (
    "deep-research",
    "explore",
    "claude-api",
    "graphify",
    "codegraph",
    "find-docs",
    "find-skills",
    "explain-code",
)
_extra_knowledge_needles = os.environ.get("GNOMON_KNOWLEDGE_SKILL_NEEDLES", "")
if _extra_knowledge_needles:
    KNOWLEDGE_SKILL_NEEDLES = KNOWLEDGE_SKILL_NEEDLES + tuple(
        n.strip().lower() for n in _extra_knowledge_needles.split(",") if n.strip())
SCHEDULE_TOOLS = {"ScheduleWakeup", "CronCreate", "CronDelete", "CronList",
                  "RemoteTrigger", "PushNotification", "Monitor"}
SKILL_TOOLS = {"Skill"}
ASK_TOOLS = {"AskUserQuestion"}

# Eligibility/routing use the taxonomy's positive work classes, but remove
# orchestration ceremony and passive lifecycle polling from those classes.
# classify_tool intentionally keeps these tools visible in descriptive tool
# metrics; this narrower predicate answers whether a call is substantive work.
_NONSUBSTANTIVE_WORK_TOOLS = frozenset(
    PLAN_TOOLS | SCHEDULE_TOOLS | ASK_TOOLS
    | {"BashOutput", "KillShell", "ToolSearch", "TaskOutput", "TaskStop"}
)

KNOWN_CLIS = {
    "git", "gh", "npm", "npx", "yarn", "pnpm", "bun", "python", "python3", "pip",
    "pip3", "node", "deno", "cargo", "go", "rg", "grep", "sed", "awk", "find",
    "curl", "wget", "jq", "docker", "kubectl", "make", "xcodebuild", "pod", "expo",
    "eas", "supabase", "vercel", "psql", "sqlite3", "open", "cp", "mv", "rm",
    "mkdir", "ls", "cat", "chmod", "ssh", "brew", "tsc", "eslint", "prettier",
    "vitest", "jest", "pytest", "ruby", "swift", "ffmpeg",
}
_CLI_SPLIT = re.compile(r"&&|\|\||\||;|\bthen\b|\bdo\b")
_COMPOUNDING_RX = re.compile(
    r"CLAUDE\.md|AGENTS\.md|GEMINI\.md|/memory/|/docs/adr|\.cursorrules|/\.cursor/rules/", re.I)
# CLIs without a first-class Skill tool (Codex & friends) use skills by shelling out to
# read skills/<name>/SKILL.md — credit that as skill usage so they aren't under-read
_SKILL_MD_RX = re.compile(r"skills/([A-Za-z0-9_.-]+)/SKILL\.md")


def extract_skill_name_from_path(path):
    """Return the skill name when `path` points at skills/<name>/SKILL.md, else None."""
    if not path:
        return None
    m = _SKILL_MD_RX.search(str(path).replace("\\", "/"))
    return m.group(1) if m else None


# Matches a dispatched Workflow agent transcript path:
# `.../subagents/workflows/wf_<runId>/agent-<hash>.jsonl`. Group 1 is the PARENT
# session id (the directory that owns `subagents/`); group 2 is the dispatch
# identity encoded in the filename. Verified against a real corpus sample
# (2026-08-06): each event inside these files also carries the SAME value in its
# own `agentId` field, while the file's `sessionId` field is the PARENT's session
# id, not a distinct child identity -- `agentId` (falling back to this
# filename-derived value) is therefore the correct dedup key component, not
# `sessionId`. One level shallower, `.../subagents/agent-*.jsonl` (no
# `/workflows/wf_*/` segment) is a regular Agent/Task dispatch sidechain, which
# already counts via the 1-call==1-agent tool_use gate, and is deliberately
# excluded here to avoid double-crediting.
_WORKFLOW_AGENT_RX = re.compile(
    r'(?:^|/)([^/]+)/subagents/workflows/wf_[^/]+/agent-([^/]+)\.jsonl$'
)


def parse_workflow_agent_dispatch(path):
    """Return (parent_session_id, filename_agent_id) for a dispatched Workflow
    agent transcript path, else (None, None) when `path` doesn't match."""
    if not path:
        return None, None
    m = _WORKFLOW_AGENT_RX.search(_norm_path_seps(path))
    if not m:
        return None, None
    return m.group(1), m.group(2)

MCP_INSPECT_HINTS = ("read", "get", "list", "search", "find", "describe",
                     "snapshot", "screenshot", "query", "fetch", "whoami",
                     "details", "status", "info", "show", "doc_", "explore")

# Compounding credit for MCP knowledge-writes (contract 16:16:16): the positive
# mirror of MCP_INSPECT_HINTS above, scoped to knowledge-subcategory MCP servers.
# Symmetric-to-existing-design, not a novel taxonomy -- see
# is_mcp_knowledge_write's precedence rules.
MCP_WRITE_HINTS = ("add", "write", "store", "create", "update", "upsert",
                   "save", "remember", "persist")

# Knowledge-subcategory MCP servers that persist NOTHING -- doc/search fetchers
# only (context7 resolves library docs, exa is a web search MCP). A server-level
# DENYLIST checked before any write-hint match, so a future fetch-only tool leaf
# that happens to contain a write substring can never false-positive. Extensible.
MCP_FETCH_ONLY_KNOWLEDGE_SERVERS = ("context7", "exa")


def is_mcp_knowledge_write(server_name, tool_name=""):
    """True when an MCP call is BOTH knowledge-subcategory AND a genuine
    persistence write, for Compounding axis crediting. Strict precedence:
    1. classify_mcp_subcategory(server, tool) == "knowledge", else False.
    2. server not in MCP_FETCH_ONLY_KNOWLEDGE_SERVERS (substring match), else False.
    3. leaf matches any MCP_INSPECT_HINTS -> False (read-hint match wins).
    4. leaf matches any MCP_WRITE_HINTS -> True, else False.
    """
    if classify_mcp_subcategory(server_name, tool_name) != "knowledge":
        return False
    low_server = (server_name or "").lower()
    if any(needle in low_server for needle in MCP_FETCH_ONLY_KNOWLEDGE_SERVERS):
        return False
    low_tool = (tool_name or "").lower()
    if any(needle in low_tool for needle in MCP_INSPECT_HINTS):
        return False
    return any(needle in low_tool for needle in MCP_WRITE_HINTS)

# Two-layer MCP subcategory classification, grounded in awesome-mcp-servers ecosystem
# data (500+ servers, 51 categories) and validated against 62-user production corpus
# (neat-buzzard-863, 208 distinct servers, 87.5% classification rate).
MCP_SERVER_HINTS = {
    "knowledge": ("codegraph", "engram", "context7", "memory", "cortex",
                  "knowledge", "rag", "embedding", "lightrag", "mem0", "exa"),
    "browser": ("chrome", "browser", "playwright", "puppeteer", "selenium",
                "safari", "scraper", "devtools", "mobile", "argent",
                "computer_use", "computer-use"),
    "communication": ("slack", "discord", "teams", "email", "gmail",
                      "outlook", "telegram", "whatsapp", "calendar"),
    "project": ("linear", "jira", "asana", "monday", "github", "gitlab",
                "bitbucket", "trello", "shortcut", "atlassian", "confluence",
                "gitkraken", "dart"),
    "data": ("supabase", "postgres", "sqlite", "redis", "mongo", "notion",
             "drive", "box", "dropbox", "s3", "airtable", "firebase",
             "mysql", "convex", "lake", "toggl"),
    "infra": ("vercel", "aws", "gcp", "azure", "docker", "kubernetes",
              "sentry", "datadog", "grafana", "terraform", "heroku",
              "netlify", "cloudflare", "coolify", "dynatrace", "bugsee"),
    "design": ("figma", "canva", "penpot", "sketch", "storybook", "stitch",
               "pencil"),
    "automation": ("homeassistant", "automation", "cron", "zapier", "n8n",
                   "appium"),
}

MCP_TOOL_HINTS = {
    "knowledge": ("memory", "knowledge", "graph", "embedding", "rag",
                  "recall", "context"),
    "browser": ("browse", "navigate", "screenshot", "page", "click",
                "tab"),
    "communication": ("send_message", "post_message", "channel", "thread",
                      "chat", "dm"),
    "project": ("issue", "pull_request", "commit", "branch", "merge",
                "ticket", "sprint"),
    "data": ("query", "sql", "table", "migration", "schema", "collection",
             "database", "record"),
    "infra": ("deploy", "container", "log", "metric", "alert", "incident",
              "build"),
    "design": ("component", "design", "layout", "style", "asset", "frame"),
}

# MCP subcategories that arm Context Intelligence grounding when the tool call
# classifies as "explore" (read/query operations via MCP_INSPECT_HINTS).
# Knowledge MCPs arm unconditionally (handled separately in accumulator.py).
CI_CONTEXT_SUBCATS = frozenset({"project", "data", "design"})

# ---- Ordered-planning file taxonomy (C1/C2/C3) -----------------------------
# classify_change_target/is_plan_file_target back the ordered-planning eligibility
# and plan-detection redesign: a write's file TYPE decides whether it counts toward
# change-session eligibility (C2) and whether it counts as a plan artifact (C3).
_LOCKFILE_NAMES = frozenset({
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "npm-shrinkwrap.json",
    "cargo.lock", "poetry.lock", "pipfile.lock", "gemfile.lock", "go.sum",
    "composer.lock", "mix.lock", "flake.lock", "packages.lock.json",
})
_CODE_EXTS = frozenset({
    ".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".go", ".rb", ".java",
    ".kt", ".kts", ".swift", ".c", ".h", ".cpp", ".cc", ".hpp", ".rs", ".php",
    ".cs", ".scala", ".m", ".mm", ".vue", ".svelte", ".dart", ".ex", ".exs",
    ".sh", ".bash", ".zsh", ".sql", ".lua", ".r", ".pl", ".clj", ".elm",
})
_TEST_NAME_RX = re.compile(
    r'(^|[/_.-])tests?([/_.-]|$)|\.test\.[a-z]+$|\.spec\.[a-z]+$|_test\.[a-z]+$|'
    r'_spec\.[a-z]+$|^test_|(^|/)__tests__(/|$)|(^|/)spec(/|$)',
    re.I,
)
_DOC_EXTS = frozenset({".md", ".mdx", ".rst", ".txt", ".adoc"})
_DOC_NAMES = frozenset({"readme", "changelog", "license", "contributing", "authors"})
_CONFIG_EXTS = frozenset({
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".env",
    ".properties", ".xml",
})
_CONFIG_NAMES = frozenset({
    "dockerfile", "makefile", "vagrantfile", "procfile", "gemfile",
    ".gitignore", ".dockerignore", ".editorconfig", ".eslintrc",
    ".eslintrc.json", ".eslintrc.js", ".prettierrc",
})


def _norm_path_seps(path):
    """Windows transcripts record file paths with backslashes, inconsistently mixed with
    forward slashes for the same file. Every path pattern here is written with `/`, so
    normalize before matching (and before using a path as a dict key)."""
    return str(path or "").replace("\\", "/")


# The harness assigns a throwaway `scratchpad/` directory under an OS temp root; writes
# there are discarded by construction and must not count as real code changes regardless
# of file extension. We require BOTH a temp root AND the `scratchpad/` segment so a
# legitimate checkout that merely lives under a temp dir (e.g. /tmp/repo/src/a.py) is not
# misclassified as disposable. Temp roots, after `_norm_path_seps` rewrites backslashes:
#   POSIX / macOS: /tmp/... , /private/tmp/... , /var/folders/... , /private/var/folders/...
#                  (`/var` realpaths to `/private/var` on macOS, so both spellings appear)
#   Windows:       C:/Users/<u>/AppData/Local/Temp/... , C:/Windows/Temp/...
_EPHEMERAL_PATH_RX = re.compile(
    r'(?:^(?:/private)?/tmp/'
    r'|^(?:/private)?/var/folders/'
    r'|/appdata/local/temp/'
    r'|^[a-z]:/windows/temp/)'
    r'.*/scratchpad/',
    re.I)


def classify_change_target(path):
    """Classify a write target into code/test/doc/config/lockfile/other for
    change-session eligibility and file-type semantics.
    Order matters: lockfile and test checks run before the generic extension/
    name maps, since e.g. package-lock.json is a .json (config-looking) file
    and foo.test.ts has a code extension. Harness scratchpad paths short-circuit
    to "other" first: a scratchpad write is discardable, not a real code change."""
    if not path:
        return "other"
    path = _norm_path_seps(path)
    if _EPHEMERAL_PATH_RX.search(path):
        return "other"
    name = path.rsplit("/", 1)[-1]
    low = name.lower()
    if low in _LOCKFILE_NAMES:
        return "lockfile"
    ext = ""
    if "." in name:
        ext = "." + name.rsplit(".", 1)[-1].lower()
    if _TEST_NAME_RX.search(path):
        return "test"
    if ext in _CODE_EXTS:
        return "code"
    if ext in _DOC_EXTS or low.split(".")[0] in _DOC_NAMES:
        return "doc"
    if ext in _CONFIG_EXTS or low in _CONFIG_NAMES:
        return "config"
    return "other"


_PLAN_FILE_RX = re.compile(
    r'(^|/)\.claude/plans/[^/]*\.md$|(^|/)\.cursor/plans/|(^|/)\.context/[^/]*plan[^/]*$|'
    r'(^|/)plans/[^/]+\.(md|mdx|txt)$',
    re.I,
)


def is_plan_file_target(path):
    """True when a write target is a durable plan artifact on disk (C3/C4):
    `.claude/plans/*.md`, `.cursor/plans/`, `.context/*plan*`, or any
    `.md`/`.mdx`/`.txt` file directly inside a `plans/` directory at any depth
    (e.g. the superpowers `docs/**/plans/<n>-<name>.md` convention), regardless
    of filename — matched by taxonomy so cross-session credit (C4) can recognize
    hand-off plan files regardless of source CLI."""
    if not path:
        return False
    return bool(_PLAN_FILE_RX.search(_norm_path_seps(path)))


def classify_mcp_subcategory(server_name, tool_name=""):
    low = server_name.lower()
    for category, needles in MCP_SERVER_HINTS.items():
        if any(needle in low for needle in needles):
            return category
    if tool_name:
        tlow = tool_name.lower()
        for category, needles in MCP_TOOL_HINTS.items():
            if any(needle in tlow for needle in needles):
                return category
    return "other"


def classify_tool(name: str) -> str:
    if name in WRITE_TOOLS:
        return "produce"
    # Planning/workspace ceremony gets its own class, ahead of the explore branch it used
    # to share. It is neither exploring nor building: `plan` appears on NEITHER side of
    # planning_ratio_explore_to_doing, so entering plan mode or updating a todo list no
    # longer inflates the explore numerator — which matters now that plan mode also feeds
    # the separate Planning practice term, and one action must not pay twice in one axis.
    if name in PLAN_TOOLS:
        return "plan"
    if name in READ_TOOLS or name in DISCOVER_TOOLS:
        return "explore"
    if name in EXEC_TOOLS:
        return "execute"
    if name in DELEGATE_TOOLS:
        return "delegate"
    if name in SKILL_TOOLS:
        return "execute"
    if name in SCHEDULE_TOOLS:
        return "execute"
    if name in ASK_TOOLS:
        return "ask"
    if name.startswith("mcp__"):
        last = name.split("__")[-1].lower()
        if any(h in last for h in MCP_INSPECT_HINTS):
            return "explore"
        return "produce"
    return "other"


def is_substantive_tool(name: str) -> bool:
    """Whether a canonical tool call represents substantive project work."""
    name = str(name or "")
    if name in _NONSUBSTANTIVE_WORK_TOOLS:
        return False
    leaf = name.split("__")[-1].lower().replace("-", "_")
    if (leaf in {"status", "get_status", "check_status", "wait", "poll"}
            or leaf.endswith("_status")):
        return False
    return classify_tool(name) in {"produce", "explore", "execute", "delegate"}


_REDIR = re.compile(r'(?<!2)>{1,2}(?!\s*(?:/dev/null|&\d))')


def bash_writes_file(cmd):
    return bool(_REDIR.search(cmd)
                or re.search(r'<<(?!<)', cmd)            # heredoc, not a <<< here-string
                or re.search(r'\bsed\s+-i', cmd)
                or re.search(r'\btee\s+(?![>|])', cmd))   # tee to a file, not a process sub


_SHELL_TEST_RE = re.compile(
    r'(?:^|[\s;&|(/])('          # start / separator / '/' → so ./venv/bin/pytest, node_modules/.bin/jest match
    # Python
    r'pytest|py\.test|tox|nox|nosetests?|unittest|coverage\s+run|hypothesis'
    r'|hatch\s+(?:run\s+)?test|pdm\s+run\s+test|manage\.py\s+test'   # hatch test, pdm scripts, Django
    # JS/TS
    r'|jest|vitest|mocha|jasmine|ava|cypress|playwright\s+test|wtr|web-test-runner|karma'
    r'|(?:node|tsx)\s+(?:[^\s;&|)]+\s+)*?--test'                     # node/tsx built-in runner
    # Go / Rust
    r'|go\s+test|gotestsum|cargo\s+test|cargo\s+nextest'
    # Ruby
    r'|rspec|minitest|rails\s+test|rake\s+(?:test|spec)'
    # PHP
    r'|phpunit|pest|paratest|behat|php\s+artisan\s+test|composer\s+(?:run\s+)?test|codecept\s+run'
    # C/C++
    r'|ctest|gtest|catch2|make\s+(?:test|check)'
    # JVM: gradle (lazy args + optional ':module:' path + test-task token, camelCase only with
    # capital Test/Tests so testClasses/processTestResources/compileTestJava are rejected; bare
    # 'check' only as a full word so spotlessCheck is rejected), maven (wrapper + intermediate
    # args), detekt counted bare only (ideally it'd live under 'check', but Gradle users
    # run it standalone), sbt (optional 'it:' qualifier), scala-cli, lein.
    r'|(?:\./)?gradlew?\s+(?:[^\s;&|)]+\s+)*?(?::?[\w.-]+:)*(?:test|check|detekt|\w*Tests?)'
    r'|(?:\./)?mvnw?\s+(?:[^\s;&|)]+\s+)*?(?:test|verify|integration-test)'
    r'|sbt\s+(?:[^\s;&|)]+\s+)*?(?:[\w.:-]*:)?(?:test|testOnly)'
    r'|lein\s+(?:[^\s;&|)]+\s+)*?test|scala-cli\s+test'
    # .NET
    r'|dotnet\s+test|xunit|nunit'
    # package-manager script aliases (incl. 'npm t' / 'yarn t' shorthand)
    r'|(?:npm|yarn|pnpm|bun)\s+(?:run\s+)?(?:test|t)'
    # misc
    r'|bazel\s+test|elixir\s+test|mix\s+test|swift\s+test|flutter\s+test|deno\s+test|dart\s+test'
    r')(?=$|[\s;&|):])', re.I)   # trailing guard kills ava.json / nox/ / tox.ini / *cache; ':' keeps npm test:unit


def bash_runs_tests(cmd):
    return bool(_SHELL_TEST_RE.search(cmd or ""))


_SHELL_KNOWLEDGE_RE = re.compile(
    r'(?:^|[\s;&|(/])('
    r'codegraph\s+(?:explore|search|query)'
    r'|graphify'
    r'|gh\s+(?:issue|pr)\s+view'
    r')(?=$|[\s;&|):])',
    re.IGNORECASE,
)


def bash_runs_knowledge(cmd):
    return bool(_SHELL_KNOWLEDGE_RE.search(cmd or ""))


def _extract_clis(command):
    """Return the known-CLI heads invoked in a shell command (one per &&/|/;-separated part)."""
    found = []
    for part in _CLI_SPLIT.split(command or ""):
        toks = part.strip().split()
        i = 0
        while i < len(toks) and ("=" in toks[i] and not toks[i].startswith("-")):
            i += 1  # skip leading VAR=val env assignments
        if i < len(toks):
            head = toks[i].split("/")[-1]
            if head in KNOWN_CLIS:
                found.append(head)
    return found


def _is_compounding_path(path):
    """True if a write target is a compounding artifact (project memory / instructions / ADRs)."""
    return bool(path) and bool(_COMPOUNDING_RX.search(_norm_path_seps(path)))


def _canon_mcp_server(server, tool=""):
    """Normalize MCP server bucket names so plugin-wrapped Cursor tools collapse to the vendor.

    Cursor sometimes records `mcp__plugin__atlassian_atlassian_get_jira_issue` alongside
    `mcp__atlassian__get_jira_issue`; without this, mcp_servers_distinct is inflated."""
    s = str(server or "")
    if s.lower() != "plugin":
        return s
    t = str(tool or "").lower()
    m = re.match(r"^([a-z][a-z0-9-]*)_\1(?:_|$)", t)
    if m:
        return m.group(1)
    m = re.match(r"^([a-z][a-z0-9-]+?)_", t)
    if m and m.group(1) not in ("plugin", "tool", "get", "list", "search"):
        return m.group(1)
    return s


def _canon_tool(name):
    """Normalize Pi/opencode/Gemini lower-case tool names to the Claude-style taxonomy."""
    n = str(name or "tool")
    key = n.lower().replace("-", "_")
    leaf = key.rsplit(".", 1)[-1]
    mapping = {
        "bash": "Bash", "shell": "Bash", "exec": "Bash", "run": "Bash",
        "run_shell_command": "Bash",
        "read": "Read", "read_file": "Read",
        "grep": "Grep", "search_file_content": "Grep", "find_line_numbers": "Grep",
        "glob": "Glob", "list": "Glob", "ls": "Glob",
        "edit": "Edit", "patch": "Edit",
        "write": "Write", "write_file": "Write",
        "multi_edit": "MultiEdit",
        "todowrite": "TodoWrite", "todo_write": "TodoWrite", "todoread": "TodoRead",
        "task": "Agent", "agent": "Agent", "webfetch": "WebFetch", "web_fetch": "WebFetch",
        "websearch": "WebSearch", "web_search": "WebSearch",
    }
    if leaf in {"spawn_agent", "delegate", "dispatch_agent"}:
        return "Agent"
    return mapping.get(key, mapping.get(leaf, n))


def _canon_input(name, inp):
    """Normalize common argument names enough for churn/test metrics to work."""
    if not isinstance(inp, dict):
        return {}
    out = dict(inp)
    cname = _canon_tool(name)
    if cname == "Bash":
        out.setdefault("command", out.get("cmd") or out.get("command") or out.get("script") or "")
    elif cname in ("Read", "Write", "Edit", "MultiEdit"):
        if "filePath" in out and "file_path" not in out:
            out["file_path"] = out["filePath"]
        if "path" in out and "file_path" not in out:
            out["file_path"] = out["path"]
    if cname == "Write" and "content" not in out:
        out["content"] = out.get("text") or ""
    if cname == "Edit":
        out.setdefault("old_string", out.get("oldString") or out.get("old") or "")
        out.setdefault("new_string", out.get("newString") or out.get("new") or out.get("content") or "")
    if cname == "Agent":
        st = (out.get("subagent_type") or out.get("subagentType")
              or out.get("agent_type") or "general-purpose")
        if st in ("generalPurpose", "unspecified", ""):
            st = "general-purpose"
        out["subagent_type"] = st
    return out
