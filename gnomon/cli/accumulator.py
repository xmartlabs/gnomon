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
import re
import statistics
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from gnomon.config import (
    parse_ts, line_count, strip_injections, planning_session_scope, sidechain_label_scope,
)
from gnomon.scoring.inputs import _adjusted_doing
from gnomon.taxonomy import (
    SCHEDULE_TOOLS, ASK_TOOLS, PLAN_MODE_TOOLS, PLAN_SIGNAL_TOOLS,
    PLAN_SKILL_NEEDLES, KNOWLEDGE_SKILL_NEEDLES, ORCHESTRATION_TOOLS,
    FANOUT_BY_TRANSCRIPT_TOOLS, parse_workflow_agent_dispatch,
    classify_tool, classify_mcp_subcategory, CI_CONTEXT_SUBCATS,
    is_substantive_tool, classify_change_target, is_plan_file_target,
    bash_writes_file, bash_runs_tests, bash_runs_knowledge, _extract_clis,
    _is_compounding_path, _norm_path_seps, _SKILL_MD_RX,
    extract_skill_name_from_path, _canon_mcp_server, is_mcp_knowledge_write,
)
from gnomon.sources.discovery import _AGENT_UNSUPPORTED_SOURCES
from gnomon.analysis.churn import git_churn
from gnomon.analysis.metrics import (
    _error_rate_per_100, _error_recovery_ratio, _iteration_depth_stats,
    _fanout_median, _peak_hours, _preferred_days, _active_hours_and_longest_run,
    _token_usage_block, _usage_int,
)
from gnomon.scoring.aq import (
    compute_aq, CHURN_MIN, WINDOW, PLAN_MIN_LINES, PLAN_MIN_STEPS,
    MIN_ELIGIBLE_SESSIONS, ORCHESTRATABLE_CODE_FILES, ORCHESTRATABLE_SUBSTANTIVE,
)
from gnomon.scoring.inputs import build_monthly_scoring_stats
from gnomon.output.summary import _build_monthly_noticed_stats
from gnomon.analysis.quotes import _POLITE_RE

GAP_CAP_S = 600                   # cap idle gaps at 10 min when summing active time
BURST_GAP_S = 1800                # a gap > 30 min ends a contiguous work "run"
DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

_KNOWLEDGE_NATIVE_TOOLS = frozenset({"WebFetch", "WebSearch"})
# Keep native web tools out of Context Intelligence while recalibrating the metric.
# They remain counted as explore/native tool activity; this only controls whether
# they can arm a later write session as context-grounded.
ENABLE_WEB_CONTEXT_GROUNDING = False


def _is_local_url(url):
    if not url:
        return False
    low = url.lower()
    return any(h in low for h in ("localhost", "127.0.0.1", "0.0.0.0", "[::1]"))


def _zero_tok():
    return {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0}


def _notification_tag(text, tag):
    match = re.search(rf"<{re.escape(tag)}>(.*?)</{re.escape(tag)}>", text or "", re.DOTALL)
    return match.group(1).strip() if match else None


def _normalize_bash_command(raw):
    """Coerce a Bash tool's `command` input to the shell-string shape every regex-based
    classifier here (`bash_runs_tests`, `bash_runs_knowledge`, `bash_writes_file`,
    `_extract_clis`, `_SKILL_MD_RX`) expects. Some non-Claude adapters emit `command` as
    an argv LIST rather than a joined string; searching a list with a compiled regex
    raises `TypeError` and aborts the whole `observe()` call. Joining with ' && ' mirrors
    the join this module already applied ad hoc in three separate places (the per-event
    ordered-fact enrichment, `_fact_plan_skill`, and the Bash tool-name accounting
    branch) -- centralized here so a list-valued command is normalized ONCE and scores
    identically everywhere, instead of crashing wherever the join was missing."""
    if isinstance(raw, list):
        return " && ".join(str(c) for c in raw)
    return raw or ""


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

        # Typed user text only; bare slash commands stay out so prompt-length and
        # politeness statistics do not include zero-length instructions.
        self.prompts_count = 0
        self.polite_prompts = 0
        self.prompt_lengths = []
        self.command_invocations = 0
        # Bare slash commands complete the human-instruction denominator for
        # `actions_per_prompt` without changing the typed-prompt metrics above.
        self.command_only_prompts = 0

        self.assistant_turns = 0
        self.text_blocks = 0
        self.thinking_blocks = 0
        self.thinking_chars = 0
        self.tool_use_total = 0
        # Sidechain calls remain in the total and are separately published so the
        # top-level actions-per-instruction ratio can be reconstructed.
        self.sidechain_tool_use_total = 0
        # Count observed delegation from a source without sidechain labels. The
        # scoring layer drops Steering for this case rather than guessing.
        self.unlabelled_delegate_dispatches = 0
        self.tool_counter = Counter()
        self.cat_counter = Counter()
        # Planning DISPATCHES — the Skill call or Agent dispatch itself. Named 'dispatch',
        # not 'ceremony', because gstack already uses plan_ceremony for the CREDITED
        # Planning-practice score; this counter is the opposite, a count to EXCLUDE.
        # Tracked separately rather than re-routed through
        # cat_counter: delegate_actions is derived from cat_counter["delegate"], so moving
        # a planning Agent into another category would silently cut Execution-axis
        # delegation credit and desync the corpus from the independent month_delegate
        # counter. Subtracted from `doing` at the ratio sites only.
        self.planning_dispatch_calls = 0
        self.mcp_calls = 0
        self.native_calls = 0

        self.model_counter = Counter()
        self.session_models = {}
        self.codex_spawn_events = defaultdict(list)
        self.routing_links = []
        # Claude parent/child linkage is split across the parent transcript and
        # subagent files. Keep raw join facts until shaping so file order is irrelevant.
        self.claude_agent_attempts = {}
        self.claude_child_facts = defaultdict(
            lambda: {"models": set(), "substantive_calls": 0, "writes": 0})
        self.skill_counter = Counter()
        # Skill-counting dedup is corpus-lifetime and session-keyed; do not reset it per file.
        # _skill_span_claimed: {(sid_or_fp, name)} claimed by a DISCRETE site
        #   (injectedSkills, the Skill tool, a Read/Bash SKILL.md hit).
        # _skill_span_pending: {(sid_or_fp, name): first_seen_mkey} recorded by the
        #   per-turn `attributionSkill` site ONLY -- never incremented at record
        #   time; resolved once by _flush_pending_skills().
        self._skill_span_claimed = set()
        self._skill_span_pending = {}
        self._skill_flush_done = False
        self.subagent_counter = Counter()
        self.agents_per_session = defaultdict(int)
        self.session_subagent_types = defaultdict(set)  # sessionId -> distinct subagent roles
        self.parallel_dispatch_turns = 0
        self.mcp_server_counter = Counter()
        self.mcp_subcategory_counter = Counter()
        self.mcp_subcategory_servers = defaultdict(set)
        # Context Intelligence (behavioral): sessions where a knowledge-MCP call
        # OR an explore-class project/data/design MCP call preceded a later
        # Edit/Write/MultiEdit/NotebookEdit in the SAME session.
        self.grounded_sessions = set()
        self.write_sessions = set()
        self.month_grounded_sessions = defaultdict(set)
        self.month_write_sessions = defaultdict(set)
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
        # The qualified Planning practice numerator uses source-qualified session IDs so
        # pooled sources cannot collide. Numerator and denominator are admitted
        # by the same event-level predicate.
        self.planning_skill_sessions = set()
        self.planning_skill_eligible_sessions = set()
        self.planning_skill_unmeasured_sessions = set()
        self.session_ordered_tools = defaultdict(list)
        self.month_session_ordered_tools = defaultdict(lambda: defaultdict(list))
        self.ordered_facts_complete = True

        self.hour_hist = Counter()
        self.weekday_hist = Counter()
        self.date_set = set()
        self.all_min_dt = None
        self.all_max_dt = None

        # monthly progression ("YYYY-MM" buckets)
        self.month_prompts = Counter()
        self.month_tools = Counter()
        # Month-scoped sibling of sidechain_tool_use_total. Threaded into
        # build_monthly_scoring_stats so the monthly slice publishes the same
        # `actions_per_prompt` DEFINITION the corpus and per-source slices do — otherwise the
        # rolling series would mix two populations across months.
        self.month_sidechain_tools = Counter()
        # Month-scoped sibling of command_only_prompts, threaded into
        # build_monthly_scoring_stats for the same reason: the monthly slice has to divide by
        # the same population the corpus and per-source slices do.
        self.month_command_only = Counter()
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
        self.month_planning_dispatch_calls = Counter()
        self.month_background = Counter()
        self.month_scheduled = Counter()
        self.month_fanouts = defaultdict(lambda: defaultdict(int))
        self.month_session_subagent_types = defaultdict(lambda: defaultdict(set))  # month -> sid -> roles
        self.month_hour_hist = defaultdict(Counter)
        self.month_weekday_hist = defaultdict(Counter)
        self.month_tool_counter = defaultdict(Counter)
        self.month_session_ts = defaultdict(lambda: defaultdict(list))
        self.month_skill_counter = defaultdict(Counter)
        self.month_subagent_counter = defaultdict(Counter)
        self.month_mcp_server_counter = defaultdict(Counter)
        self.month_mcp_subcategory_counter = defaultdict(Counter)
        self.month_mcp_subcategory_servers = defaultdict(lambda: defaultdict(set))
        self.month_cli_counter = defaultdict(Counter)
        self.month_compounding = Counter()
        self.month_shell_test_runs = Counter()
        self.month_plan_sessions = defaultdict(set)   # "YYYY-MM" -> {sessionId with planning}
        self.month_planning_skill_sessions = defaultdict(set)
        self.month_planning_skill_eligible_sessions = defaultdict(set)
        self.month_planning_skill_unmeasured_sessions = defaultdict(set)
        self.month_api_errors = Counter()

        self.model_tokens = defaultdict(_zero_tok)
        self.month_tokens = defaultdict(_zero_tok)
        self.month_model_tokens = defaultdict(lambda: defaultdict(_zero_tok))

        self.source_files = Counter()
        self.source_sessions = defaultdict(set)
        self.source_prompts = Counter()
        # NOTE: there is deliberately no per-source `command_only` Counter beside
        # source_prompts. The per-source SCORING slice comes from a dedicated single-source
        # Accumulator (gnomon/cli/local.py builds one per source and calls to_source_stats on
        # it), so `command_only_prompts` is already source-scoped there; and the corpus-level
        # `sources` rollup publishes prompts only. A second counter would be written and never
        # read.
        self._plan_sessions_degraded = False

        # per-file transient state (reset in begin_file, flushed in end_file)
        self._cur_src = None
        self._cur_fp = None
        self._pending_error = defaultdict(bool)
        self._pending_knowledge_grounding = defaultdict(bool)
        self._file_edit_run = defaultdict(lambda: defaultdict(int))
        self._file_edit_month = defaultdict(dict)
        # Workflow fan-out fix (contract 15:15:15): (parent_sid, dispatch_id) pairs
        # already credited to agents_per_session/month_fanouts, so a resumed run
        # that re-references the same dispatched-agent transcript credits once.
        # Corpus-lifetime, NOT reset per-file (dedup must survive across files).
        self._fanout_credited_agents = set()
        # MCP knowledge-write compounding credit (contract 16:16:16): (sid,
        # persist_id_or_tool_bucket) pairs already credited to compounding_counter/
        # month_compounding, so target-less or same-target repeat calls within a
        # session cannot linearly inflate the axis while genuinely DISTINCT
        # persisted targets each still earn their own credit. Corpus-lifetime,
        # NOT reset per-file -- mirrors _fanout_credited_agents above.
        self._mcp_compounding_credited = set()
        # Set in begin_file when `_cur_fp` is a dispatched Workflow agent transcript
        # (`.../subagents/workflows/wf_*/agent-*.jsonl`): (parent_sid,
        # filename_agent_id), or None for every other file. Consumed in observe()
        # AFTER the window early-return so an out-of-window run credits nothing.
        self._pending_fanout_credit = None

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
        # sessionId -> an external-context MCP call (knowledge, or explore-class
        # project/data/design) occurred earlier in this session, not yet consumed
        # by a later write (Edit/Write/MultiEdit/NotebookEdit)
        self._pending_knowledge_grounding = defaultdict(bool)
        self._file_edit_run = defaultdict(lambda: defaultdict(int))  # session -> file -> edits since commit
        self._file_edit_month = defaultdict(dict)      # session -> file -> month key
        # Workflow fan-out fix: (parent_sid, filename_agent_id) when `fp` is a
        # dispatched Workflow agent transcript, else None. Read by observe() after
        # its window early-return so an out-of-window run credits nothing.
        parent_sid, filename_agent_id = parse_workflow_agent_dispatch(fp)
        self._pending_fanout_credit = (
            (parent_sid, filename_agent_id) if parent_sid else None)

    def skip_file(self):
        """Undo begin_file's bookkeeping for a file we end up not processing
        (codex empty-seed sessions)."""
        self.source_files[self._cur_src] -= 1
        self.files_parsed -= 1

    def _git_cwds(self):
        return list(self.project_activity.keys())

    def _scoped_git_churn(self, since_dt, until_dt):
        """Real git churn scoped to the INTERSECTION of the requested window and
        the corpus's own observed span (all_min_dt/all_max_dt), so numerator
        (churn) and denominator (active_hours, itself already corpus-scoped) are
        commensurate (design decision D: scope, not winsorize -- winsorizing
        would need cross-user percentiles the local CLI does not have).

        An empty corpus (no observed events) emits a zeroed dict and invokes NO
        git subprocess at all -- not merely relying on an empty cwd list.
        Returns (gc, gc_since, gc_until); gc_since/gc_until are None for an
        empty corpus."""
        if self.all_min_dt is None or self.all_max_dt is None:
            return (
                {"repos_seen": 0, "repos_with_commits": 0, "insertions": 0,
                 "deletions": 0, "churn": 0, "commits": 0, "per_repo": []},
                None, None,
            )
        _req_since = since_dt if since_dt is not None else self.all_min_dt
        _req_until = until_dt if until_dt is not None else (self.all_max_dt + timedelta(days=1))
        _gc_since_dt = max(_req_since, self.all_min_dt)
        _gc_until_dt = min(_req_until, self.all_max_dt + timedelta(days=1))
        gc_since = _gc_since_dt.strftime("%Y-%m-%d")
        gc_until = _gc_until_dt.strftime("%Y-%m-%d")
        return (git_churn(self._git_cwds(), gc_since, gc_until), gc_since, gc_until)

    def _record_skill(self, name, sid, mkey, planning_event_eligible=False, per_turn=False):
        """Record one skill signal.

        `per_turn=True` (the `attributionSkill` per-turn site ONLY) defers the
        counter increment: it records a pending span keyed by (session, skill)
        and returns without touching skill_counter/month_skill_counter. Every
        OTHER (discrete) site increments immediately AND claims the span, so a
        later flush (_flush_pending_skills, run once at the start of
        to_corpus_stats/to_source_stats) can skip anything already claimed and
        credit anything that was only ever seen via per-turn attribution.

        Dedup gates ONLY the two counter increments below. _mark_plan_session,
        _record_planning_skill_signal and _pending_knowledge_grounding stay
        unconditional and immediate so Planning/Context-Intelligence are not
        perturbed by this change (design decision C)."""
        if not name:
            return
        key = (sid or self._cur_fp, name)
        if per_turn:
            self._skill_span_pending.setdefault(key, mkey)
        else:
            self.skill_counter[name] += 1
            if mkey:
                self.month_skill_counter[mkey][name] += 1
            self._skill_span_claimed.add(key)
        if self._is_plan_skill(name):
            self._mark_plan_session(sid, mkey)
            self._record_planning_skill_signal(
                sid, mkey, event_eligible=planning_event_eligible)
        if self._is_knowledge_skill(name):
            self._pending_knowledge_grounding[sid] = True

    def _flush_pending_skills(self):
        """Idempotent. Resolves every per-turn `attributionSkill` span that was
        never claimed by a discrete event (Skill tool / injectedSkills / Read
        SKILL.md / Bash SKILL.md) in the same (session, skill) span, crediting
        it exactly once. MUST run before any read of skill_counter /
        month_skill_counter -- the only two entry points that read them are
        to_corpus_stats and to_source_stats, both of which call this first."""
        if self._skill_flush_done:
            return
        self._skill_flush_done = True
        for key, mkey in self._skill_span_pending.items():
            if key in self._skill_span_claimed:
                continue
            name = key[1]
            self.skill_counter[name] += 1
            if mkey:
                self.month_skill_counter[mkey][name] += 1

    # ---- plan-ceremony (per-session) helpers -------------------------------
    @staticmethod
    def _is_plan_skill(name):
        sl = str(name).lower()
        return any(nd in sl for nd in PLAN_SKILL_NEEDLES)

    @classmethod
    def _is_planning_dispatch(cls, name, inp):
        """Whether THIS tool call is a planning DISPATCH, so the ratio can leave
        it out of `doing`. A planning Skill classifies `execute` and a planning Agent
        classifies `delegate`, which would otherwise make thinking first lower the very
        term that rewards it.

        Deliberately NARROWER than `_fact_plan_skill`: `attributionSkill` is a per-TURN
        field, so honouring it here would strip every Edit/Bash in a planning-attributed
        turn out of the denominator — and on a real corpus most planning-skill evidence
        arrives by attribution. A shell read of a SKILL.md is a read, not a dispatch, and
        stays in `doing` for the same reason."""
        if name == "Skill":
            return cls._is_plan_skill(inp.get("skill"))
        if name == "Agent":
            return cls._is_plan_skill(inp.get("subagent_type", "general-purpose"))
        return False

    # ---- ordered-fact enrichment helpers (C1) ------------------------------
    @staticmethod
    def _write_loc(name, inp):
        """Net changed lines for a write-tool call; None for non-write tools.
        NEVER used to flip ordered_facts_complete — that flag is timestamp-
        completeness only (C1 risk: a missing loc must degrade gracefully)."""
        if name == "Edit":
            return line_count(inp.get("new_string", "")) + line_count(inp.get("old_string", ""))
        if name == "Write":
            return line_count(inp.get("content", ""))
        if name == "MultiEdit":
            total = 0
            for e in inp.get("edits", []) or []:
                if isinstance(e, dict):
                    total += (line_count(e.get("new_string", ""))
                              + line_count(e.get("old_string", "")))
            return total
        if name == "NotebookEdit":
            return line_count(inp.get("new_source", ""))
        return None

    @classmethod
    def _fact_plan_skill(cls, name, inp, ev):
        """Whether THIS tool_use event signals a planning skill (C1/C3): a
        Skill invocation, an Agent subagent_type, an attributionSkill on the
        surrounding assistant turn (attributionSkill is per-turn, so it applies
        to every tool_use block within that turn, not just Skill/Agent calls),
        or a codex-style shell SKILL.md read. All checked via PLAN_SKILL_NEEDLES
        (the same needles that drive plan_sessions/planning_skill_sessions)."""
        if name == "Skill" and cls._is_plan_skill(inp.get("skill")):
            return True
        if name == "Agent" and cls._is_plan_skill(inp.get("subagent_type", "general-purpose")):
            return True
        if ev.get("attributionSkill") and cls._is_plan_skill(ev["attributionSkill"]):
            return True
        if name == "Bash":
            cmd = _normalize_bash_command(inp.get("command"))
            for m in _SKILL_MD_RX.finditer(cmd):
                if cls._is_plan_skill(m.group(1)):
                    return True
        return False

    def _is_knowledge_skill(self, name):
        low = (name or "").lower()
        return any(n in low for n in KNOWLEDGE_SKILL_NEEDLES)

    def _mark_plan_session(self, sid, mkey):
        """Record that session `sid` (in month `mkey`) contained a planning signal.
        Idempotent per session — repeated signals in one session count once."""
        if not sid:
            return
        self.plan_sessions.add(sid)
        if mkey:
            self.month_plan_sessions[mkey].add(sid)

    def _record_planning_skill_signal(self, sid, mkey, *, event_eligible):
        """The sole mutation path for the qualified planning numerator.

        Descriptive skill counters are updated before this guard, so rejecting a
        child marker changes scoring attribution only. A synthetic timestamp is
        provenance for a real event: it may credit an already-eligible root at
        corpus level, but never creates eligibility or a mismatched monthly credit.
        """
        if not event_eligible or not sid:
            return
        key = (self._cur_src, sid)
        self.planning_skill_sessions.add(key)
        if mkey and key in self.month_planning_skill_eligible_sessions[mkey]:
            self.month_planning_skill_sessions[mkey].add(key)

    def _counted_plan_sessions(self):
        """Plan sessions restricted to the same universe as total_sessions, so the
        plan_sessions / total_sessions fraction can never exceed 1 (a session that
        never entered session_ts is not in the denominator either)."""
        if not self.plan_sessions:
            self._plan_sessions_degraded = False
            return 0
        if self.session_ts:
            self._plan_sessions_degraded = False
            return len(self.plan_sessions & set(self.session_ts))
        # No real timestamps at all — fall back to session_files (synth-only / undated).
        self._plan_sessions_degraded = True
        return min(len(self.plan_sessions), len(self.session_files))

    def _counted_planning_skill_sessions(self):
        return len(self.planning_skill_sessions & self.planning_skill_eligible_sessions)

    @staticmethod
    def _planning_skill_fields(numerator, denominator, unmeasured):
        assert 0 <= numerator <= denominator
        assert unmeasured >= 0
        state = ("measured" if denominator > 0 and unmeasured == 0
                 else "partial" if denominator > 0 and unmeasured > 0
                 else "unmeasured")
        return {
            "planning_skill_sessions": numerator,
            "planning_skill_eligible_sessions": denominator,
            "planning_skill_unmeasured_sessions": unmeasured,
            "planning_skill_session_scope_state": state,
            "planning_skill_session_share": (
                round(numerator / denominator, 6)
                if state in {"measured", "partial"} else None),
            "planning_skill_session_coverage": (
                round(denominator / (denominator + unmeasured), 6)
                if state in {"measured", "partial"} else None),
        }

    def _counted_planning_skill_unmeasured_sessions(self, month=None):
        unresolved = (self.month_planning_skill_unmeasured_sessions.get(month, set())
                      if month else self.planning_skill_unmeasured_sessions)
        eligible = (self.month_planning_skill_eligible_sessions.get(month, set())
                    if month else self.planning_skill_eligible_sessions)
        return len(unresolved - eligible)

    # ---- Context Intelligence (behavioral grounding) helper ----------------
    def _consume_knowledge_grounding(self, sid, mkey):
        """A write (Edit/Write/MultiEdit/NotebookEdit) consumes a pending knowledge-MCP
        grounding flag for this session, marking the session grounded. Consume-once: the
        FIRST grounded write flips the flag off, so repeated writes after one knowledge
        call still count as exactly one grounded session.
        Also tracks this session as a write-session (CI denominator)."""
        if sid:
            self.write_sessions.add(sid)
            if mkey:
                self.month_write_sessions[mkey].add(sid)
        if sid and self._pending_knowledge_grounding.get(sid):
            self.grounded_sessions.add(sid)
            if mkey:
                self.month_grounded_sessions[mkey].add(sid)
            self._pending_knowledge_grounding[sid] = False

    def _counted_grounded_sessions(self):
        """Grounded sessions restricted to the same universe as total_sessions, mirroring
        _counted_plan_sessions, so grounded/total can never exceed 1."""
        if self.session_ts:
            return len(self.grounded_sessions & set(self.session_ts))
        return min(len(self.grounded_sessions), len(self.session_files))

    def _counted_write_sessions(self):
        """Write sessions restricted to same universe as total_sessions."""
        if self.session_ts:
            return len(self.write_sessions & set(self.session_ts))
        return min(len(self.write_sessions), len(self.session_files))

    def _claude_attempt(self, tool_use_id):
        return self.claude_agent_attempts.setdefault(tool_use_id, {
            "tool_use_id": tool_use_id, "invocation_seen": False,
            "result_seen": False,
            "parent_session": None, "lead_model": None, "assistant_uuid": None,
            "agent_id": None, "status": None, "resolved_model": None,
            "substantive_calls": 0, "writes": 0, "ambiguous": False,
        })

    def _record_claude_agent_result(self, ev, block, sid):
        result = ev.get("toolUseResult")
        if self._cur_src != "claude" or not isinstance(result, dict):
            return
        tool_use_id = block.get("tool_use_id")
        if not tool_use_id:
            return
        # Claude adds toolUseResult metadata to many native tool results. Only an
        # already-observed Agent call or a result carrying agent identity belongs
        # to the routing join.
        if tool_use_id not in self.claude_agent_attempts and not result.get("agentId"):
            return
        attempt = self._claude_attempt(tool_use_id)
        attempt["result_seen"] = True
        agent_id = result.get("agentId")
        status = result.get("status")
        assistant_uuid = ev.get("sourceToolAssistantUUID")
        if attempt["parent_session"] not in (None, sid):
            attempt["ambiguous"] = True
        if attempt["assistant_uuid"] and assistant_uuid and attempt["assistant_uuid"] != assistant_uuid:
            attempt["ambiguous"] = True
        if attempt["agent_id"] not in (None, agent_id):
            attempt["ambiguous"] = True
        if attempt["status"] not in (None, "async_launched", status):
            attempt["ambiguous"] = True
        attempt["parent_session"] = attempt["parent_session"] or sid
        attempt["agent_id"] = attempt["agent_id"] or agent_id
        attempt["status"] = status or attempt["status"]
        attempt["resolved_model"] = result.get("resolvedModel") or attempt["resolved_model"]
        tool_stats = result.get("toolStats") or {}
        try:
            attempt["writes"] = max(attempt["writes"], int(tool_stats.get("editFileCount") or 0))
        except (ValueError, TypeError):
            pass

    def _record_claude_notification(self, ev, content):
        if (self._cur_src != "claude" or not isinstance(content, str)
                or (ev.get("origin") or {}).get("kind") != "task-notification"):
            return
        tool_use_id = _notification_tag(content, "tool-use-id")
        agent_id = _notification_tag(content, "task-id")
        status = _notification_tag(content, "status")
        if not tool_use_id:
            return
        attempt = self._claude_attempt(tool_use_id)
        if attempt["agent_id"] not in (None, agent_id):
            attempt["ambiguous"] = True
        if attempt["status"] not in (None, "async_launched", status):
            attempt["ambiguous"] = True
        attempt["agent_id"] = attempt["agent_id"] or agent_id
        attempt["status"] = status or attempt["status"]

    def _routing_snapshot(self, src_name=None):
        supported = ({src_name} if src_name else set(self.source_sessions)) & {"claude", "codex"}
        if not supported:
            return [], "unsupported"

        pairs = []
        matched_spawns = set()
        # Resolve Codex delegation identity at snapshot time so source file order
        # cannot affect the join.  A reused child path is matched one-to-one in
        # event order; if more than one same-identity call could own a turn, do
        # not guess.
        ordered_links = sorted(
            enumerate(self.routing_links),
            key=lambda item: (item[1].get("_order") is None,
                              item[1].get("_order") or (float("inf"), 0), item[0]),
        )
        resolved = {}
        ambiguous_links = set()
        for link_index, link in ordered_links:
            parent = link.get("parent_session")
            link_order = link.get("_order")
            identity = link.get("delegation_identity")
            turn_id = link.get("turn_id")
            exact_candidates = []
            identity_candidates = []
            for spawn_index, spawn in enumerate(self.codex_spawn_events.get(parent, [])):
                key = (parent, spawn_index)
                if key in matched_spawns:
                    continue
                exact_turn = bool(turn_id and spawn.get("turn_id") == turn_id)
                exact_identity = bool(identity and spawn.get("identity") == identity)
                spawn_order = spawn.get("order")
                if exact_turn:
                    exact_candidates.append((key, spawn))
                elif exact_identity:
                    if (link_order is not None and spawn_order is not None
                            and spawn_order > link_order):
                        continue
                    identity_candidates.append((key, spawn))
            # Submission/turn identity is authoritative. Stable child identity and
            # event order are only a fallback when no exact submission exists.
            candidates = exact_candidates or identity_candidates
            if len(candidates) == 1:
                key, spawn = candidates[0]
                matched_spawns.add(key)
                resolved[link_index] = spawn.get("model")
            elif len(candidates) > 1:
                ambiguous_links.add(link_index)

        for link_index, link in enumerate(self.routing_links):
            pair = dict(link)
            pair.pop("_order", None)
            if not pair.get("lead_model"):
                pair["lead_model"] = resolved.get(link_index)
            pairs.append(pair)
        incomplete = any(not p.get("lifecycle_known", False) for p in pairs)
        incomplete = incomplete or bool(ambiguous_links)
        # Completed work requires a proven parent delegation.  Known aborts are
        # still measured exclusions even when their parent call is outside the
        # selected window, because they never enter the routing denominator.
        incomplete = incomplete or any(
            p.get("completed") and not p.get("lead_model") for p in pairs
            if p.get("provider") == "openai"
        )
        unmatched_spawns = {
            (parent, index)
            for parent, spawns in self.codex_spawn_events.items()
            for index, _spawn in enumerate(spawns)
        } - matched_spawns
        incomplete = incomplete or bool(unmatched_spawns)

        if "claude" in supported:
            referenced_children = set()
            for attempt in self.claude_agent_attempts.values():
                agent_id = attempt.get("agent_id")
                child = self.claude_child_facts.get(agent_id) if agent_id else None
                models = child.get("models", set()) if child else set()
                child_model = attempt.get("resolved_model")
                if not child_model and len(models) == 1:
                    child_model = next(iter(models))
                lifecycle_known = attempt.get("status") not in (None, "async_launched")
                aborted = attempt.get("status") in {"killed", "cancelled", "stopped"}
                if (aborted and attempt.get("invocation_seen") and attempt.get("result_seen")
                        and not attempt.get("ambiguous") and lifecycle_known
                        and attempt.get("lead_model")):
                    if agent_id:
                        referenced_children.add(agent_id)
                    pairs.append({
                        "provider": "anthropic",
                        "parent_session": attempt.get("parent_session"),
                        "child_session": agent_id,
                        "lead_model": attempt.get("lead_model"),
                        "child_model": child_model,
                        "completed": False,
                        "substantive_calls": 0,
                        "writes": 0,
                    })
                    continue
                valid = (attempt.get("invocation_seen") and not attempt.get("ambiguous")
                         and agent_id and lifecycle_known and attempt.get("lead_model")
                         and child_model and child is not None)
                if not valid:
                    incomplete = True
                    continue
                referenced_children.add(agent_id)
                pairs.append({
                    "provider": "anthropic",
                    "parent_session": attempt.get("parent_session"),
                    "child_session": agent_id,
                    "lead_model": attempt.get("lead_model"),
                    "child_model": child_model,
                    "completed": attempt.get("status") == "completed",
                    "substantive_calls": max(
                        attempt.get("substantive_calls", 0), child["substantive_calls"]),
                    "writes": max(attempt.get("writes", 0), child["writes"]),
                })
            if set(self.claude_child_facts) - referenced_children:
                incomplete = True
        return pairs, "unmeasured" if incomplete else "measured"

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

        # Workflow fan-out fix (contract 15:15:15): this event survived the window
        # filter above, so if the CURRENT file is a dispatched Workflow agent
        # transcript, credit one dispatch to the PARENT session now (never before
        # the window check, so an entirely out-of-window run credits nothing).
        # `agentId` is the real per-dispatch child identity (the file's own
        # `sessionId` is the PARENT's, not distinct per child -- verified against a
        # real corpus sample); the filename-derived id is a fallback for sources/
        # shapes that omit the field. Dedup on (parent_sid, child_id) makes a
        # resumed run that re-references the same transcript a no-op.
        if self._pending_fanout_credit is not None:
            _parent_sid, _filename_agent_id = self._pending_fanout_credit
            _child_id = ev.get("agentId") or _filename_agent_id
            _credit_key = (_parent_sid, _child_id)
            if _credit_key not in self._fanout_credited_agents:
                self._fanout_credited_agents.add(_credit_key)
                self.agents_per_session[_parent_sid] += 1
                if mkey:
                    self.month_fanouts[mkey][_parent_sid] += 1

        # Planning eligibility is deliberately event-scoped. In particular,
        # Cursor root and child events can share a SID, so filtering only after
        # session dedupe would let a child marker credit its parent.
        _scope_measured = planning_session_scope(self._cur_src) == "measured"
        _identity_valid = isinstance(ev.get("isSidechain"), bool)
        _planning_key = (self._cur_src, sid) if sid else None
        _planning_candidate = bool(
            sid and dt is not None
            and not ev.get("__synth_ts__")
            and not ev.get("__codex_usage__")
            and etype != "routing_link")
        planning_denominator_eligible = bool(
            _planning_candidate and _scope_measured and _identity_valid
            and ev.get("isSidechain") is False)
        if planning_denominator_eligible:
            self.planning_skill_eligible_sessions.add(_planning_key)
            if mkey:
                self.month_planning_skill_eligible_sessions[mkey].add(_planning_key)
        elif _planning_candidate and (
                not _scope_measured or not _identity_valid):
            self.planning_skill_unmeasured_sessions.add(_planning_key)
            if mkey:
                self.month_planning_skill_unmeasured_sessions[mkey].add(_planning_key)
        # ``__synth_ts__`` marks timestamp provenance, not a fabricated event.
        # Cursor may therefore credit a root admitted by an earlier real event,
        # but it can never create denominator eligibility by itself.
        _already_eligible = _planning_key in self.planning_skill_eligible_sessions
        planning_event_eligible = bool(
            sid and dt is not None
            and not ev.get("__codex_usage__")
            and etype != "routing_link"
            and _scope_measured
            and _identity_valid
            and ev.get("isSidechain") is False
            and (not ev.get("__synth_ts__") or _already_eligible)
        )

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

        for skill in ev.get("injectedSkills") or []:
            self._record_skill(skill, sid, mkey, planning_event_eligible)

        msg = ev.get("message") if isinstance(ev.get("message"), dict) else None

        if self._cur_src == "claude" and ev.get("isSidechain") and ev.get("agentId"):
            child = self.claude_child_facts[ev["agentId"]]
            child_model = (msg or {}).get("model")
            if child_model:
                child["models"].add(child_model)

        if etype == "routing_link":
            link = dict(ev.get("routing") or {})
            link["_order"] = (dt.timestamp(), ev.get("__ordinal__", 0)) if dt else None
            self.routing_links.append(link)
            return None

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
            self._record_claude_notification(ev, msg.get("content"))
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
                        # A bare slash command IS a human instruction -- it just carries no
                        # text for the length/politeness/quote machinery below, which is the
                        # only reason it does not increment prompts_count. Counted here so
                        # `actions_per_prompt` can divide by the whole instruction
                        # population; see __init__ for why this is not folded in above.
                        self.command_only_prompts += 1
                        if mkey:
                            self.month_command_only[mkey] += 1
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
                        self._record_claude_agent_result(ev, b, sid)
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
                if sid:
                    self.session_models[sid] = mdl
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
                self._record_skill(
                    ev["attributionSkill"], sid, mkey, planning_event_eligible,
                    per_turn=True)
            content = msg.get("content")
            if isinstance(content, list):
                _turn_agent_count = 0
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
                        # Some non-Claude adapters emit a Bash tool's `command` as an argv
                        # LIST rather than a shell string. Normalize ONCE, here, so every
                        # regex-based Bash classifier below (the ordered-fact "knowledge"/
                        # "runs_tests" enrichment AND the "elif name == 'Bash':" accounting
                        # further down) reads the same string and a list-valued command
                        # scores identically to its already-joined sibling instead of
                        # raising TypeError wherever the join was missing.
                        _bash_cmd = (_normalize_bash_command(inp.get("command"))
                                    if name == "Bash" else "")
                        self.tool_use_total += 1
                        # Identity is an EVENT fact, so it is read here rather than derived
                        # from the session: a parent transcript and its subagent turns share
                        # one sessionId (see _cursor_jsonl_meta / the claude sidechain files),
                        # so a session-level split would credit the parent.
                        _sidechain_call = bool(ev.get("isSidechain"))
                        if _sidechain_call:
                            self.sidechain_tool_use_total += 1
                        self.tool_counter[name] += 1
                        _cat = classify_tool(name)
                        # A dispatch on a source that cannot label sidechain means subagent
                        # calls are about to be counted as top-level. Recorded here (on the
                        # dispatch, where it is observable) so `sidechain_label_state` reflects
                        # what this corpus actually did rather than what its adapter could in
                        # principle mislabel.
                        if (_cat == "delegate"
                                and sidechain_label_scope(self._cur_src) == "cannot_label"):
                            self.unlabelled_delegate_dispatches += 1
                        if (self._cur_src == "claude" and ev.get("isSidechain")
                                and ev.get("agentId")):
                            child = self.claude_child_facts[ev["agentId"]]
                            if is_substantive_tool(name):
                                child["substantive_calls"] += 1
                            if name in {"Edit", "Write", "MultiEdit", "NotebookEdit"}:
                                child["writes"] += 1
                        if sid:
                            _target = _norm_path_seps(
                                inp.get("file_path") or inp.get("notebook_path")
                                or inp.get("path") or inp.get("pattern") or inp.get("query") or "")
                            _items = (inp.get("todos") or inp.get("items") or inp.get("tasks")
                                      or inp.get("plan") or [])
                            if isinstance(_items, list):
                                _items = [
                                    (x.get("content") or x.get("step") or "")
                                    if isinstance(x, dict) else x for x in _items
                                ]
                            _fact_sid = (self._cur_src, sid)
                            _ordered_fact = {
                                "name": name, "target": _target, "items": _items,
                                "cwd": cwd,
                                "order": dt.timestamp() if dt is not None else float("inf"),
                                "ordinal": ev.get(
                                    "__ordinal__", len(self.session_ordered_tools[_fact_sid])),
                                "knowledge": bool(name.startswith("mcp__") and (
                                    classify_mcp_subcategory(
                                        name.split("__")[1] if len(name.split("__")) > 1 else "",
                                        name.split("__")[-1]) == "knowledge" or (
                                        classify_mcp_subcategory(
                                            name.split("__")[1] if len(name.split("__")) > 1 else "",
                                            name.split("__")[-1]) in CI_CONTEXT_SUBCATS
                                        and _cat == "explore")))
                                if name.startswith("mcp__") else bool(name == "Bash" and bash_runs_knowledge(_bash_cmd)),
                                # C1 — write-fact enrichment (ordered-planning redesign):
                                # file_class/plan_file are computed from the target for
                                # every fact (harmless no-op for non-file tools); loc is
                                # only meaningful for write tools and MUST stay None
                                # otherwise — a missing loc never flips
                                # ordered_facts_complete (see the `dt is None` check below,
                                # which is the ONLY thing that flips it).
                                "file_class": classify_change_target(_target),
                                "loc": self._write_loc(name, inp),
                                "plan_file": is_plan_file_target(_target),
                                "plan_skill": self._fact_plan_skill(name, inp, ev),
                                # v18 — per-session Verification COVERAGE numerator: mark a
                                # Bash fact that ran a shell test (bash_runs_tests), so
                                # derive_session_ordered_facts/aggregate_ordered can count the
                                # eligible change-sessions that verified, next to the raw
                                # cumulative shell_test_runs density that fed the dropped term.
                                "runs_tests": bool(
                                    name == "Bash"
                                    and bash_runs_tests(_bash_cmd)),
                            }
                            self.session_ordered_tools[_fact_sid].append(_ordered_fact)
                            if dt is None:
                                self.ordered_facts_complete = False
                            if mkey:
                                self.month_session_ordered_tools[mkey][_fact_sid].append(_ordered_fact)
                        if mkey:
                            self.month_tools[mkey] += 1
                            if _sidechain_call:
                                self.month_sidechain_tools[mkey] += 1
                            self.month_tool_counter[mkey][name] += 1
                            if _cat == "delegate":
                                self.month_delegate[mkey] += 1
                        self.cat_counter[_cat] += 1
                        if self._is_planning_dispatch(name, inp):
                            self.planning_dispatch_calls += 1
                            if mkey:
                                self.month_planning_dispatch_calls[mkey] += 1
                        if name.startswith("mcp__"):
                            self.mcp_calls += 1
                            parts = name.split("__")
                            if len(parts) > 1 and parts[1]:
                                tool_part = parts[-1] if len(parts) > 2 else ""
                                server = _canon_mcp_server(parts[1], tool_part)
                                self.mcp_server_counter[server] += 1
                                if mkey:
                                    self.month_mcp_server_counter[mkey][server] += 1
                                subcat = classify_mcp_subcategory(server, tool_part)
                                self.mcp_subcategory_counter[subcat] += 1
                                self.mcp_subcategory_servers[subcat].add(server)
                                if mkey:
                                    self.month_mcp_subcategory_counter[mkey][subcat] += 1
                                    self.month_mcp_subcategory_servers[mkey][subcat].add(server)
                                # Context Intelligence (behavioral): arm grounding
                                # for knowledge MCPs (any call) or project/data/design
                                # MCPs (explore/read calls only), consumed by the next
                                # write (Edit/Write/MultiEdit/NotebookEdit) below.
                                if sid and (subcat == "knowledge"
                                            or (subcat in CI_CONTEXT_SUBCATS
                                                and _cat == "explore")):
                                    self._pending_knowledge_grounding[sid] = True
                                # Compounding credit for MCP knowledge-writes (contract
                                # 16:16:16): numerator-only, additive to the existing
                                # filesystem _is_compounding_path sites below (disjoint
                                # gate -- this fires on mcp__* tool_use, those fire on
                                # Edit/Write/MultiEdit/NotebookEdit -- so no double
                                # count). Dedup by (sid, distinct persisted target) so
                                # target-less/repeat-target spam cannot saturate the
                                # axis while genuinely distinct targets each credit.
                                if sid and is_mcp_knowledge_write(server, tool_part):
                                    _persist_id = (
                                        inp.get("memory_id") or inp.get("topic_key")
                                        or inp.get("id") or inp.get("entity")
                                        or inp.get("name")
                                        or f"{server}:{tool_part.lower()}")
                                    _ck = (sid, _persist_id)
                                    if _ck not in self._mcp_compounding_credited:
                                        self._mcp_compounding_credited.add(_ck)
                                        self.compounding_counter += 1
                                        if mkey:
                                            self.month_compounding[mkey] += 1
                        else:
                            self.native_calls += 1

                        if (ENABLE_WEB_CONTEXT_GROUNDING and sid
                                and name in _KNOWLEDGE_NATIVE_TOOLS):
                            url = inp.get("url", "")
                            if not _is_local_url(url):
                                self._pending_knowledge_grounding[sid] = True

                        # a tool use after a pending error = recovery
                        if sid and self._pending_error.get(sid):
                            self.recovered_errors += 1
                            if mkey:
                                self.month_recovered_errors[mkey] += 1
                            self._pending_error[sid] = False

                        if name == "Skill":
                            s = inp.get("skill")
                            if s:
                                self._record_skill(
                                    s, sid, mkey, planning_event_eligible)
                        # Plan-ceremony signal: mark this SESSION as a planning session.
                        # PLAN_SIGNAL_TOOLS normalizes across sources (EnterPlanMode = Cursor
                        # create_plan; ExitPlanMode = Claude Code native plan mode, shift+tab ->
                        # present plan; TodoWrite = Codex update_plan / Antigravity manage_task /
                        # Cursor todos). We count DISTINCT SESSIONS, not tool calls, so TodoWrite
                        # firing many times per session (todo bookkeeping) can't inflate the metric.
                        # Subset of taxonomy.PLAN_TOOLS: TodoRead/TaskList/TaskGet are reads.
                        #
                        # Only the PLAN_MODE subset also reaches the QUALIFIED numerator: entering
                        # or exiting plan mode is a human deciding to plan and a plan existing
                        # before code, the same construct a planning Skill expresses. TodoWrite /
                        # TaskCreate stay legacy-only — they are the agent's own execution
                        # bookkeeping, they already earn "Ordered planning readiness" through the
                        # PLAN_MIN_STEPS distinct-step gate in derive_session_ordered_facts, and
                        # TaskCreate alone appears in most sessions, so admitting it here would
                        # saturate the term without anyone changing how they work.
                        if name in PLAN_SIGNAL_TOOLS:
                            self._mark_plan_session(sid, mkey)
                            if name in PLAN_MODE_TOOLS:
                                self._record_planning_skill_signal(
                                    sid, mkey, event_eligible=planning_event_eligible)
                        if name in ORCHESTRATION_TOOLS:
                            _turn_agent_count += 1
                            if self._cur_src == "codex" and sid:
                                self.codex_spawn_events[sid].append({
                                    "order": ((dt.timestamp(), ev.get("__ordinal__", 0))
                                              if dt is not None else None),
                                    "model": mdl,
                                    "identity": inp.get("_routing_identity"),
                                    "turn_id": inp.get("_routing_turn_id"),
                                })
                            if self._cur_src == "claude":
                                tool_use_id = b.get("id")
                                if tool_use_id:
                                    attempt = self._claude_attempt(tool_use_id)
                                    invocation = (sid, mdl, ev.get("uuid"))
                                    previous = (attempt.get("parent_session"), attempt.get("lead_model"),
                                                attempt.get("assistant_uuid"))
                                    if attempt["invocation_seen"] and previous != invocation:
                                        attempt["ambiguous"] = True
                                    attempt.update({
                                        "invocation_seen": True, "parent_session": sid,
                                        "lead_model": mdl, "assistant_uuid": ev.get("uuid"),
                                    })
                            st = inp.get("subagent_type", "general-purpose")
                            self.subagent_counter[st] += 1
                            if self._is_plan_skill(st):
                                self._mark_plan_session(sid, mkey)
                                self._record_planning_skill_signal(
                                    sid, mkey, event_eligible=planning_event_eligible)
                            if self._is_knowledge_skill(st):
                                self._pending_knowledge_grounding[sid] = True
                            if mkey:
                                self.month_subagent_counter[mkey][st] += 1
                            if sid:
                                # Workflow fan-out fix (contract 15:15:15): Agent/Task
                                # stay 1-call==1-agent (unchanged) via this direct
                                # increment. Workflow is excluded here -- one call can
                                # dispatch many real agents, so its fan-out is sourced
                                # from the real dispatched-agent transcripts instead
                                # (observe()'s _pending_fanout_credit handling above),
                                # which increments these SAME two accumulators, so
                                # Workflow-only sessions still stay in _fanouts/
                                # delegating_sessions -- no membership special-case.
                                if name not in FANOUT_BY_TRANSCRIPT_TOOLS:
                                    self.agents_per_session[sid] += 1
                                    if mkey:
                                        self.month_fanouts[mkey][sid] += 1
                                self.session_subagent_types[sid].add(st)
                                if mkey:
                                    self.month_session_subagent_types[mkey][sid].add(st)
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

                        if name == "Read":
                            skill_name = extract_skill_name_from_path(inp.get("file_path"))
                            if skill_name:
                                self._record_skill(
                                    skill_name, sid, mkey, planning_event_eligible)

                        # ---- code churn + iteration depth ----------
                        if name == "Edit":
                            self._consume_knowledge_grounding(sid, mkey)
                            a = line_count(inp.get("new_string", ""))
                            r = line_count(inp.get("old_string", ""))
                            self.lines_added += a
                            self.lines_removed += r
                            if mkey:
                                self.month_churn[mkey] += a + r
                            fpth = _norm_path_seps(inp.get("file_path"))
                            if sid and fpth:
                                self._file_edit_run[sid][fpth] += 1
                                if mkey:
                                    self._file_edit_month[sid][fpth] = mkey
                            if _is_compounding_path(fpth):
                                self.compounding_counter += 1
                                if mkey:
                                    self.month_compounding[mkey] += 1
                        elif name == "Write":
                            self._consume_knowledge_grounding(sid, mkey)
                            a = line_count(inp.get("content", ""))
                            self.lines_added += a
                            if mkey:
                                self.month_churn[mkey] += a
                            fpth = _norm_path_seps(inp.get("file_path"))
                            if sid and fpth:
                                self._file_edit_run[sid][fpth] += 1
                                if mkey:
                                    self._file_edit_month[sid][fpth] = mkey
                            if _is_compounding_path(fpth):
                                self.compounding_counter += 1
                                if mkey:
                                    self.month_compounding[mkey] += 1
                        elif name == "MultiEdit":
                            self._consume_knowledge_grounding(sid, mkey)
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
                            fpth = _norm_path_seps(inp.get("file_path"))
                            if sid and fpth:
                                self._file_edit_run[sid][fpth] += 1
                                if mkey:
                                    self._file_edit_month[sid][fpth] = mkey
                            if _is_compounding_path(fpth):
                                self.compounding_counter += 1
                                if mkey:
                                    self.month_compounding[mkey] += 1
                        elif name == "NotebookEdit":
                            self._consume_knowledge_grounding(sid, mkey)
                            _nb_a = line_count(inp.get("new_source", ""))
                            self.lines_added += _nb_a
                            fpth = _norm_path_seps(inp.get("notebook_path"))
                            if sid and fpth:
                                self._file_edit_run[sid][fpth] += 1
                                if mkey:
                                    self._file_edit_month[sid][fpth] = mkey
                            if _is_compounding_path(fpth):
                                self.compounding_counter += 1
                                if mkey:
                                    self.month_compounding[mkey] += 1
                        elif name == "Bash":
                            cmd = _bash_cmd
                            for _cli in _extract_clis(cmd):
                                self.cli_counter[_cli] += 1
                                if mkey:
                                    self.month_cli_counter[mkey][_cli] += 1
                            if self._cur_src != "claude":
                                # Claude invokes skills via the Skill tool (counted
                                # above); other CLIs read SKILL.md through the shell
                                for _sm in _SKILL_MD_RX.finditer(cmd):
                                    self._record_skill(
                                        _sm.group(1), sid, mkey,
                                        planning_event_eligible)
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
                            if bash_runs_knowledge(cmd):
                                self._pending_knowledge_grounding[sid] = True
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
                if _turn_agent_count >= 2:
                    self.parallel_dispatch_turns += 1

        return prompt_info

    # ---- shaping: whole-corpus stats ---------------------------------------
    def to_corpus_stats(self, since_dt, until_dt, antigravity):
        """Build the full corpus stats dict. Also stashes self.gc (the raw git_churn
        dict) for the narrative payload main() consumes."""
        self._flush_pending_skills()
        # ---- derive ----------------------------------------------------------
        # C4: aggregate_ordered applies cross-session consume-once plan credit
        # across the WHOLE corpus (not per-session derive_ordered_behavior).
        _agg = aggregate_ordered(self.session_ordered_tools.values())
        _eligible = _agg["eligible"]
        _planned = _agg["planned"]
        _evidence = _agg["evidence"]
        _test_covered = _agg["test_covered"]
        # Orchestratable: per-session cross-ref with agents_per_session
        _orchestratable = _agg["orchestratable"]
        _orchestratable_sids = set()
        for (src, sid), facts in self.session_ordered_tools.items():
            d = derive_session_ordered_facts(facts)
            if d["orchestratable"]:
                _orchestratable_sids.add(sid)
        _delegated_orchestratable = sum(
            1 for sid in _orchestratable_sids
            if self.agents_per_session.get(sid, 0) > 0)
        _routing_pairs, _routing_state = self._routing_snapshot()
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

        # Gold-standard churn: real git insertions/deletions, scoped to the
        # INTERSECTION of the requested window and the corpus's own observed span
        # (design decision D: scope, not winsorize -- see _scoped_git_churn).
        gc, gc_since, gc_until = self._scoped_git_churn(since_dt, until_dt)
        self.gc = gc
        git_velocity = (gc["churn"] / active_hours) if active_hours > 0 else 0

        explore = self.cat_counter.get("explore", 0) + self.thinking_blocks
        produce = self.cat_counter.get("produce", 0)
        execute = self.cat_counter.get("execute", 0)
        delegate = self.cat_counter.get("delegate", 0)
        # Planning dispatches leave the denominator: invoking a planning Skill (execute) or
        # dispatching a planning subagent (delegate) is thinking first, not building, so it
        # must not lower the term that rewards thinking first.
        #
        # But the subtraction must never EMPTY the denominator. A corpus whose only
        # execute/delegate activity is planning dispatch, with no writes, would otherwise
        # publish a ratio of 0 — the worst value for a term that rewards exploring, handed to
        # someone who did nothing but explore and plan. Inverting a score is worse than not
        # adjusting it, so we fall back to the raw denominator: a corpus with no build has
        # nothing to compare its exploring against.
        doing = _adjusted_doing(produce + execute + delegate, self.planning_dispatch_calls)
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
        max_session_fanout = max(_fanouts, default=0)
        delegating_sessions = len(_fanouts)
        parallel_delegating_sessions = sum(1 for n in _fanouts if n >= 2)
        parallel_session_share = (
            round(parallel_delegating_sessions / delegating_sessions, 3)
            if delegating_sessions else 0.0)
        _ids = _iteration_depth_stats(self.edits_per_file_events, no_tool_activity)
        iteration_mean = _ids["mean"]
        iteration_median = _ids["median"]
        iteration_p90 = _ids["p90"]
        iteration_max = _ids["max"]
        heavy_files = _ids["heavy_files"]

        # Top-level tool calls per human instruction. Bare commands count as
        # instructions; `total_prompts` remains typed text for length statistics.
        top_level_tool_calls = self.tool_use_total - self.sidechain_tool_use_total
        total_instructions = self.prompts_count + self.command_only_prompts
        actions_per_prompt = (
            (top_level_tool_calls / total_instructions) if total_instructions else 0)
        # Autonomy is a local diagnostic; its divisor is not a published scoring calibration.
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
                # The ACTUAL observed span of events that survived the window filter
                # (always all_min_dt/all_max_dt), independent of `date_range` above --
                # which reports the *requested* window verbatim when one is given.
                # Never uploaded before this field (span_days, computed from the same
                # two datetimes, already was) -- see design decision A's data flow.
                "observed_range": [
                    self.all_min_dt.isoformat() if self.all_min_dt else None,
                    self.all_max_dt.isoformat() if self.all_max_dt else None,
                ],
                "span_days": span_days,
                "active_days": active_days,
                "timezone": f"{tzname} (UTC{tzoffset[:3]}:{tzoffset[3:]})",
                "antigravity_experimental": antigravity,
            },
            "volume": {
                "total_sessions": total_sessions,
                "total_prompts": self.prompts_count,
                "command_invocations": self.command_invocations,
                # Persist the ratio denominator so it can be reconstructed from the payload.
                "total_instructions": total_instructions,
                "avg_prompt_length_chars": round(avg_prompt_len, 1),
                "median_prompt_length_chars": round(median_prompt_len, 1),
                "assistant_turns": self.assistant_turns,
                "tool_calls_total": self.tool_use_total,
                # Diagnostic sidechain count; rate terms continue to use the total.
                "sidechain_tool_calls": self.sidechain_tool_use_total,
                "thinking_blocks": self.thinking_blocks,
            },
            "tools": {
                "tool_diversity": tool_diversity,
                "tool_entropy_normalized": round(norm_entropy, 3),
                "mcp_calls": self.mcp_calls,
                "native_calls": self.native_calls,
                "mcp_share": round(self.mcp_calls / (self.mcp_calls + self.native_calls), 3) if (self.mcp_calls + self.native_calls) else 0,
                "top_tools": self.tool_counter.most_common(100),
                "category_breakdown": dict(self.cat_counter),
                "mcp_servers": self.mcp_server_counter.most_common(),
                "top_mcp_servers": self.mcp_server_counter.most_common(100),
                "mcp_servers_distinct": len(self.mcp_server_counter),
                "mcp_knowledge_calls": self.mcp_subcategory_counter.get("knowledge", 0),
                "mcp_knowledge_servers": len(self.mcp_subcategory_servers.get("knowledge", set())),
                "mcp_knowledge_server_names": sorted(self.mcp_subcategory_servers.get("knowledge", set())),
                "mcp_grounded_sessions": self._counted_grounded_sessions(),
                "mcp_write_sessions": self._counted_write_sessions(),
                "mcp_grounded_session_names": sorted(self.grounded_sessions),
                "mcp_subcategory_breakdown": {
                    cat: {"calls": self.mcp_subcategory_counter[cat],
                          "servers": len(self.mcp_subcategory_servers[cat])}
                    for cat in sorted(set(self.mcp_subcategory_counter))
                },
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
                # Disclosure of the actual [since, until) bound git_churn ran over,
                # after intersecting the requested window with the observed corpus
                # span (design decision D) -- None for an empty corpus.
                "git_churn_basis": [gc_since, gc_until],
            },
            "behavior": {
                "planning_ratio_explore_to_doing": round(planning_ratio, 2),
                "explore_actions": explore,
                "produce_actions": produce,
                "execute_actions": execute,
                "delegate_actions": delegate,
                # Published so the ratio reconciles against its own components in the
                # report (explore vs produce+execute+delegate MINUS this) and so the
                # subtraction is auditable rather than invisible.
                "planning_dispatch_actions": self.planning_dispatch_calls,
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
                "max_session_fanout": max_session_fanout,
                "parallel_dispatch_turns": self.parallel_dispatch_turns,
                "delegating_sessions": delegating_sessions,
                "parallel_session_share": parallel_session_share,
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
                **self._planning_skill_fields(
                    self._counted_planning_skill_sessions(),
                    len(self.planning_skill_eligible_sessions),
                    self._counted_planning_skill_unmeasured_sessions()),
                "eligible_change_sessions": _eligible,
                "test_covered_change_sessions": _test_covered,
                "planned_eligible_sessions": _planned,
                "evidence_eligible_sessions": _evidence,
                "orchestratable_sessions": _orchestratable,
                "delegated_orchestratable_sessions": _delegated_orchestratable,
                "ordered_facts_state": ("measured" if self.tool_use_total
                                        and self.ordered_facts_complete else "unmeasured"),
                # A combined ratio is unmeasured when observed delegation lacks labels.
                "sidechain_label_state": ("unmeasured"
                                          if self.unlabelled_delegate_dispatches
                                          else "measured"),
                "linked_model_pairs": _routing_pairs,
                "linked_model_routing_state": _routing_state,
                "no_tool_activity": no_tool_activity,
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
                "top_skills": self.skill_counter.most_common(100),
                "skills_distinct": len(self.skill_counter),
                "skills_total": sum(self.skill_counter.values()),
                "model_signal_missing": (
                    self.assistant_turns > 0 and not self.model_counter),
                "subagent_types_distinct": len(self.subagent_counter),
                "max_session_subagent_types": max(
                    (len(v) for v in self.session_subagent_types.values()), default=0),
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
        stats["monthly_noticed_stats"] = self.to_monthly_noticed_stats()

        # ---- per-month FULL stats slices (for scoring_inputs_by_source monthly) --
        stats["_scoring_monthly_full"] = self.to_monthly(planning_ratio, no_tool_activity, all_sources_no_agent)
        return stats

    def to_monthly_noticed_stats(self):
        """Per-calendar-month `noticed_stats` evidence, WITHOUT the rest of the corpus
        pipeline.

        `to_corpus_stats` calls this so there is one shaper and no drift, but a caller
        that wants only the monthly block must be able to get it without paying for a
        windowed `git_churn`, a `compute_aq` and a `to_monthly` it would discard. That
        caller is the self-heal accumulator in gnomon/cli/local.py: under the one-month
        scoring window the scored corpus produces a single monthly entry, which would end
        mirdash's per-calendar-month self-heal, so a second corpus-only accumulator reads
        a trailing multi-month window purely to reshape this block.

        The two null-honesty flags are recomputed here from the same expressions
        `to_corpus_stats` uses, so passing them in would only create a way for them to
        disagree.
        """
        self._flush_pending_skills()
        no_tool_activity = (self.tool_use_total == 0 and bool(self.source_sessions))
        all_sources_no_agent = bool(self.source_sessions) and (
            set(self.source_sessions.keys()) <= _AGENT_UNSUPPORTED_SOURCES
        )
        return _build_monthly_noticed_stats(
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
            month_skill_counter=self.month_skill_counter,
            month_mcp_server_counter=self.month_mcp_server_counter,
            month_session_ts=self.month_session_ts,
            no_tool_activity=no_tool_activity,
            all_sources_no_agent=all_sources_no_agent,
            cwds=self._git_cwds(),
            gap_cap_s=GAP_CAP_S,
            burst_gap_s=BURST_GAP_S,
            dow=DOW,
        )

    def to_monthly(self, planning_ratio, no_tool_activity, all_sources_no_agent):
        """Per-month full stats slices, shaped by the same builder for corpus and
        per-source so window AND month share one code path."""
        return build_monthly_scoring_stats(
            months=sorted(set(self.month_dates) | set(self.month_prompts) | set(self.month_tools)
                          | set(self.month_tokens) | set(self.month_sessions)
                          | set(self.month_command_only)),
            sources_present=sorted(self.source_files),
            month_prompts=self.month_prompts, month_tools_count=self.month_tools,
            month_sidechain_tools=self.month_sidechain_tools,
            month_command_only=self.month_command_only,
            month_churn=self.month_churn, month_models=self.month_models,
            month_sessions=self.month_sessions, month_assistant_turns=self.month_assistant_turns,
            month_thinking_blocks=self.month_thinking_blocks,
            month_bash_authored_lines=self.month_bash_authored_lines,
            month_tool_errors=self.month_tool_errors, month_recovered_errors=self.month_recovered_errors,
            month_edits_per_file=self.month_edits_per_file, month_questions=self.month_questions,
            month_delegate=self.month_delegate, month_background=self.month_background,
            month_scheduled=self.month_scheduled, month_fanouts=self.month_fanouts,
            month_session_subagent_types=self.month_session_subagent_types,
            month_tool_counter=self.month_tool_counter, month_session_ts=self.month_session_ts,
            month_skill_counter=self.month_skill_counter, month_subagent_counter=self.month_subagent_counter,
            month_mcp_server_counter=self.month_mcp_server_counter, month_cli_counter=self.month_cli_counter,
            month_mcp_subcategory_counter=self.month_mcp_subcategory_counter,
            month_mcp_subcategory_servers=self.month_mcp_subcategory_servers,
            month_grounded_sessions=self.month_grounded_sessions,
            month_write_sessions=self.month_write_sessions,
            month_session_ordered_tools=self.month_session_ordered_tools,
            month_planning_dispatch_calls=self.month_planning_dispatch_calls,
            month_compounding=self.month_compounding, month_shell_test_runs=self.month_shell_test_runs,
            month_plan_sessions=self.month_plan_sessions,
            month_planning_skill_sessions=self.month_planning_skill_sessions,
            month_planning_skill_eligible_sessions=self.month_planning_skill_eligible_sessions,
            month_planning_skill_unmeasured_sessions=(
                self.month_planning_skill_unmeasured_sessions),
            month_api_errors=self.month_api_errors,
            cwds=self._git_cwds(),
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
        self._flush_pending_skills()
        _s_tool_total = self.tool_use_total
        # C4: cross-session consume-once credit, scoped to this source's sessions.
        _s_agg = aggregate_ordered(self.session_ordered_tools.values())
        _s_eligible = _s_agg["eligible"]
        _s_test_covered = _s_agg["test_covered"]
        _s_orchestratable = _s_agg["orchestratable"]
        _s_orchestratable_sids = set()
        for (src, sid), facts in self.session_ordered_tools.items():
            d = derive_session_ordered_facts(facts)
            if d["orchestratable"]:
                _s_orchestratable_sids.add(sid)
        _s_delegated_orchestratable = sum(
            1 for sid in _s_orchestratable_sids
            if self.agents_per_session.get(sid, 0) > 0)
        _s_routing_pairs, _s_routing_state = self._routing_snapshot(src_name)
        _s_all_no_agent = src_name in _AGENT_UNSUPPORTED_SOURCES
        # Null-honesty per source: a source slice with sessions but zero tool calls
        # cannot measure tool-level metrics → None (not a real 0).
        _s_no_tool = (_s_tool_total == 0 and bool(self.source_sessions))

        _s_ids = _iteration_depth_stats(self.edits_per_file_events, _s_no_tool)
        _s_err_rate = _error_rate_per_100(self.tool_errors, _s_tool_total, _s_no_tool)
        _s_recov = _error_recovery_ratio(self.recovered_errors, self.tool_errors, _s_no_tool)
        _s_fanouts_list = [n for n in self.agents_per_session.values() if n > 0]
        _s_fan_med = _fanout_median(_s_fanouts_list, _s_no_tool, _s_all_no_agent)
        _s_max_fanout = max(_s_fanouts_list, default=0)
        _s_delegating_sessions = len(_s_fanouts_list)
        _s_parallel_delegating = sum(1 for n in _s_fanouts_list if n >= 2)
        _s_parallel_session_share = (
            round(_s_parallel_delegating / _s_delegating_sessions, 3)
            if _s_delegating_sessions else 0.0)
        _s_active_hours, _ = _active_hours_and_longest_run(
            self.session_ts, GAP_CAP_S, BURST_GAP_S)

        _s_total_churn = self.lines_added + self.lines_removed
        _s_prompts = self.prompts_count
        # Match the corpus numerator and denominator so a single-source corpus has one reading.
        _s_top_level = _s_tool_total - self.sidechain_tool_use_total
        _s_instructions = _s_prompts + self.command_only_prompts
        _s_actions_per_prompt = (
            round(_s_top_level / _s_instructions, 1) if _s_instructions else 0)

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
        # Mirrors the corpus path above, including the empty-denominator fallback.
        _s_doing = _adjusted_doing(
            _s_produce + _s_execute + _s_cats.get("delegate", 0),
            self.planning_dispatch_calls)
        _s_planning_ratio = round((_s_explore / _s_doing) if _s_doing else 0, 2)

        # Source-local git window: same intersection formula as to_corpus_stats
        # (design decision D), scoped to this source's own observed span.
        _s_gc, _s_gc_since, _s_gc_until = self._scoped_git_churn(since_dt, until_dt)
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
                "total_instructions": _s_instructions,
                "tool_calls_total": _s_tool_total,
                "sidechain_tool_calls": self.sidechain_tool_use_total,
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
                "max_session_fanout": _s_max_fanout,
                "parallel_dispatch_turns": self.parallel_dispatch_turns,
                "delegating_sessions": _s_delegating_sessions,
                "parallel_session_share": _s_parallel_session_share,
                "shell_test_runs": self.shell_test_runs,
                "plan_sessions": self._counted_plan_sessions(),
                **self._planning_skill_fields(
                    self._counted_planning_skill_sessions(),
                    len(self.planning_skill_eligible_sessions),
                    self._counted_planning_skill_unmeasured_sessions()),
                "eligible_change_sessions": _s_eligible,
                "test_covered_change_sessions": _s_test_covered,
                "planned_eligible_sessions": _s_agg["planned"],
                "evidence_eligible_sessions": _s_agg["evidence"],
                "orchestratable_sessions": _s_orchestratable,
                "delegated_orchestratable_sessions": _s_delegated_orchestratable,
                "ordered_facts_state": ("measured" if _s_tool_total
                                        and self.ordered_facts_complete else "unmeasured"),
                # A source slice is unmeasured when its observed delegation lacks labels.
                "sidechain_label_state": ("unmeasured"
                                          if self.unlabelled_delegate_dispatches
                                          else "measured"),
                "linked_model_pairs": _s_routing_pairs,
                "linked_model_routing_state": _s_routing_state,
                "delegate_actions": _s_cats.get("delegate", 0),
                "planning_dispatch_actions": self.planning_dispatch_calls,
                "background_tasks": self.background_tasks,
                "scheduled_actions": self.scheduled_actions,
                "iteration_depth_mean": (round(_s_ids["mean"], 2)
                                         if _s_ids["mean"] is not None else None),
                "iteration_depth_median": (round(_s_ids["median"], 2)
                                           if _s_ids["median"] is not None else None),
                "iteration_depth_p90": _s_ids["p90"],
                "iteration_depth_max": _s_ids["max"],
                "files_hammered_over_15x": _s_ids["heavy_files"],
                "no_tool_activity": _s_no_tool,
            },
            "tools": {
                "tool_diversity": _s_diversity,
                "tool_entropy_normalized": round(_s_norm_entropy, 3),
                "mcp_calls": self.mcp_calls,
                "native_calls": self.native_calls,
                "top_tools": _s_tc.most_common(100),
                "mcp_servers_distinct": len(self.mcp_server_counter),
                "mcp_knowledge_calls": self.mcp_subcategory_counter.get("knowledge", 0),
                "mcp_knowledge_servers": len(self.mcp_subcategory_servers.get("knowledge", set())),
                "mcp_knowledge_server_names": sorted(self.mcp_subcategory_servers.get("knowledge", set())),
                "mcp_grounded_sessions": self._counted_grounded_sessions(),
                "mcp_write_sessions": self._counted_write_sessions(),
                "mcp_grounded_session_names": sorted(self.grounded_sessions),
                "mcp_subcategory_breakdown": {
                    cat: {"calls": self.mcp_subcategory_counter[cat],
                          "servers": len(self.mcp_subcategory_servers[cat])}
                    for cat in sorted(set(self.mcp_subcategory_counter))
                },
                "top_mcp_servers": self.mcp_server_counter.most_common(100),
                "clis_distinct": len(self.cli_counter),
                "cli_calls": sum(self.cli_counter.values()),
                "toolsearch_calls": _s_tc.get("ToolSearch", 0),
                "task_tool_calls": (_s_tc.get("TaskCreate", 0)
                                    + _s_tc.get("TaskUpdate", 0)),
                "agent_calls": _s_tc.get("Agent", 0),
            },
            "stack": {
                "models": self.model_counter.most_common(),
                "top_skills": self.skill_counter.most_common(100),
                "skills_all": self.skill_counter.most_common(200),
                "skills_distinct": len(self.skill_counter),
                "skills_total": sum(self.skill_counter.values()),
                "subagent_types_distinct": len(self.subagent_counter),
                "max_session_subagent_types": max(
                    (len(v) for v in self.session_subagent_types.values()), default=0),
                "subagent_types": self.subagent_counter.most_common(10),
                "compounding_writes": self.compounding_counter,
            },
            "token_usage": _token_usage_block(dict(self.model_tokens)),
            "agentic": {},
        }
        s_stats["_scoring_monthly_full"] = self.to_monthly(
            _s_planning_ratio, _s_no_tool, _s_all_no_agent)
        return s_stats
_WRITE_TOOLS_V5 = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
_EVIDENCE_TOOLS_V5 = {"Read", "Grep", "Glob", "NotebookRead"}


def _normalized_ordered_target(event):
    target = str(event.get("target") or "")
    if not target:
        return ""
    cwd = str(event.get("cwd") or "")
    if cwd and not os.path.isabs(target):
        target = os.path.join(cwd, target)
    return os.path.normpath(target)


def derive_session_ordered_facts(events):
    """Rich per-session ordered-planning facts (ordered-planning redesign C2/C3/C6).

    Facts are expected to already carry the C1 enrichment (file_class/loc/
    plan_file/plan_skill) from accumulator.py's per-write construction; raw
    facts missing that enrichment are handled by derive_ordered_behavior's
    back-compat fallback, not here.

    C2 — eligible iff there is at least one CODE write AND (>=2 distinct code
    files, OR code_churn >= CHURN_MIN, OR substantive >= 10). Doc/config/
    lockfile/test-only sessions are excluded; mixed code+test stays eligible
    via the code files.

    C3/C6 — "planned" signals (plan-file write, >=PLAN_MIN_STEPS todo/task
    steps, or a planning-skill accompanied by a plan-file) are only evaluated
    BEFORE the first CODE write (not just any write — a doc/test write must
    not close the planning window), and only count if they clear the C6
    substance floor. A plan-file write with unmeasurable `loc` (None) still
    counts (ceremony fallback); a short plan-file with no accompanying
    planning-skill does not.

    Returns eligible/planned_intra/evidence plus first_write_order/cwd and
    plan_artifacts — the latter two feed aggregate_ordered's cross-session
    consume-once credit (C4), which is NOT applied here (this function is
    single-session only)."""
    events = sorted(
        enumerate(events or []),
        key=lambda item: (
            item[1].get("order", float("inf")),
            item[1].get("ordinal", item[0]),
        ),
    )
    events = [event for _, event in events]

    code_written, substantive, orchestration_substantive, seen_reads = set(), 0, 0, set()
    code_churn = 0
    first_code_write = None
    first_write_order = None
    first_write_cwd = None
    evidence_before = False
    actionable_plan_steps = set()
    todo_threshold_hit = None       # (cwd, order) once >=PLAN_MIN_STEPS is first reached
    plan_file_events = []           # (cwd, order, loc) for plan-file writes before the cutoff
    saw_plan_skill = False
    ran_test = False                # v18: any shell-test Bash fact in this session

    for index, event in enumerate(events):
        name = str(event.get("name") or "")
        if event.get("runs_tests"):
            ran_test = True
        target = _normalized_ordered_target(event)
        is_write = name in _WRITE_TOOLS_V5
        file_class = event.get("file_class")
        if is_write and file_class == "code":
            if first_code_write is None:
                first_code_write = index
                first_write_order = event.get("order")
                first_write_cwd = event.get("cwd")
            if target:
                code_written.add(target)
            loc = event.get("loc")
            if loc:
                code_churn += loc
        if is_substantive_tool(name):
            if name in _EVIDENCE_TOOLS_V5:
                key = target
                if key not in seen_reads:
                    substantive += 1
                    orchestration_substantive += 1
                    seen_reads.add(key)
            else:
                substantive += 1
                if classify_tool(name) != "delegate":
                    orchestration_substantive += 1
        if first_code_write is None:
            items = event.get("items") or []
            if name in {"TodoWrite", "TaskCreate"}:
                before_n = len(actionable_plan_steps)
                actionable_plan_steps.update(
                    str(item).strip() for item in items if str(item).strip())
                if (before_n < PLAN_MIN_STEPS <= len(actionable_plan_steps)
                        and todo_threshold_hit is None):
                    todo_threshold_hit = (event.get("cwd"), event.get("order"))
            if is_write and event.get("plan_file"):
                plan_file_events.append(
                    (event.get("cwd"), event.get("order"), event.get("loc")))
            if event.get("plan_skill"):
                saw_plan_skill = True
            if name in _EVIDENCE_TOOLS_V5 or event.get("knowledge"):
                evidence_before = True

    eligible = bool(code_written) and (
        len(code_written) >= 2 or code_churn >= CHURN_MIN or substantive >= 10)
    orchestratable = bool(code_written) and (
        len(code_written) >= ORCHESTRATABLE_CODE_FILES
        or orchestration_substantive >= ORCHESTRATABLE_SUBSTANTIVE)

    plan_artifacts = []
    planned_intra = False
    if todo_threshold_hit is not None:
        planned_intra = True
        plan_artifacts.append(todo_threshold_hit)
    for cwd, order, loc in plan_file_events:
        substantive_plan_file = loc is None or loc >= PLAN_MIN_LINES or saw_plan_skill
        if substantive_plan_file:
            planned_intra = True
            plan_artifacts.append((cwd, order))

    # A planning-skill invocation before the first code write is itself the
    # planning act and counts on its own, even without a plan-file. It does NOT
    # become a shared plan_artifact, so cross-session (C4) credit is unchanged.
    if saw_plan_skill:
        planned_intra = True

    return {
        "eligible": eligible,
        "orchestratable": orchestratable,
        "planned_intra": planned_intra,
        "evidence": eligible and evidence_before,
        "ran_test": ran_test,
        "first_write_order": first_write_order,
        "cwd": first_write_cwd,
        "plan_artifacts": plan_artifacts,
    }


def derive_ordered_behavior(events):
    """Thin back-compat wrapper around derive_session_ordered_facts (single
    session, no cross-session credit — see aggregate_ordered for C4). Callers
    that pass raw facts predating the C1 enrichment (missing file_class) get
    a classify_change_target(target) fallback so eligibility keeps working;
    already-enriched facts pass through unchanged."""
    enriched = []
    for event in events or []:
        if "file_class" in event:
            enriched.append(event)
        else:
            fallback = dict(event)
            fallback["file_class"] = classify_change_target(fallback.get("target") or "")
            fallback.setdefault("loc", None)
            fallback.setdefault("plan_file", False)
            fallback.setdefault("plan_skill", False)
            enriched.append(fallback)
    facts = derive_session_ordered_facts(enriched)
    return {
        "eligible": facts["eligible"],
        "planned": facts["eligible"] and facts["planned_intra"],
        "evidence": facts["evidence"],
    }


def aggregate_ordered(sessions):
    """C4 — cross-session consume-once plan credit. `sessions` is an iterable
    of per-session ordered-fact lists (values of session_ordered_tools, or a
    single month's bucket of the same shape). Each session is derived via
    derive_session_ordered_facts; an eligible, not-yet-planned session's first
    CODE write then consumes the earliest still-unconsumed plan artifact from
    the SAME cwd within [T - WINDOW, T]. Executions are matched in ascending
    first-code-write order so the earliest execution gets first claim on a
    shared artifact (one plan credits exactly one execution)."""
    derived = [derive_session_ordered_facts(facts) for facts in sessions]

    artifacts = []
    for d in derived:
        own = [{"cwd": cwd, "order": order, "consumed": False}
               for cwd, order in d["plan_artifacts"]]
        artifacts.extend(own)
        if d["eligible"] and d["planned_intra"] and own:
            min(own, key=lambda a: (a["order"] is None, a["order"]))["consumed"] = True

    pending = [d for d in derived
               if d["eligible"] and not d["planned_intra"]
               and d["first_write_order"] is not None]
    pending.sort(key=lambda d: d["first_write_order"])
    for d in pending:
        t = d["first_write_order"]
        cwd = d["cwd"]
        candidates = [
            a for a in artifacts
            if not a["consumed"] and a["cwd"] == cwd and a["order"] is not None
            and t - WINDOW <= a["order"] <= t
        ]
        if candidates:
            chosen = min(candidates, key=lambda a: a["order"])
            chosen["consumed"] = True
            d["planned_final"] = True

    eligible = sum(1 for d in derived if d["eligible"])
    planned = sum(1 for d in derived
                  if d["eligible"] and (d["planned_intra"] or d.get("planned_final")))
    evidence = sum(1 for d in derived if d["evidence"])
    orchestratable = sum(1 for d in derived if d.get("orchestratable"))
    # v18 — Verification coverage numerator: eligible change-sessions that also ran a
    # shell test, computed HERE beside `eligible` so the coverage ratio shares the exact
    # same eligibility population (no duplicated eligibility logic downstream).
    test_covered = sum(1 for d in derived if d["eligible"] and d.get("ran_test"))
    return {"eligible": eligible, "planned": planned, "evidence": evidence,
            "orchestratable": orchestratable, "test_covered": test_covered}
