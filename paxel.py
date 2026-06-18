#!/usr/bin/env python3
"""
paxel-local: a fully-local recreation of YC's Paxel builder-profile tool.

Paxel reads your AI coding-agent session transcripts and emits a "how you build
with AI" profile. The catch: it ships transcript-derived content to YC's LLM
proxy and uploads narratives + metadata to YC (readable by any YC employee,
retained indefinitely). This recreation does the same analysis with ZERO data
leaving your machine:

  - This script computes the metrics Paxel reports, deterministically, from
    ~/.claude/projects/**/*.jsonl  (Claude Code transcripts).
  - The qualitative half (Builder Archetype, Autonomy, standout traits) is written
    by YOUR OWN Claude/GPT session, reading narrative_input.md locally — i.e. the
    local stand-in for the LLM Paxel would otherwise send your data to.

Usage:
    python3 paxel.py            # reads ~/.claude/projects, writes outputs here

No dependencies beyond the Python 3 standard library. No NETWORK calls anywhere.
For accurate "gold-standard" churn it shells out to the local `git` CLI to read
`git log --numstat` on repos found in your transcripts — this captures every
committed change however it was made (Edit, Bash heredoc, sed, vim...), not just
the Edit/Write tool path. That git read is 100% on-device; nothing is uploaded.

Outputs (in this script's directory):
  - stats.json          machine-readable metrics
  - report.md           deterministic stats report (human-readable)
  - narrative_input.md  curated, LOCAL-ONLY excerpts for the narrative pass
                        (may contain names/PII from your prompts — keep local)

Sources: Claude Code, Codex CLI, Gemini CLI, Pi, opencode, and Cursor (auto-detected).
Google Antigravity is detected but not scored (transcripts live server-side; only
conversation metadata exists locally). Restrict with args, e.g. `python3 paxel.py
claude` for Claude-only; no args = all detected.

Sandbox / self-hosted: honors CLAUDE_CONFIG_DIR and CODEX_HOME, and accepts
--claude-dir=PATH / --codex-dir=PATH / --gemini-dir=PATH / --pi-dir=PATH /
--opencode-dir=PATH for histories mounted or copied from another machine.
One-shot; just re-run to rebuild as sessions accumulate.
"""

import json
import os
import glob
import math
import re
import sys
import sqlite3
import subprocess
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta

# ---- Stats dataclasses (ADR-0001: single-file) --------------------------------
# These declare the cross-stage shape of stats.json so the contract is explicit.
# main() builds a Stats instance then converts it to a plain dict via asdict()
# before any downstream code touches it.  Readers always use dict-indexing.

@dataclass
class CorpusBlock:
    sources: dict = field(default_factory=dict)
    files_parsed: int = 0
    lines_total: int = 0
    lines_unparseable: int = 0
    date_range: list = field(default_factory=list)
    window: dict = None
    span_days: int = 0
    active_days: int = 0
    timezone: str = ""
    # placeholder ({} from EventAccumulator.finalize); main() fills the real
    # antigravity_summary() value post-asdict (like the `agentic` field)
    antigravity_experimental: dict = field(default_factory=dict)

@dataclass
class VolumeBlock:
    total_sessions: int = 0
    total_prompts: int = 0
    command_invocations: int = 0
    avg_prompt_length_chars: float = 0.0
    median_prompt_length_chars: float = 0.0
    assistant_turns: int = 0
    tool_calls_total: int = 0
    thinking_blocks: int = 0

@dataclass
class ToolsBlock:
    tool_diversity: int = 0
    tool_entropy_normalized: float = 0.0
    mcp_calls: int = 0
    native_calls: int = 0
    mcp_share: float = 0.0
    top_tools: list = field(default_factory=list)
    category_breakdown: dict = field(default_factory=dict)
    mcp_servers: list = field(default_factory=list)
    mcp_servers_distinct: int = 0
    clis: list = field(default_factory=list)
    clis_distinct: int = 0
    cli_calls: int = 0
    toolsearch_calls: int = 0
    task_tool_calls: int = 0
    agent_calls: int = 0

@dataclass
class VelocityBlock:
    git_churn_total: int = 0
    git_insertions: int = 0
    git_deletions: int = 0
    git_commits_real: int = 0
    git_velocity_lines_per_hour: float = 0.0
    git_repos_with_commits: int = 0
    git_repos_seen: int = 0
    git_per_repo: list = field(default_factory=list)
    tool_churn_edit_write: int = 0
    tool_lines_added: int = 0
    tool_lines_removed: int = 0
    tool_velocity_lines_per_hour: float = 0.0
    shell_write_calls: int = 0
    shell_authored_lines_est: int = 0
    active_hours: float = 0.0
    git_commits_grep: int = 0

@dataclass
class BehaviorBlock:
    planning_ratio_explore_to_doing: float = 0.0
    explore_actions: int = 0
    produce_actions: int = 0
    execute_actions: int = 0
    delegate_actions: int = 0
    avg_session_minutes: float = 0.0
    median_session_minutes: float = 0.0
    longest_run_minutes: float = 0.0
    polite_prompts: int = 0
    error_recovery_ratio: float = 0.0
    error_rate_per_100_tools: float = 0.0
    tool_errors: int = 0
    recovered_errors: int = 0
    api_errors_retries: int = 0
    fanout_median: float = 0.0
    iteration_depth_mean: float = 0.0
    iteration_depth_median: float = 0.0
    iteration_depth_p90: float = 0.0
    iteration_depth_max: int = 0
    files_hammered_over_15x: int = 0
    actions_per_prompt: float = 0.0
    questions_asked: int = 0
    background_tasks: int = 0
    scheduled_actions: int = 0
    shell_test_runs: int = 0

@dataclass
class RhythmBlock:
    hour_histogram_local: dict = field(default_factory=dict)
    weekday_histogram: dict = field(default_factory=dict)
    peak_hours_local: list = field(default_factory=list)
    preferred_days: list = field(default_factory=list)

@dataclass
class ProgressionBlock:
    monthly: dict = field(default_factory=dict)

@dataclass
class StackBlock:
    models: list = field(default_factory=list)
    top_skills: list = field(default_factory=list)
    skills_distinct: int = 0
    skills_total: int = 0
    subagent_types_distinct: int = 0
    skills_all: list = field(default_factory=list)
    compounding_writes: dict = field(default_factory=dict)
    subagent_types: list = field(default_factory=list)
    top_projects: list = field(default_factory=list)

@dataclass
class AutonomyComponents:
    actions_per_prompt: float = 0.0
    delegation: float = 0.0
    scheduling_background: float = 0.0
    low_question_rate: float = 0.0

@dataclass
class AutonomyBlock:
    autonomy_score_0_100: float = 0.0
    components: AutonomyComponents = field(default_factory=AutonomyComponents)

@dataclass
class TokenUsageBlock:
    total_input: int = 0
    total_output: int = 0
    total_cache_read: int = 0
    total_cache_creation: int = 0
    by_model: list = field(default_factory=list)

@dataclass
class Stats:
    """Top-level shape of stats.json.  All blocks must match the dict assembled
    in main() exactly — the golden test enforces byte-equivalent output."""
    scope: str = ""
    generated_local_only: bool = True
    corpus: CorpusBlock = field(default_factory=CorpusBlock)
    volume: VolumeBlock = field(default_factory=VolumeBlock)
    tools: ToolsBlock = field(default_factory=ToolsBlock)
    velocity: VelocityBlock = field(default_factory=VelocityBlock)
    behavior: BehaviorBlock = field(default_factory=BehaviorBlock)
    rhythm: RhythmBlock = field(default_factory=RhythmBlock)
    progression: ProgressionBlock = field(default_factory=ProgressionBlock)
    stack: StackBlock = field(default_factory=StackBlock)
    autonomy: AutonomyBlock = field(default_factory=AutonomyBlock)
    token_usage: TokenUsageBlock = field(default_factory=TokenUsageBlock)
    # empty placeholder; filled post-asdict by compute_aq(stats), not via the dataclass
    agentic: dict = field(default_factory=dict)

# ---- end Stats dataclasses ---------------------------------------------------


def _zero_churn():
    """A fresh churn result with all git-derived values zeroed — used when finalize()
    is given churn=None (e.g. unit tests with no git repo). Built fresh per call so the
    mutable `per_repo` list is never aliased into output. Mirrors git_churn()'s shape."""
    return {
        "repos_seen": 0,
        "repos_with_commits": 0,
        "insertions": 0,
        "deletions": 0,
        "churn": 0,
        "commits": 0,
        "per_repo": [],
    }


class EventAccumulator:
    """Encapsulates main()'s accumulator state, per-file/event folding, and the
    final derivation into a Stats object. Behavior is a verbatim move of main()'s
    loop + derive + Stats assembly — see Task 2 of the refactor.

    Interface:
      consume_file(source, events) — fold one file's events (owns per-file reset +
                                     codex empty-seed skip + window event-drop)
      cwds()                       — project cwds seen (input to git_churn)
      window()                     — (since_iso, until_iso) for git_churn
      finalize(churn)              — derive metrics, return a Stats object (NOT asdict);
                                     churn=None => zero git velocity
      voice_samples()              — verbatim go-to / cryptic / crash-out + opening/
                                     longest prompts (LOCAL ONLY, never on stats.json)
    """

    GAP_CAP_S = 600                   # cap idle gaps at 10 min when summing active time
    BURST_GAP_S = 1800                # a gap > 30 min ends a contiguous work "run"

    def __init__(self, window=(None, None)):
        self._since, self._until = window

        # ---- accumulators ----------------------------------------------------
        self._files_parsed = 0
        self._lines_total = 0
        self._lines_bad = 0

        self._session_ts = defaultdict(list)   # sessionId -> [epoch seconds]
        self._session_files = defaultdict(set)
        self._file_seq = 0                      # per-consume_file identity counter

        self._prompts_count = 0
        self._polite_prompts = 0
        self._prompt_lengths = []
        self._phrase_counts = Counter()
        self._phrase_repr = {}
        self._phrase_sess = defaultdict(set)
        self._cryptic_cands = []
        self._crashout_cands = []
        self._command_invocations = 0

        self._assistant_turns = 0
        self._text_blocks = 0
        self._thinking_blocks = 0
        self._thinking_chars = 0
        self._tool_use_total = 0
        self._tool_counter = Counter()
        self._cat_counter = Counter()
        self._mcp_calls = 0
        self._native_calls = 0

        self._model_counter = Counter()
        self._skill_counter = Counter()
        self._subagent_counter = Counter()
        self._agents_per_session = defaultdict(int)
        self._mcp_server_counter = Counter()
        self._cli_counter = Counter()
        self._compounding_counter = 0
        self._project_activity = Counter()
        self._project_sessions = defaultdict(set)

        self._lines_added = 0
        self._lines_removed = 0
        self._edits_per_file_events = []
        self._git_commits = 0
        self._background_tasks = 0
        self._scheduled_actions = 0
        self._questions_asked = 0

        self._tool_errors = 0
        self._api_errors = 0
        self._recovered_errors = 0

        self._bash_write_calls = 0
        self._bash_authored_lines = 0
        self._shell_test_runs = 0

        self._hour_hist = Counter()
        self._weekday_hist = Counter()
        self._date_set = set()
        self._all_min_dt = None
        self._all_max_dt = None

        self._month_prompts = Counter()
        self._month_tools = Counter()
        self._month_churn = Counter()
        self._month_dates = defaultdict(set)
        self._month_sessions = defaultdict(set)
        self._month_models = defaultdict(Counter)

        _zero_tok = lambda: {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0}
        self._model_tokens = defaultdict(_zero_tok)
        self._month_tokens = defaultdict(_zero_tok)

        self._opening_prompts = []
        self._longest_prompts = []

        self._seen_session_open = set()
        self._source_files = Counter()
        self._source_sessions = defaultdict(set)
        self._source_prompts = Counter()

    def consume_file(self, source, events):
        """Fold one file's events. `source` is the source format/name (e.g. "claude",
        "codex"); `events` is an iterable of Claude-shaped event dicts (iter_events
        output). Owns the codex empty-seed skip, the per-file reset, and the
        since/until window event-drop."""
        cur_src = source
        since_dt, until_dt = self._since, self._until
        _ev_list = list(events)

        self._files_parsed += 1
        self._source_files[cur_src] += 1
        # per-file identity marker for session_files (a fallback session count when no
        # timestamps); main() uses the file path — any stable per-file token works.
        self._file_seq += 1
        _file_tok = self._file_seq

        # per-session, per-file ordered state for error-recovery + iteration depth
        pending_error = defaultdict(bool)
        file_edit_run = defaultdict(lambda: defaultdict(int))

        # Codex emits ~37k empty "seed" sessions (only injected wrappers + a 2+2 probe).
        # If a codex file has no genuine human prompt after filtering, skip it entirely so
        # it doesn't inflate session counts and drag the scores.
        if cur_src == "codex" and not any(
            e.get("type") == "user"
            and isinstance((e.get("message") or {}).get("content"), str)
            and (e.get("message") or {}).get("content", "").strip()
            for e in _ev_list
        ):
            self._source_files[cur_src] -= 1
            self._files_parsed -= 1
            return

        for ev in _ev_list:
            if ev.get("__bad__"):
                self._lines_bad += 1
                continue
            self._lines_total += 1

            etype = ev.get("type")
            sid = ev.get("sessionId")
            cwd = ev.get("cwd")
            dt = parse_ts(ev.get("timestamp"))
            if (since_dt is not None or until_dt is not None) and (
                    dt is None
                    or (since_dt is not None and dt < since_dt)
                    or (until_dt is not None and dt >= until_dt)):
                continue
            mkey = dt.strftime("%Y-%m") if dt is not None else None

            if dt is not None:
                _synth_ts = ev.get("__synth_ts__")
                if self._all_min_dt is None or dt < self._all_min_dt:
                    self._all_min_dt = dt
                if self._all_max_dt is None or dt > self._all_max_dt:
                    self._all_max_dt = dt
                if not _synth_ts:
                    self._hour_hist[dt.hour] += 1
                    self._weekday_hist[dt.weekday()] += 1
                self._date_set.add(dt.date().isoformat())
                self._month_dates[mkey].add(dt.date().isoformat())
                if sid:
                    if not _synth_ts:
                        self._session_ts[sid].append(dt.timestamp())
                    self._month_sessions[mkey].add(sid)
            if sid:
                self._session_files[sid].add(_file_tok)
                self._source_sessions[cur_src].add(sid)
            if cwd:
                self._project_activity[cwd] += 1
                if sid:
                    self._project_sessions[cwd].add(sid)

            msg = ev.get("message") if isinstance(ev.get("message"), dict) else None

            # ---- API error / retry events (system + assistant) ----------
            if ev.get("isApiErrorMessage") or ev.get("apiErrorStatus"):
                self._api_errors += 1
            if etype == "system" and ev.get("retryAttempt"):
                self._api_errors += 1

            # ---- genuine user prompts -----------------------------------
            if etype == "user" and msg is not None:
                if (ev.get("isMeta") or ev.get("isCompactSummary")
                        or ev.get("isVisibleInTranscriptOnly") or ev.get("isSidechain")):
                    pass  # injected / non-human / subagent-dispatch instruction
                else:
                    content = msg.get("content")
                    text = None
                    if isinstance(content, str):
                        text = content
                    elif isinstance(content, list):
                        parts = [b.get("text", "") for b in content
                                 if isinstance(b, dict) and b.get("type") == "text"]
                        if parts:
                            text = "\n".join(parts)
                    if text is not None:
                        is_command = ("<command-name>" in text or
                                      text.lstrip().startswith("<local-command"))
                        cleaned = strip_injections(text)
                        if is_command and not cleaned:
                            self._command_invocations += 1
                        elif cleaned:
                            self._prompts_count += 1
                            self._source_prompts[cur_src] += 1
                            if mkey:
                                self._month_prompts[mkey] += 1
                            self._prompt_lengths.append(len(cleaned))
                            if _POLITE_RE.search(cleaned):
                                self._polite_prompts += 1
                            _wc = len(cleaned.split())
                            if _safe_quote(cleaned) and 1 <= _wc <= 6:
                                _norm = re.sub(r"\s+", " ", cleaned.strip().lower()).strip("?.!,. ")
                                if len(_norm) >= 2:
                                    self._phrase_counts[_norm] += 1
                                    self._phrase_repr.setdefault(_norm, cleaned.strip())
                                    self._phrase_sess[_norm].add(sid)
                            if _safe_quote(cleaned):
                                if 3 <= _wc <= 14:
                                    _words = re.findall(r"[a-z']+", cleaned.lower())
                                    if _words and not all(w in _FILLER for w in _words):
                                        _csc = _cryptic_score(cleaned)
                                        if _csc >= 1.8:
                                            self._cryptic_cands.append((round(_csc, 2), cleaned.strip()))
                                if sum(c.isalpha() for c in cleaned) >= 6 and _wc <= 16:
                                    _bangs = cleaned.count("!") + cleaned.count("?")
                                    if _RAGE_RE.search(cleaned) or _bangs >= 2:
                                        _xsc = _crashout_score(cleaned, hour=dt.hour if dt else None)
                                        if _xsc >= 2.0:
                                            self._crashout_cands.append((round(_xsc, 2), cleaned.strip()))
                            if is_command:
                                self._command_invocations += 1
                            proj = os.path.basename(cwd) if cwd else "?"
                            if sid and sid not in self._seen_session_open:
                                self._seen_session_open.add(sid)
                                self._opening_prompts.append((dt, proj, cleaned[:600]))
                            self._longest_prompts.append((len(cleaned), proj, cleaned[:600]))
                            if len(self._longest_prompts) > 400:
                                self._longest_prompts.sort(key=lambda x: -x[0])
                                del self._longest_prompts[120:]

                # ---- tool results inside user turns ---------------------
                content = msg.get("content")
                if isinstance(content, list):
                    for b in content:
                        if isinstance(b, dict) and b.get("type") == "tool_result":
                            if b.get("is_error"):
                                self._tool_errors += 1
                                if sid:
                                    pending_error[sid] = True

            # ---- assistant turns ---------------------------------------
            elif etype == "assistant" and msg is not None:
                self._assistant_turns += 1
                mdl = msg.get("model")
                if mdl:
                    self._model_counter[mdl] += 1
                    if mkey:
                        self._month_models[mkey][mdl] += 1
                    # ---- token usage extraction (fully defensive) -------
                    _u = msg.get("usage") or {}
                    _ti  = _usage_int(_u, "input_tokens")
                    _to  = _usage_int(_u, "output_tokens")
                    _tcr = _usage_int(_u, "cache_read_input_tokens")
                    _tcc = _usage_int(_u, "cache_creation_input_tokens")
                    self._model_tokens[mdl]["input"]          += _ti
                    self._model_tokens[mdl]["output"]         += _to
                    self._model_tokens[mdl]["cache_read"]     += _tcr
                    self._model_tokens[mdl]["cache_creation"] += _tcc
                    if mkey:
                        self._month_tokens[mkey]["input"]          += _ti
                        self._month_tokens[mkey]["output"]         += _to
                        self._month_tokens[mkey]["cache_read"]     += _tcr
                        self._month_tokens[mkey]["cache_creation"] += _tcc
                if ev.get("attributionSkill"):
                    self._skill_counter[ev["attributionSkill"]] += 1
                content = msg.get("content")
                if isinstance(content, list):
                    for b in content:
                        if not isinstance(b, dict):
                            continue
                        bt = b.get("type")
                        if bt == "text":
                            self._text_blocks += 1
                        elif bt == "thinking":
                            self._thinking_blocks += 1
                            self._thinking_chars += len(b.get("thinking", "") or "")
                        elif bt == "tool_use":
                            name = b.get("name", "?")
                            inp = b.get("input", {}) if isinstance(b.get("input"), dict) else {}
                            self._tool_use_total += 1
                            self._tool_counter[name] += 1
                            if mkey:
                                self._month_tools[mkey] += 1
                            self._cat_counter[classify_tool(name)] += 1
                            if name.startswith("mcp__"):
                                self._mcp_calls += 1
                                parts = name.split("__")
                                if len(parts) > 1 and parts[1]:
                                    self._mcp_server_counter[parts[1]] += 1
                            else:
                                self._native_calls += 1

                            # a tool use after a pending error = recovery
                            if sid and pending_error.get(sid):
                                self._recovered_errors += 1
                                pending_error[sid] = False

                            if name == "Skill":
                                s = inp.get("skill")
                                if s:
                                    self._skill_counter[s] += 1
                            if name == "Agent":
                                st = inp.get("subagent_type", "general-purpose")
                                self._subagent_counter[st] += 1
                                if sid:
                                    self._agents_per_session[sid] += 1
                            if name in ASK_TOOLS:
                                self._questions_asked += 1
                            if inp.get("run_in_background"):
                                self._background_tasks += 1
                            if name in SCHEDULE_TOOLS:
                                self._scheduled_actions += 1

                            # ---- code churn + iteration depth ----------
                            if name == "Edit":
                                a = line_count(inp.get("new_string", ""))
                                r = line_count(inp.get("old_string", ""))
                                self._lines_added += a
                                self._lines_removed += r
                                if mkey:
                                    self._month_churn[mkey] += a + r
                                fpth = inp.get("file_path")
                                if sid and fpth:
                                    file_edit_run[sid][fpth] += 1
                                if _is_compounding_path(fpth):
                                    self._compounding_counter += 1
                            elif name == "Write":
                                a = line_count(inp.get("content", ""))
                                self._lines_added += a
                                if mkey:
                                    self._month_churn[mkey] += a
                                fpth = inp.get("file_path")
                                if sid and fpth:
                                    file_edit_run[sid][fpth] += 1
                                if _is_compounding_path(fpth):
                                    self._compounding_counter += 1
                            elif name == "MultiEdit":
                                for e in inp.get("edits", []) or []:
                                    if isinstance(e, dict):
                                        _ea = line_count(e.get("new_string", ""))
                                        _er = line_count(e.get("old_string", ""))
                                        self._lines_added += _ea
                                        self._lines_removed += _er
                                        if mkey:
                                            self._month_churn[mkey] += _ea + _er
                                fpth = inp.get("file_path")
                                if sid and fpth:
                                    file_edit_run[sid][fpth] += 1
                                if _is_compounding_path(fpth):
                                    self._compounding_counter += 1
                            elif name == "NotebookEdit":
                                self._lines_added += line_count(inp.get("new_source", ""))
                                fpth = inp.get("notebook_path")
                                if sid and fpth:
                                    file_edit_run[sid][fpth] += 1
                                if _is_compounding_path(fpth):
                                    self._compounding_counter += 1
                            elif name == "Bash":
                                cmd = inp.get("command", "") or ""
                                if isinstance(cmd, list):
                                    cmd = " && ".join(str(c) for c in cmd)
                                for _cli in _extract_clis(cmd):
                                    self._cli_counter[_cli] += 1
                                if cur_src != "claude":
                                    for _sm in _SKILL_MD_RX.finditer(cmd):
                                        self._skill_counter[_sm.group(1)] += 1
                                if bash_writes_file(cmd):
                                    self._bash_write_calls += 1
                                    self._bash_authored_lines += cmd.count("\n")
                                if bash_runs_tests(cmd):
                                    self._shell_test_runs += 1
                                if "git commit" in cmd:
                                    self._git_commits += 1
                                    # flush iteration-depth run for this session
                                    if sid in file_edit_run:
                                        for cnt in file_edit_run[sid].values():
                                            if cnt > 0:
                                                self._edits_per_file_events.append(cnt)
                                        file_edit_run[sid].clear()

        # end of file: flush any remaining edit runs as iteration-depth samples
        for sdict in file_edit_run.values():
            for cnt in sdict.values():
                if cnt > 0:
                    self._edits_per_file_events.append(cnt)

    def cwds(self):
        """Project cwds seen — the input to git_churn."""
        return list(self._project_activity.keys())

    def window(self):
        """(since_iso, until_iso) for git_churn, derived per main()'s logic: when a
        date window is active, churn covers the REQUESTED window; otherwise it spans
        the min/max of observed event timestamps."""
        since_dt, until_dt = self._since, self._until
        if since_dt is not None or until_dt is not None:
            gc_since = since_dt.strftime("%Y-%m-%d") if since_dt is not None else (
                self._all_min_dt.isoformat() if self._all_min_dt else "1970-01-01")
            gc_until = (until_dt.strftime("%Y-%m-%d")
                        if until_dt is not None else (self._all_max_dt.isoformat() if self._all_max_dt else "2100-01-01"))
        else:
            gc_since = self._all_min_dt.isoformat() if self._all_min_dt else "1970-01-01"
            gc_until = self._all_max_dt.isoformat() if self._all_max_dt else "2100-01-01"
        return (gc_since, gc_until)

    def voice_samples(self):
        """Verbatim go-to / cryptic / crash-out quotes + opening/longest prompts.
        LOCAL ONLY — these are never written to stats.json."""
        phrase_counts = self._phrase_counts
        phrase_repr = self._phrase_repr
        phrase_sess = self._phrase_sess
        goto = None
        for ph, cnt in phrase_counts.most_common(25):
            if cnt >= 3 and len(phrase_sess.get(ph, ())) >= 2:
                goto = (phrase_repr[ph], cnt, len(phrase_sess[ph]))
                break

        def _dedup_rank(cands):
            best = {}
            for sc, tx in cands:
                k = tx.lower()
                if k not in best or sc > best[k][0]:
                    best[k] = (sc, tx)
            return sorted(best.values(), key=lambda x: (-x[0], x[1]))
        cryptic_cands = _dedup_rank(self._cryptic_cands)
        crashout_cands = _dedup_rank(self._crashout_cands)

        def _quote_pool(cands, n=6, floor=0.5):
            if not cands:
                return []
            top = cands[0][0]
            return [tx for sc, tx in cands if sc >= top * floor][:n]
        rage_pool = _quote_pool([(sc, tx) for sc, tx in crashout_cands if len(tx.split()) <= 9])
        cuff_pool = _quote_pool(cryptic_cands)
        voice = {"goto": goto, "crashouts": rage_pool, "cryptics": cuff_pool}
        return {
            "voice": voice,
            "opening_prompts": self._opening_prompts,
            "longest_prompts": self._longest_prompts,
        }

    def finalize(self, churn):
        """Derive final metrics and assemble a Stats OBJECT (not asdict'd). `churn` is
        the git_churn() result dict; churn=None => all git-derived values are 0."""
        gc = churn if churn is not None else _zero_churn()

        # ---- derive ----------------------------------------------------------
        total_sessions = len(self._session_ts) or len(self._session_files)
        durations_min = []
        longest_burst_s = 0.0
        GAP_CAP_S = self.GAP_CAP_S
        BURST_GAP_S = self.BURST_GAP_S
        for ts_list in self._session_ts.values():
            ts_list.sort()
            active_s = 0.0
            for a, bnext in zip(ts_list, ts_list[1:]):
                active_s += min(bnext - a, GAP_CAP_S)
            durations_min.append(active_s / 60.0)
            bstart = bprev = None
            for t in ts_list:
                if bprev is None:
                    bstart = bprev = t
                elif t - bprev > BURST_GAP_S:
                    longest_burst_s = max(longest_burst_s, bprev - bstart)
                    bstart = bprev = t
                else:
                    bprev = t
            if bstart is not None:
                longest_burst_s = max(longest_burst_s, bprev - bstart)
        active_hours = sum(durations_min) / 60.0
        avg_session_min = statistics.mean(durations_min) if durations_min else 0
        median_session_min = statistics.median(durations_min) if durations_min else 0
        longest_run_min = longest_burst_s / 60.0

        avg_prompt_len = statistics.mean(self._prompt_lengths) if self._prompt_lengths else 0
        median_prompt_len = statistics.median(self._prompt_lengths) if self._prompt_lengths else 0

        total_churn = self._lines_added + self._lines_removed
        code_velocity = (total_churn / active_hours) if active_hours > 0 else 0

        git_velocity = (gc["churn"] / active_hours) if active_hours > 0 else 0

        explore = self._cat_counter.get("explore", 0) + self._thinking_blocks
        produce = self._cat_counter.get("produce", 0)
        execute = self._cat_counter.get("execute", 0)
        delegate = self._cat_counter.get("delegate", 0)
        doing = produce + execute + delegate
        planning_ratio = (explore / doing) if doing else 0

        tool_diversity = len(self._tool_counter)
        tot = sum(self._tool_counter.values()) or 1
        entropy = -sum((c / tot) * math.log2(c / tot) for c in self._tool_counter.values())
        norm_entropy = entropy / math.log2(tool_diversity) if tool_diversity > 1 else 0

        error_recovery_ratio = (self._recovered_errors / self._tool_errors) if self._tool_errors else 0
        error_rate_per_100_tools = (self._tool_errors / self._tool_use_total * 100) if self._tool_use_total else 0
        _fanouts = [n for n in self._agents_per_session.values() if n > 0]
        fanout_median = statistics.median(_fanouts) if _fanouts else 0
        _depths = sorted(self._edits_per_file_events)
        iteration_mean = statistics.mean(_depths) if _depths else 0
        iteration_median = statistics.median(_depths) if _depths else 0
        iteration_p90 = pctile(_depths, 90)
        iteration_max = max(_depths) if _depths else 0
        heavy_files = sum(1 for d in _depths if d > 15)

        actions_per_prompt = (self._tool_use_total / self._prompts_count) if self._prompts_count else 0
        auto_actions = min(actions_per_prompt / 25.0, 1.0) * 45
        auto_deleg = min(delegate / max(total_sessions, 1) / 1.5, 1.0) * 20
        auto_sched = min((self._scheduled_actions + self._background_tasks) / max(total_sessions, 1), 1.0) * 15
        auto_lowq = (1 - min(self._questions_asked / max(self._prompts_count, 1) * 6, 1.0)) * 20
        autonomy_score = round(auto_actions + auto_deleg + auto_sched + auto_lowq, 1)

        span_days = (self._all_max_dt - self._all_min_dt).days + 1 if (self._all_min_dt and self._all_max_dt) else 0
        active_days = len(self._date_set)

        DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        tzname = datetime.now().astimezone().tzname()
        tzoffset = datetime.now().astimezone().strftime("%z")

        peak_hours = [h for h, _ in self._hour_hist.most_common(3)]
        preferred_days = [DOW[d] for d, _ in self._weekday_hist.most_common(3)]

        since_dt, until_dt = self._since, self._until

        progression = []
        for mk in sorted(set(self._month_dates) | set(self._month_prompts) | set(self._month_tools) | set(self._month_tokens)):
            mm = self._month_models.get(mk, Counter())
            _mt = self._month_tokens.get(mk) or {}
            _ti  = _mt.get("input", 0)
            _to  = _mt.get("output", 0)
            _tcr = _mt.get("cache_read", 0)
            _tcc = _mt.get("cache_creation", 0)
            progression.append({
                "month": mk,
                "prompts": self._month_prompts.get(mk, 0),
                "tool_calls": self._month_tools.get(mk, 0),
                "sessions": len(self._month_sessions.get(mk, ())),
                "active_days": len(self._month_dates.get(mk, ())),
                "tool_churn_lines": self._month_churn.get(mk, 0),
                "models": mm.most_common(3),
                "top_model": mm.most_common(1)[0][0] if mm else None,
                "tokens_input": _ti,
                "tokens_output": _to,
                "tokens_cache_read": _tcr,
                "tokens_cache_creation": _tcc,
                "tokens_total": _ti + _to + _tcr + _tcc,
            })

        # ---- aggregate token_usage block ----------------------------------------
        _all_tok_input  = sum(v["input"]          for v in self._model_tokens.values())
        _all_tok_output = sum(v["output"]         for v in self._model_tokens.values())
        _all_tok_cr     = sum(v["cache_read"]     for v in self._model_tokens.values())
        _all_tok_cc     = sum(v["cache_creation"] for v in self._model_tokens.values())
        _by_model_tok = sorted(
            self._model_tokens.items(),
            key=lambda kv: kv[1]["input"] + kv[1]["output"] + kv[1]["cache_read"] + kv[1]["cache_creation"],
            reverse=True,
        )

        stats_obj = Stats(
            scope="Sources: " + (", ".join(sorted(self._source_files)) or "none"),
            generated_local_only=True,
            corpus=CorpusBlock(
                sources={s: {"files": self._source_files[s], "sessions": len(self._source_sessions[s]),
                             "prompts": self._source_prompts[s]} for s in sorted(self._source_files)},
                files_parsed=self._files_parsed,
                lines_total=self._lines_total,
                lines_unparseable=self._lines_bad,
                date_range=(
                    [since_dt.isoformat() if since_dt is not None else (self._all_min_dt.isoformat() if self._all_min_dt else None),
                     (until_dt - timedelta(days=1)).isoformat() if until_dt is not None else (self._all_max_dt.isoformat() if self._all_max_dt else None)]
                    if (since_dt is not None or until_dt is not None) else
                    [self._all_min_dt.isoformat() if self._all_min_dt else None,
                     self._all_max_dt.isoformat() if self._all_max_dt else None]
                ),
                window=({"since": since_dt.isoformat() if since_dt else None,
                         "until": until_dt.isoformat() if until_dt else None}
                        if (since_dt or until_dt) else None),
                span_days=span_days,
                active_days=active_days,
                timezone=f"{tzname} (UTC{tzoffset[:3]}:{tzoffset[3:]})",
                antigravity_experimental={},
            ),
            volume=VolumeBlock(
                total_sessions=total_sessions,
                total_prompts=self._prompts_count,
                command_invocations=self._command_invocations,
                avg_prompt_length_chars=round(avg_prompt_len, 1),
                median_prompt_length_chars=round(median_prompt_len, 1),
                assistant_turns=self._assistant_turns,
                tool_calls_total=self._tool_use_total,
                thinking_blocks=self._thinking_blocks,
            ),
            tools=ToolsBlock(
                tool_diversity=tool_diversity,
                tool_entropy_normalized=round(norm_entropy, 3),
                mcp_calls=self._mcp_calls,
                native_calls=self._native_calls,
                mcp_share=round(self._mcp_calls / (self._mcp_calls + self._native_calls), 3) if (self._mcp_calls + self._native_calls) else 0,
                top_tools=self._tool_counter.most_common(15),
                category_breakdown=dict(self._cat_counter),
                mcp_servers=self._mcp_server_counter.most_common(),
                mcp_servers_distinct=len(self._mcp_server_counter),
                clis=self._cli_counter.most_common(),
                clis_distinct=len(self._cli_counter),
                cli_calls=sum(self._cli_counter.values()),
                toolsearch_calls=self._tool_counter.get("ToolSearch", 0),
                task_tool_calls=self._tool_counter.get("TaskCreate", 0) + self._tool_counter.get("TaskUpdate", 0),
                agent_calls=self._tool_counter.get("Agent", 0),
            ),
            velocity=VelocityBlock(
                git_churn_total=gc["churn"],
                git_insertions=gc["insertions"],
                git_deletions=gc["deletions"],
                git_commits_real=gc["commits"],
                git_velocity_lines_per_hour=round(git_velocity, 1),
                git_repos_with_commits=gc["repos_with_commits"],
                git_repos_seen=gc["repos_seen"],
                git_per_repo=list(gc["per_repo"]),
                tool_churn_edit_write=total_churn,
                tool_lines_added=self._lines_added,
                tool_lines_removed=self._lines_removed,
                tool_velocity_lines_per_hour=round(code_velocity, 1),
                shell_write_calls=self._bash_write_calls,
                shell_authored_lines_est=self._bash_authored_lines,
                active_hours=round(active_hours, 1),
                git_commits_grep=self._git_commits,
            ),
            behavior=BehaviorBlock(
                planning_ratio_explore_to_doing=round(planning_ratio, 2),
                explore_actions=explore,
                produce_actions=produce,
                execute_actions=execute,
                delegate_actions=delegate,
                avg_session_minutes=round(avg_session_min, 1),
                median_session_minutes=round(median_session_min, 1),
                longest_run_minutes=round(longest_run_min, 1),
                polite_prompts=self._polite_prompts,
                error_recovery_ratio=round(error_recovery_ratio, 3),
                error_rate_per_100_tools=round(error_rate_per_100_tools, 1),
                tool_errors=self._tool_errors,
                recovered_errors=self._recovered_errors,
                api_errors_retries=self._api_errors,
                fanout_median=fanout_median,
                iteration_depth_mean=round(iteration_mean, 2),
                iteration_depth_median=round(iteration_median, 2),
                iteration_depth_p90=iteration_p90,
                iteration_depth_max=iteration_max,
                files_hammered_over_15x=heavy_files,
                actions_per_prompt=round(actions_per_prompt, 1),
                questions_asked=self._questions_asked,
                background_tasks=self._background_tasks,
                scheduled_actions=self._scheduled_actions,
                shell_test_runs=self._shell_test_runs,
            ),
            rhythm=RhythmBlock(
                hour_histogram_local={str(h): self._hour_hist.get(h, 0) for h in range(24)},
                weekday_histogram={DOW[d]: self._weekday_hist.get(d, 0) for d in range(7)},
                peak_hours_local=peak_hours,
                preferred_days=preferred_days,
            ),
            progression=ProgressionBlock(monthly=progression),
            stack=StackBlock(
                models=self._model_counter.most_common(),
                top_skills=self._skill_counter.most_common(15),
                skills_distinct=len(self._skill_counter),
                skills_total=sum(self._skill_counter.values()),
                subagent_types_distinct=len(self._subagent_counter),
                skills_all=self._skill_counter.most_common(),
                compounding_writes=self._compounding_counter,
                subagent_types=self._subagent_counter.most_common(10),
                top_projects=[(os.path.basename(p), c, len(self._project_sessions[p]))
                              for p, c in self._project_activity.most_common(12)],
            ),
            autonomy=AutonomyBlock(
                autonomy_score_0_100=autonomy_score,
                components=AutonomyComponents(
                    actions_per_prompt=round(auto_actions, 1),
                    delegation=round(auto_deleg, 1),
                    scheduling_background=round(auto_sched, 1),
                    low_question_rate=round(auto_lowq, 1),
                ),
            ),
            token_usage=TokenUsageBlock(
                total_input=_all_tok_input,
                total_output=_all_tok_output,
                total_cache_read=_all_tok_cr,
                total_cache_creation=_all_tok_cc,
                by_model=[
                    {
                        "model_id": m,
                        "model": _pretty_model(m),
                        "input": tok["input"],
                        "output": tok["output"],
                        "cache_read": tok["cache_read"],
                        "cache_creation": tok["cache_creation"],
                    }
                    for m, tok in _by_model_tok
                ],
            ),
        )
        return stats_obj

# Sandbox / self-hosted friendly: honor the same env vars the CLIs themselves use
# (CLAUDE_CONFIG_DIR, CODEX_HOME), and accept --<source>-dir=PATH overrides (see main())
# for histories copied off a sandbox, devcontainer, or remote box.
BASE = os.path.join(os.path.expanduser(os.environ.get("CLAUDE_CONFIG_DIR", "~/.claude")), "projects")
_script_dir = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = _script_dir if os.path.isdir(_script_dir) and not _script_dir.startswith("/dev") else os.getcwd()

# ---- tool taxonomy -----------------------------------------------------------
WRITE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
READ_TOOLS = {"Read", "Grep", "Glob", "NotebookRead"}
DISCOVER_TOOLS = {"WebSearch", "WebFetch", "ToolSearch"}
EXEC_TOOLS = {"Bash", "BashOutput", "KillShell"}
DELEGATE_TOOLS = {"Agent", "Task"}
PLAN_TOOLS = {"TodoWrite", "TodoRead", "ExitPlanMode", "EnterPlanMode", "EnterWorktree",
              "ExitWorktree", "TaskCreate", "TaskUpdate", "TaskList", "TaskGet"}
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

# verbs that mark an MCP tool as read/inspect rather than produce/act
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


# a Bash command writes/modifies a file if it redirects (not to /dev/null),
# uses a heredoc, sed -i, or tee — used to estimate shell-authored churn the
# Edit/Write tools never see.
_REDIR = re.compile(r'(?<!2)>{1,2}(?!\s*(?:/dev/null|&\d))')


def bash_writes_file(cmd):
    return bool(_REDIR.search(cmd)
                or re.search(r'<<(?!<)', cmd)            # heredoc, not a <<< here-string
                or re.search(r'\bsed\s+-i', cmd)
                or re.search(r'\btee\s+(?![>|])', cmd))   # tee to a file, not a process sub


# A Bash command that RUNS A TEST SUITE — so a builder who does TDD through the shell
# (pytest / go test / npm test …) isn't read as "0 test runs" just because they don't use a
# named gstack test-skill. Critical fix: skill-name-only detection was blind to CLI testing,
# the single most common way people actually test. Matches the runner invocation, not the
# bare word "test" (so it won't fire on "latest" or "git request").
_SHELL_TEST_RE = re.compile(
    r'(?:^|[\s;&|(/])('          # start / separator / '/' → so ./venv/bin/pytest, node_modules/.bin/jest match
    r'pytest|py\.test|tox|nox|nosetests?|unittest|coverage\s+run|hypothesis'
    r'|jest|vitest|mocha|jasmine|ava|cypress|playwright\s+test|wtr|web-test-runner|karma'
    r'|go\s+test|gotestsum|cargo\s+test|cargo\s+nextest'
    r'|rspec|minitest|rails\s+test|phpunit|pest'
    r'|ctest|gtest|catch2'
    r'|\./gradlew\s+(?:test|check)|gradle\s+(?:test|check)|mvn\s+(?:test|verify)'
    r'|dotnet\s+test|xunit|nunit'
    r'|(?:npm|yarn|pnpm|bun)\s+(?:run\s+)?test'
    r'|rake\s+(?:test|spec)|make\s+(?:test|check)'
    r'|bazel\s+test|elixir\s+test|mix\s+test|swift\s+test|flutter\s+test|deno\s+test'
    r'|hatch\s+run\s+test'
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


def _git(cwd, args, timeout=30):
    """Run a git command locally; return stdout or '' on any failure. Never raises."""
    try:
        p = subprocess.run(["git", "-C", cwd] + args, capture_output=True,
                           text=True, timeout=timeout)
        return p.stdout if p.returncode == 0 else ""
    except Exception:
        return ""


def git_churn(cwds, since_iso, until_iso):
    """Gold-standard churn: real insertions/deletions from `git log --numstat`,
    capturing EVERY committed change regardless of how it was made (Edit, Bash,
    vim, etc.). 100% local — git reads .git on disk, nothing is uploaded.
    Repos that are missing/non-git are reported as unavailable, not silently dropped.
    """
    # Dedupe by repo IDENTITY (root-commit SHA), not path — otherwise multiple
    # clones/worktrees of the same project (e.g. a fork + a worktree + a copy)
    # each contribute the same commits and inflate the total.
    tops = {}                       # identity -> toplevel path (first seen)
    for cwd in cwds:
        if not cwd or not os.path.isdir(cwd):
            continue
        top = _git(cwd, ["rev-parse", "--show-toplevel"]).strip()
        if not top:
            continue
        root = _git(top, ["rev-list", "--max-parents=0", "HEAD"]).split()
        if root:
            ident = "root:" + ",".join(sorted(root))
        else:
            remote = _git(top, ["config", "remote.origin.url"]).strip()
            ident = "remote:" + remote if remote else "path:" + top
        tops.setdefault(ident, top)
    per_repo, ins_tot, del_tot, commits_tot = [], 0, 0, 0
    for top in sorted(tops.values()):
        email = _git(top, ["config", "user.email"]).strip()
        args = ["log", "--numstat", "--no-merges",
                f"--since={since_iso}", f"--until={until_iso}",
                "--pretty=tformat:__C__"]
        if email:
            args.append(f"--author={email}")
        out = _git(top, args)
        ins = dels = commits = 0
        for ln in out.splitlines():
            if ln == "__C__":
                commits += 1
                continue
            parts = ln.split("\t")
            if len(parts) == 3:
                a, d, _ = parts
                if a.isdigit():
                    ins += int(a)
                if d.isdigit():
                    dels += int(d)
        if ins or dels or commits:
            per_repo.append((os.path.basename(top), ins, dels, commits))
            ins_tot += ins
            del_tot += dels
            commits_tot += commits
    per_repo.sort(key=lambda x: -(x[1] + x[2]))
    return {
        "repos_seen": len(tops),
        "repos_with_commits": len(per_repo),
        "insertions": ins_tot,
        "deletions": del_tot,
        "churn": ins_tot + del_tot,
        "commits": commits_tot,
        "per_repo": per_repo[:12],
    }


def pctile(sorted_vals, p):
    if not sorted_vals:
        return 0
    k = max(0, min(len(sorted_vals) - 1, int(round((p / 100) * (len(sorted_vals) - 1)))))
    return sorted_vals[k]


def _usage_int(usage, k):
    """Return usage[k] as int; handles str/float coercion; missing/None/bad → 0."""
    v = usage.get(k)
    if v is None:
        return 0
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


# Skills whose terminal name ends in "-review" but are PLANNING ceremonies, not
# verification — they live in plan_skills for the Planning pillar. Counting them as
# review would inflate Verification and fire the review-reflex edge for planners.
_PLANNING_REVIEW_TAILS = frozenset((
    "ceo-review", "eng-review", "design-review",
    "plan-eng-review", "plan-ceo-review", "plan-design-review",
))


def _is_review_skill_name(name):
    """True for actual review/verification skills, false for planning-review ceremonies.

    We want `code-review`, `requesting-code-review`, `verify`, `cerberus`, a bare
    terminal `review`, and any other `*-review` verification skill (e.g.
    `caveman-review`, `security-review`, `hand-review`) — but NOT planning ceremonies
    like `plan-eng-review` or `ceo-review`, which are planning rather than verification."""
    s = str(name or "").lower()
    if any(k in s for k in ("code-review", "requesting-code-review", "cerberus", "verify")):
        return True
    tail = s.split(":")[-1].split("/")[-1]
    if tail in _PLANNING_REVIEW_TAILS or tail.startswith("plan"):
        return False
    return tail == "review" or tail.endswith("-review")


def _review_skill_uses(skills):
    """Count only true review/verification skill invocations from a skills list."""
    return sum(n for k, n in skills if _is_review_skill_name(k))


# ---------------------------------------------------------------------------
# Multi-source discovery + translators. Each non-Claude format is translated
# into Claude-shaped event dicts so the single aggregation loop in main() works
# unchanged across tools. Every read is local — nothing is uploaded.
# Solid/tested: Claude Code, Codex CLI, Gemini CLI, Pi, opencode, Cursor.
# ---------------------------------------------------------------------------
CODEX_DIR = os.path.join(os.path.expanduser(os.environ.get("CODEX_HOME", "~/.codex")), "sessions")
GEMINI_DIR = os.path.expanduser("~/.gemini/tmp")
ANTIGRAVITY_DB = os.path.expanduser(
    "~/Library/Application Support/Antigravity/User/globalStorage/state.vscdb")
PI_DIR = os.path.expanduser("~/.pi/agent/sessions")
OPENCODE_DIR = os.path.expanduser("~/.local/share/opencode")
CURSOR_DIR = os.path.expanduser("~/.cursor/projects")


def _cursor_db_path():
    if sys.platform == "darwin":
        return os.path.expanduser("~/Library/Application Support/Cursor/User/globalStorage/state.vscdb")
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA", "")
        return os.path.join(appdata, "Cursor", "User", "globalStorage", "state.vscdb")
    return os.path.expanduser("~/.config/Cursor/User/globalStorage/state.vscdb")


CURSOR_DB = _cursor_db_path()
ALL_SOURCES = ("claude", "codex", "gemini", "pi", "opencode", "cursor")

# --<source>-dir=PATH → which module-level dir each flag overrides. For claude/codex the
# flag may point at either the config root (~/.claude) or the inner transcripts dir;
# _resolve_source_dir() picks the right one.
_DIR_FLAGS = {"claude": ("BASE", "projects"), "codex": ("CODEX_DIR", "sessions"),
              "gemini": ("GEMINI_DIR", None), "pi": ("PI_DIR", None),
              "opencode": ("OPENCODE_DIR", None), "cursor": ("CURSOR_DIR", "projects")}


def parse_window(argv, now=None):
    """Time-window flags → (since_dt, until_dt), tz-aware local datetimes, either None.

    --since=YYYY-MM-DD   inclusive start of window
    --until=YYYY-MM-DD   inclusive END DAY (internally exclusive next-midnight, so
                         --until=2026-03-31 keeps the whole 31st)
    --last=N[d|w|m]      rolling window ending now (d=days, w=weeks, m=30-day months);
                         overrides --since/--until

    Bad values warn and are ignored (same spirit as unknown sources/flags)."""
    since = until = None
    for a in argv:
        m = re.match(r"--(since|until)=(\d{4}-\d{2}-\d{2})$", a)
        if m:
            try:
                dt = datetime.fromisoformat(m.group(2)).astimezone()
            except ValueError:
                print(f"  warning: bad date in {a} ignored (use YYYY-MM-DD)")
                continue
            if m.group(1) == "since":
                since = dt
            else:
                until = dt + timedelta(days=1)
            continue
        if a.startswith(("--since=", "--until=")):
            print(f"  warning: bad date in {a} ignored (use YYYY-MM-DD)")
            continue
        m = re.match(r"--last=(\d+)([dwm]?)$", a)
        if m:
            days = int(m.group(1)) * {"": 1, "d": 1, "w": 7, "m": 30}[m.group(2)]
            end = now or datetime.now().astimezone()
            return end - timedelta(days=days), None    # open-ended: up to now
        if a.startswith("--last="):
            print(f"  warning: bad value in {a} ignored (use --last=N[d|w|m])")
    return since, until


def _resolve_source_dir(path, inner):
    """Accept a source dir override as either the tool's config root or the transcripts
    subdir itself (e.g. --claude-dir=~/.claude OR ~/.claude/projects)."""
    p = os.path.expanduser(path)
    if inner and os.path.isdir(os.path.join(p, inner)):
        return os.path.join(p, inner)
    return p


def discover_sources(selected):
    out = []
    if "claude" in selected and os.path.isdir(BASE):
        for fp in sorted(glob.glob(os.path.join(BASE, "**", "*.jsonl"), recursive=True)):
            out.append(("claude", fp, "claude"))
    if "codex" in selected and os.path.isdir(CODEX_DIR):
        for fp in sorted(glob.glob(os.path.join(CODEX_DIR, "**", "*.jsonl"), recursive=True)):
            out.append(("codex", fp, "codex"))
    if "gemini" in selected and os.path.isdir(GEMINI_DIR):
        for fp in sorted(glob.glob(os.path.join(GEMINI_DIR, "**", "*.json"), recursive=True)):
            out.append(("gemini", fp, "gemini"))
    if "pi" in selected and os.path.isdir(PI_DIR):
        for fp in sorted(glob.glob(os.path.join(PI_DIR, "**", "*.jsonl"), recursive=True)):
            out.append(("pi", fp, "pi"))
    if "opencode" in selected and os.path.isdir(OPENCODE_DIR):
        session_glob = os.path.join(OPENCODE_DIR, "storage", "session", "*", "*.json")
        for fp in sorted(glob.glob(session_glob)):
            out.append(("opencode", fp, "opencode"))
    if "cursor" in selected and os.path.isdir(CURSOR_DIR):
        for fp in sorted(_cursor_jsonl_files()):
            out.append(("cursor", fp, "cursor-jsonl"))
    if "cursor" in selected and os.path.isfile(CURSOR_DB):
        out.append(("cursor", CURSOR_DB, "cursor-sqlite"))
    return out


def _cursor_jsonl_files():
    """All agent-transcripts JSONL files: main sessions AND subagent sidechains
    (…/agent-transcripts/<session>/subagents/<id>.jsonl — one glob level deeper)."""
    main_pat = os.path.join(CURSOR_DIR, "**", "agent-transcripts", "*", "*.jsonl")
    sub_pat = os.path.join(CURSOR_DIR, "**", "agent-transcripts", "*", "subagents", "*.jsonl")
    return glob.glob(main_pat, recursive=True) + glob.glob(sub_pat, recursive=True)


def _cursor_dedup(sources):
    """Prefer the SQLite copy of a Cursor session over its JSONL transcript.

    The same modern session exists in BOTH places with complementary data: SQLite
    bubbles carry per-event timestamps and tool error statuses (JSONL has neither),
    while the JSONL carries full tool inputs — edit old/new strings the SQLite params
    omit — and the workspace path (via the project folder slug). So JSONL files whose
    session id is already a composer in state.vscdb are dropped from the event stream,
    and a twin map {sessionId: {"cwd", "jsonl"}} is forwarded to the SQLite reader,
    which backfills cwd and churn-bearing edit inputs from the twin.
    Subagent sidechains exist only as JSONL and are always kept.
    Returns (filtered sources, twin map)."""
    if not any(fmt == "cursor-jsonl" for _, _, fmt in sources):
        return sources, {}
    sqlite_ids = _cursor_sqlite_composer_ids(CURSOR_DB)
    twins = {}
    out = []
    for entry in sources:
        src, fp, fmt = entry
        if fmt != "cursor-jsonl":
            out.append(entry)
            continue
        sid, cwd, is_sidechain = _cursor_jsonl_meta(fp)
        if is_sidechain or sid not in sqlite_ids:
            out.append(entry)
        else:
            twins[sid] = {"cwd": cwd, "jsonl": fp}
    return out, twins


def _cursor_sqlite_composer_ids(db_path):
    """Composer (session) UUIDs present in state.vscdb; empty set if unreadable."""
    if not db_path or not os.path.isfile(db_path):
        return set()
    conn = _cursor_open_sqlite(db_path)
    if conn is None:
        return set()
    try:
        rows = conn.execute(
            "SELECT key FROM cursorDiskKV WHERE key LIKE 'composerData:%'").fetchall()
        return {k.split(":", 1)[-1] for (k,) in rows}
    except Exception:
        return set()
    finally:
        conn.close()


# ---- Google Antigravity (experimental) ----------------------------------------
# Antigravity keeps full transcripts server-side; the only local trace is a protobuf
# blob in state.vscdb (key jetskiStateSync.agentManagerInitState) holding conversation
# ids, titles and timestamps. We surface conversation count + date range as metadata —
# never folded into scores (no per-event data to grade honestly).

def _pb_varint(buf, i):
    val = shift = 0
    while i < len(buf):
        b = buf[i]; i += 1
        val |= (b & 0x7F) << shift
        if not b & 0x80:
            return val, i
        shift += 7
    raise ValueError("truncated varint")


def _pb_fields(buf):
    """Decode one protobuf message into [(field_no, wire_type, value)]. Raises on
    malformed input — callers treat any raise as 'not a message'."""
    i, out = 0, []
    while i < len(buf):
        key, i = _pb_varint(buf, i)
        f, w = key >> 3, key & 7
        if f == 0:
            raise ValueError("field 0")
        if w == 0:
            v, i = _pb_varint(buf, i)
        elif w == 1:
            v, i = buf[i:i + 8], i + 8
        elif w == 2:
            ln, i = _pb_varint(buf, i)
            if i + ln > len(buf):
                raise ValueError("truncated bytes")
            v, i = buf[i:i + ln], i + ln
        elif w == 5:
            v, i = buf[i:i + 4], i + 4
        else:
            raise ValueError(f"wire type {w}")
        out.append((f, w, v))
    return out


_UUID_RX = re.compile(rb"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def antigravity_summary():
    """Best-effort read of Antigravity's local conversation metadata. Returns
    {"conversations": n, "first": iso, "last": iso} or None. Fully local, read-only."""
    if not os.path.exists(ANTIGRAVITY_DB):
        return None
    try:
        import sqlite3
        import base64
        con = sqlite3.connect(f"file:{ANTIGRAVITY_DB}?mode=ro&immutable=1", uri=True)
        row = con.execute("SELECT value FROM ItemTable WHERE key="
                          "'jetskiStateSync.agentManagerInitState'").fetchone()
        con.close()
        if not row or not row[0]:
            return None
        raw = row[0]
        buf = base64.b64decode(raw if isinstance(raw, (bytes, bytearray)) else str(raw))
        tmin = tmax = None

        def _scan_ts(b, depth=0):
            nonlocal tmin, tmax
            if depth > 6:
                return
            for _f, w, v in _pb_fields(b):
                if w == 0 and 1.3e9 < v < 2.2e9:        # plausible unix seconds
                    ts = datetime.fromtimestamp(v).astimezone()
                    tmin = ts if tmin is None or ts < tmin else tmin
                    tmax = ts if tmax is None or ts > tmax else tmax
                elif w == 2:
                    try:
                        _scan_ts(v, depth + 1)
                    except Exception:
                        pass

        convs = 0
        for f, w, root in _pb_fields(buf):
            if f != 1 or w != 2:
                continue
            try:
                children = _pb_fields(root)
            except Exception:
                continue
            for cf, cw, cv in children:
                if cf != 1 or cw != 2:
                    continue
                try:
                    inner = _pb_fields(cv)
                except Exception:
                    continue
                # a conversation record leads with its uuid as field 1
                if any(g == 1 and gw == 2 and _UUID_RX.match(gv)
                       for g, gw, gv in inner):
                    convs += 1
                    _scan_ts(cv)
        if not convs:
            return None
        return {"conversations": convs,
                "first": tmin.isoformat() if tmin else None,
                "last": tmax.isoformat() if tmax else None}
    except Exception:
        return None


def _texts(content):
    """Join text from a Claude/Codex/Gemini/Pi/opencode content list (or plain string)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = []
        for b in content:
            if isinstance(b, dict):
                out.append(b.get("text") or b.get("input_text") or b.get("output_text") or "")
            elif isinstance(b, str):
                out.append(b)
        return "\n".join(x for x in out if x)
    return ""


def _iso_ms(ms):
    if ms is None:
        return None
    try:
        return datetime.fromtimestamp(float(ms) / 1000).astimezone().isoformat()
    except Exception:
        return None


def _canon_tool(name):
    """Normalize Pi/opencode lower-case tool names to the Claude-style taxonomy."""
    n = str(name or "tool")
    key = n.lower().replace("-", "_")
    mapping = {
        "bash": "Bash", "shell": "Bash", "exec": "Bash", "run": "Bash",
        "read": "Read", "grep": "Grep", "glob": "Glob", "list": "Glob", "ls": "Glob",
        "edit": "Edit", "patch": "Edit", "write": "Write", "multi_edit": "MultiEdit",
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


def iter_events(fp, fmt, cursor_twins=None):
    """Yield Claude-shaped event dicts for any supported source format."""
    if fmt == "claude":
        try:
            fh = open(fp, "r", errors="replace")
        except Exception:
            return
        with fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    yield {"__bad__": True}
                    continue
                yield obj if isinstance(obj, dict) else {"__bad__": True}
    elif fmt == "codex":
        yield from _codex_events(fp)
    elif fmt == "gemini":
        yield from _gemini_events(fp)
    elif fmt == "pi":
        yield from _pi_events(fp)
    elif fmt == "opencode":
        yield from _opencode_events(fp)
    elif fmt == "cursor-jsonl":
        yield from _cursor_jsonl_events(fp)
    elif fmt == "cursor-sqlite":
        yield from _cursor_sqlite_events(fp, cursor_twins)


def _codex_tool(p):
    """Map a Codex tool/function call to a Claude-shaped (name, input) tool_use."""
    pt = p.get("type")
    if pt == "web_search_call":
        return "WebSearch", {}
    name = p.get("name") or pt or "tool"
    try:
        args = json.loads(p.get("arguments") or "{}")
    except Exception:
        args = {}
    if not isinstance(args, dict):
        args = {}
    if pt == "local_shell_call" or name in ("exec_command", "shell", "local_shell", "bash"):
        return "Bash", {"command": args.get("cmd") or args.get("command") or str(p.get("action") or "")}
    if name in ("apply_patch", "patch", "edit_file", "write_file", "create_file"):
        return "Edit", {"new_string": args.get("patch") or args.get("content") or "",
                        "old_string": "", "file_path": args.get("path") or args.get("file") or ""}
    if name == "update_plan":          # Codex's plan tool ≈ Claude's TodoWrite
        return "TodoWrite", args
    if name == "write_stdin":          # input to a running shell ≈ BashOutput interaction
        return "BashOutput", {}
    return name, args


def _codex_is_injected(text):
    """True for Codex tooling wrappers (environment context, project instructions, turn
    notices, and the boot 'whats 2+2?' probe) that are sent as `user` messages but are
    NOT human prompts. Real task wrappers like <task> are NOT injected."""
    if not text:
        return False
    s = text.lstrip()
    if s.startswith(("<environment_context", "<user_instructions", "<turn_aborted")):
        return True
    if s.startswith("# AGENTS.md instructions for"):
        return True
    if s.rstrip().lower() in ("whats 2+2?", "what's 2+2?", "whats 2 + 2?"):
        return True
    return False


def _codex_events(fp):
    rows = []
    try:
        with open(fp, "r", errors="replace") as _f:
            for line in _f:
                line = line.strip()
                if line:
                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue
                    if isinstance(obj, dict):
                        rows.append(obj)
    except Exception:
        return
    sid = os.path.basename(fp).split(".")[0]
    cwd = None
    for ev in rows:                       # first pass: session id + working dir
        p = ev.get("payload") or {}
        if ev.get("type") == "session_meta":
            sid = p.get("id") or sid
            cwd = p.get("cwd") or cwd
        elif ev.get("type") == "response_item" and p.get("type") == "function_call":
            try:
                a = json.loads(p.get("arguments") or "{}")
                cwd = cwd or (a.get("workdir") if isinstance(a, dict) else None)
            except Exception:
                pass
    base = {"sessionId": sid, "cwd": cwd}
    model = None
    for ev in rows:
        # the active model lives in turn_context (e.g. "gpt-5.4"), not on the
        # response items — track it as we stream so assistant turns carry it and
        # Codex usage shows up in the Model mix instead of reading as model-less
        if ev.get("type") == "turn_context":
            model = (ev.get("payload") or {}).get("model") or model
            continue
        if ev.get("type") != "response_item":
            continue
        ts = ev.get("timestamp")
        p = ev.get("payload") or {}
        pt = p.get("type")
        if pt == "message":
            role = p.get("role")
            text = _texts(p.get("content"))
            if role == "user" and text and not _codex_is_injected(text):
                yield {**base, "type": "user", "timestamp": ts,
                       "message": {"role": "user", "content": text}}
            elif role == "assistant":
                yield {**base, "type": "assistant", "timestamp": ts,
                       "message": {"role": "assistant", "model": model,
                                   "content": [{"type": "text", "text": text}] if text else []}}
            # developer/system messages are tooling, not human prompts → skipped
        elif pt == "reasoning":
            yield {**base, "type": "assistant", "timestamp": ts,
                   "message": {"role": "assistant", "model": model,
                               "content": [{"type": "thinking",
                                            "thinking": _texts(p.get("content")) or p.get("summary") or ""}]}}
        elif pt in ("function_call", "local_shell_call", "custom_tool_call", "web_search_call"):
            name, inp = _codex_tool(p)
            yield {**base, "type": "assistant", "timestamp": ts,
                   "message": {"role": "assistant", "model": model,
                               "content": [{"type": "tool_use", "name": name, "input": inp}]}}
        elif pt == "function_call_output":
            out = p.get("output")
            is_err = isinstance(out, dict) and out.get("success") is False
            yield {**base, "type": "user", "timestamp": ts,
                   "message": {"role": "user",
                               "content": [{"type": "tool_result", "is_error": bool(is_err)}]}}


def _gemini_events(fp):
    try:
        with open(fp, "r", errors="replace") as _f:
            d = json.load(_f)
    except Exception:
        return
    if not isinstance(d, dict):
        return
    base = {"sessionId": d.get("sessionId") or os.path.basename(fp), "cwd": None}
    for m in d.get("messages") or []:
        if not isinstance(m, dict):
            continue
        ts = m.get("timestamp")
        role = m.get("type") or m.get("role")
        content = m.get("content")
        text = _texts(content)
        if role == "user" and text:
            yield {**base, "type": "user", "timestamp": ts,
                   "message": {"role": "user", "content": text}}
        elif role in ("gemini", "model", "assistant"):
            blocks = [{"type": "text", "text": text}] if text else []
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and isinstance(part.get("functionCall"), dict):
                        fc = part["functionCall"]
                        blocks.append({"type": "tool_use", "name": fc.get("name", "tool"),
                                       "input": fc.get("args") if isinstance(fc.get("args"), dict) else {}})
            yield {**base, "type": "assistant", "timestamp": ts,
                   "message": {"role": "assistant", "content": blocks}}


def _pi_blocks(content):
    blocks = []
    if isinstance(content, str):
        if content:
            blocks.append({"type": "text", "text": content})
        return blocks
    if not isinstance(content, list):
        return blocks
    for part in content:
        if not isinstance(part, dict):
            continue
        pt = part.get("type")
        if pt == "text" and part.get("text"):
            blocks.append({"type": "text", "text": part.get("text", "")})
        elif pt == "thinking":
            blocks.append({"type": "thinking", "thinking": part.get("thinking") or part.get("text") or ""})
        elif pt in ("toolCall", "tool_use"):
            name = _canon_tool(part.get("name"))
            inp = part.get("arguments") or part.get("input") or {}
            blocks.append({"type": "tool_use", "name": name, "input": _canon_input(name, inp)})
        elif pt == "tool_result":
            blocks.append({"type": "tool_result", "is_error": bool(part.get("is_error") or part.get("isError"))})
    return blocks


def _pi_events(fp):
    sid, cwd = os.path.basename(fp).split(".")[0], None
    try:
        with open(fp, "r", errors="replace") as _f:
            rows = [json.loads(line) for line in _f if line.strip()]
    except Exception:
        return
    for obj in rows:
        if isinstance(obj, dict) and obj.get("type") == "session":
            sid = obj.get("id") or sid
            cwd = obj.get("cwd") or cwd
            break
    base = {"sessionId": sid, "cwd": cwd}
    for obj in rows:
        if not isinstance(obj, dict) or obj.get("type") != "message":
            continue
        msg = obj.get("message") if isinstance(obj.get("message"), dict) else {}
        role = msg.get("role")
        ts = obj.get("timestamp") or _iso_ms(msg.get("timestamp"))
        if role == "user":
            text = _texts(msg.get("content"))
            if text:
                yield {**base, "type": "user", "timestamp": ts,
                       "message": {"role": "user", "content": text}}
        elif role == "assistant":
            yield {**base, "type": "assistant", "timestamp": ts,
                   "message": {"role": "assistant", "model": msg.get("model"),
                               "content": _pi_blocks(msg.get("content"))}}
        elif role == "toolResult":
            yield {**base, "type": "user", "timestamp": ts,
                   "message": {"role": "user",
                               "content": [{"type": "tool_result", "is_error": bool(msg.get("isError"))}]}}


def _opencode_events(fp):
    try:
        with open(fp, "r", errors="replace") as _f:
            sess = json.load(_f)
    except Exception:
        return
    if not isinstance(sess, dict):
        return
    sid = sess.get("id") or os.path.basename(fp).split(".")[0]
    cwd = sess.get("directory")
    msg_dir = os.path.join(OPENCODE_DIR, "storage", "message", sid)
    part_root = os.path.join(OPENCODE_DIR, "storage", "part")
    messages = []
    for mp in sorted(glob.glob(os.path.join(msg_dir, "*.json"))):
        try:
            with open(mp, "r", errors="replace") as _f:
                m = json.load(_f)
        except Exception:
            continue
        if isinstance(m, dict):
            messages.append(m)
    messages.sort(key=lambda m: (m.get("time") or {}).get("created") or 0)
    base = {"sessionId": sid, "cwd": cwd}
    for m in messages:
        mid = m.get("id")
        ts = _iso_ms((m.get("time") or {}).get("created"))
        parts = []
        for pp in sorted(glob.glob(os.path.join(part_root, str(mid), "*.json"))):
            try:
                with open(pp, "r", errors="replace") as _f:
                    p = json.load(_f)
            except Exception:
                continue
            if isinstance(p, dict):
                parts.append(p)
        parts.sort(key=lambda p: ((p.get("time") or {}).get("start") or 0, p.get("id") or ""))
        if m.get("role") == "user":
            texts = [p.get("text") for p in parts if p.get("type") == "text" and p.get("text")]
            if not texts:
                summ = m.get("summary") if isinstance(m.get("summary"), dict) else {}
                texts = [x for x in (summ.get("title"), summ.get("body")) if x]
            if texts:
                yield {**base, "type": "user", "timestamp": ts,
                       "message": {"role": "user", "content": "\n".join(texts)}}
        elif m.get("role") == "assistant":
            blocks, tool_results = [], []
            for p in parts:
                pt = p.get("type")
                if pt == "text" and p.get("text"):
                    blocks.append({"type": "text", "text": p.get("text", "")})
                elif pt == "reasoning":
                    blocks.append({"type": "thinking", "thinking": p.get("text", "")})
                elif pt == "tool":
                    st = p.get("state") if isinstance(p.get("state"), dict) else {}
                    name = _canon_tool(p.get("tool"))
                    inp = _canon_input(name, st.get("input") if isinstance(st.get("input"), dict) else {})
                    blocks.append({"type": "tool_use", "name": name, "input": inp})
                    is_err = st.get("status") not in (None, "completed") or bool(st.get("error"))
                    tool_results.append({"type": "tool_result", "is_error": is_err})
            yield {**base, "type": "assistant", "timestamp": ts,
                   "message": {"role": "assistant", "model": m.get("modelID"), "content": blocks}}
            if tool_results:
                yield {**base, "type": "user", "timestamp": ts,
                       "message": {"role": "user", "content": tool_results}}


# ---- Cursor: agent-transcripts JSONL + state.vscdb SQLite (deduped) ---------
# Keys are snake_case: the SQLite era uses snake_case names natively, and the modern
# JSONL CamelCase names (StrReplace, ReadLints, CallMcpTool, …) are snake_cased by
# _cursor_tool_name before lookup, so one table covers both generations.
_CURSOR_TOOL_MAP = {
    "run_terminal_command_v2": "Bash", "run_terminal_cmd": "Bash",
    "read_file_v2": "Read", "read_file": "Read",
    "edit_file_v2": "Edit", "edit_file": "Edit", "search_replace": "Edit",
    "str_replace": "Edit", "apply_patch": "Edit",
    "delete_file": "Edit", "delete": "Edit", "write_file": "Write",
    "glob_file_search": "Glob", "list_dir_v2": "Glob", "list_dir": "Glob",
    "ripgrep_raw_search": "Grep", "semantic_search_full": "Grep",
    "semantic_search": "Grep", "rg": "Grep",
    "web_search": "WebSearch", "web_fetch": "WebFetch",
    "task_v2": "Agent", "subagent": "Agent", "todo_write": "TodoWrite",
    "create_plan": "EnterPlanMode", "ask_question": "AskUserQuestion",
    "read_lints": "Read", "edit_notebook": "NotebookEdit",
    "await_shell": "BashOutput", "await": "BashOutput",
}

# Patch headers in an ApplyPatch payload, e.g. "*** Update File: src/foo.py"
_CURSOR_PATCH_FILE_RE = re.compile(r"^\*{3}\s*(?:Update|Add|Create|Delete)\s+File:\s*(.+)$", re.M)


def _cursor_project_cwd(project_slug):
    """Best-effort reverse of Cursor's project folder slug -> workspace path."""
    if not project_slug:
        return None
    norm = project_slug.replace("\\", "/")
    if norm.startswith("Users/") or norm.startswith("Users-"):
        return "/" + norm.replace("-", "/")
    if norm.startswith("home/") or norm.startswith("home-"):
        return "/" + norm.replace("-", "/")
    return None


def _cursor_jsonl_meta(fp):
    """Return (sessionId, cwd, is_sidechain) from an agent-transcripts path.
    Subagent transcripts (…/<session>/subagents/<id>.jsonl) attribute to the PARENT
    session id, mirroring Claude's sidechains-share-the-session semantics."""
    norm = fp.replace("\\", "/")
    sid = os.path.basename(fp).rsplit(".", 1)[0]
    is_sidechain = "/subagents/" in norm
    cwd = None
    parts = norm.split("/agent-transcripts/")
    if len(parts) == 2:
        proj = parts[0].rstrip("/").split("/")[-1]
        cwd = _cursor_project_cwd(proj)
        if is_sidechain:
            sid = parts[1].split("/")[0] or sid
    return sid, cwd, is_sidechain


# Harness-injected wrapper blocks that surround the human's words in Cursor JSONL user
# turns (attachments, skill manifests, linter dumps, …) — stripped so prompt length and
# the verbatim-quote cards reflect what the human actually typed.
_CURSOR_WRAPPER_RE = re.compile(
    r"<(attached_files|image_files|manually_attached_skills|available_skills|agent_skills|"
    r"external_links|code_selection|recently_viewed_files|open_and_recently_viewed_files|"
    r"linter_errors|system_notification|system_reminder|additional_data|user_info|"
    r"current_file|cursor_position|edit_history|timestamp)>.*?</\1>", re.S | re.I)


def _cursor_clean_prompt(text):
    if not text:
        return ""
    # The human-typed turn lives inside <user_query>…</user_query>; everything around it
    # is injected context. When the tag is present, keep ONLY its contents.
    found = re.findall(r"<user_query>(.*?)</user_query>", text, flags=re.S | re.I)
    if found:
        text = "\n".join(found)
    else:
        text = _CURSOR_WRAPPER_RE.sub("", text)
    return strip_injections(text).strip()


def _cursor_tool_key(name):
    """snake_case a Cursor tool name ('StrReplace' -> 'str_replace') for map lookup."""
    n = str(name or "tool")
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", n).lower().replace("-", "_")


def _cursor_tool_name(name):
    n = str(name or "tool")
    key = _cursor_tool_key(n)
    if key.startswith("mcp") and not key.startswith("mcp__"):
        return "mcp__" + n
    if n.startswith("mcp__"):
        return n
    mapped = _CURSOR_TOOL_MAP.get(key)
    if mapped:
        return mapped
    return _canon_tool(n)


def _cursor_tool_input(raw_name, raw):
    key = _cursor_tool_key(raw_name)
    if isinstance(raw, str):
        if key == "apply_patch":
            # ApplyPatch carries the raw patch text, not JSON — count it like Codex's
            # apply_patch (patch lines as added churn; diff markers over-count a bit).
            m = _CURSOR_PATCH_FILE_RE.search(raw)
            raw = {"new_string": raw, "old_string": "",
                   "file_path": m.group(1).strip() if m else ""}
        else:
            try:
                raw = json.loads(raw or "{}")
            except Exception:
                raw = {"raw": raw}
    if not isinstance(raw, dict):
        raw = {}
    cname = _cursor_tool_name(raw_name)
    inp = dict(raw)
    if cname == "Bash":
        inp.setdefault("command", inp.get("command") or "")
    elif cname in ("Read", "Write", "Edit", "MultiEdit"):
        fp = (inp.get("targetFile") or inp.get("file_path") or inp.get("path")
              or inp.get("filePath") or inp.get("relativeWorkspacePath"))
        if fp:
            inp["file_path"] = fp
        if cname == "Edit":
            inp.setdefault("new_string", inp.get("codeEdit") or inp.get("code")
                            or inp.get("new_string") or "")
            inp.setdefault("old_string", inp.get("old_string") or inp.get("oldString") or "")
        if cname == "Write":
            inp.setdefault("content", inp.get("contents") or inp.get("code") or "")
    return _canon_input(cname, inp)


def _cursor_tool(raw_name, raw_input):
    """Resolve a Cursor tool call to (canonical name, normalized input).
    CallMcpTool is special: the real MCP tool lives in the input (server/toolName),
    so it's renamed mcp__<server>__<tool> to count as an MCP call, not a native one."""
    inp = _cursor_tool_input(raw_name, raw_input)
    if _cursor_tool_key(raw_name) == "call_mcp_tool":
        server = str(inp.get("server") or "server")
        tool = str(inp.get("toolName") or inp.get("tool_name") or "tool")
        return f"mcp__{server}__{tool}", inp
    return _cursor_tool_name(raw_name), inp


def _cursor_jsonl_blocks(content):
    blocks = []
    if isinstance(content, str):
        if content:
            blocks.append({"type": "text", "text": content})
        return blocks
    if not isinstance(content, list):
        return blocks
    for part in content:
        if not isinstance(part, dict):
            continue
        pt = part.get("type")
        if pt == "text" and part.get("text"):
            blocks.append({"type": "text", "text": part.get("text", "")})
        elif pt == "thinking":
            blocks.append({"type": "thinking",
                            "thinking": part.get("thinking") or part.get("text") or ""})
        elif pt in ("tool_use", "toolCall"):
            raw_inp = part.get("input") or part.get("arguments") or {}
            name, inp = _cursor_tool(part.get("name"), raw_inp)
            blocks.append({"type": "tool_use", "name": name, "input": inp})
        elif pt == "tool_result":
            blocks.append({"type": "tool_result",
                           "is_error": bool(part.get("is_error") or part.get("isError"))})
    return blocks


def _cursor_jsonl_events(fp):
    sid, cwd, is_sidechain = _cursor_jsonl_meta(fp)
    base = {"sessionId": sid, "cwd": cwd}
    if is_sidechain:
        base["isSidechain"] = True
    # Real Cursor JSONL carries NO per-event timestamps (the SQLite copy of the same
    # session does — and is preferred). For JSONL-only sessions, stamp the FIRST event
    # with the file mtime so the session still lands on the calendar / time window,
    # without flooding the hour histogram with thousands of identical fake timestamps.
    mtime_iso = None
    try:
        mtime_iso = datetime.fromtimestamp(os.path.getmtime(fp)).astimezone().isoformat()
    except Exception:
        pass
    first = True
    try:
        fh = open(fp, "r", errors="replace")
    except Exception:
        return
    with fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                yield {"__bad__": True}
                continue
            if not isinstance(obj, dict):
                yield {"__bad__": True}
                continue
            role = obj.get("role")
            msg = obj.get("message") if isinstance(obj.get("message"), dict) else {}
            ts = obj.get("timestamp") or msg.get("timestamp")
            # Stamp EVERY timestampless event with the file mtime — not just the first —
            # so monthly/backfill date-window runs don't drop later prompts/tool calls of
            # a JSONL-only Cursor session (the window gate skips dt-None events). The first
            # event is the session's representative point and feeds the hour/weekday
            # histograms; later mtime-stamped events are flagged synthetic so they're
            # excluded from those histograms (avoiding a fake spike in one bucket) while
            # still being counted as prompts/tool calls inside the window.
            synth_ts = False
            if ts is None:
                ts = mtime_iso
                synth_ts = not first
            content = msg.get("content")
            if role == "user":
                text = _cursor_clean_prompt(_texts(content))
                if text:
                    first = False
                    yield {**base, "type": "user", "timestamp": ts, "__synth_ts__": synth_ts,
                           "message": {"role": "user", "content": text}}
            elif role == "assistant":
                blocks = _cursor_jsonl_blocks(content)
                tool_results = [b for b in blocks if b.get("type") == "tool_result"]
                blocks = [b for b in blocks if b.get("type") != "tool_result"]
                if blocks:
                    first = False
                    yield {**base, "type": "assistant", "timestamp": ts, "__synth_ts__": synth_ts,
                           "message": {"role": "assistant", "model": msg.get("model"),
                                       "content": blocks}}
                if tool_results:
                    yield {**base, "type": "user", "timestamp": ts, "__synth_ts__": synth_ts,
                           "message": {"role": "user", "content": tool_results}}
            elif role is None and obj.get("type") == "turn_ended":
                # status-only marker line; a failed turn is the closest thing the JSONL
                # format has to an API error signal ("aborted" = user stop, not an error)
                if str(obj.get("status") or "").lower() in ("error", "failed"):
                    yield {**base, "type": "system", "timestamp": ts, "__synth_ts__": synth_ts,
                           "isApiErrorMessage": True}


def _cursor_bubble_blocks(bubble):
    blocks = []
    text = bubble.get("text") or ""
    if text:
        blocks.append({"type": "text", "text": text})
    for tb in bubble.get("allThinkingBlocks") or []:
        if isinstance(tb, dict):
            t = tb.get("text") or tb.get("thinking") or ""
            if t:
                blocks.append({"type": "thinking", "thinking": t})
        elif isinstance(tb, str) and tb:
            blocks.append({"type": "thinking", "thinking": tb})
    tfd = bubble.get("toolFormerData")
    tool_meta = None
    if isinstance(tfd, dict) and tfd.get("name"):
        name, inp = _cursor_tool(tfd.get("name"), tfd.get("params"))
        blocks.append({"type": "tool_use", "name": name, "input": inp})
        st = str(tfd.get("status") or "completed").lower()
        if st in ("error", "failed"):
            tool_meta = True
        elif st in ("completed", "success", "done"):
            tool_meta = False
        # cancelled / aborted / interrupted: user stopped it — neither success nor error
    return blocks, tool_meta


def _cursor_open_sqlite(db_path):
    try:
        return sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except Exception:
        return None


def _cursor_jsonl_edit_inputs(fp):
    """Per-tool FIFO queues of churn-bearing inputs (Edit/Write/MultiEdit) from a
    session's JSONL twin. The SQLite copy of the same session stores only the edited
    file's path in its tool params — the old/new strings live ONLY in the JSONL — so
    the SQLite reader pops these to backfill churn, pairing nth Edit with nth Edit."""
    queues = defaultdict(list)
    for ev in _cursor_jsonl_events(fp):
        msg = ev.get("message")
        content = msg.get("content") if isinstance(msg, dict) else None
        if not isinstance(content, list):
            continue
        for b in content:
            if (isinstance(b, dict) and b.get("type") == "tool_use"
                    and b.get("name") in ("Edit", "Write", "MultiEdit")):
                queues[b["name"]].append(b.get("input") or {})
    return queues


def _cursor_sqlite_events(db_path, twins=None):
    conn = _cursor_open_sqlite(db_path)
    if conn is None:
        return
    twins = twins or {}
    try:
        rows = conn.execute(
            "SELECT key, value FROM cursorDiskKV WHERE key LIKE 'composerData:%'"
        ).fetchall()
    except Exception:
        conn.close()
        return
    for key, val in rows:
        composer_id = key.split(":", 1)[-1]
        try:
            meta = json.loads(val)
        except Exception:
            continue
        if not isinstance(meta, dict):
            continue
        headers = meta.get("fullConversationHeadersOnly") or []
        if not headers:
            continue
        # cwd comes from the JSONL twin's project slug — the DB stores no workspace path
        twin = twins.get(composer_id) or {}
        base = {"sessionId": composer_id, "cwd": twin.get("cwd")}
        edit_queues = _cursor_jsonl_edit_inputs(twin["jsonl"]) if twin.get("jsonl") else None
        for hdr in headers:
            if not isinstance(hdr, dict):
                continue
            bubble_id = hdr.get("bubbleId")
            if not bubble_id:
                continue
            bkey = f"bubbleId:{composer_id}:{bubble_id}"
            try:
                brow = conn.execute(
                    "SELECT value FROM cursorDiskKV WHERE key = ?", (bkey,)
                ).fetchone()
            except Exception:
                continue
            if not brow:
                continue
            try:
                bubble = json.loads(brow[0])
            except Exception:
                continue
            if not isinstance(bubble, dict):
                continue
            ts = bubble.get("createdAt")
            btype = hdr.get("type")
            if btype is None:
                btype = bubble.get("type")
            blocks, tool_err = _cursor_bubble_blocks(bubble)
            if edit_queues:
                for b in blocks:
                    if (b.get("type") == "tool_use" and b.get("name") in edit_queues
                            and not (b["input"].get("new_string") or b["input"].get("content")
                                     or b["input"].get("edits"))):
                        for k, v in edit_queues[b["name"]].pop(0).items():
                            if not b["input"].get(k):   # fill missing AND ""-normalized keys
                                b["input"][k] = v
                        if not edit_queues[b["name"]]:
                            del edit_queues[b["name"]]
            if btype == 1:
                text = _texts(blocks) or bubble.get("text") or ""
                if text:
                    yield {**base, "type": "user", "timestamp": ts,
                           "message": {"role": "user", "content": text}}
            elif btype == 2:
                if blocks:
                    yield {**base, "type": "assistant", "timestamp": ts,
                           "message": {"role": "assistant", "content": blocks}}
                if tool_err is not None:
                    yield {**base, "type": "user", "timestamp": ts,
                           "message": {"role": "user",
                                       "content": [{"type": "tool_result",
                                                    "is_error": bool(tool_err)}]}}
    conn.close()


# Politeness markers in your own prompts (for the "how polite are you" card). Word-boundaried.
_POLITE_RE = re.compile(r'\b(thanks|thank you|thank u|thx|please|pls|appreciate|'
                        r'much appreciated|good (?:job|work)|nice work|well done)\b', re.I)

# --- "In your own words" cards: pulled VERBATIM from your real prompts. These quote raw
# session text, so they render ONLY on the local page and are deliberately kept OUT of the
# shareable download card (see card_data). HTML-escape every quote before injecting it. ---
_TYPO_WORDS = {"teh", "hte", "thge", "wrok", "adn", "nad", "recieve", "seperate", "definately",
               "thier", "alot", "wtih", "wiht", "taht", "thta", "jsut", "becuase", "plz", "pls",
               "u", "ur", "r", "y", "k", "yea", "yeah", "yep", "yup", "nope", "lol", "lmao", "idk",
               "dont", "wont", "cant", "doesnt", "didnt", "couldnt", "wouldnt", "isnt", "wasnt",
               "youre", "theyre", "thats", "whats", "hows", "im", "ive", "ill", "id", "hes", "shes",
               "wodn", "fo", "ot", "si", "hmm", "hmmm", "wat", "wut", "tho", "thru", "fix", "undo",
               "nvm", "rn", "btw", "fr", "ok", "okay", "kk", "gah", "ugh", "argh", "oof",
               "wtf", "wth", "omg", "ya", "nah", "meh", "huh", "welp", "oop", "oops", "aight"}


def _typo_score(text):
    """Rough 'how garbled/casual is this' score — counts likely-typo / texting tokens.
    Heuristic, not a spell-checker; only used to surface a genuinely odd REAL prompt."""
    s = 0
    for t in re.findall(r"[a-z0-9']+", text.lower()):
        if t in _TYPO_WORDS:
            s += 1
        elif len(t) >= 4 and not re.search(r'[aeiou]', t):   # a vowel-less chunk
            s += 1
        elif re.search(r'(.)\1\1', t):                        # 3+ of the same letter (loool, yesss)
            s += 1
        elif re.search(r'[a-z]\d|\d[a-z]', t):                # digits glued into a word
            s += 1
        elif "'" not in t and t.endswith(("nt", "re", "ll", "ve")) and t in _TYPO_WORDS:
            s += 1                                            # missing apostrophe (dont, youre)
    return s


def _caps_ratio(text):
    letters = [c for c in text if c.isalpha()]
    return (sum(1 for c in letters if c.isupper()) / len(letters)) if letters else 0.0


# Frustration / distress markers for the "biggest crash-out" card — these gate it, so a
# clean all-caps EXCITEMENT prompt ("ONWARDS", "PUSH THRU") doesn't read as a meltdown.
_RAGE_RE = re.compile(r'\b(wtf|wth|ffs|ugh+|argh+|seriously|literally|stop+|nope|why+|'
                      r'are you (?:kidding|serious|sure|joking)|come on|for real|already said|'
                      r'i said|told you|do ?not|dont|cant|never|jesus|christ|damn|hell|crap|'
                      r'shit|fuck\w*|wrong|broke|broken|nightmare|stuck|fail\w*|hate|pressure|'
                      r'stress\w*|overwhelm\w*|dying|exhaust\w*|help|no+\b|not\b)\b', re.I)


def _crashout_score(text, hour=None):
    """How 'heated' a prompt reads — caps, exclamation pile-ups, ALLCAPS words, frustration
    words, and BREVITY (terse all-caps menace — 'NO STOP', 'SOMETHING IS WRONG' — is funnier
    than a long rant). A 2–6am prompt gets extra weight too: the witching-hour grind is its
    own genre of crash-out. Pulls a REAL prompt, never invents one."""
    wc = len(text.split())
    caps = _caps_ratio(text)
    bangs = min(text.count("!") + text.count("?"), 5)
    allcaps = min(len(re.findall(r'\b[A-Z]{3,}\b', text)), 4)
    rage = min(len(_RAGE_RE.findall(text)), 3)
    brevity = max(0, 9 - wc) * 0.5
    witching = 1.8 if hour is not None and 2 <= hour < 6 else 0   # 2–6am: posted from the trenches
    return caps * 2.5 + brevity + allcaps * 0.4 + rage * 0.5 + bangs * 0.3 + witching


_FEELS_RE = re.compile(r'\b(worried|scared|nervous|anxious|stressed|exhausted|confused|'
                       r'stupid|dumb|idiot|hopeless|unemploy\w*|crying|sobbing|sad|miserable|'
                       r'overwhelmed|panic\w*|dying|losing my mind|cant anymore|please work)\b', re.I)
_EMOTICON_RE = re.compile(r"[:;=]['\-^]?[\(\)\[\]\/\\|dpox3<>]", re.I)
# Content-free affirmations/fillers — an "off the cuff" card needs more than "yep :)".
_FILLER = {"ok", "okay", "yes", "yep", "yup", "yeah", "ya", "sure", "nice", "great", "cool",
           "perfect", "thanks", "thank", "you", "done", "k", "kk", "good", "awesome", "love",
           "got", "it", "this", "that", "lol", "haha", "nvm", "fine", "right", "correct", "exactly"}


def _cryptic_score(text):
    """The funniest off-the-cuff prompts: tiny, typo'd, lowercase, vague, and — the gold —
    a stray emoticon or a flash of human vulnerability ('Im worried im unemploybale :(')."""
    wc = len(text.split())
    typ = _typo_score(text)
    vague = len(re.findall(r'\b(it|that|this|the thing|those|them|stuff|one)\b', text, re.I))
    lower = 1 if text == text.lower() else 0
    nopunct = 1 if not re.search(r'[.?!]', text.strip()) else 0
    short = max(0, 7 - wc) * 0.25
    emo = 1.6 if _EMOTICON_RE.search(text) else 0
    feels = 1.3 if _FEELS_RE.search(text) else 0
    return typ * 1.0 + vague * 0.55 + lower * 0.5 + nopunct * 0.35 + short + emo + feels


# A prompt can be surfaced verbatim only if it's actually the user's words — not a harness
# marker, and not carrying a secret. We NEVER alter a shown prompt (Max: zero redaction); we
# just refuse to SELECT one that's a credential or a system artifact rather than a real prompt.
_SECRET_RE = re.compile(r'eyJ[A-Za-z0-9_\-]{20,}|sk-[A-Za-z0-9]{16,}|gh[posru]_[A-Za-z0-9]{16,}|'
                        r'AKIA[0-9A-Z]{12,}|Bearer\s+\S{16,}|[A-Fa-f0-9]{32,}|[A-Za-z0-9_\-]{36,}', re.I)
_SYS_MARKER_RE = re.compile(r'\[request interrupted|\[image\b|\[image\s*#|\[pasted|\[tool|'
                            r'<system|<command|<local-command|this block is not|tool_use|caveat:', re.I)


def _safe_quote(text):
    if not text or len(text) > 140:
        return False
    if _SYS_MARKER_RE.search(text) or _SECRET_RE.search(text):
        return False
    if any(len(tok) > 32 for tok in text.split()):   # a giant unbroken token = key/url/hash, not a word
        return False
    toks = text.split()
    if len(toks) == 1 and re.fullmatch(r"[A-Z0-9]*\d[A-Z0-9]*", toks[0]) and len(toks[0]) >= 7:
        return False                                  # a lone caps+digits token = Slack/ID, not a prompt
    # PII guard — don't auto-SURFACE someone else's email / phone / long digit run. (This is a
    # safe DEFAULT for arbitrary users; it never alters a prompt, it just won't select this one.)
    if re.search(r'[\w.+-]+@[\w-]+\.[a-z]{2,}|\b\d{3}[\s.\-]?\d{3}[\s.\-]?\d{4}\b|\b\d{6,}\b', text, re.I):
        return False
    return True


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


def main():
    # Sources to analyze: pass names as args (e.g. `python3 paxel.py claude`) to
    # restrict; default is every detected source. ("claude" keeps it to your own
    # Claude Code work; omit args to fold in Codex + Gemini too.)
    selected = [a.lower() for a in sys.argv[1:] if not a.startswith("-")] or list(ALL_SOURCES)
    unknown = [s for s in selected if s not in ALL_SOURCES]
    if unknown:
        print(f"  warning: unknown source(s) {unknown} ignored; valid: {', '.join(ALL_SOURCES)}")
    # --<source>-dir=PATH overrides for sandbox / self-hosted / copied histories
    # (e.g. --claude-dir=/mnt/sandbox-home/.claude). Env vars CLAUDE_CONFIG_DIR and
    # CODEX_HOME are honored too (applied at import; flags win).
    for a in sys.argv[1:]:
        m = re.match(r"--([a-z]+)-dir=(.+)$", a)
        if not m:
            continue
        src, path = m.group(1), m.group(2)
        if src not in _DIR_FLAGS:
            print(f"  warning: unknown flag {a} ignored; valid: "
                  + ", ".join(f"--{s}-dir=PATH" for s in _DIR_FLAGS))
            continue
        gname, inner = _DIR_FLAGS[src]
        resolved = _resolve_source_dir(path, inner)
        globals()[gname] = resolved
        if not os.path.isdir(resolved):
            print(f"  warning: --{src}-dir path not found: {resolved}")
    sources = discover_sources(selected)
    by_src = Counter(s for s, _, _ in sources)
    print(f"Found {len(sources)} transcript files across "
          f"{', '.join(f'{k}:{v}' for k, v in by_src.items()) or 'no sources'}")
    # Optional time window (--since/--until/--last): events outside it are skipped, so
    # every downstream metric — INCLUDING git churn, whose since/until follow the kept
    # events' date range — reads the same window. Timestampless events are DROPPED when
    # a window is active (they can't honor "this period only"); Cursor JSONL-only
    # sessions ride their single file-mtime timestamp.
    since_dt, until_dt = parse_window(sys.argv[1:])
    if since_dt or until_dt:
        print(f"  window: {since_dt.date() if since_dt else '…'} → "
              f"{(until_dt - timedelta(days=1)).date() if until_dt else 'now'}")
    sources, cursor_twins = _cursor_dedup(sources)
    antigravity = antigravity_summary()
    if antigravity:
        print(f"  note: Google Antigravity detected — {antigravity['conversations']} conversations "
              f"(metadata only; transcripts live server-side, so it can't be scored)")
    if not sources:
        print("\n  No transcripts found in ~/.claude/projects, ~/.codex/sessions, "
              "~/.gemini/tmp, ~/.pi/agent/sessions, ~/.local/share/opencode/storage, "
              "or ~/.cursor/projects.")
        print("  Nothing to analyze — run this where you've actually used a coding agent.")
        return

    # ---- accumulate ----------------------------------------------------------
    # main() is a thin feed over EventAccumulator: discovery + I/O skips + progress
    # prints stay here; per-file/event folding, derivation, and Stats assembly live in
    # the accumulator (golden-safe verbatim move — see Task 2/3 of the refactor).
    acc = EventAccumulator(window=(since_dt, until_dt))
    _files_fed = 0   # local, progress-print only; authoritative count is corpus.files_parsed
    for cur_src, fp, fmt in sources:
        # mtime pre-filter: a file last written before the window start can't contain
        # in-window events — skip the parse entirely (big win on ~38k codex seeds).
        # No mtime skip for --until: old events can live in recently-written files.
        if since_dt is not None:
            try:
                if datetime.fromtimestamp(os.path.getmtime(fp)).astimezone() < since_dt:
                    continue
            except OSError:
                pass
        _files_fed += 1
        if _files_fed % 300 == 0:
            print(f"  ...{_files_fed}/{len(sources)}")
        # iter_events() yields Claude-shaped event dicts for every source format,
        # so the accumulator's per-event logic is identical across all sources.
        acc.consume_file(cur_src, iter_events(fp, fmt, cursor_twins=cursor_twins))

    churn = git_churn(acc.cwds(), *acc.window())
    stats_obj = acc.finalize(churn)
    stats = asdict(stats_obj)
    # finalize() has no antigravity input (sets {} as a placeholder); inject the real
    # value computed above. metadata only — never folded into scores.
    stats["corpus"]["antigravity_experimental"] = antigravity
    stats["agentic"] = compute_aq(stats)
    _vs = acc.voice_samples()
    opening_prompts = _vs["opening_prompts"]
    longest_prompts = _vs["longest_prompts"]
    voice = _vs["voice"]

    with open(os.path.join(OUT_DIR, "stats.json"), "w") as f:
        json.dump(stats, f, indent=2, default=str)

    if "--summary" in sys.argv:
        with open(os.path.join(OUT_DIR, "summary.json"), "w") as f:
            json.dump(build_summary(stats), f, indent=2, default=str)
        print("  wrote summary.json (shareable subset — measured metrics + monthly progression)")

    write_report(stats)
    write_narrative_input(stats, opening_prompts, longest_prompts)
    scores = compute_scores(stats)
    archetype, quote = pick_archetype(stats, scores)
    # "In your own words" voice quotes (go-to / cryptic / crash-out) are computed by the
    # accumulator and pulled above (acc.voice_samples()) — VERBATIM, never in stats.json.
    write_profile_html(stats, archetype, quote, scores, voice)
    print("\nWrote stats.json, report.md, narrative_input.md, profile.html to", OUT_DIR)
    if "--no-open" not in sys.argv:
        _open_in_browser(os.path.join(OUT_DIR, "profile.html"))
    # closing summary — re-read from the assembled stats (single source of truth)
    _c = stats["corpus"]; _v = stats["volume"]; _vel = stats["velocity"]; _b = stats["behavior"]
    print(f"  archetype: {archetype}  scores: {scores}")
    print(f"  sources: " + ", ".join(f"{s}({d['files']}f/{d['sessions']}s)"
                                      for s, d in (_c.get("sources") or {}).items()))
    print(f"  sessions={_v['total_sessions']}  prompts={_v['total_prompts']}  tool_calls={_v['tool_calls_total']}")
    print(f"  git churn={_vel['git_churn_total']:,} lines (gold std, {_vel['git_repos_with_commits']}/{_vel['git_repos_seen']} repos)  "
          f"vs tool-only={_vel['tool_churn_edit_write']:,}  git velocity={_vel['git_velocity_lines_per_hour']:.0f} ln/hr")
    print(f"  iteration depth: mean {_b['iteration_depth_mean']:.1f} / max {_b['iteration_depth_max']} ({_b['files_hammered_over_15x']} files >15x)  "
          f"errors={_b['tool_errors']} ({_b['error_rate_per_100_tools']:.1f}/100 tools)")
    print(f"  autonomy={stats['autonomy']['autonomy_score_0_100']}/100  planning_ratio={_b['planning_ratio_explore_to_doing']:.2f}")


def _build_profile(stats):
    """Assemble the `profile` sub-dict for build_summary: level, per-axis scores with
    explainable drill-down, archetype, and steering style. All values are computed or
    count-based — no prompts, no verbatim quotes, no skill/project names beyond what
    compute_aq already exposes. Defensive: if stats lacks the grading keys (e.g. a
    zero-activity corpus) it still returns a well-formed dict."""
    aq = stats.get("agentic", {})
    sb = score_breakdown(stats)
    arch_scores = {
        "Execution": sb["execution"]["value"],
        "Planning": sb["planning"]["value"],
        "Engineering": sb["engineering"]["value"],
    }
    arch_title, arch_quote = pick_archetype(stats, arch_scores)
    all_models = (stats.get("stack") or {}).get("models") or []
    # pct is a GLOBAL share: total counts ALL models, then we cap the list to the
    # top 12 for payload size. So if >12 models exist the shown pcts sum to <1
    # (the dropped tail is honestly missing), never an inflated 100%.
    total = sum(n for _, n in all_models)
    _tok_by_model = {e["model_id"]: e for e in (stats.get("token_usage") or {}).get("by_model") or []}
    model_usage = (
        [
            {
                "model_id": m,
                "model": _pretty_model(m),
                "count": int(n),
                "pct": round(n / total, 3),
                "tokens_input":          (_tok_by_model.get(m) or {}).get("input", 0),
                "tokens_output":         (_tok_by_model.get(m) or {}).get("output", 0),
                "tokens_cache_read":     (_tok_by_model.get(m) or {}).get("cache_read", 0),
                "tokens_cache_creation": (_tok_by_model.get(m) or {}).get("cache_creation", 0),
            }
            for m, n in all_models[:12]  # most_common() already desc
        ]
        if total > 0 else []
    )
    return {
        "aq": aq,
        "archetype": {"title": arch_title, "quote": arch_quote},
        "scores": sb,
        "steering": steering_reading(stats),
        "growth_edges": growth_edges_structured(stats, arch_scores),
        "signature_moves": signature_moves_structured(stats),
        "model_usage": model_usage,
    }


def build_summary(stats):
    """The shareable subset for the low-cost feedback loop (docs/metrics-evaluation.md):
    the 8 high-signal MEASURED metrics + monthly progression + rubric profile block.
    The profile sub-dict carries scores/level/archetype/steering; all values are computed
    or count-based — no prompts, no verbatim quotes, no raw skill/project names.
    Safe to share as-is."""
    v, b, vel, st, t, c = (stats["volume"], stats["behavior"], stats["velocity"],
                           stats["stack"], stats["tools"], stats["corpus"])
    return {
        "context": {
            "date_range": c.get("date_range"),
            "window": c.get("window"),
            "sources": sorted((c.get("sources") or {}).keys()),
            "total_sessions": v["total_sessions"],
        },
        "planning_ratio_explore_to_doing": b["planning_ratio_explore_to_doing"],
        "errors": {
            "error_recovery_ratio": b["error_recovery_ratio"],
            "error_rate_per_100_tools": b["error_rate_per_100_tools"],
        },
        "iteration_depth": {
            "mean": b["iteration_depth_mean"], "median": b["iteration_depth_median"],
            "p90": b["iteration_depth_p90"], "max": b["iteration_depth_max"],
            "files_over_15x": b["files_hammered_over_15x"],
        },
        "churn": {
            "git_churn_total": vel["git_churn_total"],
            "tool_churn_edit_write": vel["tool_churn_edit_write"],
        },
        "orchestration": {
            "fanout_median": b["fanout_median"],
            "delegate_actions": b["delegate_actions"],
        },
        "compounding_writes": st["compounding_writes"],
        "ecosystem": {
            "skills_distinct": st["skills_distinct"], "skills_total": st["skills_total"],
            "mcp_servers_distinct": t["mcp_servers_distinct"],
        },
        "progression_monthly": (stats.get("progression") or {}).get("monthly", []),
        "profile": _build_profile(stats),
        "token_usage": stats.get("token_usage") or {
            "total_input": 0, "total_output": 0,
            "total_cache_read": 0, "total_cache_creation": 0,
            "by_model": [],
        },
    }


def bar(n, mx, width=28):
    if mx <= 0:
        return ""
    return "█" * max(1, round(n / mx * width)) if n else ""


def write_report(s):
    L = []
    A = L.append
    c = s["corpus"]; v = s["volume"]; t = s["tools"]; vel = s["velocity"]
    b = s["behavior"]; r = s["rhythm"]; st = s["stack"]; au = s["autonomy"]
    A("# Local Paxel — Builder Stats Report\n")
    A(f"_Scope: {s['scope']}. Generated entirely on-device — nothing uploaded._\n")
    A("## Corpus")
    if c.get("sources"):
        A("- Sources: " + ", ".join(
            f"**{name}** ({d['files']} files, {d['sessions']} sessions, {d['prompts']:,} prompts)"
            for name, d in c["sources"].items()))
    A(f"- Transcripts parsed: **{c['files_parsed']}** ({c['lines_total']:,} events, "
      f"{c['lines_unparseable']} unparseable)")
    A(f"- Date range: **{_d10(c['date_range'][0])} → {_d10(c['date_range'][1])}** "
      f"({c['span_days']} days span, **{c['active_days']} active days**)")
    A(f"- Timezone: {c['timezone']}\n")
    A("## Volume")
    A(f"- Sessions: **{v['total_sessions']}**")
    A(f"- Genuine prompts (human-typed): **{v['total_prompts']:,}**  "
      f"(+{v['command_invocations']} slash-command invocations)")
    A(f"- Avg prompt length: **{v['avg_prompt_length_chars']:.0f} chars** "
      f"(median {v['median_prompt_length_chars']:.0f})")
    A(f"- Assistant turns: {v['assistant_turns']:,} · tool calls: **{v['tool_calls_total']:,}** "
      f"· thinking blocks: {v['thinking_blocks']:,}\n")
    A("## Tools")
    A(f"- Tool diversity: **{t['tool_diversity']} distinct tools** "
      f"(normalized entropy {t['tool_entropy_normalized']})")
    A(f"- MCP share: **{t['mcp_share']*100:.0f}%** ({t['mcp_calls']:,} MCP / {t['native_calls']:,} native)")
    A("- Top tools:")
    mx = t["top_tools"][0][1] if t["top_tools"] else 1
    for name, cnt in t["top_tools"]:
        A(f"  - `{name}` · {cnt:,} {bar(cnt, mx)}")
    A(f"- Category mix: {t['category_breakdown']}\n")
    A("## Code velocity")
    A(f"- **Git churn (gold standard): {vel['git_churn_total']:,} lines** "
      f"(+{vel['git_insertions']:,} / -{vel['git_deletions']:,}) across {vel['git_commits_real']:,} commits "
      f"in {vel['git_repos_with_commits']}/{vel['git_repos_seen']} repos on disk")
    A(f"  - **{vel['git_velocity_lines_per_hour']:.0f} lines/hour** over {vel['active_hours']:,} active hours")
    if vel.get("git_per_repo"):
        A("  - By repo: " + ", ".join(f"{n} ({i+d:,})" for n, i, d, _c in vel["git_per_repo"][:6]))
    _gtot, _ttot = vel['git_churn_total'], max(vel['tool_churn_edit_write'], 1)
    _missing = vel['git_repos_seen'] - vel['git_repos_with_commits']
    if _missing > 0:
        _cov = (f" — note this is **partial**: only {vel['git_repos_with_commits']} of "
                f"{vel['git_repos_seen']} repos were counted (the rest are missing from disk, have no "
                f"commits under your git email, or were too large to scan in time). "
                f"The Execution score nudges its throughput term up modestly (≤1.4×) to avoid "
                f"penalizing you for repos paxel couldn't read")
    else:
        _cov = ""
    A(f"- Tool-only churn (Edit/Write — what most profilers see): {vel['tool_churn_edit_write']:,} lines. "
      f"Git/tool ratio: **{_gtot/_ttot:.1f}×**{_cov}")
    A(f"- Shell-authored work the Edit/Write path misses entirely: {vel['shell_write_calls']:,} file-writing Bash "
      f"calls, ~{vel['shell_authored_lines_est']:,} lines of heredoc/redirect content\n")
    A("## Behavior")
    A(f"- Planning ratio (explore : doing): **{b['planning_ratio_explore_to_doing']}** "
      f"(explore {b['explore_actions']:,} vs doing {b['produce_actions']+b['execute_actions']+b['delegate_actions']:,})")
    A(f"- Avg session: **{b['avg_session_minutes']:.0f} min** (median {b['median_session_minutes']:.0f})")
    A(f"- Errors: **{b['tool_errors']:,} tool errors** ({b['error_rate_per_100_tools']} per 100 tool calls); "
      f"{b['recovered_errors']:,} recovered ({b['error_recovery_ratio']*100:.0f}%); {b['api_errors_retries']} API retries")
    A(f"- Iteration depth (edits/file before commit): mean **{b['iteration_depth_mean']:.1f}**, "
      f"median {b['iteration_depth_median']:.0f}, p90 {b['iteration_depth_p90']}, "
      f"**max {b['iteration_depth_max']}** — {b['files_hammered_over_15x']} files hammered >15× in one session")
    A(f"- Actions per prompt: **{b['actions_per_prompt']:.1f}** · "
      f"questions asked: {b['questions_asked']} · background: {b['background_tasks']} · scheduled: {b['scheduled_actions']}\n")
    A("## Rhythm")
    A(f"- Peak hours (local): **{', '.join(f'{h:02d}:00' for h in r['peak_hours_local'])}**")
    A(f"- Preferred days: **{', '.join(r['preferred_days'])}**")
    A("- Hours:")
    hh = r["hour_histogram_local"]; hmx = max(hh.values()) if hh else 1
    for h in range(24):
        n = hh.get(str(h), 0)
        A(f"  - {h:02d} {bar(n, hmx, 24)} {n}")
    A("- Days:")
    wd = r["weekday_histogram"]; wmx = max(wd.values()) if wd else 1
    for d in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]:
        n = wd.get(d, 0)
        A(f"  - {d} {bar(n, wmx, 24)} {n}")
    A("")
    prog = s.get("progression", {}).get("monthly") or []
    if len(prog) >= 2:
        A("## Progression (monthly)")
        A("_Month-over-month evolution — the slope matters more than the totals when "
          "plan limits cap any single month._")
        pmx = max(p["prompts"] for p in prog) or 1
        tmx = max(p["tool_calls"] for p in prog) or 1
        for p in prog:
            top = f" · top model {p['top_model']}" if p["top_model"] else ""
            A(f"- **{p['month']}** · prompts {bar(p['prompts'], pmx, 16)} {p['prompts']:,} "
              f"· tool calls {bar(p['tool_calls'], tmx, 16)} {p['tool_calls']:,} "
              f"· {p['active_days']} active days · {p['sessions']} sessions"
              f" · ~{p['tool_churn_lines']:,} lines{top}")
        A("")
    A("## Stack")
    A(f"- Models: {', '.join(f'{m} ({n})' for m, n in st['models'][:6])}")
    A(f"- Top skills: {', '.join(f'{k} ({n})' for k, n in st['top_skills'][:10]) or '—'}")
    A(f"- Subagent types: {', '.join(f'{k} ({n})' for k, n in st['subagent_types']) or '—'}")
    A("- Top projects (events, sessions):")
    for name, cnt, sess in st["top_projects"]:
        A(f"  - {name} · {cnt:,} events · {sess} sessions")
    A("")
    A("## Autonomy")
    A(f"- **Autonomy score: {au['autonomy_score_0_100']}/100**")
    A(f"- Components: {au['components']}")
    aq = s.get("agentic")
    if aq:
        A("\n## Agentic Quotient (AQ) — how you operate agents")
        A("_The scorecard above grades how you **build** (gstack); AQ grades how you **operate agents**._")
        A(f"- **AQ: {aq['aq_0_100']}/100 — {aq['tier']}** "
          "_(custom metric, not from paxel; Breadth · Craft · Efficiency · Savvy)_")
        for pillar in aq["pillars"]:
            A(f"  - **{pillar['name']}** ({pillar['weight']}%): **{pillar['score']}**")
            for ax in pillar["axes"]:
                sig = ", ".join(f"{k}={v}" for k, v in ax["signals"].items())
                A(f"    - {ax['name']}: **{ax['score']}/{ax['weight']}** ({sig})")
        mv = aq["mcp_vs_cli"]
        _ratio = f"{mv['ratio']}:1" if mv["ratio"] is not None else "all-CLI (no MCP)"
        A(f"- MCP vs CLI _(described, not graded)_: **CLI** {mv['cli_calls']:,} calls / "
          f"{mv['cli_distinct']} tools · **MCP** {mv['mcp_calls']:,} calls / {mv['mcp_distinct']} servers "
          f"· ratio {_ratio} CLI-first")
        td = aq["tool_diversity"]
        A(f"- Tool diversity _(described)_: {td['distinct']} distinct tools, entropy {td['entropy']}")
    with open(os.path.join(OUT_DIR, "report.md"), "w") as f:
        f.write("\n".join(L))


def write_narrative_input(s, opening_prompts, longest_prompts):
    L = []
    A = L.append
    A("# Narrative input (LOCAL ONLY — for the archetype/traits pass)\n")
    A("Full metrics:\n```json")
    A(json.dumps(s, indent=2, default=str))
    A("```\n")
    A("## Opening prompts (first human message per session — characteristic asks)\n")
    op = [p for p in opening_prompts if p[0] is not None]
    op.sort(key=lambda x: x[0])
    # spread a sample across the timeline
    sample = op[:: max(1, len(op) // 60)] if op else []
    for dt, proj, text in sample[:60]:
        A(f"- [{dt.date()} · {proj}] {text.replace(chr(10), ' ')[:280]}")
    A("\n## Longest prompts (most detailed specs)\n")
    longest_prompts.sort(key=lambda x: -x[0])
    for ln, proj, text in longest_prompts[:20]:
        A(f"- [{ln} chars · {proj}] {text.replace(chr(10), ' ')[:280]}")
    with open(os.path.join(OUT_DIR, "narrative_input.md"), "w") as f:
        f.write("\n".join(L))


# ---------------------------------------------------------------------------
# User-facing profile: a transparent rubric turns the measured metrics into an
# archetype + 0-10 scores (no LLM needed), then we emit a branded, shareable
# profile.html. The COUNTS are measured; the scores/archetype are a rubric and
# the report says so. narrative_input.md is still written for optional LLM polish.
#
# The three score axes are NOT an arbitrary rubric — each one is grounded in
# Garry Tan's open-source gstack (github.com/garrytan/gstack), the same
# Garry-Tan-world framework YC's Paxel comes out of. gstack frames building as a
# sprint — Think → Plan → Build → Review → Test → Ship → Reflect — on top of
# three ethos pillars: "Boil the Lake" (completeness is cheap, do the complete
# thing), "Search Before Building" (know what exists first), and "User
# Sovereignty" (AI recommends, the human decides — and per Anthropic's own
# research, experts interrupt MORE, not less). Each axis below maps a slice of
# that framework onto the metrics paxel can honestly measure from transcripts.
#
# The rubric was then AUDITED by running the real installed gstack skills
# (/plan-eng-review, /plan-ceo-review, /review) via independent subagents. That
# audit drove the current design: each metric is owned by EXACTLY ONE axis (so no
# two axes silently move together), and a 5th "Product Instinct" axis was CUT — the
# audit showed it was mostly skill-detection plus terms recycled from other axes, i.e.
# it didn't honestly measure product judgment. Coding transcripts don't reveal that, so
# we don't fake it. A later validity pass then DEMOTED a 4th axis, Steering, from a
# scored 0–10 to a described reading (see steering_reading): hands-on cadence is real
# but has no good/bad end, and grading it `(15 - actions_per_prompt)` ran backwards
# (a more autonomous engineer scored lower). So: 3 graded axes + 1 described.
# ---------------------------------------------------------------------------
REPO_URL = "https://github.com/Photobombastic/paxel-local"

# Plain-language explanation shown under each score bar — what the axis measures, in
# human terms, no jargon. (The gstack grounding lives in the disclaimer + README, not here.)
SCORE_NOTES = {
    "Execution": "How much you ship, and how fast — your committed-code rate, how much of what "
                 "you generate actually lands in git, and how hard you delegate to agents.",
    "Planning": "How much you think before you build — exploring before writing, reasoning "
                "depth, and laying out a plan first. (Prompt length was dropped — terse expert "
                "prompts shouldn't score below verbose ones.)",
    "Engineering": "How clean your work is — getting files right early, not re-editing the same "
                   "one over and over, low error rate, and checking your work.",
}

# One-line versions of the axis notes for the shareable poster image — the full SCORE_NOTES
# don't fit on a single line under a bar on the card.
SCORE_NOTES_SHORT = {
    "Execution": "Shipped output, at AI leverage",
    "Planning": "Think before you build",
    "Engineering": "Craft, with little rework",
}

# Hover tooltips for the AQ pillars and axes — what each one measures, in plain language,
# grounded in the actual compute_aq formulas (keep in sync if an axis changes). Every
# pillar/axis name emitted by compute_aq must have an entry (tested).
AQ_PILLAR_NOTES = {
    "Breadth": "How much machinery you operate — agents coordinated, skills in rotation, "
               "tools wired in, structured tracking.",
    "Craft": "How well you operate it — verified work, grounded edits, and learnings that persist.",
    "Efficiency": "Leverage per intervention — how far each prompt goes, and how well errors get absorbed.",
    "Savvy": "Smart choices — routing models to tasks and spending tokens lean.",
}
AQ_AXIS_NOTES = {
    "Orchestration": "Coordination over volume: distinct subagent types, median fan-out per "
                     "orchestrating session, and harness use — raw agent runs only count as a small floor.",
    "Skill fluency": "Range and volume of skills you invoke, plus whether process skills "
                     "(planning, debugging, brainstorming) are in the rotation.",
    "Tool command (MCP + CLI)": "External reach: distinct MCP servers, distinct CLIs, and "
                                "loading tool schemas on demand (ToolSearch).",
    "Discipline": "Structured work: task-tool usage plus planning skills in evidence.",
    "Verification": "Whether work gets checked: shell test runs and review-type skill invocations.",
    "Grounding": "Reading before writing — how much the agent explores relative to how much it edits.",
    "Compounding": "Whether learnings persist: writes to memory/docs/skills, plus retro and planning habits.",
    "Steering leverage": "Agent actions per prompt, scored as a sweet spot (5–20): enough leash "
                         "to run, not so loose it drifts.",
    "Recovery": "Share of tool errors recovered from, minus API-retry noise.",
    "Model mix": "Using more than one model, with real work routed off your default — "
                 "match the model to the task.",
    "Token economy": "Token-lean habits: on-demand schema loading (ToolSearch) and a CLI-first "
                     "share of tool traffic.",
}


def _clamp(x):
    return max(0.0, min(1.0, x))


def _d10(x):
    """First 10 chars of an ISO date, or '—' when missing (empty/timestampless corpus)."""
    return (x or "")[:10] or "—"


_MONTHS = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _mon_yr(iso):
    """'2025-06-08' -> 'Jun 2025' (human-readable timeframe for the share poster)."""
    iso = iso or ""
    if len(iso) >= 7 and iso[4] == "-":
        try:
            return f"{_MONTHS[int(iso[5:7])]} {iso[0:4]}"
        except (ValueError, IndexError):
            pass
    return (iso[:10] or "—")


def _js(obj):
    """json.dumps for embedding INSIDE a <script> tag. Python's json.dumps does not escape
    '<', '>', '&', so a prompt containing '</script>' (a real web-dev question) would close
    the script element early and break the whole page. Escape them to \\uXXXX (still valid
    JSON/JS), plus the U+2028/U+2029 line separators that break JS string literals."""
    return (json.dumps(obj)
            .replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
            .replace(" ", "\\u2028").replace(" ", "\\u2029"))


def _skill_uses(stats, needle):
    return sum(n for k, n in stats["stack"].get("top_skills", []) if needle in k.lower())


def _skill_uses_any(stats, needles):
    return sum(n for k, n in stats["stack"].get("top_skills", [])
               if any(nd in k.lower() for nd in needles))


def _evidence(stats):
    """How much activity we actually have to judge habits on, 0..1. ~1.0 for any real
    corpus, near 0 for a thin one. Used to stop 'absence of a signal' from reading as
    'did it perfectly' in the inverse score terms — a barely-used corpus shouldn't grade
    as a flawless builder. (See _ev and the LOW_DATA flag in write_profile_html.)
    Saturates at ~2000 tool calls (≈15 real sessions) so the gating actually has a
    gradient across thin→mid corpora, not just sub-30-minute ones."""
    return _clamp(stats["volume"]["tool_calls_total"] / 2000)


def _ev(credit, ev):
    """Pull an ABSENCE-reward score term toward a neutral 0.5 when evidence (ev) is low,
    so 'no data' lands at the midpoint (admitted uncertainty) instead of a flattering 1.0.
    At ev=1.0 (any real corpus) this returns `credit` unchanged — a true no-op for real
    users; it only ever bites thin corpora. Apply ONLY to inverse terms (those that score
    high when a 'bad' metric is low/zero); presence terms already score 0 for 'didn't do it'."""
    return 0.5 * (1 - ev) + ev * credit


def _verdict(pct):
    """Map 0..1 pct to human-readable verdict."""
    if pct >= 0.9: return "excellent"
    if pct >= 0.7: return "good"
    if pct >= 0.5: return "adequate"
    if pct >= 0.3: return "weak"
    return "poor"

def _axis_verdict(value):
    """Map 0..10 axis score to verdict."""
    if value >= 8.0: return "excellent"
    if value >= 6.5: return "good"
    if value >= 5.0: return "adequate"
    if value >= 3.0: return "weak"
    return "poor"

def _fmt_val(value, unit):
    """Format a measured value with its unit for display."""
    if abs(value) >= 100:
        return f"{value:,.0f} {unit}"
    return f"{value:.2g} {unit}"

def _fmt_target(target, unit, direction):
    """Format target with direction prefix for lower-is-better metrics."""
    pfx = "≤ " if direction == "lower" else ""
    if abs(target) >= 100:
        return f"{pfx}{target:,.0f} {unit}"
    return f"{pfx}{target:.2g} {unit}"

def _sub_narrative(label, verdict, display_value, display_target, direction, score_pct):
    """Build one canonical sentence explaining a sub-metric."""
    if direction == "higher":
        if score_pct >= 90:
            rel = "well above target"
        elif score_pct >= 50:
            rel = "approaching target"
        else:
            rel = "below target"
    else:
        if score_pct >= 90:
            rel = "well within target"
        elif score_pct >= 50:
            rel = "near target threshold"
        else:
            rel = "above target threshold"
    return (f"{label} is {verdict} ({display_value}, target {display_target}"
            f" — {rel}, scoring {score_pct}%).")

def _enrich_sub(sub):
    """Add narrative fields to a score_breakdown sub dict, in-place."""
    p = sub["pct"]
    sub["verdict"] = _verdict(p)
    sub["score_pct"] = round(p * 100)
    sub["display_value"] = _fmt_val(sub["your_value"], sub["unit"])
    sub["display_target"] = _fmt_target(sub["target"], sub["unit"], sub["direction"])
    sub["narrative"] = _sub_narrative(
        sub["label"], sub["verdict"], sub["display_value"],
        sub["display_target"], sub["direction"], sub["score_pct"])
    return sub


class _Sub:
    """One sub-metric spec, single-sourced for both compute_scores and score_breakdown.
    `pct(ctx)` returns the clamped 0..1 contribution EXACTLY as compute_scores computes it
    (including any `_ev(..., ctx.ev)` wrapping). `value(ctx)` returns the raw `your_value`
    score_breakdown reports — kept SEPARATE because for some subs (e.g. Delegation) value is
    NOT derivable from pct (different denominator); see the per-sub notes."""
    __slots__ = ("label", "target", "unit", "weight", "direction", "pct", "value")

    def __init__(self, label, target, unit, weight, direction, pct, value):
        self.label = label
        self.target = target
        self.unit = unit
        self.weight = weight
        self.direction = direction
        self.pct = pct
        self.value = value


class _Axis:
    __slots__ = ("gloss", "subs")

    def __init__(self, gloss, subs):
        self.gloss = gloss
        self.subs = subs


# THE single source of truth for axis scoring. Every weight, target, unit, direction, and
# pct/value formula across the 3 axes / 11 sub-metrics lives here EXACTLY ONCE. Both
# compute_scores (axis values) and score_breakdown (rich UI subs + zero-activity path) derive
# from this table. Any future change is one edit. pct callables mirror compute_scores
# line-for-line; the equality test (test_value_equals_compute_scores) enforces no drift.
_SCORE_AXES = {
    "execution": _Axis("How much you ship, at AI leverage", [
        _Sub("Committed-code rate", 400, "lines/hr", 0.40, "higher",
             pct=lambda c: _clamp((c["eff_git_churn"] / c["hours"]) / 400),
             value=lambda c: c["eff_git_churn"] / c["hours"]),
        _Sub("Ship fidelity", 0.5, "committed/generated", 0.25, "higher",
             pct=lambda c: _clamp(c["fidelity"] / 0.5),
             value=lambda c: c["fidelity"]),
        # value uses /prompts; pct uses /(prompts*0.3) — they diverge for tiny corpora
        # (prompts < 4) because of the max(prompts*0.3, 1) floor. DO NOT derive one from
        # the other; that would break the value==compute_scores invariant for small corpora.
        _Sub("Delegation & parallelism", 0.30, "agent-runs/prompt", 0.35, "higher",
             pct=lambda c: _clamp((c["b"].get("delegate_actions", 0) + c["b"].get("background_tasks", 0)) / max(c["prompts"] * 0.3, 1)),
             value=lambda c: (c["b"].get("delegate_actions", 0) + c["b"].get("background_tasks", 0)) / max(c["prompts"], 1)),
    ]),
    "planning": _Axis("Think before you build", [
        _Sub("Explore-before-build", 0.65, "explore/doing ratio", 0.45, "higher",
             pct=lambda c: _clamp(c["b"].get("planning_ratio_explore_to_doing", 0) / 0.65),
             value=lambda c: c["b"].get("planning_ratio_explore_to_doing", 0)),
        _Sub("Reasoning depth", 12.0, "thinking blocks/session", 0.30, "higher",
             pct=lambda c: _clamp((c["v"].get("thinking_blocks", 0) / c["sess"]) / 12.0),
             value=lambda c: c["v"].get("thinking_blocks", 0) / c["sess"]),
        _Sub("Plan ceremony", 0.8, "plan-skills/session", 0.25, "higher",
             pct=lambda c: _clamp((c["plan_skills"] / c["sess"]) / 0.8),
             value=lambda c: c["plan_skills"] / c["sess"]),
    ]),
    "engineering": _Axis("Craft and low rework", [
        _Sub("Low rework", 2.0, "mean file-edit depth", 0.30, "lower",
             pct=lambda c: _ev(1 - _clamp((c["b"].get("iteration_depth_mean", 0) - 2) / 8), c["ev"]),
             value=lambda c: c["b"].get("iteration_depth_mean", 0)),
        _Sub("Clean iteration", 3.0, "p90 file-edit depth", 0.25, "lower",
             pct=lambda c: _ev(1 - _clamp((c["b"].get("iteration_depth_p90", 0) - 3) / 9), c["ev"]),
             value=lambda c: c["b"].get("iteration_depth_p90", 0)),
        _Sub("Focus", 0.25, "hammered-files/session", 0.20, "lower",
             pct=lambda c: _ev(1 - _clamp((c["b"].get("files_hammered_over_15x", 0) / c["sess"]) / 0.25), c["ev"]),
             value=lambda c: c["b"].get("files_hammered_over_15x", 0) / c["sess"]),
        _Sub("Quality ceremony", 3.0, "quality-skills/session", 0.15, "higher",
             pct=lambda c: _clamp((c["eng_skills"] / c["sess"]) / 3.0),
             value=lambda c: c["eng_skills"] / c["sess"]),
        _Sub("Low errors", 10.0, "errors/100 tools", 0.10, "lower",
             pct=lambda c: _ev(1 - _clamp(c["b"].get("error_rate_per_100_tools", 0) / 10), c["ev"]),
             value=lambda c: c["b"].get("error_rate_per_100_tools", 0)),
    ]),
}


def _score_ctx(stats):
    """Build ONCE the precomputed locals both scoring functions consume, using the SAME
    formulas/.get defaults score_breakdown uses today."""
    v, b, vel = stats.get("volume", {}), stats.get("behavior", {}), stats.get("velocity", {})
    sess = max(v.get("total_sessions", 0), 1)
    prompts = max(v.get("total_prompts", 0), 1)
    hours = max(vel.get("active_hours", 0.1), 0.1)
    ev = _evidence(stats)
    git_cov = max(vel.get("git_repos_with_commits", 0) / max(vel.get("git_repos_seen", 1), 1), 0.7)
    eff_git_churn = vel.get("git_churn_total", 0) / git_cov
    fidelity = eff_git_churn / max(vel.get("tool_churn_edit_write", 1), 1)
    plan_skills = _skill_uses_any(stats, ("brainstorm", "writing-plan", "plan", "spec",
                                          "office-hours", "autoplan", "grill", "ceo-review",
                                          "eng-review", "design-review"))
    eng_skills = _skill_uses_any(stats, ("code-review", "test", "tdd", "qa", "investigate",
                                         "retro", "learn", "cso", "karpathy", "debug")) \
        + b.get("shell_test_runs", 0)
    return {"v": v, "b": b, "vel": vel, "sess": sess, "prompts": prompts, "hours": hours,
            "ev": ev, "git_cov": git_cov, "eff_git_churn": eff_git_churn,
            "fidelity": fidelity, "plan_skills": plan_skills, "eng_skills": eng_skills}


def compute_scores(stats):
    # THREE graded axes (Execution/Planning/Engineering), grounded in gstack (module note
    # above) and then hardened by a gstack self-audit. Steering is NOT scored here — it's
    # described in steering_reading (it was inverted; see that function). Design rules:
    #   1. Each metric is owned by EXACTLY ONE place — no metric drives two graded axes, so
    #      the axes are genuinely independent (no hidden correlation).
    #   2. actions_per_prompt and questions_asked live ONLY in steering_reading (hands-on
    #      cadence — described, not scored); neither graded axis rewards them.
    #   3. iteration_depth_p90 lives ONLY in Engineering.
    #   4. Skill-detection terms are kept but de-weighted (a builder who plans in Notion
    #      and reviews on GitHub shouldn't score 0) — behavior carries the axes.
    # Weights sum to 1.0 per axis; every term is clamped 0..1 against a justified target;
    # `_ev` pulls the INVERSE terms toward neutral on a thin corpus.
    v = stats["volume"]
    if v["total_sessions"] == 0 or v["tool_calls_total"] == 0:
        # No real activity → don't manufacture a flattering "Quality Guardian 9.0"
        return {"Execution": 0.0, "Planning": 0.0, "Engineering": 0.0}

    # EXECUTION — shipped output at AI leverage. Three signals, no overlap with other axes:
    #   (a) RATE: gold-standard git churn per active hour (coverage-corrected — git often
    #       sees only some repos; we nudge ≤1.4× by coverage rather than penalize, and the
    #       report discloses it). (b) FIDELITY: how much of what you GENERATED actually got
    #       committed — git churn vs tool churn — the audit's headline "are you shipping or
    #       just exploring" signal (also coverage-corrected). (c) DELEGATION/parallelism.
    #   Dropped vs the old version: actions_per_prompt (now in steering_reading, described
    #   not scored) and raw session length (the audit called it noise — a long distracted
    #   session isn't execution).
    # PLANNING — think before you build. Behavior-led.
    # DROPPED the avg_prompt_length term (was 0.25): it is experience-INVERTING — expertise
    # produces TERSER, more precise prompts, so the term paid for verbosity. It's the main reason a
    # 4-month vibe-coder maxed Planning over a 30-year engineer (an expert-elicitation validity
    # review caught this). Weight redistributed to the construct-relevant terms.
    # STEERING IS NOT SCORED — it's DESCRIBED (see steering_reading). Hands-on cadence
    # (actions/prompt + how often the agent checks in) is real and measurable, but it has no
    # good/bad end: a deliberate hands-off operator who delegates and gets clean autonomous output
    # back is steering by a mechanism we CANNOT read from transcripts (it needs delegation→
    # survived-to-commit attribution). Grading it INVERTED the axis — `(15 - actions_per_prompt)`
    # meant a more autonomous engineer scored LOWER (the Chris Sells case). You don't fix a
    # backwards gauge with a disclaimer underneath it; you stop grading it and state the fact.
    # (An earlier "autonomous command" term that tried to credit delegation×low-error was also
    # reverted — it collapsed to error-rate-in-a-costume; see git history.)
    # ENGINEERING — craft / low rework. The old churn_back term (deletion ratio) was CUT:
    # it scored a clean refactor as "thrash" and gave a perfect score to anyone who never
    # committed. Replaced by iteration_depth_mean ("did you get the file right early"), the
    # honest rework signal. p90 + file-hammering stay here (their only home). Ceremony de-weighted.
    # "code-review" (not bare "review") so this doesn't greedily match Planning's
    # plan-eng-review / plan-design-review / ceo-review ceremonies (which live in plan_skills).
    # All weights/targets/pct-formulas now live in _SCORE_AXES (single source of truth);
    # `_ev` (inside the engineering pct callables) pulls INVERSE terms toward neutral on a
    # thin corpus. The equality test pins these axis values to score_breakdown's.
    ctx = _score_ctx(stats)
    return {
        "Execution": round(10 * sum(s.weight * s.pct(ctx) for s in _SCORE_AXES["execution"].subs), 1),
        "Planning": round(10 * sum(s.weight * s.pct(ctx) for s in _SCORE_AXES["planning"].subs), 1),
        "Engineering": round(10 * sum(s.weight * s.pct(ctx) for s in _SCORE_AXES["engineering"].subs), 1),
    }


def score_breakdown(stats):
    """Per-axis sub-component breakdown for the dashboard UI. Returns the same three
    axes as compute_scores with per-sub pct/value/target fields so the UI can show WHY
    a score is high or low.  Axis constants/formulas live once in _SCORE_AXES; both this
    function and compute_scores derive from it, so a formula change is a single edit.
    test_value_equals_compute_scores enforces the value invariant (subs values == axis values)."""
    v, b, vel = stats.get("volume", {}), stats.get("behavior", {}), stats.get("velocity", {})
    # Guard: no real activity → well-formed zeros (mirrors compute_scores early-return)
    if v.get("total_sessions", 0) == 0 or v.get("tool_calls_total", 0) == 0:
        def _zero_sub(label, target, unit, weight, direction):
            return {"label": label, "your_value": 0.0, "target": target, "unit": unit,
                    "weight": weight, "pct": 0.5, "direction": direction, "is_drag": False,
                    "verdict": "adequate", "score_pct": 50,
                    "display_value": _fmt_val(0.0, unit),
                    "display_target": _fmt_target(target, unit, direction),
                    "narrative": f"No activity recorded for {label}."}
        def _zero_axis(axis_key):
            axis = _SCORE_AXES[axis_key]
            subs = [_zero_sub(s.label, s.target, s.unit, s.weight, s.direction)
                    for s in axis.subs]
            subs[0]["is_drag"] = True   # deterministic sentinel for the no-activity case;
                                        # NOT a meaningful weakest-sub signal (all values are 0)
            return {"value": 0.0, "gloss": axis.gloss, "drag_note": "No activity recorded.", "subs": subs,
                    "axis_verdict": "poor", "score_out_of_10": "0.0 / 10",
                    "drag_narrative": "No activity recorded.",
                    "axis_narrative": "No activity recorded."}
        return {
            "execution": _zero_axis("execution"),
            "planning": _zero_axis("planning"),
            "engineering": _zero_axis("engineering"),
        }

    # All weights/targets/units/directions/pct/value formulas come from _SCORE_AXES (the
    # single source of truth shared with compute_scores). pct = s.pct(ctx); your_value =
    # s.value(ctx). NOTE on Delegation: value uses /prompts, pct uses /(prompts*0.3); they
    # diverge for tiny corpora (see the table's per-sub comment) — both callables are kept
    # so this never re-derives one from the other. The UI fills bars from pct, not your_value.
    ctx = _score_ctx(stats)

    def _build_subs(axis_key):
        subs = [{"label": s.label, "your_value": s.value(ctx), "target": s.target,
                 "unit": s.unit, "weight": s.weight, "pct": s.pct(ctx),
                 "direction": s.direction, "is_drag": False}
                for s in _SCORE_AXES[axis_key].subs]
        return [_enrich_sub(s) for s in subs]

    exec_subs = _build_subs("execution")
    plan_subs = _build_subs("planning")
    eng_subs = _build_subs("engineering")
    execution_val = round(10 * sum(s["weight"] * s["pct"] for s in exec_subs), 1)
    planning_val = round(10 * sum(s["weight"] * s["pct"] for s in plan_subs), 1)
    engineering_val = round(10 * sum(s["weight"] * s["pct"] for s in eng_subs), 1)

    def _mark_drag(axis_name, subs, gloss):
        """Flag the sub with the smallest weight*pct contribution; build a drag_note."""
        drag_idx = min(range(len(subs)), key=lambda i: subs[i]["weight"] * subs[i]["pct"])
        for i, s in enumerate(subs):
            s["is_drag"] = (i == drag_idx)
        d = subs[drag_idx]
        if d["direction"] == "higher":
            note = (f"{d['label']} is dragging this down — "
                    f"{d['your_value']:.2g} {d['unit']}, target ~{d['target']:.2g}.")
        else:
            note = (f"{d['label']} is dragging this down — "
                    f"{d['your_value']:.2g} {d['unit']} (target ≤{d['target']:.2g}).")
        _axis_values = {
            "execution": execution_val,
            "planning": planning_val,
            "engineering": engineering_val,
        }
        drag_sub = subs[drag_idx]
        best_sub = max(subs, key=lambda s: s["pct"])
        av = _axis_verdict(_axis_values[axis_name])
        dir_hint = "higher is better" if drag_sub["direction"] == "higher" else "lower is better"
        drag_narr = (
            f"{drag_sub['label']} is the weakest contributor, scoring {drag_sub['score_pct']}%. "
            f"Your value: {drag_sub['display_value']} (target: {drag_sub['display_target']}, {dir_hint}).")
        axis_name_display = axis_name.capitalize()
        axis_narr = (
            f"{axis_name_display} scores {_axis_values[axis_name]}/10 ({av}). "
            f"Strongest: {best_sub['label']} ({best_sub['score_pct']}%); "
            f"weakest: {drag_sub['label']} ({drag_sub['score_pct']}%).")
        return {"value": _axis_values[axis_name],
                "gloss": gloss, "drag_note": note, "subs": subs,
                "axis_verdict": av,
                "score_out_of_10": f"{_axis_values[axis_name]} / 10",
                "drag_narrative": drag_narr,
                "axis_narrative": axis_narr}

    return {
        "execution": _mark_drag("execution", exec_subs, _SCORE_AXES["execution"].gloss),
        "planning":  _mark_drag("planning",  plan_subs, _SCORE_AXES["planning"].gloss),
        "engineering": _mark_drag("engineering", eng_subs, _SCORE_AXES["engineering"].gloss),
    }


def steering_reading(stats):
    """Steering is DESCRIBED, not graded (see compute_scores for why). We report how you run
    agents — long leash vs short leash — as a fact, with no implied good/bad. Returns a short
    label + a one-line detail, both safe to render and to share (numbers only, no prompt text)."""
    v, b = stats["volume"], stats["behavior"]
    prompts = max(v["total_prompts"], 1)
    apr = b["actions_per_prompt"]               # tool actions between your prompts
    qrate = b["questions_asked"] / prompts      # how often the agent stopped to check in
    if apr >= 12:
        label, gloss = "Long leash", "you point the agent and let it run"
    elif apr >= 6:
        label, gloss = "Medium leash", "autonomous stretches, hands-on steering"
    else:
        label, gloss = "Short leash", "you stay close and course-correct often"
    detail = (f'~{apr:.0f} actions per turn before you weigh in · '
              f'the agent checked in on {qrate*100:.0f}% of your prompts')
    return {"label": label, "gloss": gloss, "detail": detail}


def compute_aq(stats):
    """Agentic Quotient v2 — 'how well you OPERATE AGENTS' (distinct from the gstack
    scorecard, which grades how you BUILD). Four pillars: Breadth (how much machinery),
    Craft (how well), Efficiency (leverage per intervention), Savvy (smart choices).
    MCP-vs-CLI and tool diversity stay descriptive (not graded)."""
    t, st, b = stats.get("tools", {}), stats.get("stack", {}), stats.get("behavior", {})

    def sat(x, target):
        return min(1.0, x / target) if target else 0.0

    skills = st.get("skills_all") or st.get("top_skills", [])

    def skill_uses(needles):
        return sum(n for k, n in skills if any(nd in str(k).lower() for nd in needles))

    def has_skill(needles):
        return any(any(nd in str(k).lower() for nd in needles) for k, _ in skills)

    # ---- Pillar 1: Breadth (unchanged axes) ----
    agent_runs = t.get("agent_calls", 0)
    fanout = b.get("fanout_median", 0)
    o_harn = 1.0 if (any(re.search(r"harness|trisel", str(k), re.I)
                         for k, _ in st.get("subagent_types", [])) or has_skill(["trisel"])) else 0.6
    # Coordination over volume: fan-out (agents coordinated per orchestrating session)
    # is the orchestration tell — a serial grinder firing N agents one-per-session reads
    # fanout=1, a real orchestrator reads its team size. agent_runs stays only as a small
    # volume floor; the old (background + scheduled) COUNT term was cut (it double-counted
    # volume and rewarded firing-and-forgetting, not coordinating).
    orchestration = (.30 * sat(st.get("subagent_types_distinct", 0), 8) + .30 * sat(fanout, 5)
                     + .20 * o_harn + .20 * sat(agent_runs, 400))
    skill_fluency = (.40 * sat(st.get("skills_distinct", 0), 40) + .30 * sat(st.get("skills_total", 0), 1500)
                     + .30 * (1.0 if has_skill(["subagent-driven", "brainstorm", "writing-plans",
                                                "cerberus", "systematic-debugging"]) else 0.6))
    tool_command = (.40 * sat(t.get("mcp_servers_distinct", 0), 15) + .40 * sat(t.get("clis_distinct", 0), 40)
                    + .20 * sat(t.get("toolsearch_calls", 0), 300))
    discipline = (.60 * sat(t.get("task_tool_calls", 0), 1500)
                  + .40 * (1.0 if has_skill(["writing-plans", "autoplan", "plan"]) else 0.6))
    breadth_axes = [
        ("Orchestration", 33, orchestration, {"agent_runs": agent_runs,
         "subagent_types": st.get("subagent_types_distinct", 0), "fanout_median": fanout}),
        ("Skill fluency", 22, skill_fluency, {"skills_distinct": st.get("skills_distinct", 0),
         "skills_total": st.get("skills_total", 0)}),
        ("Tool command (MCP + CLI)", 28, tool_command, {"mcp_servers": t.get("mcp_servers_distinct", 0),
         "clis": t.get("clis_distinct", 0), "toolsearch": t.get("toolsearch_calls", 0)}),
        ("Discipline", 17, discipline, {"task_tool_calls": t.get("task_tool_calls", 0)}),
    ]

    # ---- Pillar 2: Craft ----
    review_n = _review_skill_uses(skills)
    verification = .5 * sat(b.get("shell_test_runs", 0), 150) + .5 * sat(review_n, 100)
    grounding = sat(b.get("planning_ratio_explore_to_doing", 0), 1.0)
    compounding = (.6 * sat(st.get("compounding_writes", 0), 30)
                   + .4 * (1.0 if has_skill(["retro", "writing-plans", "brainstorm"]) else 0.6))
    craft_axes = [
        ("Verification", 40, verification, {"test_runs": b.get("shell_test_runs", 0), "review_skills": review_n}),
        ("Grounding", 30, grounding, {"planning_ratio": b.get("planning_ratio_explore_to_doing", 0)}),
        ("Compounding", 30, compounding, {"compounding_writes": st.get("compounding_writes", 0)}),
    ]

    # ---- Pillar 3: Efficiency ----
    app = b.get("actions_per_prompt", 0)
    if app <= 0:
        lever = 0.0
    elif app < 5:
        lever = app / 5
    elif app <= 20:
        lever = 1.0
    else:
        lever = max(0.0, 1 - (app - 20) / 40)
    recovery = .85 * sat(b.get("error_recovery_ratio", 0), 1.0) + .15 * (1 - sat(b.get("api_errors_retries", 0), 50))
    eff_axes = [
        ("Steering leverage", 50, lever, {"actions_per_prompt": app}),
        ("Recovery", 50, recovery, {"recovery_ratio": b.get("error_recovery_ratio", 0),
         "api_retries": b.get("api_errors_retries", 0)}),
    ]

    # ---- Pillar 4: Savvy ----
    # Provider-agnostic: works across Claude / OpenAI-Codex / Gemini / etc. "Model mix"
    # rewards using more than one model and routing work off your single default model
    # (match model to task) — no hard-coded model names or tiers.
    models = st.get("models", [])
    total_turns = sum(n for _, n in models)
    top_turns = max((n for _, n in models), default=0)
    offload_share = (1 - top_turns / total_turns) if total_turns else 0
    model_mix = .5 * sat(len(models), 3) + .5 * sat(offload_share, 0.30)
    cli_calls, mcp_calls = t.get("cli_calls", 0), t.get("mcp_calls", 0)
    cli_share = cli_calls / (cli_calls + mcp_calls) if (cli_calls + mcp_calls) else 0
    token_economy = .5 * sat(t.get("toolsearch_calls", 0), 300) + .5 * sat(cli_share, 0.70)
    savvy_axes = [
        ("Model mix", 50, model_mix, {"distinct_models": len(models), "offload_share": round(offload_share, 2)}),
        ("Token economy", 50, token_economy, {"toolsearch": t.get("toolsearch_calls", 0), "cli_share": round(cli_share, 2)}),
    ]

    def build_pillar(name, weight, axes):
        out = [{"name": n, "weight": w, "score": round(w * s, 1), "signals": sig} for n, w, s, sig in axes]
        return {"name": name, "weight": weight, "score": round(sum(a["score"] for a in out), 1), "axes": out}

    pillars = [build_pillar("Breadth", 30, breadth_axes), build_pillar("Craft", 35, craft_axes),
               build_pillar("Efficiency", 20, eff_axes), build_pillar("Savvy", 15, savvy_axes)]
    total = round(sum(p["weight"] / 100 * p["score"] for p in pillars))
    # ONE honest level vocabulary, driven by AQ (the score that actually separates level).
    # No flattery at the floor: a low score reads low. Also drives the profile archetype.
    tier = ("Elite" if total >= 88 else "Advanced" if total >= 75 else "Proficient" if total >= 60
            else "Adequate" if total >= 45 else "Apprentice" if total >= 25 else "Novice")
    return {
        "aq_0_100": total, "tier": tier, "pillars": pillars,
        "mcp_vs_cli": {"cli_calls": cli_calls, "cli_distinct": t.get("clis_distinct", 0),
                       "mcp_calls": mcp_calls, "mcp_distinct": t.get("mcp_servers_distinct", 0),
                       "ratio": round(cli_calls / mcp_calls, 1) if mcp_calls else None},
        "tool_diversity": {"distinct": t.get("tool_diversity", 0), "entropy": t.get("tool_entropy_normalized", 0)},
    }


def pick_archetype(stats, scores):
    """Honest level read — NOT a flattering identity. One vocabulary, driven by AQ
    (the score that actually separates level): Novice < Apprentice < Adequate <
    Proficient < Advanced < Elite. A low score reads low; we don't dress it up. The
    quote names the thinnest AQ pillar so the gap is visible, not hidden — if you fall
    short somewhere, it says so."""
    aq = stats.get("agentic", {})
    rung = aq.get("tier", "Novice")
    score = aq.get("aq_0_100", 0)
    pillars = aq.get("pillars", [])
    gap = min(pillars, key=lambda p: p["score"])["name"].lower() if pillars else None
    g = f" Your thinnest axis is {gap} — that's where the next gain is." if gap else ""
    if score >= 75:
        q = "You operate at the top — broad machinery, well used." + g
    elif score >= 60:
        q = "Proficient and consistent, but not yet at the top tier." + g
    elif score >= 45:
        q = "Adequate. The fundamentals are there, with real room to grow." + g
    elif score >= 25:
        q = "Still developing — the habits aren't compounding yet." + g
    else:
        q = "Just getting started. Broad gaps to close before the rest pays off." + g
    return rung, q


def _signature_moves_pool(stats):
    """Build the sorted+sliced pool of signature moves as dicts.

    Returns a list of up to 5 dicts with keys:
        tag, title, evidence_html
    sorted by descending strength, already sliced to [:5].
    Single source of truth — both the HTML wrapper and the structured emitter
    read from here, so the two outputs can never drift.
    MAINTAINERS: evidence_html is trusted / safe-by-construction — every value
    interpolated below is a number or a static template. NEVER interpolate
    user/transcript-derived strings (skill, project, tool names) without
    html.escape (the lone tool-name use is gated to == "Bash" and emits a literal)."""
    v, b, vel, t, st = (stats["volume"], stats["behavior"], stats["velocity"],
                        stats["tools"], stats["stack"])
    sess = max(v["total_sessions"], 1)
    prompts = max(v["total_prompts"], 1)

    def sk(*needles):
        return sum(n for k, n in st.get("top_skills", []) if any(nd in k.lower() for nd in needles))

    top_tool = (str(t["top_tools"][0][0]) if t["top_tools"] else "")
    deleg = b["delegate_actions"] + b["background_tasks"]
    raw = []   # (strength 0..1, tag, title, evidence_html)

    rev = _review_skill_uses(st.get("top_skills", []))
    if rev >= 50 and rev >= sess * 0.5:
        raw.append((_clamp(rev / (sess * 2)), "Review",
            "You review more than you write",
            f'<b>{rev:,}</b> code-review passes — one of your most-used skills. '
            f'You don\'t trust a diff until a second set of eyes has seen it.'))

    if b["planning_ratio_explore_to_doing"] >= 0.55 and b["iteration_depth_max"] >= 40:
        raw.append((_clamp(b["iteration_depth_max"] / 100.0), "Think → Build",
            "Plan wide, then grind narrow",
            f'A <b>{b["planning_ratio_explore_to_doing"]:.2f}</b> explore-to-build ratio — you read and '
            f'search far more than you type — yet you\'ll hammer one file <b>{b["iteration_depth_max"]}×</b> '
            f'rather than re-architect. Blueprint, then bulldozer.'))

    if deleg >= 100 and deleg >= prompts * 0.3:
        shell = " with the shell as your top tool" if top_tool == "Bash" else ""
        raw.append((_clamp(deleg / (prompts * 0.8)), "Build",
            "You run a team, not a tool",
            f'<b>{deleg:,}</b> delegated &amp; backgrounded agent runs{shell}. '
            f'You parallelize and grind rather than babysit one chat.'))

    tb = v["thinking_blocks"]
    if tb / sess >= 8:
        raw.append((_clamp((tb / sess) / 30.0), "Think",
            "You think before you touch the diff",
            f'<b>{tb:,}</b> reasoning blocks (~{tb // sess}/session) before edits land — '
            f'you deliberate hard, then commit.'))

    plan = sk("brainstorm", "writing-plan", "autoplan", "spec")
    if plan >= 30 and plan >= sess * 0.35:
        raw.append((_clamp(plan / float(sess)), "Plan",
            "You write the plan before the code",
            f'<b>{plan:,}</b> planning &amp; brainstorming runs — you scaffold the decision '
            f'before the implementation, gstack-style.'))

    qrate = b["questions_asked"] / prompts
    if qrate < 0.03 and prompts > 200:
        raw.append((0.45, "User Sovereignty",
            "You direct, you don't deliberate",
            f'The agent stopped to ask you on just <b>{qrate*100:.0f}%</b> of {prompts:,} prompts — '
            f'you point it and let it run, rather than getting pulled into a back-and-forth.'))

    if vel["shell_authored_lines_est"] >= 20000 and top_tool == "Bash":
        raw.append((_clamp(vel["shell_authored_lines_est"] / 80000.0), "Build",
            "You live in the shell",
            f'~<b>{vel["shell_authored_lines_est"]:,}</b> lines authored through Bash heredocs and '
            f'redirects — real work most profilers never even see.'))

    raw.sort(key=lambda x: -x[0])
    return [{"tag": tag, "title": title, "evidence_html": ev}
            for _, tag, title, ev in raw[:5]]


def signature_moves(stats):
    """Named decision-patterns ('signature moves') drawn from real session behavior,
    each tagged with the gstack sprint stage it expresses. Only moves whose gate
    actually fires are returned (we never pad) — top 5 by a comparable 0..1 strength.
    Cites measured numbers, NEVER raw prompt text, so the profile stays shareable
    without leaking session content. NOTE for maintainers: evidence HTML is trusted /
    safe-by-construction — never interpolate user/transcript-derived strings (skill,
    project, tool names) here without html.escape; today every value is a number or a
    static template (the lone tool-name use is gated to == "Bash" and emits a literal)."""
    return [(d["tag"], d["title"], d["evidence_html"])
            for d in _signature_moves_pool(stats)]


def _growth_edges_pool(stats, scores):
    """Build the sorted+sliced pool of growth edges as dicts.

    Returns a list of up to 3 dicts with keys:
        priority, eyebrow, title, advice_html, axis
    sorted ascending by priority (lowest = most urgent), already sliced to [:3].
    axis is the AQ axis name string for AQ-driven edges, else None.
    Single source of truth for both the HTML wrapper and the structured emitter.
    MAINTAINERS: advice_html is trusted / safe-by-construction — every interpolated
    value is a number or a static template. NEVER interpolate user/transcript-derived
    strings (skill, project, tool names) here without html.escape."""
    v, b, vel, st = (stats["volume"], stats["behavior"], stats["velocity"], stats["stack"])
    sess = max(v["total_sessions"], 1)
    prompts = max(v["total_prompts"], 1)

    def sk(*needles):
        return sum(n for k, n in st.get("top_skills", []) if any(nd in k.lower() for nd in needles))

    rev = _review_skill_uses(st.get("top_skills", []))
    tdd = sk("test", "tdd", "qa") + b.get("shell_test_runs", 0)   # named test skills + CLI test runs
    err = b["error_rate_per_100_tools"]
    raw = []   # (priority, eyebrow, title, advice_html, axis)

    # NO steering edge: hands-on cadence has no good/bad end (it's described, not scored — see
    # steering_reading), so telling an autonomous operator to "steer harder" is exactly the
    # inversion we removed. We don't advise people to babysit clean autonomous runs.

    # Only fires when we genuinely see few tests — and it SAYS what it can and can't detect, so a
    # CLI tester is never told "0 test runs" as though it were fact.
    if rev >= 50 and tdd < max(rev * 0.1, 5):
        raw.append((1.5, "Add a reflex",
            "Pair your review reflex with a test reflex",
            f'We spotted <b>{rev:,}</b> code-reviews but only <b>{tdd}</b> test runs — counting named test '
            f'skills <i>and</i> shell runners like <code>pytest</code> / <code>go test</code> / '
            f'<code>npm test</code>. If you test some other way we can\'t see, skip this. If tests really '
            f'are thin, make the double-check a <i>regression test</i>: one for every bug you fix. '
            f'(gstack\'s <code>/qa</code> does this.)',
            None))

    # High iteration is only "whack-a-mole" if it's THRASH — so we require an elevated error rate
    # alongside it. A clean deep-iterator (low errors) is doing deliberate work, not flailing, and
    # is left alone (this also spares agent-driven iteration, which tends to keep errors low).
    if (b["iteration_depth_max"] >= 40 or b["files_hammered_over_15x"] >= 10) and err >= 5:
        raw.append((2.0, "Stop the grind",
            "When a file fights back, root-cause it",
            f'<b>{b["iteration_depth_max"]}×</b> on one file and <b>{b["files_hammered_over_15x"]}</b> files '
            f'past 15 edits, next to ~<b>{err}</b> errors per 100 tool calls — that pairing reads as '
            f'retry-thrash more than deliberate iteration. When a file resists past ~15 tries, find the root '
            f'cause before the next edit. (gstack names this <code>/investigate</code>.)',
            None))

    if scores.get("Planning", 10) < 6:
        raw.append((scores.get("Planning", 10), "Plan first",
            "Spend more time in Think + Plan",
            f'Planning is <b>{scores.get("Planning")}</b>. Sketch the plan and reframe the ask <i>before</i> '
            f'writing code — it\'s the cheapest place to catch a wrong turn. '
            f'(gstack front-loads this with <code>/office-hours</code> + <code>/autoplan</code>.)',
            None))

    eng_skills = _review_skill_uses(st.get("top_skills", [])) + sk("qa", "investigate", "retro")
    if scores.get("Engineering", 10) < 6 and eng_skills < sess * 0.3:
        raw.append((scores.get("Engineering", 10) + 0.1, "Boil the lake",
            "Run a quality pass before you ship",
            f'Engineering is <b>{scores.get("Engineering")}</b>. Add one deliberate review-and-test pass on '
            f'every branch before you ship — that\'s where craft compounds. '
            f'(gstack\'s back half: <code>/review</code>, <code>/qa</code>, <code>/investigate</code>, <code>/retro</code>.)',
            None))

    # AQ-driven edges: any AQ axis filled under 45% of its weight is a candidate. Advised
    # axes only — excluded on purpose: Verification (covered by the review/test edge above),
    # Compounding (the /retro fallback already owns it), Steering leverage (steering is
    # described, not scored — see the NO-steering note above), Recovery / Skill fluency /
    # Discipline (no single practice maps cleanly onto them). Priority 2.5 + fill*5 keeps
    # the hard behavioral edges (1.5/2.0) and very-low gstack scores ahead of mild AQ gaps.
    def _aq_advice(pillar, axis, sig):
        lead = f'<b>{pillar} · {axis}</b> is your thinnest AQ signal. '
        if axis == "Orchestration":
            return ("Multiply yourself", "Run agents in parallel, not in series",
                lead + f'<b>{sig.get("subagent_types", 0)}</b> distinct subagent types with a median '
                f'fan-out of <b>{sig.get("fanout_median", 0)}</b>. When a task splits into independent '
                f'pieces, hand them to parallel subagents in one orchestrating session instead of '
                f'grinding through them serially.')
        if axis.startswith("Tool command"):
            return ("Widen the toolbelt", "Wire your daily services into the agent",
                lead + f'<b>{sig.get("mcp_servers", 0)}</b> MCP servers and <b>{sig.get("clis", 0)}</b> '
                f'CLIs in evidence. Connect the things you touch every day — issue tracker, browser, '
                f'cloud — as MCP servers or CLIs, so the agent reaches them directly instead of through you.')
        if axis == "Model mix":
            return ("Route the work", "Match the model to the task",
                lead + f'<b>{sig.get("distinct_models", 0)}</b> model(s), with only '
                f'<b>{round(sig.get("offload_share", 0) * 100)}%</b> of turns routed off your default. '
                f'Send mechanical work — renames, bulk edits, summaries — to a faster model and save '
                f'the heavyweight for design and review.')
        if axis == "Token economy":
            return ("Spend tokens like money", "Keep the context lean",
                lead + f'<b>{round(sig.get("cli_share", 0) * 100)}%</b> of tool traffic goes through '
                f'CLIs (vs MCP). Prefer CLIs for bulk operations and load MCP schemas on demand — '
                f'a leaner context buys longer, sharper runs.')
        if axis == "Grounding":
            return ("Read before you write", "Make the agent explore before it edits",
                lead + f'Your explore-to-doing ratio is <b>{sig.get("planning_ratio", 0)}</b> — edits '
                f'outpace reading. Ask for a read-the-code pass before changes; grounded edits fail less.')
        return None

    for p in (stats.get("agentic") or {}).get("pillars", []):
        for a in p.get("axes", []):
            w = a.get("weight") or 0
            fill = (a.get("score", 0) / w) if w else 1.0
            if fill >= 0.45:
                continue
            made = _aq_advice(p.get("name", ""), a.get("name", ""), a.get("signals", {}))
            if made:
                eb, title, adv = made
                raw.append((2.5 + fill * 5, eb, title, adv, a.get("name", "")))

    if not raw:
        worst = min(scores, key=scores.get) if scores else ""
        wv = scores.get(worst, 10)
        if worst and wv < 6.5:
            # Nothing specific fired, but an axis IS low — don't claim "balanced" when the scorecard
            # shows otherwise. Point at the softest axis honestly instead.
            raw.append((8.5, "Closest to an edge", f'Your softest axis is {worst}',
                f'Nothing jumped out as a single clear next-step, but <b>{worst}</b> at <b>{wv}</b> is your '
                f'lowest axis — the cheapest place to gain. See how {worst} is scored above and lean there.',
                None))
        else:
            raw.append((9.0, "Go deeper",
                "You're balanced — your edge is depth",
                'You\'re even across the build sprint, so the next gear isn\'t a weak spot to patch — it\'s depth. '
                'Add a short retro after each session and let the learnings compound session over session. '
                '(gstack names this <code>/retro</code> — the Reflect stage.)',
                None))

    raw.sort(key=lambda x: x[0])
    return [{"priority": pri, "eyebrow": eb, "title": title, "advice_html": adv, "axis": axis}
            for pri, eb, title, adv, axis in raw[:3]]


def growth_edges(stats, scores):
    """Specific next-steps keyed off the user's OWN weakest signals — not generic advice.
    Each leads with a PRACTICE the reader can adopt today; gstack-flavored edges then name
    the gstack skill that embodies it (in parens) as an optional, installable upgrade.
    Edges come from BOTH grading systems: the gstack scorecard (how you BUILD) and the AQ
    pillars in stats["agentic"] (how you OPERATE AGENTS) — so a clean builder with a thin
    operator side still gets a real edge instead of "you're balanced". Only gated edges
    are returned; top 3, most-urgent first. NOTE for maintainers: advice HTML is
    trusted/safe-by-construction — never interpolate user/transcript-derived strings
    (skill, project, tool names) here without html.escape; today every interpolated value
    is a number or static."""
    return [(d["eyebrow"], d["title"], d["advice_html"])
            for d in _growth_edges_pool(stats, scores)]


def _strip_html(s):
    """Remove HTML tags and unescape HTML entities, returning plain text.

    Handles: <b>, <i>, <code>, and any other tags; entities &amp;, &lt;, &gt;,
    &quot;, &#39;, &#x27;.  Collapses internal whitespace to single spaces and
    strips leading/trailing whitespace.  Input is trusted safe-by-construction
    (same provenance as the advice_html / evidence_html strings)."""
    if not s:
        return ""
    # Strip all HTML tags
    text = re.sub(r"<[^>]+>", "", s)
    # Unescape HTML entities (ordered so &amp; doesn't re-escape other entities)
    text = text.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
    text = text.replace("&#39;", "'").replace("&#x27;", "'")
    text = text.replace("&amp;", "&")
    # Collapse whitespace
    return re.sub(r"\s+", " ", text).strip()


def _commands_in(s):
    """Return ordered, de-duplicated list of slash-commands found inside <code>…</code>.

    A slash-command is any <code> body that starts with '/'.  Order matches first
    appearance; duplicates are dropped.  Used to extract actionable commands from
    advice_html without any HTML parsing dependency."""
    if not s:
        return []
    seen = []
    for m in re.finditer(r"<code>(/[^<]+)</code>", s):
        cmd = m.group(1)
        if cmd not in seen:
            seen.append(cmd)
    return seen


def growth_edges_structured(stats, scores):
    """Structured version of growth_edges for the dashboard payload.

    Returns a list of up to 3 dicts:
        eyebrow   – short action label
        title     – longer title
        advice    – plain-text advice (HTML stripped, entities unescaped)
        commands  – ordered de-duped list of /slash-commands mentioned in the advice
        axis      – AQ axis name if this is an AQ-driven edge, else None
        severity  – "high" (priority < 2) | "medium" (< 5) | "low" (>= 5)
                    In practice "high" is the review/test-reflex edge or a near-zero
                    gstack axis; most edges are "medium"; "low" is the balanced fallbacks.

    HTML path is unchanged — this reads the same pool as growth_edges()."""
    result = []
    for item in _growth_edges_pool(stats, scores):
        p = item["priority"]
        severity = "high" if p < 2 else ("medium" if p < 5 else "low")
        result.append({
            "eyebrow": item["eyebrow"],
            "title": item["title"],
            "advice": _strip_html(item["advice_html"]),
            "commands": _commands_in(item["advice_html"]),
            "axis": item["axis"],
            "severity": severity,
        })
    return result


def signature_moves_structured(stats):
    """Structured version of signature_moves for the dashboard payload.

    Returns a list of up to 5 dicts:
        tag      – gstack sprint stage tag
        title    – move title
        evidence – plain-text evidence (HTML stripped, entities unescaped)

    HTML path is unchanged — this reads the same pool as signature_moves()."""
    return [
        {
            "tag": item["tag"],
            "title": item["title"],
            "evidence": _strip_html(item["evidence_html"]),
        }
        for item in _signature_moves_pool(stats)
    ]


def _pretty_model(m):
    # "claude-opus-4-7" -> "Opus 4.7"; "claude-3-5-sonnet-20241022" -> "Sonnet 3.5";
    # "gpt-5.4" -> "GPT 5.4"; "gpt-5-codex" -> "GPT 5 Codex"; "gemini-2.5-pro" -> "Gemini 2.5 Pro".
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


def _img_data_uri(path):
    try:
        import base64
        with open(path, "rb") as fh:
            return "data:image/png;base64," + base64.b64encode(fh.read()).decode()
    except Exception:
        return ""


_PROFILE_CSS = """<style>
  :root{--slate:#313941;--beak:#ED7379;--beak-deep:#D14E57;--bg:#eef1f3;--panel:#fff;
    --line:#d9dee2;--text:#16191d;--muted:#5e6a73;
    --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
    --display:"Josefin Sans","Futura","Century Gothic","Trebuchet MS",sans-serif;
    --serif:"Merriweather",Georgia,"Times New Roman",serif;}
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--text);font-family:var(--sans);line-height:1.5;-webkit-font-smoothing:antialiased}
  #report{background:var(--bg)} .mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
  a{color:var(--slate);text-decoration:none} a:hover{text-decoration:underline}
  .wrap{max-width:900px;margin:0 auto;padding:0 22px 70px}
  .topbar{background:var(--panel);border-bottom:1px solid var(--line);padding:13px 0}
  .topbar .wrap{display:flex;align-items:center;gap:12px;padding:0}
  .brandlink{display:flex;align-items:center;gap:12px;color:var(--text)} .brandlink:hover{text-decoration:none;color:var(--beak-deep)}
  .chip{width:40px;height:40px;flex:0 0 auto;background:#fff;border:1px solid var(--line);border-radius:9px;display:flex;align-items:center;justify-content:center}
  .chip img{width:32px;height:32px;object-fit:contain}
  .brand{font-family:var(--display);font-weight:700;font-size:20px;letter-spacing:.05em} .brand .dim{opacity:.6;font-weight:600;font-size:15px}
  .badge{margin-left:auto;font-size:12px;font-weight:600;color:var(--slate);background:#e8edf0;padding:5px 11px;border-radius:999px;border:1px solid var(--line)}
  .hero{padding:54px 0 30px} .eyebrow{color:var(--muted);font-size:14px;margin:0 0 16px}
  .hero h1{font-family:var(--serif);font-size:50px;line-height:1.06;margin:0 0 8px;font-weight:700;letter-spacing:-.01em} .hero h1 .accent{color:var(--beak)}
  .hero .quote{font-family:var(--serif);font-size:19px;font-style:italic;color:#3b444b;margin:18px 0 0;max-width:660px;line-height:1.55}
  .hero .sub{color:var(--muted);margin-top:18px;font-size:15px;max-width:680px} .hero .sub b{color:var(--text)}
  .stat-strip{display:flex;flex-wrap:wrap;gap:24px;margin-top:28px;padding-top:24px;border-top:1px solid var(--line)}
  .stat-strip div{display:flex;flex-direction:column} .stat-strip .n{font-family:var(--serif);font-size:25px;font-weight:700} .stat-strip .l{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}
  .share{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-top:34px} .share .lbl{font-size:13px;color:var(--muted)}
  .btn{display:inline-flex;align-items:center;gap:8px;padding:9px 15px;border-radius:999px;cursor:pointer;font-weight:600;font-size:14px;color:#fff;border:1px solid transparent;font-family:var(--sans)}
  .btn:hover{text-decoration:none;opacity:.9} .btn.x{background:#000} .btn.ghost{background:#fff;color:var(--slate);border-color:var(--line)}
  .btn svg{width:15px;height:15px} .btn.x svg{fill:#fff}
  h2.section{font-family:var(--display);font-size:15px;text-transform:uppercase;letter-spacing:.18em;color:var(--slate);margin:60px 0 14px;font-weight:700}
  p.lead{color:var(--muted);font-size:14.5px;margin:-4px 0 20px;max-width:700px;line-height:1.55}
  .card code{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12.5px;background:#eef1f3;color:var(--beak-deep);padding:1px 5px;border-radius:4px}
  .disclaimer{background:#fff;border:1px solid var(--line);border-left:4px solid var(--beak);border-radius:6px;padding:14px 16px;margin:-6px 0 24px;font-size:13.5px;color:#48535b;line-height:1.55} .disclaimer b{color:var(--text)}
  .score{display:grid;grid-template-columns:160px 1fr 46px;align-items:center;gap:14px;margin:0 0 14px} .score .name{font-weight:600;font-size:15px}
  .score .track,.aq-axis .track,.prog-row .track{display:block;height:12px;background:#dde2e6;border-radius:999px;overflow:hidden} .score .fill,.aq-axis .fill,.prog-row .fill{display:block;height:100%;min-width:8px;background:linear-gradient(90deg,var(--beak-deep),var(--beak));border-radius:999px}
  .score .val{font-weight:800;text-align:right} .score .note{grid-column:1/-1;color:var(--muted);font-size:13px;margin:-6px 0 4px;padding-left:174px}
  @media(max-width:560px){.score .note{padding-left:0}}
  .steerread{display:grid;grid-template-columns:160px 1fr;align-items:baseline;gap:14px;margin:4px 0 6px;padding-top:14px;border-top:1px solid var(--line)} .steerread .sr-k{font-weight:600;font-size:15px}
  .steerread .sr-v{font-size:15px;color:#48535b} .steerread .sr-v b{color:var(--beak-deep);font-weight:700} .steerread .sr-d{grid-column:2;color:var(--muted);font-size:13px;margin-top:2px}
  @media(max-width:560px){.steerread{grid-template-columns:1fr}.steerread .sr-d{grid-column:1}}
  .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(255px,1fr));gap:14px}
  .card{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:18px 18px 16px;box-shadow:0 1px 2px rgba(20,30,40,.04)} .card.flag{border-left:4px solid var(--beak)}
  .card .q{color:var(--beak-deep);font-size:12.5px;font-weight:700;margin:0 0 8px;text-transform:uppercase;letter-spacing:.03em}
  .card .reroll{font-family:var(--sans);text-transform:none;letter-spacing:0;font-size:11px;font-weight:600;color:var(--beak-deep);background:none;border:1px solid var(--line);border-radius:999px;padding:1px 8px;margin-left:8px;cursor:pointer;vertical-align:middle}
  .card .reroll:hover{background:#fff;border-color:var(--beak)}
  .card .a{font-family:var(--serif);font-size:19px;font-weight:700;margin:0 0 6px} .card .d{color:var(--muted);font-size:13.5px;margin:0}
  footer{margin-top:54px;padding-top:22px;border-top:1px solid var(--line);color:var(--muted);font-size:13px;line-height:1.7} footer .lock{color:var(--beak-deep);font-weight:700} footer .by{color:var(--text)}
  .aq-head{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap;margin:0 0 6px}
  .aq-big{font-family:var(--serif);font-size:46px;font-weight:800;color:var(--beak-deep);line-height:1}
  .aq-tier{font-size:12px;letter-spacing:.1em;text-transform:uppercase;color:var(--beak-deep);border:1px solid var(--beak);border-radius:999px;padding:4px 11px}
  .aq-axis{display:grid;grid-template-columns:200px 1fr 56px;align-items:center;gap:14px;margin:0 0 12px}
  .aq-axis .nm{font-weight:600;font-size:14px} .aq-axis .vl{font-weight:800;text-align:right}
  .prog-row{display:grid;grid-template-columns:74px 1fr 260px;align-items:center;gap:14px;margin:0 0 10px}
  .prog-row .nm{font-weight:700;font-size:13px} .prog-row .vl{font-size:12.5px;color:var(--muted);text-align:right;white-space:nowrap}
  @media(max-width:640px){.prog-row{grid-template-columns:64px 1fr;}.prog-row .vl{display:none}}
  .aq-split{margin-top:18px;background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:15px 16px}
  .aq-split .bar{display:flex;height:28px;border-radius:6px;overflow:hidden;font-size:11.5px;font-weight:700;margin:8px 0}
  .aq-split .cli{background:var(--beak-deep);color:#fff;display:flex;align-items:center;padding:0 12px}
  .aq-split .mcp{background:var(--beak);color:#fff;display:flex;align-items:center;justify-content:flex-end;padding:0 12px}
  .aq-split .meta{font-size:12.5px;color:var(--muted);margin:6px 0 0;line-height:1.5} .aq-split .meta b{color:var(--text)}
  .aq-pillar{margin:18px 0 4px;display:flex;align-items:baseline;gap:10px}
  .aq-pillar .pn{font-family:var(--display);font-size:13px;text-transform:uppercase;letter-spacing:.12em;color:var(--slate);font-weight:700}
  .aq-pillar .pv{font-weight:800;color:var(--beak-deep)}
  .aq-pillar .pw{font-size:12px;color:var(--muted)}
  .aq-axis .nm[title],.aq-pillar .pn[title]{cursor:help;text-decoration:underline dotted;text-underline-offset:3px;text-decoration-color:var(--muted)}
</style>"""


def _plain(s):
    """Flatten the trusted <b>/<i>/<code> markup (and the few HTML entities we emit) out of
    a card string so it can be drawn as plain text on the canvas poster. Inputs are
    safe-by-construction (numbers / static templates — see _card)."""
    s = re.sub(r"<[^>]+>", "", s or "")
    for a, b in (("&amp;", "&"), ("&rsquo;", "’"), ("&lsquo;", "‘"),
                 ("&ldquo;", "“"), ("&rdquo;", "”"), ("&mdash;", "—")):
        s = s.replace(a, b)
    return s


def _card(q, a, d, flag=False):
    # q/a/d are injected RAW (no escaping) so callers can use intentional <b>/<code>/<i>
    # markup. Every caller must pass safe-by-construction strings: numbers, static
    # templates, or html.escape()'d values — NEVER raw user/transcript-derived text.
    cls = "card flag" if flag else "card"
    return f'<div class="{cls}"><p class="q">{q}</p><p class="a">{a}</p><p class="d">{d}</p></div>'


def _hero_lead(archetype):
    """The HTML hero says "You're a {archetype}" — but the "The …" archetypes (The Architect/
    Director/Builder/Bulldozer) would read "You're a The Architect". Drop the article for those.
    The archetype string itself is never altered, so the poster keeps its "The Architect." title.
    (No archetype starts with a vowel, so "a" is always right for the rest.)
    NOTE: gnomon's hero headline is the AQ tier (an adjective — "Elite"), rendered with a bare
    "You're"; this helper is kept for upstream parity (tests + future merges)."""
    return "You're" if (archetype or "")[:4].lower() == "the " else "You're a"


def _profile_signals(stats):
    """Derive every shared display signal from stats, ONCE — PURE, no rendering.

    Single home for the formulas used by BOTH the "What we noticed" cards (noticed_cards)
    and the share poster (write_profile_html). Returns a dict; keys map to the values both
    consumers read. Escaping of model/tool fields and the inline <b>/HTML in detail strings
    is baked in here, identical to the original inline derivation. Changing a threshold (e.g.
    the weekend 0.6 ratio or the teammate 0.05/0.04 cutoffs) here updates cards and poster
    together — no silent desync."""
    import html as _h
    v, vel, b, r, t, st = (stats["volume"], stats["velocity"], stats["behavior"],
                           stats["rhythm"], stats["tools"], stats["stack"])

    peak = (r["peak_hours_local"] or [12])[0]
    tod = ("Night owl" if (peak >= 22 or peak <= 4) else "Morning person" if peak <= 11
           else "Afternoon" if peak <= 16 else "Evening")
    h12 = f'{(peak - 1) % 12 + 1}{"am" if peak < 12 else "pm"}'   # 17 -> "5pm", 0 -> "12am"
    wd = r["weekday_histogram"]
    wknd = wd.get("Sat", 0) + wd.get("Sun", 0)
    wkday_avg = sum(wd.get(d, 0) for d in ["Mon", "Tue", "Wed", "Thu", "Fri"]) / 5 or 1
    weekend_a = "No days off" if wknd / 2 >= wkday_avg * 0.6 else "Weekday warrior"
    _DAYFULL = {"Mon": "Monday", "Tue": "Tuesday", "Wed": "Wednesday", "Thu": "Thursday",
                "Fri": "Friday", "Sat": "Saturday", "Sun": "Sunday"}
    busy_day = _DAYFULL.get((r["preferred_days"] or ["—"])[0], (r["preferred_days"] or ["—"])[0])
    weekend_d = (f'Your busiest day is {busy_day} — and you logged time most days, weekends included.'
                 if weekend_a == "No days off" else f'Your busiest day is {busy_day}; weekends stay quiet.')
    models = st.get("models", [])
    mtot = sum(n for _, n in models) or 1
    model_a = _h.escape(" → ".join(_pretty_model(m) for m, _ in models[:2]) or "—")
    model_d = _h.escape((", ".join(f"{_pretty_model(m)} {round(n/mtot*100)}%" for m, n in models[:2]) + " of turns.") if models else "—")
    top_tool = (t["top_tools"][0] if t["top_tools"] else ["—", 0])
    top_tool_name = _h.escape(str(top_tool[0]))
    sess = max(v["total_sessions"], 1)
    prompts = max(v["total_prompts"], 1)
    per_sess = round(b["delegate_actions"] / sess, 1)
    two_gears = v["avg_prompt_length_chars"] > v["median_prompt_length_chars"] * 2
    prompt_a = "Short, with the odd essay" if two_gears else "Consistent length"
    prompt_d = (f'Half run under {v["median_prompt_length_chars"]:,.0f} characters — quick commands — '
                f'but the average is {v["avg_prompt_length_chars"]:,.0f}.' if two_gears else
                f'Median {v["median_prompt_length_chars"]:,.0f} characters, average {v["avg_prompt_length_chars"]:,.0f} — pretty steady.')
    polite_n = b.get("polite_prompts", 0)
    polite_rate = polite_n / prompts
    polite_a = ("You say thanks a lot" if polite_rate >= 0.12 else
                "Polite enough" if polite_rate >= 0.04 else "All business")
    polite_d = (f'You said please or thank-you in <b>{polite_n:,}</b> of your {v["total_prompts"]:,} prompts '
                f'({polite_rate*100:.0f}%).' + (" When the robots take over, they'll remember."
                                                if polite_rate >= 0.12 else ""))
    lr = b.get("longest_run_minutes", 0)
    lr_h, lr_m = int(lr // 60), int(lr % 60)
    longrun_a = f'{lr_h}h {lr_m}m' if lr_h else f'{lr_m}m'
    qrate_c = b["questions_asked"] / prompts
    teammate = polite_rate >= 0.05 or qrate_c >= 0.04
    agent_a = "Like a teammate" if teammate else "Like a tool"
    agent_d = ('You bounce ideas off it and ask for pushback — more collaborator than command line.'
               if teammate else 'You hand it work and check the result — more command line than collaborator.')
    return {
        "tod": tod, "h12": h12,
        "weekend_a": weekend_a, "weekend_d": weekend_d,
        "model_a": model_a, "model_d": model_d,
        "top_tool": top_tool, "top_tool_name": top_tool_name,
        "per_sess": per_sess,
        "prompt_a": prompt_a, "prompt_d": prompt_d,
        "polite_a": polite_a, "polite_d": polite_d,
        "longrun_a": longrun_a,
        "agent_a": agent_a, "agent_d": agent_d,
    }


def noticed_cards(stats, voice=None):
    """Derive the 12 "What we noticed" cards from stats — PURE: no rendering.

    Returns a list of (question, answer, detail) tuples in display order, exactly
    the args write_profile_html passes to _card(...). All shared formulas come from
    _profile_signals (single source of truth, shared with the poster).
    These cards are descriptive (unflagged); the coral flag is reserved for Growth-edge
    cards, which are derived elsewhere."""
    b, vel = stats["behavior"], stats["velocity"]
    s = _profile_signals(stats)
    # "What we noticed" — question-framed eyebrows + plain second-person copy (no jargon).
    return [
        ("How much did you ship?", "Depends how you count",
         f'Edit/Write touched <b>{vel["tool_churn_edit_write"]:,}</b> lines and the shell ~{vel["shell_authored_lines_est"]:,} '
         f'more — but only <b>{vel["git_churn_total"]:,}</b> actually landed in committed git history. '
         f'That committed number is the honest one.'),
        ("How hard do you grind?", f'{b["iteration_depth_max"]}× on one file',
         f'Your deepest single-file grind in one session — and {b["files_hammered_over_15x"]} files went past 15 edits. '
         f'Your typical file, though? About {b["iteration_depth_mean"]:.1f}.'),
        ("How often do things break?", f'{b["tool_errors"]:,} errors, {round(b["error_recovery_ratio"]*100)}% recovered',
         f'Roughly {b["error_rate_per_100_tools"]} per 100 tool calls — and you kept going after almost all of them.'),
        ("Which model do you reach for?", s["model_a"], s["model_d"]),
        ("When do you do your best work?", s["tod"], f'You do your heaviest work around {s["h12"]}.'),
        ("Do you take weekends off?", s["weekend_a"], s["weekend_d"]),
        ("How long are your prompts?", s["prompt_a"], s["prompt_d"]),
        ("How many agents do you run?", f'{b["delegate_actions"]:,} subagents',
         f'About {s["per_sess"]} per session, plus {b["background_tasks"]:,} background tasks and {b["scheduled_actions"]} scheduled runs.'),
        ("How do you see your agent?", s["agent_a"], s["agent_d"]),
        ("How polite are you to it?", s["polite_a"], s["polite_d"]),
        ("What's your longest run?", s["longrun_a"],
         'Your longest unbroken stretch of active work in a single session.'),
        ("What's your go-to tool?", s["top_tool_name"], f'{s["top_tool"][1]:,} calls — more than any other tool.'),
    ]


def write_profile_html(stats, archetype, quote, scores, voice=None):
    import html as _h
    v, vel, b, r, t, st, c = (stats["volume"], stats["velocity"], stats["behavior"],
                              stats["rhythm"], stats["tools"], stats["stack"], stats["corpus"])
    logo = _img_data_uri(os.path.join(OUT_DIR, "tern.png"))
    chip = f'<span class="chip"><img src="{logo}" alt="Roadmap tern"></span>' if logo else ""

    cards = [_card(q, a, d) for (q, a, d) in noticed_cards(stats, voice)]

    # The share POSTER (built below) reuses several of the same derived insights as the
    # cards (per_sess, tod/h12, weekend, agent-perception, politeness). Both read from the
    # one pure helper, so a threshold change can't desync card copy from poster copy.
    sig = _profile_signals(stats)
    per_sess = sig["per_sess"]

    score_rows = "".join(
        f'<div class="score"><span class="name">{name}</span>'
        f'<span class="track"><span class="fill" style="width:{val*10:.0f}%"></span></span>'
        f'<span class="val mono">{val}</span>'
        + (f'<span class="note">{_h.escape(SCORE_NOTES[name])}</span>' if name in SCORE_NOTES else "")
        + '</div>'
        for name, val in scores.items())

    moves = signature_moves(stats)
    edges = growth_edges(stats, scores)
    steer_read = steering_reading(stats)   # Steering is described here, not scored
    moves_html = "".join(_card(tag, title, ev) for tag, title, ev in moves)
    edges_html = "".join(_card(eb, title, adv, flag=True) for eb, title, adv in edges)

    # Data for the canvas-drawn share POSTER (one tall 1200px-wide PNG, drawn at download
    # time so there's no foreignObject → no canvas taint → it works in every browser).
    # Carries: archetype + tagline + timeframe, the scorecard (with one-line notes) paired
    # with the headline numbers, and the curated insight/quote cards. SUBSTANCE FIRST: the
    # signature move + insights lead; the two quote cards (funny, low-substance) come LAST.
    # Quotes are routed through _safe_quote, and the off-the-cuff card is re-read LIVE from
    # the page (#q-cuff) at click time, so a reroll is honored and the user is the gate.
    _voc = voice or {}
    poster_cards = []
    if moves:
        _mtag, _mtitle, _mev = moves[0]
        poster_cards.append({"mode": "insight", "eyebrow": _plain(_mtag),
                             "headline": _plain(_mtitle), "sub": _plain(_mev)})
    if b["delegate_actions"] > 0:
        poster_cards.append({"mode": "insight", "eyebrow": "How many agents?",
                             "headline": f'{b["delegate_actions"]:,} subagents',
                             "sub": f'About {per_sess} per session, plus {b["background_tasks"]:,} '
                                    f'background tasks and {b["scheduled_actions"]} scheduled runs.'})
    poster_cards += [
        {"mode": "insight", "eyebrow": "Best work?", "headline": sig["tod"],
         "sub": f"Heaviest work around {sig['h12']}."},
        {"mode": "insight", "eyebrow": "Weekends?", "headline": sig["weekend_a"], "sub": _plain(sig["weekend_d"])},
        {"mode": "insight", "eyebrow": "Your agent is…", "headline": sig["agent_a"], "sub": _plain(sig["agent_d"])},
        {"mode": "insight", "eyebrow": "Polite to it?", "headline": sig["polite_a"], "sub": _plain(sig["polite_d"])},
    ]
    if _voc.get("goto") and _safe_quote(_voc["goto"][0]):
        _ph, _cnt, _ns = _voc["goto"]
        poster_cards.append({"mode": "quote", "eyebrow": "Go-to prompt",
                             "headline": _ph, "sub": f"Most-repeated — {_cnt:,}×."})
    if _voc.get("cryptics"):
        poster_cards.append({"mode": "quote", "eyebrow": "Off the cuff", "live": "cuff",
                             "headline": _voc["cryptics"][0], "sub": "Straight from the keyboard."})

    _tag = quote.strip()
    if _tag:
        _tag = _tag[0].upper() + _tag[1:]
        if _tag[-1] not in ".!?":
            _tag += "."
    _dr = c["date_range"] or ["", ""]
    # timeframe + sessions only — prompts/tool-calls already live in "By the numbers".
    _context = f'{_mon_yr(_dr[0])} → {_mon_yr(_dr[1])}  ·  {v["total_sessions"]:,} sessions'
    # Lead "By the numbers" stat adapts so a non-delegating user (most Codex/Gemini users, and
    # plenty of Claude ones) never gets a weak "0.0 agents / session" headline: agents/session
    # for real delegators → else reasoning blocks → else lines edited (all universally non-zero).
    if b["delegate_actions"] >= 20 and per_sess >= 0.5:
        _first_stat = [f'{per_sess}', "agents / session"]
    elif v["thinking_blocks"] >= 50:
        _first_stat = [f'{v["thinking_blocks"]:,}', "reasoning blocks"]
    else:
        _first_stat = [f'{vel["tool_churn_edit_write"]:,}', "lines edited"]
    card_data = _js({
        "arch": archetype,
        "tagline": _tag,
        "context": _context,
        "scores": [[k, val, SCORE_NOTES_SHORT.get(k, "")] for k, val in scores.items()],
        "steering": {"label": steer_read["label"], "gloss": steer_read["gloss"]},  # poster uses the short gloss; the longer detail is page-only
        "stats": [_first_stat,
                  [f'{v["total_prompts"]:,}', "prompts"],
                  [f'{v["tool_calls_total"]:,}', "tool calls"],
                  [f'{vel["git_churn_total"]:,}', "git lines"]],
        "cards": poster_cards,
        "logo": logo,
    })

    caption = ("My “how I build with AI” profile, computed 100% locally — nothing uploaded. "
               "Made with paxel-local, an MIT rebuild of YC's Paxel that keeps your sessions on your machine. "
               "Run your own: " + REPO_URL)

    eyebrow = (f'{v["total_sessions"]} sessions · {v["total_prompts"]:,} prompts · '
               f'{v["tool_calls_total"]:,} tool calls · {_d10(c["date_range"][0])} → {_d10(c["date_range"][1])}')

    parts = []
    P = parts.append
    P("<!DOCTYPE html>")
    P("<!-- Generated locally by paxel.py. Zero data left this machine. Counts measured; archetype/scores are a rubric. -->")
    P('<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">')
    P("<title>Builder Profile — Roadmap</title>")
    if logo:
        P(f'<link rel="icon" href="{logo}">')
    P(_PROFILE_CSS)
    P('</head><body><div id="report">')
    P('<div class="topbar"><div class="wrap">'
      f'<a class="brandlink" href="https://www.roadmap.chat/community" target="_blank" rel="noopener" title="Roadmap — find your flock">'
      f'{chip}<span class="brand">Roadmap <span class="dim">· Builder Profile</span></span></a>'
      '<span class="badge">🔒 Generated locally · nothing uploaded</span></div></div>')
    P('<div class="wrap"><section class="hero">')
    P(f'<p class="eyebrow">{eyebrow}</p>')
    P(f'<h1>You\'re<br><span class="accent">{_h.escape(archetype)}.</span></h1>')
    P(f'<p class="quote">“{_h.escape(quote)}”</p>')
    P(f'<p class="sub"><b>{v["thinking_blocks"]:,} reasoning blocks</b> before the diffs, '
      f'<b>{b["delegate_actions"]:,} subagents</b> dispatched, and <b>{b["tool_errors"]:,} errors</b> recovered from along the way.</p>')
    P('<div class="stat-strip">'
      f'<div><span class="n mono">{vel["git_churn_total"]:,}</span><span class="l">lines committed to git</span></div>'
      f'<div><span class="n mono">{vel["tool_churn_edit_write"]:,}</span><span class="l">lines via Edit/Write</span></div>'
      f'<div><span class="n mono">~{vel["shell_authored_lines_est"]:,}</span><span class="l">lines in the shell</span></div>'
      f'<div><span class="n mono">{b["iteration_depth_max"]}</span><span class="l">max edits, one file</span></div>'
      f'<div><span class="n mono">{b["delegate_actions"]:,}</span><span class="l">agents you ran</span></div></div>')
    P('<div class="share"><span class="lbl">Share:</span>'
      '<a id="share-x" class="btn x" href="#" target="_blank" rel="noopener">'
      '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231 5.45-6.231Zm-1.161 17.52h1.833L7.084 4.126H5.117L17.083 19.77Z"/></svg>Post on X</a>'
      '<button id="share-copy" class="btn ghost" type="button">📋 Copy caption</button>'
      '<button id="share-img" class="btn ghost" type="button">🖼 Download image</button></div>')
    P('</section><h2 class="section">Your scorecard</h2>')
    P('<div class="disclaimer"><b>Counts are measured; the three scores are a read on your style</b>, '
      'grounded in <a href="https://github.com/garrytan/gstack" target="_blank" rel="noopener">gstack</a> '
      '— how you work, not a ranking of how good you are. <b>Steering isn\'t scored</b>: how hands-on you '
      'run agents has no better or worse end, so it\'s described, not graded.'
      ' This scorecard grades how you <b>build</b> (gstack); the Agentic Quotient further down grades how you <b>operate agents</b>.</div>')
    if _evidence(stats) < 0.5:   # < ~1000 tool calls: too thin to read habits confidently
        P(f'<div class="disclaimer" style="border-left-color:var(--muted)">⚠ <b>Limited data.</b> '
          f'Just {v["total_sessions"]} sessions and {v["tool_calls_total"]:,} tool calls here — not enough to read '
          f'your habits with confidence, so these scores lean toward the middle. Run more and check back.</div>')
    P(score_rows)
    P(f'<div class="steerread"><span class="sr-k">Steering</span>'
      f'<span class="sr-v"><b>{_h.escape(steer_read["label"])}</b> — {_h.escape(steer_read["gloss"])}</span>'
      f'<span class="sr-d">{_h.escape(steer_read["detail"])}</span></div>')
    aq = stats.get("agentic")
    if aq:
        P('<h2 class="section">Agentic Quotient — how you operate agents</h2>')
        P('<div class="disclaimer"><b>The scorecard above grades how you BUILD</b> (gstack). '
          '<b>The Agentic Quotient grades how you OPERATE AGENTS</b> — orchestration, craft, efficiency, '
          'and savvy. A custom metric (not part of paxel). MCP-vs-CLI and tool diversity are '
          '<b>described, not graded</b>, like Steering.</div>')
        P(f'<div class="aq-head"><span class="aq-big">{aq["aq_0_100"]}</span>'
          f'<span class="aq-tier">{_h.escape(aq["tier"])}</span></div>')
        def _tt(note):   # hover tooltip (native title attr); empty note -> no attr
            return f' title="{_h.escape(note)}"' if note else ""
        for pillar in aq["pillars"]:
            P(f'<div class="aq-pillar"><span class="pn"{_tt(AQ_PILLAR_NOTES.get(pillar["name"], ""))}>'
              f'{_h.escape(pillar["name"])}</span>'
              f'<span class="pv">{pillar["score"]:.0f}</span><span class="pw">/ {pillar["weight"]} weight</span></div>')
            for ax in pillar["axes"]:
                pct = (ax["score"] / ax["weight"] * 100) if ax["weight"] else 0
                P(f'<div class="aq-axis"><span class="nm"{_tt(AQ_AXIS_NOTES.get(ax["name"], ""))}>'
                  f'{_h.escape(ax["name"])}</span>'
                  f'<span class="track"><span class="fill" style="width:{pct:.0f}%"></span></span>'
                  f'<span class="vl mono">{ax["score"]:.0f}/{ax["weight"]}</span></div>')
        mv = aq["mcp_vs_cli"]
        cli_calls, mcp_calls = mv["cli_calls"], mv["mcp_calls"]
        tot = (cli_calls + mcp_calls) or 1
        cli_pct = max(8, round(cli_calls / tot * 100))
        _ratio = f'{mv["ratio"]}:1' if mv["ratio"] is not None else "all-CLI (no MCP)"
        P('<div class="aq-split"><b>MCP vs CLI</b> — described, not graded'
          f'<div class="bar"><span class="cli" style="flex:{cli_pct}">CLI · {cli_calls:,} · {mv["cli_distinct"]} tools</span>'
          f'<span class="mcp" style="flex:{100-cli_pct}">MCP · {mcp_calls:,} · {mv["mcp_distinct"]}</span></div>'
          f'<p class="meta">Ratio <b>{_ratio}</b> CLI-first. CLI is token-cheap and scriptable — '
          'you reach for it on repeatable work and reserve MCP for what CLI can\'t do (browser, design canvas, '
          'device control). Right instinct, not a gap.</p>'
          f'<p class="meta"><b>Tool diversity</b> · {aq["tool_diversity"]["distinct"]} distinct tools, '
          f'entropy {aq["tool_diversity"]["entropy"]} — high range available, concentrated use. Not penalized.</p>'
          '</div>')
    prog = (stats.get("progression") or {}).get("monthly") or []
    if len(prog) >= 2:
        P('<h2 class="section">Your trajectory</h2>')
        P('<p class="lead">Month by month. When plan limits cap any single month, '
          'the <b>slope</b> is the honest signal — not the lifetime totals.</p>')
        _tmx = max(p["tool_calls"] for p in prog) or 1
        for p in prog:
            _pct = max(2, round(p["tool_calls"] / _tmx * 100))
            _top = f' · {_h.escape(_pretty_model(p["top_model"]))}' if p["top_model"] else ""
            P(f'<div class="prog-row"><span class="nm mono">{_h.escape(p["month"])}</span>'
              f'<span class="track"><span class="fill" style="width:{_pct}%"></span></span>'
              f'<span class="vl">{p["tool_calls"]:,} calls · {p["prompts"]:,} prompts · '
              f'{p["active_days"]}d{_top}</span></div>')
    if moves:
        P('<h2 class="section">Your signature moves</h2>')
        P('<p class="lead">The patterns in how you direct the AI, pulled from your real sessions. The tag on each '
          'card is the gstack stage it maps to.</p>')
        P(f'<div class="grid">{moves_html}</div>')
    if edges:
        P('<h2 class="section">Your growth edge</h2>')
        P('<p class="lead">A few habits to try — each pulled from your own data, not a generic checklist. The '
          '<code>/commands</code> in parentheses are optional tools from '
          '<a href="https://github.com/garrytan/gstack" target="_blank" rel="noopener">gstack</a> '
          'if you\'d rather automate one of them.</p>')
        P(f'<div class="grid">{edges_html}</div>')
    P('<h2 class="section">What we noticed</h2><div class="grid">')
    P("".join(cards))
    P('</div>')

    # "In your own words" — VERBATIM prompt quotes (each already _safe_quote-filtered for
    # secrets/PII upstream). Rendered on the local page (gitignored). The go-to and the
    # off-the-cuff also feed the shareable poster (see poster_cards above) — the off-cuff via
    # a LIVE read of #q-cuff at download, so a reroll is honored. The crash-out stays
    # page-only. Escape every quote (raw user text → XSS). Only render cards that exist.
    voice = voice or {}
    vcards = []
    quote_js = {}   # target -> [raw quotes] for the ↻ reroll button (cycles the pool client-side)

    def _quote_card(eyebrow, target, pool, desc):
        quote_js[target] = pool
        reroll = (f' <button type="button" class="reroll" data-target="{target}">&#8635; another</button>'
                  if len(pool) > 1 else "")
        return (f'<div class="card"><p class="q">{eyebrow}{reroll}</p>'
                f'<p class="a" id="q-{target}">&ldquo;{_h.escape(pool[0])}&rdquo;</p>'
                f'<p class="d">{desc}</p></div>')

    if voice.get("goto"):
        ph, cnt, ns = voice["goto"]
        vcards.append(_card("What's your go-to prompt?", f'&ldquo;{_h.escape(ph)}&rdquo;',
              f'Your most-repeated prompt — <b>{cnt:,}</b> times across {ns} sessions.'))
    if voice.get("crashouts"):
        vcards.append(_quote_card("Your biggest crash-out?", "crashout", voice["crashouts"],
              "One of your most heated prompts. We&rsquo;ve all been there."))
    if voice.get("cryptics"):
        vcards.append(_quote_card("Off the cuff?", "cuff", voice["cryptics"],
              "One of your more unfiltered asks — straight from the keyboard, unedited."))
    if vcards:
        P('<h2 class="section">In your own words</h2>')
        P('<p class="lead">Pulled <b>verbatim</b> from your real prompts (filtered for secrets &amp; PII) — '
          'hit <b>&#8635; another</b> to reroll. Your go-to and off-the-cuff lines also land on the shareable '
          'image; the off-the-cuff one uses <b>whichever you&rsquo;ve rerolled to</b>, so land on one you like '
          'before you download. Everything else stays on this local page, on your machine.</p>')
        P(f'<div class="grid">{"".join(vcards)}</div>')

    P('<footer><span class="lock">🔒 Generated entirely on-device</span> by <span class="mono">paxel.py</span> — '
      'the same analysis Paxel runs, with zero data sent anywhere. Counts measured from your transcripts; '
      'archetype &amp; scores are a rubric. Raw metrics in <span class="mono">stats.json</span>.<br>'
      'Built by <a class="by" href="https://github.com/Photobombastic" target="_blank" rel="noopener">Max Schilling</a>, '
      '<a href="https://www.roadmap.chat/community" target="_blank" rel="noopener">Roadmap</a></footer>')
    P('</div></div>')
    P("<script>(function(){")
    P('var QUOTES=' + _js(quote_js) + ';var QIDX={};')
    P('document.querySelectorAll(".reroll").forEach(function(b){b.addEventListener("click",function(){'
      'var t=b.getAttribute("data-target"),arr=QUOTES[t];if(!arr||arr.length<2)return;'
      'QIDX[t]=((QIDX[t]||0)+1)%arr.length;var el=document.getElementById("q-"+t);'
      'if(el)el.textContent="\\u201c"+arr[QIDX[t]]+"\\u201d";});});')
    P(f'var caption={_js(caption)};')
    P('var x=document.getElementById("share-x");if(x)x.href="https://x.com/intent/tweet?text="+encodeURIComponent(caption);')
    P('var cb=document.getElementById("share-copy");if(cb)cb.addEventListener("click",function(){'
      'var d=function(){var o=cb.textContent;cb.textContent="✓ Copied";setTimeout(function(){cb.textContent=o;},1500);};'
      'if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(caption).then(d).catch(fb);}else{fb();}'
      'function fb(){var ta=document.createElement("textarea");ta.value=caption;document.body.appendChild(ta);ta.select();'
      'try{document.execCommand("copy");}catch(e){}document.body.removeChild(ta);d();}});')
    P('var CARD=' + card_data + ';')
    P(r'''var ib=document.getElementById("share-img");
if(ib)ib.addEventListener("click",function(){
  try{
    if(typeof HTMLCanvasElement==="undefined"||!HTMLCanvasElement.prototype.toBlob){alert("Image export isn't supported in this browser — try a screenshot.");return;}
    var W=1200,M=48,s=3,IW=W-2*M;   // 3x supersample so the logo art stays crisp when zoomed/retina
    var beak="#ED7379",beakD="#D14E57",slate="#313941",mut="#5e6a73",line="#dfe3e7",track="#dde2e6";
    function L(c,t,mw){var ws=String(t).split(" "),ln="",o=[];for(var i=0;i<ws.length;i++){var tn=ln?ln+" "+ws[i]:ws[i];if(c.measureText(tn).width>mw&&ln){o.push(ln);ln=ws[i];}else ln=tn;}o.push(ln);return o;}
    function rr(c,x,y,w,h,r){c.beginPath();c.moveTo(x+r,y);c.arcTo(x+w,y,x+w,y+h,r);c.arcTo(x+w,y+h,x,y+h,r);c.arcTo(x,y+h,x,y,r);c.arcTo(x,y,x+w,y,r);c.closePath();}
    function box(c,x,y,w,h){c.save();c.shadowColor="rgba(40,50,60,.10)";c.shadowBlur=20;c.shadowOffsetY=7;c.fillStyle="#fff";rr(c,x,y,w,h,16);c.fill();c.restore();c.strokeStyle="#e8ebee";c.lineWidth=1;rr(c,x,y,w,h,16);c.stroke();}
    function mini(c,x,y,w,h,card){
      var pad=20,iw=w-2*pad,cx=x+w/2;box(c,x,y,w,h);c.textAlign="center";
      c.fillStyle=beakD;c.font="700 10.5px -apple-system,sans-serif";if(c.letterSpacing!==undefined)c.letterSpacing="1px";
      var el=L(c,String(card.eyebrow).toUpperCase(),iw);if(el.length>2)el=el.slice(0,2);
      for(var k=0;k<el.length;k++)c.fillText(el[k],cx,y+pad+11+k*14);if(c.letterSpacing!==undefined)c.letterSpacing="0px";
      // TOP-ANCHOR the content (not vertically centered) so every headline in a row shares
      // a baseline; leftover whitespace collects at the bottom of shorter cards.
      var ebBot=y+pad+11+(el.length-1)*14+6,gTop=ebBot+14,q=card.mode==="quote";
      var hfs=q?29:23;function hf(z){return (q?"italic 800 ":"800 ")+z+"px Georgia,serif";}
      var head=q?("“"+card.headline+"”"):card.headline;c.font=hf(hfs);var hl=L(c,head,iw);
      while(hl.length>2&&hfs>16){hfs-=1;c.font=hf(hfs);hl=L(c,head,iw);}
      if(hl.length>2){hl=hl.slice(0,2);hl[1]=hl[1].replace(/[\s—-]+$/,"")+"…";}
      var hLH=hfs+4;c.fillStyle="#181c1f";c.font=hf(hfs);for(var k=0;k<hl.length;k++)c.fillText(hl[k],cx,gTop+hfs-2+k*hLH);
      c.font="400 13px -apple-system,sans-serif";var sl=L(c,card.sub,iw),smax=q?2:3;
      if(sl.length>smax){sl=sl.slice(0,smax);sl[smax-1]=sl[smax-1].replace(/[\s—-]+$/,"")+"…";}
      var sTop=gTop+hl.length*hLH+12;c.fillStyle=mut;c.font="400 13px -apple-system,sans-serif";
      for(var k=0;k<sl.length;k++)c.fillText(sl[k],cx,sTop+11+k*18);
      c.textAlign="left";
    }
    // WYSIWYG: pull whatever quote is showing on the page now into any "live" card (off-cuff reroll)
    var cards=CARD.cards.map(function(cd){
      if(cd.live){var el=document.getElementById("q-"+cd.live);
        if(el){var t=el.textContent.replace(/^[\s“"]+/,"").replace(/[\s”"]+$/,"");if(t)cd=Object.assign({},cd,{headline:t});}}
      return cd;});
    // layout — tightened top gap; height grows with the card count
    var mc=document.createElement("canvas").getContext("2d");
    var afs=88;mc.font="800 "+afs+"px Georgia,serif";while(mc.measureText(CARD.arch+".").width>IW&&afs>48){afs-=2;mc.font="800 "+afs+"px Georgia,serif";}
    mc.font="italic 27px Georgia,serif";var tll=L(mc,CARD.tagline,IW);if(tll.length>2){tll=tll.slice(0,2);tll[1]=tll[1].replace(/[\s—-]+$/,"")+"…";}   // tagline can wrap to 2 lines
    var heroY=96,archB=heroY+12+Math.round(afs*0.74),tagY=archB+40,tagLH=33,ctxY=tagY+(tll.length-1)*tagLH+30,scY=ctxY+42,scH=348,scEnd=scY+scH;
    var gridY=scEnd+30,gc=4,rows=Math.ceil(cards.length/gc),cardH=184,gapY=22;
    var gridEnd=rows>0?gridY+rows*cardH+(rows-1)*gapY:scEnd,footerY=gridEnd+44,H=footerY+34;
    while(s>1&&(W*s*H*s>16700000||H*s>4096))s--;   // iOS canvas-area/max-dim guard: degrade to a lower-res image rather than a silently-blank one
    var cv=document.createElement("canvas");cv.width=W*s;cv.height=H*s;
    var c=cv.getContext("2d");c.scale(s,s);c.textBaseline="alphabetic";c.textAlign="left";
    c.imageSmoothingEnabled=true;c.imageSmoothingQuality="high";   // proper resample of the logo, not a cheap box filter
    function finish(){cv.toBlob(function(bl){if(!bl){alert("Image export failed — try a screenshot.");return;}var u=URL.createObjectURL(bl);var a=document.createElement("a");a.href=u;a.download="builder-profile.png";a.click();setTimeout(function(){URL.revokeObjectURL(u);},4000);});}
    c.fillStyle="#edeff2";c.fillRect(0,0,W,H);c.fillStyle=beak;c.fillRect(0,0,W,8);
    var bx0=CARD.logo?M+76:M;
    c.fillStyle=slate;c.font="700 26px -apple-system,sans-serif";c.fillText("Roadmap",bx0,64);
    c.font="600 13px -apple-system,sans-serif";var bt="Generated locally · nothing uploaded",btw=c.measureText(bt).width,btx=W-M-btw;
    c.save();c.strokeStyle=mut;c.fillStyle=mut;c.lineWidth=1.5;c.beginPath();c.arc(btx-12,55,3,Math.PI,2*Math.PI);c.stroke();rr(c,btx-17,55,10,8,2);c.fill();c.restore();
    c.fillStyle=mut;c.fillText(bt,btx,61);
    c.fillStyle=beakD;c.font="700 13px -apple-system,sans-serif";if(c.letterSpacing!==undefined)c.letterSpacing="2px";c.fillText("YOUR BUILDER PROFILE",M,heroY);if(c.letterSpacing!==undefined)c.letterSpacing="0px";
    c.font="800 "+afs+"px Georgia,serif";c.fillStyle=beak;c.fillText(CARD.arch+".",M,archB);
    c.fillStyle="#3b444b";c.font="italic 27px Georgia,serif";for(var ti=0;ti<tll.length;ti++)c.fillText(tll[ti],M,tagY+ti*tagLH);
    if(CARD.context){c.fillStyle=mut;c.font="500 15px -apple-system,sans-serif";c.fillText(CARD.context,M,ctxY);}
    box(c,M,scY,IW,scH);
    var pad=40,ix=M+pad,half=IW/2;
    c.fillStyle=mut;c.font="700 13px -apple-system,sans-serif";if(c.letterSpacing!==undefined)c.letterSpacing="1px";c.fillText("GSTACK SCORECARD",ix,scY+50);
    var stx=M+half+38;c.fillText("BY THE NUMBERS",stx,scY+50);if(c.letterSpacing!==undefined)c.letterSpacing="0px";
    var sc=CARD.scores,base=scY+96,rh=64,barL=ix+150,barR=M+half-86,valX=barR+46;
    for(var i=0;i<sc.length;i++){var ry=base+i*rh,nm=sc[i][0],vl=sc[i][1],note=sc[i][2]||"";
      c.fillStyle=slate;c.font="700 16px -apple-system,sans-serif";c.fillText(nm,ix,ry);
      var bw2=barR-barL,bh=13,by=ry-13;c.fillStyle=track;rr(c,barL,by,bw2,bh,6);c.fill();
      var g=c.createLinearGradient(barL,0,barL+bw2,0);g.addColorStop(0,beakD);g.addColorStop(1,beak);c.fillStyle=g;rr(c,barL,by,Math.max(bh,bw2*(vl/10)),bh,6);c.fill();
      c.fillStyle="#16191d";c.font="800 17px ui-monospace,Menlo,monospace";c.textAlign="right";c.fillText(Number(vl).toFixed(1),valX,ry);c.textAlign="left";
      c.fillStyle=mut;c.font="400 13px -apple-system,sans-serif";c.fillText(note,ix,ry+22);}
    if(CARD.steering){var sry=base+sc.length*rh;                       // Steering: described, not graded — no bar, no number
      c.fillStyle=slate;c.font="700 16px -apple-system,sans-serif";c.fillText("Steering",ix,sry);
      c.fillStyle=beakD;c.font="700 15px -apple-system,sans-serif";c.fillText(CARD.steering.label,barL,sry);
      c.fillStyle=mut;c.font="400 13px -apple-system,sans-serif";c.fillText(CARD.steering.gloss,ix,sry+22);}
    var dvx=M+half+4;c.strokeStyle=line;c.lineWidth=1;c.beginPath();c.moveTo(dvx,scY+38);c.lineTo(dvx,scY+scH-34);c.stroke();
    var stt=CARD.stats||[];for(var j=0;j<stt.length&&j<sc.length+1;j++){var syy=base+j*rh;
      c.fillStyle=slate;c.font="800 30px ui-monospace,Menlo,monospace";c.fillText(stt[j][0],stx,syy);var w2=c.measureText(stt[j][0]).width;
      c.fillStyle=mut;c.font="500 14px -apple-system,sans-serif";c.fillText(stt[j][1],stx+w2+12,syy);}
    var gapX=16,colW=(IW-(gc-1)*gapX)/gc;
    for(var i=0;i<cards.length;i++){var row=Math.floor(i/gc),col=i%gc;
      var inRow=Math.min(gc,cards.length-row*gc);            // cards in THIS row (last row may be partial)
      var x0=M+(IW-(inRow*colW+(inRow-1)*gapX))/2;           // center the row → partial rows don't jam left
      mini(c,x0+col*(colW+gapX),gridY+row*(cardH+gapY),colW,cardH,cards[i]);}
    c.fillStyle=mut;c.font="500 14px -apple-system,sans-serif";c.textAlign="center";c.fillText("Generated 100% on-device — nothing uploaded · github.com/Photobombastic/paxel-local",W/2,footerY);c.textAlign="left";
    if(CARD.logo){var im=new Image();im.onload=function(){
      var k=Math.min(54/im.width,54/im.height),lw=im.width*k,lh=im.height*k;   // contain-fit: never squish the logo's aspect
      c.drawImage(im,M+(54-lw)/2,32+(54-lh)/2,lw,lh);finish();};im.onerror=finish;im.src=CARD.logo;}else{finish();}
  }catch(e){alert("Image export failed — try a screenshot.");}
});''')
    P("})();</script></body></html>")
    with open(os.path.join(OUT_DIR, "profile.html"), "w") as f:
        f.write("\n".join(parts))


if __name__ == "__main__":
    main()
