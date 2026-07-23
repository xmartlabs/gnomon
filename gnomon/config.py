import os
import re
from datetime import datetime


# Sandbox / self-hosted friendly: honor the same env vars the CLIs themselves use
# (CLAUDE_CONFIG_DIR, CODEX_HOME), and accept --<source>-dir=PATH overrides (see main())
# for histories copied off a sandbox, devcontainer, or remote box.
BASE = os.path.join(os.path.expanduser(os.environ.get("CLAUDE_CONFIG_DIR", "~/.claude")), "projects")
OUT_DIR = os.getcwd()


# Which presence-signals a source can even record on disk. Scoring uses this to avoid
# penalizing a tool for a signal it CANNOT emit (vs. "could, but the user didn't"): a
# sub-axis whose capability no present source supports is dropped and its weight is
# renormalized away, instead of scoring 0. Capabilities:
#   skills     - first-class Skill tool usage (attributionSkill / SKILL.md reads)
#   toolsearch - ToolSearch tool calls (Claude Code only)
#   tasktool   - TaskCreate/TaskUpdate task-tracking tools (Claude Code only)
#   delegate   - subagent delegation (the source can spawn agents at all). Without it the
#                Orchestration axis is DROPPED (not scored 0) so a no-fan-out source isn't penalized.
#   model      - persists a real per-turn model id (gates Savvy "Model mix"). Dropped when the
#                source masks it (Antigravity IDE) or when billing makes model choice irrelevant
#                to cost (Cursor: Composer 2.5 and every other included model cost 1 request).
#   thinking   - emits reasoning/thinking blocks (gates Planning "reasoning depth"). Antigravity
#                CLI doesn't, so that term drops there.
#   skill_reads - observable skill invocations without a first-class Skill tool (Cursor SKILL.md
#                 reads + manually_attached_skills; Codex shell-reads). Gates Craft review/compounding
#                 ceremony terms AND Skill fluency (which stays live when either `skills` or
#                 `skill_reads` is present).
# (errors are emitted by every source, so error_rate/recovery need no cap.)
SOURCE_CAPS = {
    "claude":   {"skills", "skill_reads", "toolsearch", "tasktool", "delegate", "model", "thinking", "linked_model_routing"},
    "codex":    {"skills", "skill_reads", "delegate", "model", "thinking", "linked_model_routing"},   # SKILL.md shell-reads; thread_spawn = delegate
    "gemini":   {"model", "thinking"},
    "antigravity": {"delegate", "skills", "skill_reads", "model"},   # CLI: real model; no separate thinking block
    "antigravity-ide": {"skills", "skill_reads", "thinking"},                 # IDE: masks model; no subagent/token
    "pi":       {"model", "thinking"},
    "opencode": {"model", "thinking"},
    "cursor":   {"delegate", "skill_reads", "thinking"},   # SKILL.md reads + manually_attached; no first-class Skill/ToolSearch/Task tool; model id recorded but not scored (flat request billing)
}
_ALL_CAPS = {"skills", "skill_reads", "toolsearch", "tasktool", "delegate", "model", "thinking", "linked_model_routing"}

# Whether a source adapter can authoritatively distinguish human-started root
# events from delegated child events.  Planning Skill Practice is scored only
# for measured sources; unknown/unsupported sources remain visible but cannot
# silently contribute a numeric value.
PLANNING_SESSION_SCOPE_BY_SOURCE = {
    "claude": "measured",
    "codex": "measured",
    "opencode": "measured",
    "cursor": "measured",
}


def planning_session_scope(source):
    return PLANNING_SESSION_SCOPE_BY_SOURCE.get(str(source or "").lower(), "unmeasured")


def available_caps(sources):
    """Union of capabilities across the sources present in this run. Unknown sources are
    assumed fully capable (don't silently strip signal for a source we haven't mapped)."""
    if not sources:
        return set(_ALL_CAPS)
    caps = set()
    for s in sources:
        caps |= SOURCE_CAPS.get(str(s).lower(), _ALL_CAPS)
    return caps


def parse_ts(ts):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone()
    except Exception:
        return None


def line_count(s):
    if not s:
        return 0
    if not isinstance(s, str):
        s = str(s)
    return s.count("\n") + (1 if s and not s.endswith("\n") else 0)


def strip_injections(text):
    """Remove injected wrappers so prompt length reflects what the human typed."""
    import re
    if not text:
        return ""
    text = re.sub(r"<system-reminder>.*?</system-reminder>", "", text, flags=re.S)
    text = re.sub(r"<command-name>.*?</command-name>", "", text, flags=re.S)
    text = re.sub(r"<command-message>.*?</command-message>", "", text, flags=re.S)
    text = re.sub(r"<command-args>.*?</command-args>", "", text, flags=re.S)
    text = re.sub(r"<local-command-stdout>.*?</local-command-stdout>", "", text, flags=re.S)
    return text.strip()


def pctile(sorted_vals, p):
    if not sorted_vals:
        return 0
    k = max(0, min(len(sorted_vals) - 1, int(round((p / 100) * (len(sorted_vals) - 1)))))
    return sorted_vals[k]


def _open_in_browser(path):
    """Best-effort: pop the finished profile in the default browser. Silent if it can't
    (headless / SSH / CI) — we just fall back to printing the path. Pass --no-open to skip."""
    try:
        import webbrowser
        if webbrowser.open("file://" + os.path.abspath(path)):
            print("  opened profile.html in your browser (pass --no-open to skip)")
            return
    except Exception:
        pass
    print("  open it yourself:", path)


def _pretty_model(m):
    # "claude-opus-4-7" -> "Opus 4.7"; "claude-3-5-sonnet-20241022" -> "Sonnet 3.5";
    # "gpt-5.4" -> "GPT 5.4"; "gpt-5-codex" -> "GPT 5 Codex"; "gemini-2.5-pro" -> "Gemini 2.5 Pro".
    # Cursor's own model ids: "default" = auto-routed pick, "composer-*" = Cursor's models,
    # bare "cursor" = token-only fallback when the session model id is missing.
    low = (m or "").lower()
    if low == "default":
        return "Cursor Auto"
    if low.startswith("composer"):
        return "Cursor " + " ".join(p.capitalize() for p in low.split("-"))
    s = re.sub(r"^claude-", "", m or "")
    s = re.sub(r"-\d{6,}$", "", s)              # drop trailing date snapshot
    parts = [p for p in s.split("-") if p]
    # A version token STARTS with a digit ("4", "5.4", "4.1", "2.5", "4o"); everything
    # else is a name/qualifier word ("opus", "gpt", "codex", "pro"). The old code kept
    # only pure-digit tokens, so dotted OpenAI/Gemini versions ("5.4", "2.5") were
    # dropped and distinct models (gpt-5.4, gpt-4.1) both collapsed to a bare "GPT".
    vers = [p for p in parts if p[:1].isdigit()]
    words = [p for p in parts if not p[:1].isdigit()]
    if not words:
        return m or "?"
    head = words[0]
    name = head.upper() if len(head) <= 3 else head.capitalize()
    # Claude splits its version across single-integer segments ("4","7" -> "4.7");
    # OpenAI/Gemini carry it in one dotted token ("5.4"). Join only the split case.
    if len(vers) >= 2 and all(v.isdigit() for v in vers):
        ver = ".".join(vers[:2])
    else:
        ver = vers[0] if vers else ""
    extra = " ".join(w.capitalize() for w in words[1:])
    return " ".join(t for t in (name, ver, extra) if t)


def _client_version():
    """Return the installed xl-ai-insights package version, or a fallback constant."""
    try:
        import importlib.metadata
        return importlib.metadata.version("xl-ai-insights")
    except Exception:
        return "0.1.0"
