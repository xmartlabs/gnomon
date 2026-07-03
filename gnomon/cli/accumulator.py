"""Single accumulation engine.

`_accumulate()` in local.py used to carry two mirrored sets of counters — the
whole-corpus accumulators as locals, and a parallel per-source `_ps[src]` dict —
updated side by side at ~125 dual-write sites in the event loop, then shaped into
stats twice. That mirror was the source of both the file's size and a silent
drift hazard (forget one `sa[...]` and a source diverges from the corpus).

This module collapses the mirror into ONE class. The corpus and every source are
just instances of `Accumulator`. The per-event update (`observe`) and the
stats-shaping (`to_corpus_stats` / `to_source_stats`) each exist exactly once;
local.py feeds every event to the corpus accumulator and to its source's
accumulator, so the two can never diverge — they run identical code.

Narrative quote candidates (opening/longest prompts, cryptic/crash-out samples)
are corpus-only and never serialized into stats, so they stay in local.py's file
loop, fed from the small info tuple `observe` returns for each genuine prompt.
"""

import math
import os
import statistics
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from gnomon.config import parse_ts, line_count, strip_injections
from gnomon.taxonomy import (
    SCHEDULE_TOOLS, ASK_TOOLS, PLAN_SIGNAL_TOOLS, PLAN_SKILL_NEEDLES,
    classify_tool, bash_writes_file, bash_runs_tests, _extract_clis,
    _is_compounding_path, _SKILL_MD_RX,
)
from gnomon.sources.discovery import _AGENT_UNSUPPORTED_SOURCES
from gnomon.analysis.churn import git_churn
from gnomon.analysis.metrics import (
    _error_rate_per_100, _error_recovery_ratio, _iteration_depth_stats,
    _fanout_median, _peak_hours, _preferred_days, _active_hours_and_longest_run,
    _token_usage_block, _usage_int,
)
from gnomon.scoring.aq import compute_aq
from gnomon.scoring.inputs import build_monthly_scoring_stats
from gnomon.output.summary import _build_monthly_noticed_stats
from gnomon.analysis.quotes import _POLITE_RE

GAP_CAP_S = 600                   # cap idle gaps at 10 min when summing active time
BURST_GAP_S = 1800                # a gap > 30 min ends a contiguous work "run"
DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _zero_tok():
    return {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0}


class Accumulator:
    """Per-event signal accumulator for one partition (the whole corpus, or one source).

    Lifecycle, driven by local.py's file loop:
        begin_file(src, fp)        # reset per-file transient state
        observe(ev, since, until)  # once per event; returns prompt info or None
        ...
        end_file()                 # flush dangling iteration-depth runs
    then one of to_corpus_stats() / to_source_stats() to shape the result.
    """

    def __init__(self):
        self.files_parsed = 0
        self.lines_total = 0
        self.lines_bad = 0

        self.session_ts = defaultdict(list)    # sessionId -> [epoch seconds]
        self.session_files = defaultdict(set)

        self.prompts_count = 0
        self.polite_prompts = 0
        self.prompt_lengths = []
        self.command_invocations = 0

        self.assistant_turns = 0
        self.text_blocks = 0
        self.thinking_blocks = 0
        self.thinking_chars = 0
        self.tool_use_total = 0
        self.tool_counter = Counter()
        self.cat_counter = Counter()
        self.mcp_calls = 0
        self.native_calls = 0

        self.model_counter = Counter()
        self.skill_counter = Counter()
        self.subagent_counter = Counter()
        self.agents_per_session = defaultdict(int)
        self.mcp_server_counter = Counter()
        self.cli_counter = Counter()
        self.compounding_counter = 0
        self.project_activity = Counter()
        self.project_sessions = defaultdict(set)

        self.lines_added = 0
        self.lines_removed = 0
        self.edits_per_file_events = []
        self.git_commits = 0
        self.background_tasks = 0
        self.scheduled_actions = 0
        self.questions_asked = 0

        self.tool_errors = 0
        self.api_errors = 0
        self.recovered_errors = 0

        self.bash_write_calls = 0
        self.bash_authored_lines = 0
        self.shell_test_runs = 0
        # Plan ceremony is a per-SESSION signal (not a raw tool count): the set of
        # sessions that contained any planning signal — a plan-mode/todo tool OR a
        # planning Skill. Counting distinct sessions (not tool calls) stops TodoWrite,
        # which fires many times per session, from inflating the metric.
        self.plan_sessions = set()

        self.hour_hist = Counter()
        self.weekday_hist = Counter()
        self.date_set = set()
        self.all_min_dt = None
        self.all_max_dt = None

        # monthly progression ("YYYY-MM" buckets)
        self.month_prompts = Counter()
        self.month_tools = Counter()
        self.month_churn = Counter()
        self.month_dates = defaultdict(set)
        self.month_sessions = defaultdict(set)
        self.month_models = defaultdict(Counter)

        self.month_assistant_turns = Counter()
        self.month_thinking_blocks = Counter()
        self.month_prompt_lengths = defaultdict(list)
        self.month_bash_write_calls = Counter()
        self.month_bash_authored_lines = Counter()
        self.month_tool_errors = Counter()
        self.month_recovered_errors = Counter()
        self.month_edits_per_file = defaultdict(list)
        self.month_polite = Counter()
        self.month_questions = Counter()
        self.month_delegate = Counter()
        self.month_background = Counter()
        self.month_scheduled = Counter()
        self.month_fanouts = defaultdict(lambda: defaultdict(int))
        self.month_hour_hist = defaultdict(Counter)
        self.month_weekday_hist = defaultdict(Counter)
        self.month_tool_counter = defaultdict(Counter)
        self.month_session_ts = defaultdict(lambda: defaultdict(list))
        self.month_skill_counter = defaultdict(Counter)
        self.month_subagent_counter = defaultdict(Counter)
        self.month_mcp_server_counter = defaultdict(Counter)
        self.month_cli_counter = defaultdict(Counter)
        self.month_compounding = Counter()
        self.month_shell_test_runs = Counter()
        self.month_plan_sessions = defaultdict(set)   # "YYYY-MM" -> {sessionId with planning}
        self.month_api_errors = Counter()

        self.model_tokens = defaultdict(_zero_tok)
        self.month_tokens = defaultdict(_zero_tok)
        self.month_model_tokens = defaultdict(lambda: defaultdict(_zero_tok))

        self.source_files = Counter()
        self.source_sessions = defaultdict(set)
        self.source_prompts = Counter()

        # per-file transient state (reset in begin_file, flushed in end_file)
        self._cur_src = None
        self._cur_fp = None
        self._pending_error = defaultdict(bool)
        self._file_edit_run = defaultdict(lambda: defaultdict(int))
        self._file_edit_month = defaultdict(dict)

        # set by to_corpus_stats to surface the raw git_churn dict in the narrative
        # payload main() consumes.
        self.gc = None

    # ---- file lifecycle ----------------------------------------------------
    def begin_file(self, cur_src, fp):
        self._cur_src = cur_src
        self._cur_fp = fp
        self.files_parsed += 1
        self.source_files[cur_src] += 1
        # per-session, per-file ordered state for error-recovery + iteration depth
        self._pending_error = defaultdict(bool)        # sessionId -> unrecovered error flag
        self._file_edit_run = defaultdict(lambda: defaultdict(int))  # session -> file -> edits since commit
        self._file_edit_month = defaultdict(dict)      # session -> file -> month key

    def skip_file(self):
        """Undo begin_file's bookkeeping for a file we end up not processing
        (codex empty-seed sessions)."""
        self.source_files[self._cur_src] -= 1
        self.files_parsed -= 1

    # ---- plan-ceremony (per-session) helpers -------------------------------
    @staticmethod
    def _is_plan_skill(name):
        sl = str(name).lower()
        return any(nd in sl for nd in PLAN_SKILL_NEEDLES)

    def _mark_plan_session(self, sid, mkey):
        """Record that session `sid` (in month `mkey`) contained a planning signal.
        Idempotent per session — repeated signals in one session count once."""
        if not sid:
            return
        self.plan_sessions.add(sid)
        if mkey:
            self.month_plan_sessions[mkey].add(sid)

    def _counted_plan_sessions(self):
        """Plan sessions restricted to the same universe as total_sessions, so the
        plan_sessions / total_sessions fraction can never exceed 1 (a session that
        never entered session_ts is not in the denominator either)."""
        if self.session_ts:
            return len(self.plan_sessions & set(self.session_ts))
        return min(len(self.plan_sessions), len(self.session_files))

    def end_file(self):
        # flush any remaining edit runs as iteration-depth samples
        for _s, sdict in self._file_edit_run.items():
            for _f, cnt in sdict.items():
                if cnt > 0:
                    self.edits_per_file_events.append(cnt)
                    _fm = self._file_edit_month.get(_s, {}).get(_f)
                    if _fm:
                        self.month_edits_per_file[_fm].append(cnt)

    # ---- per-event update --------------------------------------------------
    def observe(self, ev, since_dt, until_dt):
        """Fold one event into the accumulators.

        Returns `(cleaned, dt, sid, cwd)` for a genuine human prompt (so the
        caller can collect narrative quote candidates), else None."""
        prompt_info = None
        if ev.get("__bad__"):
            self.lines_bad += 1
            return None
        self.lines_total += 1

        etype = ev.get("type")
        sid = ev.get("sessionId")
        cwd = ev.get("cwd")
        dt = parse_ts(ev.get("timestamp"))
        if (since_dt is not None or until_dt is not None) and (
                dt is None                                   # undatable: can't
                or (since_dt is not None and dt < since_dt)  # honor "this period
                or (until_dt is not None and dt >= until_dt)):  # only" — drop
            return None
        mkey = dt.strftime("%Y-%m") if dt is not None else None

        if dt is not None:
            # Synthetic timestamps (Cursor JSONL events past the first, stamped with
            # the file mtime) must reach the date window / month bucket so windowed
            # runs count them, but must NOT distort the hour/weekday histograms or
            # session-duration math with a pile of identical fake instants.
            _synth_ts = ev.get("__synth_ts__")
            if self.all_min_dt is None or dt < self.all_min_dt:
                self.all_min_dt = dt
            if self.all_max_dt is None or dt > self.all_max_dt:
                self.all_max_dt = dt
            if not _synth_ts:
                self.hour_hist[dt.hour] += 1
                self.weekday_hist[dt.weekday()] += 1
                self.month_hour_hist[mkey][dt.hour] += 1
                self.month_weekday_hist[mkey][dt.weekday()] += 1
            self.date_set.add(dt.date().isoformat())
            self.month_dates[mkey].add(dt.date().isoformat())
            if sid:
                if not _synth_ts:
                    self.session_ts[sid].append(dt.timestamp())
                    self.month_session_ts[mkey][sid].append(dt.timestamp())
                self.month_sessions[mkey].add(sid)
        if sid:
            self.session_files[sid].add(self._cur_fp)
            self.source_sessions[self._cur_src].add(sid)
        if cwd:
            self.project_activity[cwd] += 1
            if sid:
                self.project_sessions[cwd].add(sid)

        msg = ev.get("message") if isinstance(ev.get("message"), dict) else None

        # ---- API error / retry events (system + assistant) ----------
        if ev.get("isApiErrorMessage") or ev.get("apiErrorStatus"):
            self.api_errors += 1
            if mkey:
                self.month_api_errors[mkey] += 1
        if etype == "system" and ev.get("retryAttempt"):
            self.api_errors += 1
            if mkey:
                self.month_api_errors[mkey] += 1

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
                        self.command_invocations += 1
                    elif cleaned:
                        self.prompts_count += 1
                        self.source_prompts[self._cur_src] += 1
                        if mkey:
                            self.month_prompts[mkey] += 1
                            self.month_prompt_lengths[mkey].append(len(cleaned))
                        self.prompt_lengths.append(len(cleaned))
                        if _POLITE_RE.search(cleaned):
                            self.polite_prompts += 1
                            if mkey:
                                self.month_polite[mkey] += 1
                        if is_command:
                            self.command_invocations += 1
                        # Narrative quote candidates (opening/longest/cryptic/crash-out)
                        # are corpus-only and never serialized; the caller collects
                        # them from this return value.
                        prompt_info = (cleaned, dt, sid, cwd)

            # ---- tool results inside user turns ---------------------
            content = msg.get("content")
            if isinstance(content, list):
                for b in content:
                    if isinstance(b, dict) and b.get("type") == "tool_result":
                        if b.get("is_error"):
                            self.tool_errors += 1
                            if mkey:
                                self.month_tool_errors[mkey] += 1
                            if sid:
                                self._pending_error[sid] = True

        # ---- assistant turns ---------------------------------------
        elif etype == "assistant" and msg is not None:
            # Codex emits synthetic token-usage events as type="assistant" purely
            # to carry per-(model,month) token totals. They are NOT real turns, so
            # they must not bump assistant-turn or model-mix counters — only feed
            # the token accumulators below.
            _is_codex_usage = bool(ev.get("__codex_usage__"))
            if not _is_codex_usage:
                self.assistant_turns += 1
                if mkey:
                    self.month_assistant_turns[mkey] += 1
            mdl = msg.get("model")
            if mdl:
                if not _is_codex_usage:
                    self.model_counter[mdl] += 1
                    if mkey:
                        self.month_models[mkey][mdl] += 1
                # ---- token usage extraction (fully defensive) -------
                _u = msg.get("usage") or {}
                _ti = _usage_int(_u, "input_tokens")
                _to = _usage_int(_u, "output_tokens")
                _tcr = _usage_int(_u, "cache_read_input_tokens")
                _tcc = _usage_int(_u, "cache_creation_input_tokens")
                self.model_tokens[mdl]["input"]          += _ti
                self.model_tokens[mdl]["output"]         += _to
                self.model_tokens[mdl]["cache_read"]     += _tcr
                self.model_tokens[mdl]["cache_creation"] += _tcc
                if mkey:
                    self.month_tokens[mkey]["input"]          += _ti
                    self.month_tokens[mkey]["output"]         += _to
                    self.month_tokens[mkey]["cache_read"]     += _tcr
                    self.month_tokens[mkey]["cache_creation"] += _tcc
                    self.month_model_tokens[mkey][mdl]["input"]          += _ti
                    self.month_model_tokens[mkey][mdl]["output"]         += _to
                    self.month_model_tokens[mkey][mdl]["cache_read"]     += _tcr
                    self.month_model_tokens[mkey][mdl]["cache_creation"] += _tcc
            if ev.get("attributionSkill"):
                self.skill_counter[ev["attributionSkill"]] += 1
                if mkey:
                    self.month_skill_counter[mkey][ev["attributionSkill"]] += 1
                if self._is_plan_skill(ev["attributionSkill"]):
                    self._mark_plan_session(sid, mkey)
            content = msg.get("content")
            if isinstance(content, list):
                for b in content:
                    if not isinstance(b, dict):
                        continue
                    bt = b.get("type")
                    if bt == "text":
                        self.text_blocks += 1
                    elif bt == "thinking":
                        self.thinking_blocks += 1
                        if mkey:
                            self.month_thinking_blocks[mkey] += 1
                        self.thinking_chars += len(b.get("thinking", "") or "")
                    elif bt == "tool_use":
                        name = b.get("name", "?")
                        inp = b.get("input", {}) if isinstance(b.get("input"), dict) else {}
                        self.tool_use_total += 1
                        self.tool_counter[name] += 1
                        _cat = classify_tool(name)
                        if mkey:
                            self.month_tools[mkey] += 1
                            self.month_tool_counter[mkey][name] += 1
                            if _cat == "delegate":
                                self.month_delegate[mkey] += 1
                        self.cat_counter[_cat] += 1
                        if name.startswith("mcp__"):
                            self.mcp_calls += 1
                            parts = name.split("__")
                            if len(parts) > 1 and parts[1]:
                                self.mcp_server_counter[parts[1]] += 1
                                if mkey:
                                    self.month_mcp_server_counter[mkey][parts[1]] += 1
                        else:
                            self.native_calls += 1

                        # a tool use after a pending error = recovery
                        if sid and self._pending_error.get(sid):
                            self.recovered_errors += 1
                            if mkey:
                                self.month_recovered_errors[mkey] += 1
                            self._pending_error[sid] = False

                        if name == "Skill":
                            s = inp.get("skill")
                            if s:
                                self.skill_counter[s] += 1
                                if mkey:
                                    self.month_skill_counter[mkey][s] += 1
                                # a planning Skill also marks this a planning session
                                if self._is_plan_skill(s):
                                    self._mark_plan_session(sid, mkey)
                        # Plan-ceremony signal: mark this SESSION as a planning session.
                        # PLAN_SIGNAL_TOOLS normalizes across sources (EnterPlanMode = Cursor
                        # create_plan; ExitPlanMode = Claude Code native plan mode, shift+tab ->
                        # present plan; TodoWrite = Codex update_plan / Antigravity manage_task /
                        # Cursor todos). We count DISTINCT SESSIONS, not tool calls, so TodoWrite
                        # firing many times per session (todo bookkeeping) can't inflate the metric.
                        # Subset of taxonomy.PLAN_TOOLS: TodoRead/TaskList/TaskGet are reads.
                        if name in PLAN_SIGNAL_TOOLS:
                            self._mark_plan_session(sid, mkey)
                        if name == "Agent":
                            st = inp.get("subagent_type", "general-purpose")
                            self.subagent_counter[st] += 1
                            if mkey:
                                self.month_subagent_counter[mkey][st] += 1
                            if sid:
                                self.agents_per_session[sid] += 1
                                if mkey:
                                    self.month_fanouts[mkey][sid] += 1
                        if name in ASK_TOOLS:
                            self.questions_asked += 1
                            if mkey:
                                self.month_questions[mkey] += 1
                        if inp.get("run_in_background"):
                            self.background_tasks += 1
                            if mkey:
                                self.month_background[mkey] += 1
                        if name in SCHEDULE_TOOLS:
                            self.scheduled_actions += 1
                            if mkey:
                                self.month_scheduled[mkey] += 1

                        # ---- code churn + iteration depth ----------
                        if name == "Edit":
                            a = line_count(inp.get("new_string", ""))
                            r = line_count(inp.get("old_string", ""))
                            self.lines_added += a
                            self.lines_removed += r
                            if mkey:
                                self.month_churn[mkey] += a + r
                            fpth = inp.get("file_path")
                            if sid and fpth:
                                self._file_edit_run[sid][fpth] += 1
                                if mkey:
                                    self._file_edit_month[sid][fpth] = mkey
                            if _is_compounding_path(fpth):
                                self.compounding_counter += 1
                                if mkey:
                                    self.month_compounding[mkey] += 1
                        elif name == "Write":
                            a = line_count(inp.get("content", ""))
                            self.lines_added += a
                            if mkey:
                                self.month_churn[mkey] += a
                            fpth = inp.get("file_path")
                            if sid and fpth:
                                self._file_edit_run[sid][fpth] += 1
                                if mkey:
                                    self._file_edit_month[sid][fpth] = mkey
                            if _is_compounding_path(fpth):
                                self.compounding_counter += 1
                                if mkey:
                                    self.month_compounding[mkey] += 1
                        elif name == "MultiEdit":
                            _me_added = 0
                            _me_removed = 0
                            for e in inp.get("edits", []) or []:
                                if isinstance(e, dict):
                                    _ea = line_count(e.get("new_string", ""))
                                    _er = line_count(e.get("old_string", ""))
                                    self.lines_added += _ea
                                    self.lines_removed += _er
                                    _me_added += _ea
                                    _me_removed += _er
                                    if mkey:
                                        self.month_churn[mkey] += _ea + _er
                            fpth = inp.get("file_path")
                            if sid and fpth:
                                self._file_edit_run[sid][fpth] += 1
                                if mkey:
                                    self._file_edit_month[sid][fpth] = mkey
                            if _is_compounding_path(fpth):
                                self.compounding_counter += 1
                                if mkey:
                                    self.month_compounding[mkey] += 1
                        elif name == "NotebookEdit":
                            _nb_a = line_count(inp.get("new_source", ""))
                            self.lines_added += _nb_a
                            fpth = inp.get("notebook_path")
                            if sid and fpth:
                                self._file_edit_run[sid][fpth] += 1
                                if mkey:
                                    self._file_edit_month[sid][fpth] = mkey
                            if _is_compounding_path(fpth):
                                self.compounding_counter += 1
                                if mkey:
                                    self.month_compounding[mkey] += 1
                        elif name == "Bash":
                            cmd = inp.get("command", "") or ""
                            if isinstance(cmd, list):
                                cmd = " && ".join(str(c) for c in cmd)
                            for _cli in _extract_clis(cmd):
                                self.cli_counter[_cli] += 1
                                if mkey:
                                    self.month_cli_counter[mkey][_cli] += 1
                            if self._cur_src != "claude":
                                # Claude invokes skills via the Skill tool (counted
                                # above); other CLIs read SKILL.md through the shell
                                for _sm in _SKILL_MD_RX.finditer(cmd):
                                    self.skill_counter[_sm.group(1)] += 1
                                    if mkey:
                                        self.month_skill_counter[mkey][_sm.group(1)] += 1
                                    if self._is_plan_skill(_sm.group(1)):
                                        self._mark_plan_session(sid, mkey)
                            if bash_writes_file(cmd):
                                self.bash_write_calls += 1
                                _bash_nl = cmd.count("\n")
                                self.bash_authored_lines += _bash_nl
                                if mkey:
                                    self.month_bash_write_calls[mkey] += 1
                                    self.month_bash_authored_lines[mkey] += _bash_nl
                            if bash_runs_tests(cmd):
                                self.shell_test_runs += 1
                                if mkey:
                                    self.month_shell_test_runs[mkey] += 1
                            if "git commit" in cmd:
                                self.git_commits += 1
                                # flush iteration-depth run for this session
                                if sid in self._file_edit_run:
                                    for _f, cnt in self._file_edit_run[sid].items():
                                        if cnt > 0:
                                            self.edits_per_file_events.append(cnt)
                                            _fm = self._file_edit_month.get(sid, {}).get(_f)
                                            if _fm:
                                                self.month_edits_per_file[_fm].append(cnt)
                                    self._file_edit_run[sid].clear()
                                    self._file_edit_month.get(sid, {}).clear()

        return prompt_info

    # ---- shaping: whole-corpus stats ---------------------------------------
    def to_corpus_stats(self, since_dt, until_dt, antigravity):
        """Build the full corpus stats dict. Also stashes self.gc (the raw git_churn
        dict) for the narrative payload main() consumes."""
        # ---- derive ----------------------------------------------------------
        total_sessions = len(self.session_ts) or len(self.session_files)
        # Active time = sum of consecutive inter-event gaps, each capped at GAP_CAP_S,
        # so resumed-session reuse and overnight idle don't inflate engaged time.
        durations_min = []
        for ts_list in self.session_ts.values():
            ts_list.sort()
            active_s = 0.0
            for a, bnext in zip(ts_list, ts_list[1:]):
                active_s += min(bnext - a, GAP_CAP_S)
            durations_min.append(active_s / 60.0)
        active_hours, longest_run_min = _active_hours_and_longest_run(
            self.session_ts, GAP_CAP_S, BURST_GAP_S)
        avg_session_min = statistics.mean(durations_min) if durations_min else 0
        median_session_min = statistics.median(durations_min) if durations_min else 0

        avg_prompt_len = statistics.mean(self.prompt_lengths) if self.prompt_lengths else 0
        median_prompt_len = statistics.median(self.prompt_lengths) if self.prompt_lengths else 0

        total_churn = self.lines_added + self.lines_removed   # tool-authored only (Edit/Write)
        code_velocity = (total_churn / active_hours) if active_hours > 0 else 0

        # Gold-standard churn: real git insertions/deletions over the REQUESTED window.
        if since_dt is not None or until_dt is not None:
            gc_since = since_dt.strftime("%Y-%m-%d") if since_dt is not None else (self.all_min_dt.isoformat() if self.all_min_dt else "1970-01-01")
            gc_until = (until_dt.strftime("%Y-%m-%d")
                        if until_dt is not None else (self.all_max_dt.isoformat() if self.all_max_dt else "2100-01-01"))
        else:
            gc_since = self.all_min_dt.isoformat() if self.all_min_dt else "1970-01-01"
            gc_until = self.all_max_dt.isoformat() if self.all_max_dt else "2100-01-01"
        gc = git_churn(list(self.project_activity.keys()), gc_since, gc_until)
        self.gc = gc
        git_velocity = (gc["churn"] / active_hours) if active_hours > 0 else 0

        explore = self.cat_counter.get("explore", 0) + self.thinking_blocks
        produce = self.cat_counter.get("produce", 0)
        execute = self.cat_counter.get("execute", 0)
        delegate = self.cat_counter.get("delegate", 0)
        doing = produce + execute + delegate
        planning_ratio = (explore / doing) if doing else 0

        tool_diversity = len(self.tool_counter)
        tot = sum(self.tool_counter.values()) or 1
        entropy = -sum((c / tot) * math.log2(c / tot) for c in self.tool_counter.values())
        norm_entropy = entropy / math.log2(tool_diversity) if tool_diversity > 1 else 0

        # Null-honesty: tool-level metrics are unmeasurable when the only active
        # sources never produced any tool calls. Real 0 stays 0; "never saw a tool"
        # becomes None.
        no_tool_activity = (self.tool_use_total == 0 and bool(self.source_sessions))

        error_recovery_ratio = _error_recovery_ratio(self.recovered_errors, self.tool_errors, no_tool_activity)
        error_rate_per_100_tools = _error_rate_per_100(self.tool_errors, self.tool_use_total, no_tool_activity)
        _fanouts = [n for n in self.agents_per_session.values() if n > 0]
        all_sources_no_agent = bool(self.source_sessions) and (
            set(self.source_sessions.keys()) <= _AGENT_UNSUPPORTED_SOURCES
        )
        fanout_median = _fanout_median(_fanouts, no_tool_activity, all_sources_no_agent)
        _ids = _iteration_depth_stats(self.edits_per_file_events, no_tool_activity)
        iteration_mean = _ids["mean"]
        iteration_median = _ids["median"]
        iteration_p90 = _ids["p90"]
        iteration_max = _ids["max"]
        heavy_files = _ids["heavy_files"]

        actions_per_prompt = (self.tool_use_total / self.prompts_count) if self.prompts_count else 0
        # autonomy proxy 0-100: weighted blend, transparent + bounded
        auto_actions = min(actions_per_prompt / 25.0, 1.0) * 45
        auto_deleg = min(delegate / max(total_sessions, 1) / 1.5, 1.0) * 20
        auto_sched = min((self.scheduled_actions + self.background_tasks) / max(total_sessions, 1), 1.0) * 15
        auto_lowq = (1 - min(self.questions_asked / max(self.prompts_count, 1) * 6, 1.0)) * 20
        autonomy_score = round(auto_actions + auto_deleg + auto_sched + auto_lowq, 1)

        span_days = (self.all_max_dt - self.all_min_dt).days + 1 if (self.all_min_dt and self.all_max_dt) else 0
        active_days = len(self.date_set)

        tzname = datetime.now().astimezone().tzname()
        tzoffset = datetime.now().astimezone().strftime("%z")

        peak_hours = _peak_hours(self.hour_hist)
        preferred_days = _preferred_days(self.weekday_hist, DOW)

        progression = []
        for mk in sorted(set(self.month_dates) | set(self.month_prompts) | set(self.month_tools) | set(self.month_tokens)):
            mm = self.month_models.get(mk, Counter())
            _mt = self.month_tokens.get(mk) or {}
            _ti = _mt.get("input", 0)
            _to = _mt.get("output", 0)
            _tcr = _mt.get("cache_read", 0)
            _tcc = _mt.get("cache_creation", 0)
            progression.append({
                "month": mk,
                "prompts": self.month_prompts.get(mk, 0),
                "tool_calls": self.month_tools.get(mk, 0),
                "sessions": len(self.month_sessions.get(mk, ())),
                "active_days": len(self.month_dates.get(mk, ())),
                "tool_churn_lines": self.month_churn.get(mk, 0),
                "models": mm.most_common(3),
                "top_model": mm.most_common(1)[0][0] if mm else None,
                "tokens_input": _ti,
                "tokens_output": _to,
                "tokens_cache_read": _tcr,
                "tokens_cache_creation": _tcc,
                "tokens_total": _ti + _to + _tcr + _tcc,
            })

        stats = {
            "scope": "Sources: " + (", ".join(sorted(self.source_files)) or "none"),
            "generated_local_only": True,
            "corpus": {
                "sources": {s: {"files": self.source_files[s], "sessions": len(self.source_sessions[s]),
                                "prompts": self.source_prompts[s]} for s in sorted(self.source_files)},
                "files_parsed": self.files_parsed,
                "lines_total": self.lines_total,
                "lines_unparseable": self.lines_bad,
                "date_range": (
                    [since_dt.isoformat() if since_dt is not None else (self.all_min_dt.isoformat() if self.all_min_dt else None),
                     (until_dt - timedelta(days=1)).isoformat() if until_dt is not None else (self.all_max_dt.isoformat() if self.all_max_dt else None)]
                    if (since_dt is not None or until_dt is not None) else
                    [self.all_min_dt.isoformat() if self.all_min_dt else None,
                     self.all_max_dt.isoformat() if self.all_max_dt else None]
                ),
                "window": ({"since": since_dt.isoformat() if since_dt else None,
                            "until": until_dt.isoformat() if until_dt else None}
                           if (since_dt or until_dt) else None),
                "span_days": span_days,
                "active_days": active_days,
                "timezone": f"{tzname} (UTC{tzoffset[:3]}:{tzoffset[3:]})",
                "antigravity_experimental": antigravity,
            },
            "volume": {
                "total_sessions": total_sessions,
                "total_prompts": self.prompts_count,
                "command_invocations": self.command_invocations,
                "avg_prompt_length_chars": round(avg_prompt_len, 1),
                "median_prompt_length_chars": round(median_prompt_len, 1),
                "assistant_turns": self.assistant_turns,
                "tool_calls_total": self.tool_use_total,
                "thinking_blocks": self.thinking_blocks,
            },
            "tools": {
                "tool_diversity": tool_diversity,
                "tool_entropy_normalized": round(norm_entropy, 3),
                "mcp_calls": self.mcp_calls,
                "native_calls": self.native_calls,
                "mcp_share": round(self.mcp_calls / (self.mcp_calls + self.native_calls), 3) if (self.mcp_calls + self.native_calls) else 0,
                "top_tools": self.tool_counter.most_common(20),
                "category_breakdown": dict(self.cat_counter),
                "mcp_servers": self.mcp_server_counter.most_common(),
                "mcp_servers_distinct": len(self.mcp_server_counter),
                "clis": self.cli_counter.most_common(),
                "clis_distinct": len(self.cli_counter),
                "cli_calls": sum(self.cli_counter.values()),
                "toolsearch_calls": self.tool_counter.get("ToolSearch", 0),
                "task_tool_calls": self.tool_counter.get("TaskCreate", 0) + self.tool_counter.get("TaskUpdate", 0),
                "agent_calls": self.tool_counter.get("Agent", 0),
            },
            "velocity": {
                "git_churn_total": gc["churn"],
                "git_insertions": gc["insertions"],
                "git_deletions": gc["deletions"],
                "git_commits_real": gc["commits"],
                "git_velocity_lines_per_hour": round(git_velocity, 1),
                "git_repos_with_commits": gc["repos_with_commits"],
                "git_repos_seen": gc["repos_seen"],
                "git_per_repo": gc["per_repo"],
                "tool_churn_edit_write": total_churn,
                "tool_lines_added": self.lines_added,
                "tool_lines_removed": self.lines_removed,
                "tool_velocity_lines_per_hour": round(code_velocity, 1),
                "shell_write_calls": self.bash_write_calls,
                "shell_authored_lines_est": self.bash_authored_lines,
                "active_hours": round(active_hours, 1),
                "git_commits_grep": self.git_commits,
            },
            "behavior": {
                "planning_ratio_explore_to_doing": round(planning_ratio, 2),
                "explore_actions": explore,
                "produce_actions": produce,
                "execute_actions": execute,
                "delegate_actions": delegate,
                "avg_session_minutes": round(avg_session_min, 1),
                "median_session_minutes": round(median_session_min, 1),
                "longest_run_minutes": round(longest_run_min, 1),
                "polite_prompts": self.polite_prompts,
                "error_recovery_ratio": round(error_recovery_ratio, 3) if error_recovery_ratio is not None else None,
                "error_rate_per_100_tools": round(error_rate_per_100_tools, 1) if error_rate_per_100_tools is not None else None,
                "tool_errors": self.tool_errors,
                "recovered_errors": self.recovered_errors,
                "api_errors_retries": self.api_errors,
                "fanout_median": fanout_median,
                "iteration_depth_mean": round(iteration_mean, 2) if iteration_mean is not None else None,
                "iteration_depth_median": round(iteration_median, 2) if iteration_median is not None else None,
                "iteration_depth_p90": iteration_p90,
                "iteration_depth_max": iteration_max,
                "files_hammered_over_15x": heavy_files,
                "actions_per_prompt": round(actions_per_prompt, 1),
                "questions_asked": self.questions_asked,
                "background_tasks": self.background_tasks,
                "scheduled_actions": self.scheduled_actions,
                "shell_test_runs": self.shell_test_runs,
                "plan_sessions": self._counted_plan_sessions(),
            },
            "rhythm": {
                "hour_histogram_local": {str(h): self.hour_hist.get(h, 0) for h in range(24)},
                "weekday_histogram": {DOW[d]: self.weekday_hist.get(d, 0) for d in range(7)},
                "peak_hours_local": peak_hours,
                "preferred_days": preferred_days,
            },
            "progression": {"monthly": progression},
            "stack": {
                "models": self.model_counter.most_common(),
                "top_skills": self.skill_counter.most_common(15),
                "skills_distinct": len(self.skill_counter),
                "skills_total": sum(self.skill_counter.values()),
                "subagent_types_distinct": len(self.subagent_counter),
                "skills_all": self.skill_counter.most_common(200),
                "compounding_writes": self.compounding_counter,
                "subagent_types": self.subagent_counter.most_common(10),
                "top_projects": [(os.path.basename(p), c, len(self.project_sessions[p]))
                                 for p, c in self.project_activity.most_common(12)],
            },
            "autonomy": {
                "autonomy_score_0_100": autonomy_score,
                "components": {
                    "actions_per_prompt": round(auto_actions, 1),
                    "delegation": round(auto_deleg, 1),
                    "scheduling_background": round(auto_sched, 1),
                    "low_question_rate": round(auto_lowq, 1),
                },
            },
        }
        # ---- aggregate token_usage block ----------------------------------------
        stats["token_usage"] = _token_usage_block(self.model_tokens)
        _t0_aq = time.monotonic()
        stats["agentic"] = compute_aq(stats)
        stats["_timing_compute_aq_s"] = time.monotonic() - _t0_aq

        # ---- per-calendar-month noticed_stats (GA1) -----------------------------
        stats["monthly_noticed_stats"] = _build_monthly_noticed_stats(
            months=sorted(set(self.month_dates) | set(self.month_prompts) | set(self.month_tools)
                          | set(self.month_tokens) | set(self.month_sessions)),
            month_prompts=self.month_prompts,
            month_tools_count=self.month_tools,
            month_churn=self.month_churn,
            month_models=self.month_models,
            month_model_tokens=self.month_model_tokens,
            month_sessions=self.month_sessions,
            month_dates=self.month_dates,
            month_assistant_turns=self.month_assistant_turns,
            month_thinking_blocks=self.month_thinking_blocks,
            month_prompt_lengths=self.month_prompt_lengths,
            month_bash_write_calls=self.month_bash_write_calls,
            month_bash_authored_lines=self.month_bash_authored_lines,
            month_tool_errors=self.month_tool_errors,
            month_recovered_errors=self.month_recovered_errors,
            month_edits_per_file=self.month_edits_per_file,
            month_polite=self.month_polite,
            month_questions=self.month_questions,
            month_delegate=self.month_delegate,
            month_background=self.month_background,
            month_scheduled=self.month_scheduled,
            month_fanouts=self.month_fanouts,
            month_hour_hist=self.month_hour_hist,
            month_weekday_hist=self.month_weekday_hist,
            month_tool_counter=self.month_tool_counter,
            month_session_ts=self.month_session_ts,
            no_tool_activity=no_tool_activity,
            all_sources_no_agent=all_sources_no_agent,
            cwds=list(self.project_activity.keys()),
            gap_cap_s=GAP_CAP_S,
            burst_gap_s=BURST_GAP_S,
            dow=DOW,
        )

        # ---- per-month FULL stats slices (for scoring_inputs_by_source monthly) --
        stats["_scoring_monthly_full"] = self.to_monthly(planning_ratio, no_tool_activity, all_sources_no_agent)
        return stats

    def to_monthly(self, planning_ratio, no_tool_activity, all_sources_no_agent):
        """Per-month full stats slices, shaped by the same builder for corpus and
        per-source so window AND month share one code path."""
        return build_monthly_scoring_stats(
            months=sorted(set(self.month_dates) | set(self.month_prompts) | set(self.month_tools)
                          | set(self.month_tokens) | set(self.month_sessions)),
            sources_present=sorted(self.source_files),
            month_prompts=self.month_prompts, month_tools_count=self.month_tools,
            month_churn=self.month_churn, month_models=self.month_models,
            month_sessions=self.month_sessions, month_assistant_turns=self.month_assistant_turns,
            month_thinking_blocks=self.month_thinking_blocks,
            month_bash_authored_lines=self.month_bash_authored_lines,
            month_tool_errors=self.month_tool_errors, month_recovered_errors=self.month_recovered_errors,
            month_edits_per_file=self.month_edits_per_file, month_questions=self.month_questions,
            month_delegate=self.month_delegate, month_background=self.month_background,
            month_scheduled=self.month_scheduled, month_fanouts=self.month_fanouts,
            month_tool_counter=self.month_tool_counter, month_session_ts=self.month_session_ts,
            month_skill_counter=self.month_skill_counter, month_subagent_counter=self.month_subagent_counter,
            month_mcp_server_counter=self.month_mcp_server_counter, month_cli_counter=self.month_cli_counter,
            month_compounding=self.month_compounding, month_shell_test_runs=self.month_shell_test_runs,
            month_plan_sessions=self.month_plan_sessions,
            month_api_errors=self.month_api_errors,
            planning_ratio_window=planning_ratio,
            cwds=list(self.project_activity.keys()),
            gap_cap_s=GAP_CAP_S, burst_gap_s=BURST_GAP_S,
            no_tool_activity=no_tool_activity, all_sources_no_agent=all_sources_no_agent,
        )

    # ---- shaping: per-source stats (reduced shape for build_scoring_inputs) -----
    def to_source_stats(self, src_name, since_dt, until_dt):
        """Build the reduced per-source stats dict consumed by build_scoring_inputs.

        Everything is derived from THIS source's accumulator — null-honesty, the git
        window, and the session-count fallback are all computed source-locally, so the
        result matches what running _accumulate over this source's file slice produces
        (the pre-single-pass per-source path). Inheriting corpus-level flags here would
        flip a prompt-only source's null metrics from None to 0 and mis-bound its churn."""
        _s_tool_total = self.tool_use_total
        _s_all_no_agent = src_name in _AGENT_UNSUPPORTED_SOURCES
        # Null-honesty per source: a source slice with sessions but zero tool calls
        # cannot measure tool-level metrics → None (not a real 0).
        _s_no_tool = (_s_tool_total == 0 and bool(self.source_sessions))

        _s_ids = _iteration_depth_stats(self.edits_per_file_events, _s_no_tool)
        _s_err_rate = _error_rate_per_100(self.tool_errors, _s_tool_total, _s_no_tool)
        _s_recov = _error_recovery_ratio(self.recovered_errors, self.tool_errors, _s_no_tool)
        _s_fanouts_list = [n for n in self.agents_per_session.values() if n > 0]
        _s_fan_med = _fanout_median(_s_fanouts_list, _s_no_tool, _s_all_no_agent)
        _s_active_hours, _ = _active_hours_and_longest_run(
            self.session_ts, GAP_CAP_S, BURST_GAP_S)

        _s_total_churn = self.lines_added + self.lines_removed
        _s_prompts = self.prompts_count
        _s_actions_per_prompt = round(_s_tool_total / _s_prompts, 1) if _s_prompts else 0

        _s_tc = self.tool_counter
        _s_diversity = len(_s_tc)
        _s_tot = sum(_s_tc.values()) or 1
        _s_entropy = -sum((c / _s_tot) * math.log2(c / _s_tot)
                          for c in _s_tc.values()) if _s_diversity > 1 else 0
        _s_norm_entropy = _s_entropy / math.log2(_s_diversity) if _s_diversity > 1 else 0

        _s_cats = self.cat_counter
        _s_explore = _s_cats.get("explore", 0) + self.thinking_blocks
        _s_produce = _s_cats.get("produce", 0)
        _s_execute = _s_cats.get("execute", 0)
        _s_doing = _s_produce + _s_execute + _s_cats.get("delegate", 0)
        _s_planning_ratio = round((_s_explore / _s_doing) if _s_doing else 0, 2)

        # Source-local git window: requested --since/--until, else this source's own
        # event span (same formula to_corpus_stats uses for the corpus span).
        if since_dt is not None or until_dt is not None:
            _s_gc_since = since_dt.strftime("%Y-%m-%d") if since_dt is not None else (self.all_min_dt.isoformat() if self.all_min_dt else "1970-01-01")
            _s_gc_until = (until_dt.strftime("%Y-%m-%d")
                           if until_dt is not None else (self.all_max_dt.isoformat() if self.all_max_dt else "2100-01-01"))
        else:
            _s_gc_since = self.all_min_dt.isoformat() if self.all_min_dt else "1970-01-01"
            _s_gc_until = self.all_max_dt.isoformat() if self.all_max_dt else "2100-01-01"
        _s_gc = git_churn(list(self.project_activity.keys()), _s_gc_since, _s_gc_until)
        _s_sessions = len(self.session_ts) or len(self.session_files)

        s_stats = {
            "corpus": {"sources": {src_name: {
                "files": self.source_files[src_name],
                "sessions": _s_sessions,
                "prompts": self.prompts_count,
            }}},
            "volume": {
                "total_sessions": _s_sessions,
                "total_prompts": self.prompts_count,
                "tool_calls_total": _s_tool_total,
                "assistant_turns": self.assistant_turns,
                "thinking_blocks": self.thinking_blocks,
            },
            "velocity": {
                "git_churn_total": _s_gc["churn"],
                "tool_churn_edit_write": _s_total_churn,
                "shell_authored_lines_est": self.bash_authored_lines,
                "active_hours": round(_s_active_hours, 1),
                "git_repos_seen": _s_gc["repos_seen"],
                "git_repos_with_commits": _s_gc["repos_with_commits"],
            },
            "behavior": {
                "planning_ratio_explore_to_doing": _s_planning_ratio,
                "actions_per_prompt": _s_actions_per_prompt,
                "questions_asked": self.questions_asked,
                "error_recovery_ratio": (round(_s_recov, 3)
                                         if _s_recov is not None else None),
                "error_rate_per_100_tools": (round(_s_err_rate, 1)
                                             if _s_err_rate is not None else None),
                "tool_errors": self.tool_errors,
                "recovered_errors": self.recovered_errors,
                "api_errors_retries": self.api_errors,
                "fanout_median": _s_fan_med,
                "shell_test_runs": self.shell_test_runs,
                "plan_sessions": self._counted_plan_sessions(),
                "delegate_actions": _s_cats.get("delegate", 0),
                "background_tasks": self.background_tasks,
                "scheduled_actions": self.scheduled_actions,
                "iteration_depth_mean": (round(_s_ids["mean"], 2)
                                         if _s_ids["mean"] is not None else None),
                "iteration_depth_median": (round(_s_ids["median"], 2)
                                           if _s_ids["median"] is not None else None),
                "iteration_depth_p90": _s_ids["p90"],
                "iteration_depth_max": _s_ids["max"],
                "files_hammered_over_15x": _s_ids["heavy_files"],
            },
            "tools": {
                "tool_diversity": _s_diversity,
                "tool_entropy_normalized": round(_s_norm_entropy, 3),
                "mcp_calls": self.mcp_calls,
                "native_calls": self.native_calls,
                "top_tools": _s_tc.most_common(20),
                "mcp_servers_distinct": len(self.mcp_server_counter),
                "clis_distinct": len(self.cli_counter),
                "cli_calls": sum(self.cli_counter.values()),
                "toolsearch_calls": _s_tc.get("ToolSearch", 0),
                "task_tool_calls": (_s_tc.get("TaskCreate", 0)
                                    + _s_tc.get("TaskUpdate", 0)),
                "agent_calls": _s_tc.get("Agent", 0),
            },
            "stack": {
                "models": self.model_counter.most_common(),
                "top_skills": self.skill_counter.most_common(15),
                "skills_all": self.skill_counter.most_common(200),
                "skills_distinct": len(self.skill_counter),
                "skills_total": sum(self.skill_counter.values()),
                "subagent_types_distinct": len(self.subagent_counter),
                "subagent_types": self.subagent_counter.most_common(10),
                "compounding_writes": self.compounding_counter,
            },
            "token_usage": _token_usage_block(dict(self.model_tokens)),
            "agentic": {},
        }
        s_stats["_scoring_monthly_full"] = self.to_monthly(
            _s_planning_ratio, _s_no_tool, _s_all_no_agent)
        return s_stats
