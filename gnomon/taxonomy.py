import re

WRITE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
READ_TOOLS = {"Read", "Grep", "Glob", "NotebookRead"}
DISCOVER_TOOLS = {"WebSearch", "WebFetch", "ToolSearch"}
EXEC_TOOLS = {"Bash", "BashOutput", "KillShell"}
DELEGATE_TOOLS = {"Agent", "Task"}
PLAN_TOOLS = {"TodoWrite", "TodoRead", "ExitPlanMode", "EnterPlanMode", "EnterWorktree",
              "ExitWorktree", "TaskCreate", "TaskUpdate", "TaskList", "TaskGet"}
# Plan-ceremony signal tools (a subset of PLAN_TOOLS): a plan was produced/tracked.
# EnterPlanMode = Cursor create_plan; ExitPlanMode = Claude Code native plan mode;
# TodoWrite = Codex update_plan / Antigravity manage_task / Cursor todos. TodoRead and
# the Task*/Worktree tools are reads/bookkeeping, not planning acts.
PLAN_SIGNAL_TOOLS = {"EnterPlanMode", "ExitPlanMode", "TodoWrite"}
# Substrings that mark a Skill invocation as a planning skill (shared by the accumulator's
# per-session plan detection and scoring). Keep in sync with the planning intent.
PLAN_SKILL_NEEDLES = ("brainstorm", "writing-plan", "plan", "spec", "office-hours",
                      "autoplan", "grill", "ceo-review", "eng-review", "design-review")
SCHEDULE_TOOLS = {"ScheduleWakeup", "CronCreate", "CronDelete", "CronList",
                  "RemoteTrigger", "PushNotification", "Monitor"}
SKILL_TOOLS = {"Skill"}
ASK_TOOLS = {"AskUserQuestion"}

KNOWN_CLIS = {
    "git", "gh", "npm", "npx", "yarn", "pnpm", "bun", "python", "python3", "pip",
    "pip3", "node", "deno", "cargo", "go", "rg", "grep", "sed", "awk", "find",
    "curl", "wget", "jq", "docker", "kubectl", "make", "xcodebuild", "pod", "expo",
    "eas", "supabase", "vercel", "psql", "sqlite3", "open", "cp", "mv", "rm",
    "mkdir", "ls", "cat", "chmod", "ssh", "brew", "tsc", "eslint", "prettier",
    "vitest", "jest", "pytest", "ruby", "swift", "ffmpeg",
}
_CLI_SPLIT = re.compile(r"&&|\|\||\||;|\bthen\b|\bdo\b")
_COMPOUNDING_RX = re.compile(r"CLAUDE\.md|AGENTS\.md|GEMINI\.md|/memory/|/docs/adr|\.cursorrules", re.I)
# CLIs without a first-class Skill tool (Codex & friends) use skills by shelling out to
# read skills/<name>/SKILL.md — credit that as skill usage so they aren't under-read
_SKILL_MD_RX = re.compile(r"skills/([A-Za-z0-9_.-]+)/SKILL\.md")

MCP_INSPECT_HINTS = ("read", "get", "list", "search", "find", "describe",
                     "snapshot", "screenshot", "query", "fetch", "whoami",
                     "details", "status", "info", "show", "doc_")


def classify_tool(name: str) -> str:
    if name in WRITE_TOOLS:
        return "produce"
    if name in READ_TOOLS or name in DISCOVER_TOOLS or name in PLAN_TOOLS:
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
    # args), detekt as a JVM verification task, sbt (optional 'it:' qualifier), scala-cli, lein.
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
    return bool(path) and bool(_COMPOUNDING_RX.search(path))


def _canon_tool(name):
    """Normalize Pi/opencode/Gemini lower-case tool names to the Claude-style taxonomy."""
    n = str(name or "tool")
    key = n.lower().replace("-", "_")
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
    return mapping.get(key, n)


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
    return out
