#!/usr/bin/env python3
"""Local analysis engine (formerly paxel.py's main function)."""

import contextlib
import json
import math
import os
import re
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from gnomon.config import BASE, OUT_DIR, parse_ts, line_count, strip_injections, pctile, _open_in_browser
from gnomon.taxonomy import (
    WRITE_TOOLS, READ_TOOLS, DISCOVER_TOOLS, EXEC_TOOLS, DELEGATE_TOOLS,
    PLAN_TOOLS, SCHEDULE_TOOLS, SKILL_TOOLS, ASK_TOOLS,
    classify_tool, bash_writes_file, bash_runs_tests, _extract_clis,
    _is_compounding_path, _COMPOUNDING_RX, _SKILL_MD_RX,
)
from gnomon.sources import iter_events
from gnomon.sources.discovery import (
    ALL_SOURCES, _AGENT_UNSUPPORTED_SOURCES, _DIR_FLAGS,
    discover_sources, parse_window, _resolve_source_dir,
)
from gnomon.sources.cursor import _cursor_dedup
from gnomon.sources.antigravity import antigravity_summary
from gnomon.analysis.churn import git_churn
from gnomon.analysis.metrics import (
    _error_rate_per_100, _error_recovery_ratio, _iteration_depth_stats,
    _fanout_median, _peak_hours, _preferred_days, _active_hours_and_longest_run,
    _token_usage_block, _usage_int,
)
from gnomon.analysis.quotes import _POLITE_RE, _safe_quote, _cryptic_score, _crashout_score, _RAGE_RE, _FILLER
from gnomon.scoring.gstack import compute_scores
from gnomon.scoring.aq import compute_aq
from gnomon.scoring.archetype import pick_archetype
from gnomon.output.summary import (
    build_summary, _build_monthly_noticed_stats, _build_monthly_scoring_stats,
)
from gnomon.output.report import write_report
from gnomon.output.narrative import write_narrative_input
from gnomon.output.profile_html import write_profile_html


def main(argv=None, output_dir=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
        sys.stderr.reconfigure(errors="replace")

    if argv is None:
        argv = sys.argv[1:]

    if output_dir:
        _out_dir = os.path.abspath(os.path.expanduser(output_dir))
        os.makedirs(_out_dir, exist_ok=True)
    else:
        _out_dir = OUT_DIR

    # Sources to analyze: pass names as args (e.g. `python3 paxel.py claude`) to
    # restrict; default is every detected source. ("claude" keeps it to your own
    # Claude Code work; omit args to fold in Codex + Gemini too.)
    selected = [a.lower() for a in argv if not a.startswith("-")] or list(ALL_SOURCES)
    unknown = [s for s in selected if s not in ALL_SOURCES]
    if unknown:
        print(f"  warning: unknown source(s) {unknown} ignored; valid: {', '.join(ALL_SOURCES)}")
    # --<source>-dir=PATH overrides for sandbox / self-hosted / copied histories
    # (e.g. --claude-dir=/mnt/sandbox-home/.claude). Env vars CLAUDE_CONFIG_DIR and
    # CODEX_HOME are honored too (applied at import; flags win).
    import gnomon.sources.discovery as _disc
    import gnomon.config as _cfg
    for a in argv:
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
        setattr(_disc, gname, resolved)
        if gname == "BASE":
            setattr(_cfg, 'BASE', resolved)
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
    since_dt, until_dt = parse_window(argv)
    if since_dt or until_dt:
        print(f"  window: {since_dt.date() if since_dt else '...'} -> "
              f"{(until_dt - timedelta(days=1)).date() if until_dt else 'now'}")
    sources, cursor_twins = _cursor_dedup(sources)
    antigravity = antigravity_summary()
    if antigravity:
        print(f"  note: Google Antigravity detected -- {antigravity['conversations']} conversations "
              f"(metadata only; transcripts live server-side, so it can't be scored)")
    if not sources:
        print("\n  No transcripts found in ~/.claude/projects, ~/.codex/sessions, "
              "~/.gemini/tmp, ~/.pi/agent/sessions, ~/.local/share/opencode/storage, "
              "or ~/.cursor/projects.")
        print("  Nothing to analyze -- run this where you've actually used a coding agent.")
        return

    # Whole-corpus accumulation (all sources pooled, capabilities = union) — this is
    # the legacy/primary stats dict that drives the report, HTML and `profile`.
    stats, narrative = _accumulate(
        sources, since_dt, until_dt, cursor_twins, antigravity,
        total_file_count=len(sources), verbose=True)
    opening_prompts = narrative["opening_prompts"]
    longest_prompts = narrative["longest_prompts"]
    phrase_counts = narrative["phrase_counts"]
    phrase_repr = narrative["phrase_repr"]
    phrase_sess = narrative["phrase_sess"]
    cryptic_cands = narrative["cryptic_cands"]
    crashout_cands = narrative["crashout_cands"]
    total_sessions = stats["volume"]["total_sessions"]
    prompts_count = stats["volume"]["total_prompts"]
    tool_use_total = stats["volume"]["tool_calls_total"]
    gc = narrative["gc"]
    total_churn = stats["velocity"]["tool_churn_edit_write"]
    git_velocity = stats["velocity"]["git_velocity_lines_per_hour"]
    iteration_mean = stats["behavior"]["iteration_depth_mean"]
    iteration_max = stats["behavior"]["iteration_depth_max"]
    heavy_files = stats["behavior"]["files_hammered_over_15x"]
    error_rate_per_100_tools = stats["behavior"]["error_rate_per_100_tools"]
    tool_errors = stats["behavior"]["tool_errors"]
    autonomy_score = stats["autonomy"]["autonomy_score_0_100"]
    planning_ratio = stats["behavior"]["planning_ratio_explore_to_doing"]
    source_files = narrative["source_files"]
    source_sessions = narrative["source_sessions"]

    # ---- per-source scoring inputs (recomputable per-source AND combined) ----
    # Partition the event stream by source and run the SAME _accumulate per source,
    # so each source's stats slice carries only that source's events (and only that
    # source's caps, cwds for git churn, cursor dedup partition, etc.). The window +
    # per-month raw inputs for every source feed scoring_inputs_by_source.
    stats["scoring_inputs_version"] = SCORING_INPUTS_VERSION
    stats["scoring_inputs_by_source"] = _build_scoring_inputs_by_source(
        sources, since_dt, until_dt, cursor_twins, antigravity,
        corpus_stats=stats)
    # internal-only working field (per-month full stats slices); not part of the payload
    stats.pop("_scoring_monthly_full", None)

    with open(os.path.join(_out_dir, "stats.json"), "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, default=str)

    if "--summary" in argv:
        with open(os.path.join(_out_dir, "summary.json"), "w", encoding="utf-8") as f:
            json.dump(build_summary(stats), f, indent=2, default=str)
        print("  wrote summary.json (shareable subset -- measured metrics + monthly progression)")

    write_report(stats, output_dir=_out_dir)
    write_narrative_input(stats, opening_prompts, longest_prompts, output_dir=_out_dir)
    scores = compute_scores(stats)
    archetype, quote = pick_archetype(stats, scores)
    # "In your own words" — pick the go-to phrase (most-repeated short prompt seen in >=2
    # sessions), most cryptic, biggest crash-out. VERBATIM, never stored in stats.json.
    goto = None
    for ph, cnt in phrase_counts.most_common(25):
        if cnt >= 3 and len(phrase_sess.get(ph, ())) >= 2:
            goto = (phrase_repr[ph], cnt, len(phrase_sess[ph]))
            break
    def _dedup_rank(cands):   # keep highest score per unique prompt, ranked (deterministic)
        best = {}
        for sc, tx in cands:
            k = tx.lower()
            if k not in best or sc > best[k][0]:
                best[k] = (sc, tx)
        return sorted(best.values(), key=lambda x: (-x[0], x[1]))   # tie-break on text -> reproducible
    cryptic_cands = _dedup_rank(cryptic_cands)
    crashout_cands = _dedup_rank(crashout_cands)
    # Each card shows the SINGLE best quote; a reroll button rerolls through this small pool
    # (top few within striking distance of #1 — quality only, no weak tail).
    def _quote_pool(cands, n=6, floor=0.5):
        if not cands:
            return []
        top = cands[0][0]
        return [tx for sc, tx in cands if sc >= top * floor][:n]
    rage_pool = _quote_pool([(sc, tx) for sc, tx in crashout_cands if len(tx.split()) <= 9])
    cuff_pool = _quote_pool(cryptic_cands)
    voice = {"goto": goto, "crashouts": rage_pool, "cryptics": cuff_pool}
    write_profile_html(stats, archetype, quote, scores, voice, output_dir=_out_dir)
    print("\nWrote stats.json, report.md, narrative_input.md, profile.html to", _out_dir)
    if "--no-open" not in argv:
        _open_in_browser(os.path.join(_out_dir, "profile.html"))
    print(f"  archetype: {archetype}  scores: {scores}")
    print(f"  sources: " + ", ".join(f"{s}({source_files[s]}f/{len(source_sessions[s])}s)"
                                      for s in sorted(source_files)))
    print(f"  sessions={total_sessions}  prompts={prompts_count}  tool_calls={tool_use_total}")
    print(f"  git churn={gc['churn']:,} lines (gold std, {gc['repos_with_commits']}/{gc['repos_seen']} repos)  "
          f"vs tool-only={total_churn:,}  git velocity={git_velocity:.0f} ln/hr")
    _idm_str = f"{iteration_mean:.1f}" if iteration_mean is not None else "-"
    _erp_str = f"{error_rate_per_100_tools:.1f}" if error_rate_per_100_tools is not None else "-"
    print(f"  iteration depth: mean {_idm_str} / max {iteration_max} ({heavy_files} files >15x)  "
          f"errors={tool_errors} ({_erp_str}/100 tools)")
    print(f"  autonomy={autonomy_score}/100  planning_ratio={planning_ratio:.2f}")


SCORING_INPUTS_VERSION = 1


def _build_scoring_inputs_by_source(sources, since_dt, until_dt, cursor_twins,
                                    antigravity, corpus_stats=None):
    """Run _accumulate once PER SOURCE (events partitioned by cur_src) and shape each
    source's window + per-month stats into the raw scoring-input field set. Returns
    {"<source>": {"window": {...}, "monthly": [{"month": "YYYY-MM", ...}, ...]}, ...}.

    Partitioning by source means each slice naturally carries only that source's caps,
    its own cwds for git churn, its own cursor GUI+CLI dedup partition, and its own
    active_hours / fanout / iteration_depth (all derived inside _accumulate from that
    source's session_ts / edits_per_file / fanouts).

    Fast path: when only ONE source is present, the whole-corpus stats already IS that
    source's slice (same events, same caps, same cwds), so we reuse `corpus_stats` and
    skip the redundant re-parse + re-churn."""
    from gnomon.output.summary import _build_scoring_inputs
    by_source = {}
    srcs_present = sorted({s for s, _, _ in sources})
    single_source = corpus_stats is not None and len(srcs_present) == 1
    for src in srcs_present:
        if single_source:
            s_stats = corpus_stats
        else:
            src_sources = [(s, fp, fmt) for (s, fp, fmt) in sources if s == src]
            s_stats, _ = _accumulate(
                src_sources, since_dt, until_dt, cursor_twins, antigravity,
                total_file_count=len(src_sources), verbose=False)
        window = _build_scoring_inputs(s_stats)
        monthly = [
            dict(_build_scoring_inputs(entry["stats_full"]), month=entry["month"])
            for entry in s_stats.get("_scoring_monthly_full", [])
        ]
        by_source[src] = {"window": window, "monthly": monthly}
    return by_source


def _accumulate(sources, since_dt, until_dt, cursor_twins, antigravity,
                total_file_count=None, verbose=True):
    """Accumulate every per-event signal over `sources` and return (stats, narrative).

    This is the single aggregation engine. main() calls it once over ALL sources
    (legacy whole-corpus stats), and _build_scoring_inputs_by_source calls it once per
    source partition. Because the SAME function runs for both, a per-source slice uses
    identical aggregation rules (no drift) and naturally scopes git churn (to that
    source's cwds), cursor dedup (within the cursor partition), and the post-processed
    active_hours / fanout_median / iteration_depth (derived from that slice's session_ts
    / edits_per_file / fanouts).

    `narrative` carries the verbatim-quote candidates and opening/longest prompts that
    main() needs for the local HTML page (never serialized into stats.json)."""
    if total_file_count is None:
        total_file_count = len(sources)
    # ---- accumulators --------------------------------------------------------
    files_parsed = 0
    lines_total = 0
    lines_bad = 0

    session_ts = defaultdict(list)   # sessionId -> [epoch seconds]
    session_files = defaultdict(set)
    GAP_CAP_S = 600                   # cap idle gaps at 10 min when summing active time

    prompts_count = 0
    polite_prompts = 0         # prompts that say please / thanks / etc.
    prompt_lengths = []        # chars of genuine typed prompts
    # "In your own words" cards — pulled VERBATIM from real prompts (local page only,
    # never the shared image). go-to phrase / most cryptic / biggest crash-out.
    phrase_counts = Counter()      # normalized short prompt -> times seen
    phrase_repr = {}               # normalized -> first original spelling
    phrase_sess = defaultdict(set) # normalized -> session ids it appeared in
    cryptic_cands = []             # [(score, verbatim text)] — ranked at the end
    crashout_cands = []            # [(score, verbatim text)]
    command_invocations = 0

    assistant_turns = 0
    text_blocks = 0
    thinking_blocks = 0
    thinking_chars = 0
    tool_use_total = 0
    tool_counter = Counter()
    cat_counter = Counter()    # explore/produce/execute/delegate/ask/other
    mcp_calls = 0
    native_calls = 0

    model_counter = Counter()
    skill_counter = Counter()
    subagent_counter = Counter()
    agents_per_session = defaultdict(int)   # sessionId -> Agent dispatches (for fan-out / coordination)
    mcp_server_counter = Counter()   # mcp server name -> calls
    cli_counter = Counter()          # known CLI head -> calls (from Bash commands)
    compounding_counter = 0   # writes to CLAUDE.md/AGENTS.md/memory/docs/adr
    project_activity = Counter()   # cwd -> events
    project_sessions = defaultdict(set)

    lines_added = 0
    lines_removed = 0
    edits_per_file_events = []      # iteration depth samples (edits to a file before commit)
    git_commits = 0
    background_tasks = 0
    scheduled_actions = 0
    questions_asked = 0

    tool_errors = 0
    api_errors = 0
    recovered_errors = 0

    bash_write_calls = 0       # Bash calls that write/modify a file
    bash_authored_lines = 0    # newlines inside those commands (shell-authored content estimate)
    shell_test_runs = 0        # Bash calls that run a test suite (pytest/go test/npm test/...) — CLI TDD

    hour_hist = Counter()          # local hour 0-23
    weekday_hist = Counter()       # 0=Mon..6=Sun
    date_set = set()
    all_min_dt = None
    all_max_dt = None

    # monthly progression ("YYYY-MM" buckets) — month-over-month evolution matters more
    # than lifetime totals when plan limits cap any single month's volume
    month_prompts = Counter()
    month_tools = Counter()
    month_churn = Counter()              # Edit/Write tool-authored line churn
    month_dates = defaultdict(set)       # month -> active ISO dates
    month_sessions = defaultdict(set)    # month -> sessionIds seen
    month_models = defaultdict(Counter)  # month -> model -> assistant turns

    # GA1: month-keyed counterparts for everything monthly_noticed_stats needs,
    # mirroring each window accumulator at its increment site.
    month_assistant_turns = Counter()        # month -> assistant turns
    month_thinking_blocks = Counter()        # month -> thinking blocks
    month_prompt_lengths = defaultdict(list) # month -> [prompt char lengths]
    month_bash_write_calls = Counter()       # month -> Bash file-write calls
    month_bash_authored_lines = Counter()    # month -> shell-authored line est
    month_tool_errors = Counter()            # month -> tool_result is_error count
    month_recovered_errors = Counter()       # month -> error-recovery tool uses
    month_edits_per_file = defaultdict(list) # month -> iteration-depth samples
    month_polite = Counter()                 # month -> polite prompts
    month_questions = Counter()              # month -> ASK_TOOLS calls
    month_delegate = Counter()               # month -> delegate-classified tool calls
    month_background = Counter()             # month -> run_in_background tool calls
    month_scheduled = Counter()              # month -> SCHEDULE_TOOLS calls
    month_fanouts = defaultdict(lambda: defaultdict(int))  # month -> session -> agent dispatches
    month_hour_hist = defaultdict(Counter)   # month -> local hour -> events
    month_weekday_hist = defaultdict(Counter)  # month -> weekday(0-6) -> events
    month_tool_counter = defaultdict(Counter)  # month -> tool name -> calls
    month_session_ts = defaultdict(lambda: defaultdict(list))  # month -> session -> [epoch s]

    # Per-month stack/tool accumulators — needed so per-source × month scoring inputs
    # (_build_scoring_inputs) carry the full grading field set, not just noticed_stats.
    month_skill_counter = defaultdict(Counter)     # month -> skill name -> uses
    month_subagent_counter = defaultdict(Counter)  # month -> subagent type -> dispatches
    month_mcp_server_counter = defaultdict(Counter)  # month -> mcp server -> calls
    month_cli_counter = defaultdict(Counter)       # month -> CLI head -> calls
    month_compounding = Counter()                  # month -> compounding writes
    month_shell_test_runs = Counter()              # month -> CLI test runs
    month_api_errors = Counter()                   # month -> API error/retry events

    # token usage accumulators (keyed by raw model id)
    _zero_tok = lambda: {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0}
    model_tokens = defaultdict(_zero_tok)        # raw model id -> {input, output, cache_read, cache_creation}
    month_tokens = defaultdict(_zero_tok)        # month key -> {input, output, cache_read, cache_creation}
    # GA1: month -> raw model id -> tokens, so per-month token_usage carries a real
    # by_model split (same shape as the window stats['token_usage']).
    month_model_tokens = defaultdict(lambda: defaultdict(_zero_tok))

    # narrative samples
    opening_prompts = []           # (dt, project, text) first genuine prompt per session
    longest_prompts = []           # kept small via periodic trim

    seen_session_open = set()
    source_files = Counter()             # source -> files
    source_sessions = defaultdict(set)   # source -> sessionIds
    source_prompts = Counter()           # source -> genuine prompts

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
        files_parsed += 1
        source_files[cur_src] += 1
        if verbose and files_parsed % 300 == 0:
            print(f"  ...{files_parsed}/{total_file_count}")
        # per-session, per-file ordered state for error-recovery + iteration depth
        pending_error = defaultdict(bool)        # sessionId -> unrecovered error flag
        file_edit_run = defaultdict(lambda: defaultdict(int))  # session -> file -> edits since commit
        # GA1: month of the most recent edit per (session, file), so a flushed
        # iteration-depth run is attributed to the month it happened in.
        file_edit_month = defaultdict(dict)      # session -> file -> month key

        # iter_events() yields Claude-shaped event dicts for every source format,
        # so the per-event logic below is identical across all supported sources.
        with contextlib.nullcontext(
                iter_events(fp, fmt, cursor_twins=cursor_twins)) as _evs:
            _ev_list = list(_evs)
            # Codex emits ~37k empty "seed" sessions (only injected wrappers + a 2+2 probe).
            # If a codex file has no genuine human prompt after filtering, skip it entirely so
            # it doesn't inflate session counts and drag the scores.
            if fmt == "codex" and not any(
                e.get("type") == "user"
                and isinstance((e.get("message") or {}).get("content"), str)
                and (e.get("message") or {}).get("content", "").strip()
                for e in _ev_list
            ):
                source_files[cur_src] -= 1
                files_parsed -= 1
                continue
            for ev in _ev_list:
                if ev.get("__bad__"):
                    lines_bad += 1
                    continue
                lines_total += 1

                etype = ev.get("type")
                sid = ev.get("sessionId")
                cwd = ev.get("cwd")
                dt = parse_ts(ev.get("timestamp"))
                if (since_dt is not None or until_dt is not None) and (
                        dt is None                                   # undatable: can't
                        or (since_dt is not None and dt < since_dt)  # honor "this period
                        or (until_dt is not None and dt >= until_dt)):  # only" — drop
                    continue
                mkey = dt.strftime("%Y-%m") if dt is not None else None

                if dt is not None:
                    # Synthetic timestamps (Cursor JSONL events past the first, stamped with
                    # the file mtime) must reach the date window / month bucket so windowed
                    # runs count them, but must NOT distort the hour/weekday histograms or
                    # session-duration math with a pile of identical fake instants.
                    _synth_ts = ev.get("__synth_ts__")
                    if all_min_dt is None or dt < all_min_dt:
                        all_min_dt = dt
                    if all_max_dt is None or dt > all_max_dt:
                        all_max_dt = dt
                    if not _synth_ts:
                        hour_hist[dt.hour] += 1
                        weekday_hist[dt.weekday()] += 1
                        month_hour_hist[mkey][dt.hour] += 1
                        month_weekday_hist[mkey][dt.weekday()] += 1
                    date_set.add(dt.date().isoformat())
                    month_dates[mkey].add(dt.date().isoformat())
                    if sid:
                        if not _synth_ts:
                            session_ts[sid].append(dt.timestamp())
                            month_session_ts[mkey][sid].append(dt.timestamp())
                        month_sessions[mkey].add(sid)
                if sid:
                    session_files[sid].add(fp)
                    source_sessions[cur_src].add(sid)
                if cwd:
                    project_activity[cwd] += 1
                    if sid:
                        project_sessions[cwd].add(sid)

                msg = ev.get("message") if isinstance(ev.get("message"), dict) else None

                # ---- API error / retry events (system + assistant) ----------
                if ev.get("isApiErrorMessage") or ev.get("apiErrorStatus"):
                    api_errors += 1
                    if mkey:
                        month_api_errors[mkey] += 1
                if etype == "system" and ev.get("retryAttempt"):
                    api_errors += 1
                    if mkey:
                        month_api_errors[mkey] += 1

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
                                command_invocations += 1
                            elif cleaned:
                                prompts_count += 1
                                source_prompts[cur_src] += 1
                                if mkey:
                                    month_prompts[mkey] += 1
                                    month_prompt_lengths[mkey].append(len(cleaned))
                                prompt_lengths.append(len(cleaned))
                                if _POLITE_RE.search(cleaned):
                                    polite_prompts += 1
                                    if mkey:
                                        month_polite[mkey] += 1
                                # collect verbatim-quote candidates (short prompts only, and
                                # only if safe to surface — no secrets / no harness markers)
                                _wc = len(cleaned.split())
                                if _safe_quote(cleaned) and 1 <= _wc <= 6:
                                    _norm = re.sub(r"\s+", " ", cleaned.strip().lower()).strip("?.!,. ")
                                    if len(_norm) >= 2:
                                        phrase_counts[_norm] += 1
                                        phrase_repr.setdefault(_norm, cleaned.strip())
                                        phrase_sess[_norm].add(sid)
                                if _safe_quote(cleaned):
                                    if 3 <= _wc <= 14:
                                        _words = re.findall(r"[a-z']+", cleaned.lower())
                                        if _words and not all(w in _FILLER for w in _words):
                                            _csc = _cryptic_score(cleaned)
                                            if _csc >= 1.8:
                                                cryptic_cands.append((round(_csc, 2), cleaned.strip()))
                                    if sum(c.isalpha() for c in cleaned) >= 6 and _wc <= 16:
                                        _bangs = cleaned.count("!") + cleaned.count("?")
                                        # gate: must read NEGATIVE (frustration word or !!-level
                                        # punctuation) — caps alone is excitement, not a crash-out
                                        if _RAGE_RE.search(cleaned) or _bangs >= 2:
                                            _xsc = _crashout_score(cleaned, hour=dt.hour if dt else None)
                                            # daytime gate; at 2-6am the witching bonus (+1.8) in
                                            # _crashout_score lowers the effective bar (intended)
                                            if _xsc >= 2.0:
                                                crashout_cands.append((round(_xsc, 2), cleaned.strip()))
                                if is_command:
                                    command_invocations += 1
                                proj = os.path.basename(cwd) if cwd else "?"
                                if sid and sid not in seen_session_open:
                                    seen_session_open.add(sid)
                                    opening_prompts.append((dt, proj, cleaned[:600]))
                                longest_prompts.append((len(cleaned), proj, cleaned[:600]))
                                if len(longest_prompts) > 400:
                                    longest_prompts.sort(key=lambda x: -x[0])
                                    del longest_prompts[120:]

                    # ---- tool results inside user turns ---------------------
                    content = msg.get("content")
                    if isinstance(content, list):
                        for b in content:
                            if isinstance(b, dict) and b.get("type") == "tool_result":
                                if b.get("is_error"):
                                    tool_errors += 1
                                    if mkey:
                                        month_tool_errors[mkey] += 1
                                    if sid:
                                        pending_error[sid] = True

                # ---- assistant turns ---------------------------------------
                elif etype == "assistant" and msg is not None:
                    # Codex emits synthetic token-usage events as type="assistant" purely
                    # to carry per-(model,month) token totals. They are NOT real turns, so
                    # they must not bump assistant-turn or model-mix counters — only feed
                    # the token accumulators below.
                    _is_codex_usage = bool(ev.get("__codex_usage__"))
                    if not _is_codex_usage:
                        assistant_turns += 1
                        if mkey:
                            month_assistant_turns[mkey] += 1
                    mdl = msg.get("model")
                    if mdl:
                        if not _is_codex_usage:
                            model_counter[mdl] += 1
                            if mkey:
                                month_models[mkey][mdl] += 1
                        # ---- token usage extraction (fully defensive) -------
                        _u = msg.get("usage") or {}
                        _ti  = _usage_int(_u, "input_tokens")
                        _to  = _usage_int(_u, "output_tokens")
                        _tcr = _usage_int(_u, "cache_read_input_tokens")
                        _tcc = _usage_int(_u, "cache_creation_input_tokens")
                        model_tokens[mdl]["input"]          += _ti
                        model_tokens[mdl]["output"]         += _to
                        model_tokens[mdl]["cache_read"]     += _tcr
                        model_tokens[mdl]["cache_creation"] += _tcc
                        if mkey:
                            month_tokens[mkey]["input"]          += _ti
                            month_tokens[mkey]["output"]         += _to
                            month_tokens[mkey]["cache_read"]     += _tcr
                            month_tokens[mkey]["cache_creation"] += _tcc
                            month_model_tokens[mkey][mdl]["input"]          += _ti
                            month_model_tokens[mkey][mdl]["output"]         += _to
                            month_model_tokens[mkey][mdl]["cache_read"]     += _tcr
                            month_model_tokens[mkey][mdl]["cache_creation"] += _tcc
                    if ev.get("attributionSkill"):
                        skill_counter[ev["attributionSkill"]] += 1
                        if mkey:
                            month_skill_counter[mkey][ev["attributionSkill"]] += 1
                    content = msg.get("content")
                    if isinstance(content, list):
                        for b in content:
                            if not isinstance(b, dict):
                                continue
                            bt = b.get("type")
                            if bt == "text":
                                text_blocks += 1
                            elif bt == "thinking":
                                thinking_blocks += 1
                                if mkey:
                                    month_thinking_blocks[mkey] += 1
                                thinking_chars += len(b.get("thinking", "") or "")
                            elif bt == "tool_use":
                                name = b.get("name", "?")
                                inp = b.get("input", {}) if isinstance(b.get("input"), dict) else {}
                                tool_use_total += 1
                                tool_counter[name] += 1
                                _cat = classify_tool(name)
                                if mkey:
                                    month_tools[mkey] += 1
                                    month_tool_counter[mkey][name] += 1
                                    if _cat == "delegate":
                                        month_delegate[mkey] += 1
                                cat_counter[_cat] += 1
                                if name.startswith("mcp__"):
                                    mcp_calls += 1
                                    parts = name.split("__")
                                    if len(parts) > 1 and parts[1]:
                                        mcp_server_counter[parts[1]] += 1
                                        if mkey:
                                            month_mcp_server_counter[mkey][parts[1]] += 1
                                else:
                                    native_calls += 1

                                # a tool use after a pending error = recovery
                                if sid and pending_error.get(sid):
                                    recovered_errors += 1
                                    if mkey:
                                        month_recovered_errors[mkey] += 1
                                    pending_error[sid] = False

                                if name == "Skill":
                                    s = inp.get("skill")
                                    if s:
                                        skill_counter[s] += 1
                                        if mkey:
                                            month_skill_counter[mkey][s] += 1
                                if name == "Agent":
                                    st = inp.get("subagent_type", "general-purpose")
                                    subagent_counter[st] += 1
                                    if mkey:
                                        month_subagent_counter[mkey][st] += 1
                                    if sid:
                                        agents_per_session[sid] += 1
                                        if mkey:
                                            month_fanouts[mkey][sid] += 1
                                if name in ASK_TOOLS:
                                    questions_asked += 1
                                    if mkey:
                                        month_questions[mkey] += 1
                                if inp.get("run_in_background"):
                                    background_tasks += 1
                                    if mkey:
                                        month_background[mkey] += 1
                                if name in SCHEDULE_TOOLS:
                                    scheduled_actions += 1
                                    if mkey:
                                        month_scheduled[mkey] += 1

                                # ---- code churn + iteration depth ----------
                                if name == "Edit":
                                    a = line_count(inp.get("new_string", ""))
                                    r = line_count(inp.get("old_string", ""))
                                    lines_added += a
                                    lines_removed += r
                                    if mkey:
                                        month_churn[mkey] += a + r
                                    fpth = inp.get("file_path")
                                    if sid and fpth:
                                        file_edit_run[sid][fpth] += 1
                                        if mkey:
                                            file_edit_month[sid][fpth] = mkey
                                    if _is_compounding_path(fpth):
                                        compounding_counter += 1
                                        if mkey:
                                            month_compounding[mkey] += 1
                                elif name == "Write":
                                    a = line_count(inp.get("content", ""))
                                    lines_added += a
                                    if mkey:
                                        month_churn[mkey] += a
                                    fpth = inp.get("file_path")
                                    if sid and fpth:
                                        file_edit_run[sid][fpth] += 1
                                        if mkey:
                                            file_edit_month[sid][fpth] = mkey
                                    if _is_compounding_path(fpth):
                                        compounding_counter += 1
                                        if mkey:
                                            month_compounding[mkey] += 1
                                elif name == "MultiEdit":
                                    for e in inp.get("edits", []) or []:
                                        if isinstance(e, dict):
                                            _ea = line_count(e.get("new_string", ""))
                                            _er = line_count(e.get("old_string", ""))
                                            lines_added += _ea
                                            lines_removed += _er
                                            if mkey:
                                                month_churn[mkey] += _ea + _er
                                    fpth = inp.get("file_path")
                                    if sid and fpth:
                                        file_edit_run[sid][fpth] += 1
                                        if mkey:
                                            file_edit_month[sid][fpth] = mkey
                                    if _is_compounding_path(fpth):
                                        compounding_counter += 1
                                        if mkey:
                                            month_compounding[mkey] += 1
                                elif name == "NotebookEdit":
                                    lines_added += line_count(inp.get("new_source", ""))
                                    fpth = inp.get("notebook_path")
                                    if sid and fpth:
                                        file_edit_run[sid][fpth] += 1
                                        if mkey:
                                            file_edit_month[sid][fpth] = mkey
                                    if _is_compounding_path(fpth):
                                        compounding_counter += 1
                                        if mkey:
                                            month_compounding[mkey] += 1
                                elif name == "Bash":
                                    cmd = inp.get("command", "") or ""
                                    if isinstance(cmd, list):
                                        cmd = " && ".join(str(c) for c in cmd)
                                    for _cli in _extract_clis(cmd):
                                        cli_counter[_cli] += 1
                                        if mkey:
                                            month_cli_counter[mkey][_cli] += 1
                                    if cur_src != "claude":
                                        # Claude invokes skills via the Skill tool (counted
                                        # above); other CLIs read SKILL.md through the shell
                                        for _sm in _SKILL_MD_RX.finditer(cmd):
                                            skill_counter[_sm.group(1)] += 1
                                            if mkey:
                                                month_skill_counter[mkey][_sm.group(1)] += 1
                                    if bash_writes_file(cmd):
                                        bash_write_calls += 1
                                        bash_authored_lines += cmd.count("\n")
                                        if mkey:
                                            month_bash_write_calls[mkey] += 1
                                            month_bash_authored_lines[mkey] += cmd.count("\n")
                                    if bash_runs_tests(cmd):
                                        shell_test_runs += 1
                                        if mkey:
                                            month_shell_test_runs[mkey] += 1
                                    if "git commit" in cmd:
                                        git_commits += 1
                                        # flush iteration-depth run for this session
                                        if sid in file_edit_run:
                                            for _f, cnt in file_edit_run[sid].items():
                                                if cnt > 0:
                                                    edits_per_file_events.append(cnt)
                                                    _fm = file_edit_month.get(sid, {}).get(_f)
                                                    if _fm:
                                                        month_edits_per_file[_fm].append(cnt)
                                            file_edit_run[sid].clear()
                                            file_edit_month.get(sid, {}).clear()

        # end of file: flush any remaining edit runs as iteration-depth samples
        for _s, sdict in file_edit_run.items():
            for _f, cnt in sdict.items():
                if cnt > 0:
                    edits_per_file_events.append(cnt)
                    _fm = file_edit_month.get(_s, {}).get(_f)
                    if _fm:
                        month_edits_per_file[_fm].append(cnt)

    # ---- derive ----------------------------------------------------------------
    total_sessions = len(session_ts) or len(session_files)
    # Active time = sum of consecutive inter-event gaps, each capped at GAP_CAP_S,
    # so resumed-session reuse and overnight idle don't inflate engaged time.
    # Longest *contiguous* burst (no gap > 30 min). sessionId is reused across
    # resumed sessions, so a single id can span weeks — max(session duration) is
    # meaningless; the longest unbroken burst is the honest "longest run."
    BURST_GAP_S = 1800               # a gap > 30 min ends a contiguous work "run"
    durations_min = []
    for ts_list in session_ts.values():
        ts_list.sort()
        active_s = 0.0
        for a, bnext in zip(ts_list, ts_list[1:]):
            active_s += min(bnext - a, GAP_CAP_S)
        durations_min.append(active_s / 60.0)
    active_hours, longest_run_min = _active_hours_and_longest_run(
        session_ts, GAP_CAP_S, BURST_GAP_S)
    avg_session_min = statistics.mean(durations_min) if durations_min else 0
    median_session_min = statistics.median(durations_min) if durations_min else 0

    avg_prompt_len = statistics.mean(prompt_lengths) if prompt_lengths else 0
    median_prompt_len = statistics.median(prompt_lengths) if prompt_lengths else 0

    total_churn = lines_added + lines_removed          # tool-authored only (Edit/Write)
    code_velocity = (total_churn / active_hours) if active_hours > 0 else 0

    # Gold-standard churn: real git insertions/deletions, capturing EVERY committed
    # change however it was made (Edit, Bash heredoc, sed, vim...). 100% local.
    # When a date window is active, churn must cover the REQUESTED window — not just
    # the min/max of transcript activity that fell inside it.
    if since_dt is not None or until_dt is not None:
        gc_since = since_dt.strftime("%Y-%m-%d") if since_dt is not None else (all_min_dt.isoformat() if all_min_dt else "1970-01-01")
        # until_dt is already the exclusive next-midnight (parse_window added a day), so
        # passing it straight to git --until keeps the whole requested last day. Subtracting
        # a day here would drop every commit made on that final calendar day.
        gc_until = (until_dt.strftime("%Y-%m-%d")
                    if until_dt is not None else (all_max_dt.isoformat() if all_max_dt else "2100-01-01"))
    else:
        gc_since = all_min_dt.isoformat() if all_min_dt else "1970-01-01"
        gc_until = all_max_dt.isoformat() if all_max_dt else "2100-01-01"
    gc = git_churn(list(project_activity.keys()), gc_since, gc_until)
    git_velocity = (gc["churn"] / active_hours) if active_hours > 0 else 0

    explore = cat_counter.get("explore", 0) + thinking_blocks
    produce = cat_counter.get("produce", 0)
    execute = cat_counter.get("execute", 0)
    delegate = cat_counter.get("delegate", 0)
    doing = produce + execute + delegate
    planning_ratio = (explore / doing) if doing else 0

    tool_diversity = len(tool_counter)
    # shannon entropy over tool distribution (bonus, normalized 0-1)
    tot = sum(tool_counter.values()) or 1
    entropy = -sum((c / tot) * math.log2(c / tot) for c in tool_counter.values())
    norm_entropy = entropy / math.log2(tool_diversity) if tool_diversity > 1 else 0

    # Null-honesty: metrics that depend on tool-level events cannot be measured when
    # the only active sources never produced any tool calls at all (e.g. a transcript
    # format whose parser currently emits no tool_use).  Real 0 (a Claude session with
    # zero errors) is kept as-is; only the "counter is 0 because we never saw a tool
    # call" case becomes None.  Downstream scoring treats None as missing (same as 0).
    _no_tool_activity = (tool_use_total == 0 and bool(source_sessions))

    error_recovery_ratio = _error_recovery_ratio(recovered_errors, tool_errors, _no_tool_activity)
    error_rate_per_100_tools = _error_rate_per_100(tool_errors, tool_use_total, _no_tool_activity)
    # Fan-out / coordination: among sessions that DISPATCH agents, how many do you
    # coordinate at once? Median (robust to one big fan-out outlier). A serial grinder
    # firing N agents one-per-session reads 1; a real orchestrator reads its team size.
    _fanouts = [n for n in agents_per_session.values() if n > 0]
    _all_sources_no_agent = bool(source_sessions) and (
        set(source_sessions.keys()) <= _AGENT_UNSUPPORTED_SOURCES
    )
    fanout_median = _fanout_median(_fanouts, _no_tool_activity, _all_sources_no_agent)
    _ids = _iteration_depth_stats(edits_per_file_events, _no_tool_activity)
    iteration_mean = _ids["mean"]
    iteration_median = _ids["median"]
    iteration_p90 = _ids["p90"]
    iteration_max = _ids["max"]
    heavy_files = _ids["heavy_files"]

    actions_per_prompt = (tool_use_total / prompts_count) if prompts_count else 0
    # autonomy proxy 0-100: weighted blend, transparent + bounded
    auto_actions = min(actions_per_prompt / 25.0, 1.0) * 45          # heavy agentic loops
    auto_deleg = min(delegate / max(total_sessions, 1) / 1.5, 1.0) * 20  # subagent dispatch rate
    auto_sched = min((scheduled_actions + background_tasks) / max(total_sessions, 1), 1.0) * 15
    auto_lowq = (1 - min(questions_asked / max(prompts_count, 1) * 6, 1.0)) * 20  # rarely stops to ask
    autonomy_score = round(auto_actions + auto_deleg + auto_sched + auto_lowq, 1)

    span_days = (all_max_dt - all_min_dt).days + 1 if (all_min_dt and all_max_dt) else 0
    active_days = len(date_set)

    DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    tzname = datetime.now().astimezone().tzname()
    tzoffset = datetime.now().astimezone().strftime("%z")

    peak_hours = _peak_hours(hour_hist)
    preferred_days = _preferred_days(weekday_hist, DOW)

    progression = []
    for mk in sorted(set(month_dates) | set(month_prompts) | set(month_tools) | set(month_tokens)):
        mm = month_models.get(mk, Counter())
        _mt = month_tokens.get(mk) or {}
        _ti  = _mt.get("input", 0)
        _to  = _mt.get("output", 0)
        _tcr = _mt.get("cache_read", 0)
        _tcc = _mt.get("cache_creation", 0)
        progression.append({
            "month": mk,
            "prompts": month_prompts.get(mk, 0),
            "tool_calls": month_tools.get(mk, 0),
            "sessions": len(month_sessions.get(mk, ())),
            "active_days": len(month_dates.get(mk, ())),
            "tool_churn_lines": month_churn.get(mk, 0),
            "models": mm.most_common(3),
            "top_model": mm.most_common(1)[0][0] if mm else None,
            "tokens_input": _ti,
            "tokens_output": _to,
            "tokens_cache_read": _tcr,
            "tokens_cache_creation": _tcc,
            "tokens_total": _ti + _to + _tcr + _tcc,
        })

    stats = {
        "scope": "Sources: " + (", ".join(sorted(source_files)) or "none"),
        "generated_local_only": True,
        "corpus": {
            "sources": {s: {"files": source_files[s], "sessions": len(source_sessions[s]),
                            "prompts": source_prompts[s]} for s in sorted(source_files)},
            "files_parsed": files_parsed,
            "lines_total": lines_total,
            "lines_unparseable": lines_bad,
            "date_range": (
                [since_dt.isoformat() if since_dt is not None else (all_min_dt.isoformat() if all_min_dt else None),
                 (until_dt - timedelta(days=1)).isoformat() if until_dt is not None else (all_max_dt.isoformat() if all_max_dt else None)]
                if (since_dt is not None or until_dt is not None) else
                [all_min_dt.isoformat() if all_min_dt else None,
                 all_max_dt.isoformat() if all_max_dt else None]
            ),
            "window": ({"since": since_dt.isoformat() if since_dt else None,
                        "until": until_dt.isoformat() if until_dt else None}
                       if (since_dt or until_dt) else None),
            "span_days": span_days,
            "active_days": active_days,
            "timezone": f"{tzname} (UTC{tzoffset[:3]}:{tzoffset[3:]})",
            # metadata only — Antigravity transcripts are server-side, so this is
            # detected + counted but never folded into scores
            "antigravity_experimental": antigravity,
        },
        "volume": {
            "total_sessions": total_sessions,
            "total_prompts": prompts_count,
            "command_invocations": command_invocations,
            "avg_prompt_length_chars": round(avg_prompt_len, 1),
            "median_prompt_length_chars": round(median_prompt_len, 1),
            "assistant_turns": assistant_turns,
            "tool_calls_total": tool_use_total,
            "thinking_blocks": thinking_blocks,
        },
        "tools": {
            "tool_diversity": tool_diversity,
            "tool_entropy_normalized": round(norm_entropy, 3),
            "mcp_calls": mcp_calls,
            "native_calls": native_calls,
            "mcp_share": round(mcp_calls / (mcp_calls + native_calls), 3) if (mcp_calls + native_calls) else 0,
            "top_tools": tool_counter.most_common(20),
            "category_breakdown": dict(cat_counter),
            "mcp_servers": mcp_server_counter.most_common(),
            "mcp_servers_distinct": len(mcp_server_counter),
            "clis": cli_counter.most_common(),
            "clis_distinct": len(cli_counter),
            "cli_calls": sum(cli_counter.values()),
            "toolsearch_calls": tool_counter.get("ToolSearch", 0),
            "task_tool_calls": tool_counter.get("TaskCreate", 0) + tool_counter.get("TaskUpdate", 0),
            "agent_calls": tool_counter.get("Agent", 0),
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
            "tool_lines_added": lines_added,
            "tool_lines_removed": lines_removed,
            "tool_velocity_lines_per_hour": round(code_velocity, 1),
            "shell_write_calls": bash_write_calls,
            "shell_authored_lines_est": bash_authored_lines,
            "active_hours": round(active_hours, 1),
            "git_commits_grep": git_commits,
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
            "polite_prompts": polite_prompts,
            "error_recovery_ratio": round(error_recovery_ratio, 3) if error_recovery_ratio is not None else None,
            "error_rate_per_100_tools": round(error_rate_per_100_tools, 1) if error_rate_per_100_tools is not None else None,
            "tool_errors": tool_errors,
            "recovered_errors": recovered_errors,
            "api_errors_retries": api_errors,
            "fanout_median": fanout_median,
            "iteration_depth_mean": round(iteration_mean, 2) if iteration_mean is not None else None,
            "iteration_depth_median": round(iteration_median, 2) if iteration_median is not None else None,
            "iteration_depth_p90": iteration_p90,
            "iteration_depth_max": iteration_max,
            "files_hammered_over_15x": heavy_files,
            "actions_per_prompt": round(actions_per_prompt, 1),
            "questions_asked": questions_asked,
            "background_tasks": background_tasks,
            "scheduled_actions": scheduled_actions,
            "shell_test_runs": shell_test_runs,
        },
        "rhythm": {
            "hour_histogram_local": {str(h): hour_hist.get(h, 0) for h in range(24)},
            "weekday_histogram": {DOW[d]: weekday_hist.get(d, 0) for d in range(7)},
            "peak_hours_local": peak_hours,
            "preferred_days": preferred_days,
        },
        "progression": {"monthly": progression},
        "stack": {
            "models": model_counter.most_common(),
            "top_skills": skill_counter.most_common(15),
            "skills_distinct": len(skill_counter),
            "skills_total": sum(skill_counter.values()),
            "subagent_types_distinct": len(subagent_counter),
            # Cap high (not 50): compute_aq reads skills_all, so a low cap could drop a
            # needle skill (brainstorm/code-review/…) ranked past the cap and silently shift
            # the AQ vs the pre-cap score. 200 covers any real user; the scoring inputs emit
            # the same capped list, so feeding them back reproduces the score (parity holds).
            "skills_all": skill_counter.most_common(200),
            "compounding_writes": compounding_counter,
            "subagent_types": subagent_counter.most_common(10),
            "top_projects": [(os.path.basename(p), c, len(project_sessions[p]))
                             for p, c in project_activity.most_common(12)],
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
    # order by total tokens desc (consistent with model_usage ordering in _build_profile)
    stats["token_usage"] = _token_usage_block(model_tokens)
    stats["agentic"] = compute_aq(stats)

    # ---- per-calendar-month noticed_stats (GA1) -----------------------------
    # One entry per month present in the window, chronological. Each entry's
    # `stats` is shaped by the SAME _build_noticed_stats used for the window
    # block (no drift); per-month git_churn is called once per month with that
    # month's [start, next_month_start) range (never the window total).
    stats["monthly_noticed_stats"] = _build_monthly_noticed_stats(
        months=sorted(set(month_dates) | set(month_prompts) | set(month_tools)
                      | set(month_tokens) | set(month_sessions)),
        month_prompts=month_prompts,
        month_tools_count=month_tools,
        month_churn=month_churn,
        month_models=month_models,
        month_model_tokens=month_model_tokens,
        month_sessions=month_sessions,
        month_dates=month_dates,
        month_assistant_turns=month_assistant_turns,
        month_thinking_blocks=month_thinking_blocks,
        month_prompt_lengths=month_prompt_lengths,
        month_bash_write_calls=month_bash_write_calls,
        month_bash_authored_lines=month_bash_authored_lines,
        month_tool_errors=month_tool_errors,
        month_recovered_errors=month_recovered_errors,
        month_edits_per_file=month_edits_per_file,
        month_polite=month_polite,
        month_questions=month_questions,
        month_delegate=month_delegate,
        month_background=month_background,
        month_scheduled=month_scheduled,
        month_fanouts=month_fanouts,
        month_hour_hist=month_hour_hist,
        month_weekday_hist=month_weekday_hist,
        month_tool_counter=month_tool_counter,
        month_session_ts=month_session_ts,
        no_tool_activity=_no_tool_activity,
        all_sources_no_agent=_all_sources_no_agent,
        cwds=list(project_activity.keys()),
        gap_cap_s=GAP_CAP_S,
        burst_gap_s=BURST_GAP_S,
        dow=DOW,
    )

    # ---- per-month FULL stats slices (for scoring_inputs_by_source monthly) --
    # Same months as monthly_noticed_stats; each entry's stats_full is a full
    # stats-shaped dict (corpus/volume/behavior/velocity/stack/tools) so the SAME
    # _build_scoring_inputs shaper runs over window AND each month (no drift).
    # NOT serialized into stats.json — consumed only by _build_scoring_inputs_by_source.
    stats["_scoring_monthly_full"] = _build_monthly_scoring_stats(
        months=sorted(set(month_dates) | set(month_prompts) | set(month_tools)
                      | set(month_tokens) | set(month_sessions)),
        sources_present=sorted(source_files),
        month_prompts=month_prompts, month_tools_count=month_tools,
        month_churn=month_churn, month_models=month_models,
        month_sessions=month_sessions, month_assistant_turns=month_assistant_turns,
        month_thinking_blocks=month_thinking_blocks,
        month_bash_authored_lines=month_bash_authored_lines,
        month_tool_errors=month_tool_errors, month_recovered_errors=month_recovered_errors,
        month_edits_per_file=month_edits_per_file, month_questions=month_questions,
        month_delegate=month_delegate, month_background=month_background,
        month_scheduled=month_scheduled, month_fanouts=month_fanouts,
        month_tool_counter=month_tool_counter, month_session_ts=month_session_ts,
        month_skill_counter=month_skill_counter, month_subagent_counter=month_subagent_counter,
        month_mcp_server_counter=month_mcp_server_counter, month_cli_counter=month_cli_counter,
        month_compounding=month_compounding, month_shell_test_runs=month_shell_test_runs,
        month_api_errors=month_api_errors,
        planning_ratio_window=planning_ratio,
        cwds=list(project_activity.keys()),
        gap_cap_s=GAP_CAP_S, burst_gap_s=BURST_GAP_S,
        no_tool_activity=_no_tool_activity, all_sources_no_agent=_all_sources_no_agent,
    )

    narrative = {
        "opening_prompts": opening_prompts,
        "longest_prompts": longest_prompts,
        "phrase_counts": phrase_counts,
        "phrase_repr": phrase_repr,
        "phrase_sess": phrase_sess,
        "cryptic_cands": cryptic_cands,
        "crashout_cands": crashout_cands,
        "gc": gc,
        "source_files": source_files,
        "source_sessions": source_sessions,
    }
    return stats, narrative


# Re-export public API for backwards compatibility
from gnomon.config import parse_ts, line_count, strip_injections, pctile, _pretty_model, _client_version, _open_in_browser, BASE, OUT_DIR  # noqa: E402,F811
from gnomon.taxonomy import *  # noqa: E402,F403
from gnomon.sources import iter_events, _texts  # noqa: E402,F811
from gnomon.sources.discovery import *  # noqa: E402,F403
from gnomon.sources.codex import _codex_events, _patch_files, _patch_churn  # noqa: E402
from gnomon.sources.gemini import _gemini_events  # noqa: E402
from gnomon.sources.pi import _pi_events  # noqa: E402
from gnomon.sources.opencode import _opencode_events  # noqa: E402
from gnomon.sources.cursor import _cursor_dedup, _cursor_sqlite_events, _cursor_jsonl_events  # noqa: E402,F811
from gnomon.sources.antigravity import antigravity_summary  # noqa: E402,F811
from gnomon.analysis.churn import git_churn  # noqa: E402,F811
from gnomon.analysis.metrics import *  # noqa: E402,F403
from gnomon.analysis.quotes import *  # noqa: E402,F403
from gnomon.scoring.gstack import compute_scores, score_breakdown  # noqa: E402,F811
from gnomon.scoring.aq import compute_aq  # noqa: E402,F811
from gnomon.scoring.archetype import pick_archetype  # noqa: E402,F811
from gnomon.scoring.insights import *  # noqa: E402,F403
from gnomon.output.summary import build_summary  # noqa: E402,F811
from gnomon.output.report import write_report, bar  # noqa: E402,F811
from gnomon.output.narrative import write_narrative_input  # noqa: E402,F811
from gnomon.output.profile_html import write_profile_html  # noqa: E402,F811
