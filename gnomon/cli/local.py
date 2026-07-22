#!/usr/bin/env python3
"""Local analysis engine (formerly paxel.py's main function)."""

import contextlib
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from gnomon.config import BASE, OUT_DIR, parse_ts, line_count, strip_injections, pctile, _open_in_browser
from gnomon.sources import iter_events
from gnomon.sources.discovery import (
    ALL_SOURCES, _DIR_FLAGS,
    discover_sources, parse_window, _resolve_source_dir,
)
from gnomon.sources.cursor import _cursor_dedup
from gnomon.sources.antigravity import antigravity_summary, export_antigravity_ide, ide_window_overlaps
from gnomon.analysis.churn import git_churn
from gnomon.analysis.quotes import _safe_quote, _cryptic_score, _crashout_score, _RAGE_RE, _FILLER
from gnomon.scoring.gstack import compute_scores
from gnomon.scoring.aq import compute_aq
from gnomon.scoring.archetype import pick_archetype
from gnomon.scoring.inputs import SCORING_INPUTS_VERSION, build_scoring_inputs
from gnomon.scoring.aggregate import AQ_BUCKETS, RECENCY_BLEND_ENABLED, RECENT_WEIGHT, HISTORY_WEIGHT, _blend_aq
from gnomon.cli.accumulator import Accumulator
from gnomon.output.summary import build_summary
from gnomon.output.report import write_report
from gnomon.output.narrative import write_narrative_input
from gnomon.output.profile_html import write_profile_html


# Tool metrics surfaced by --tools: (label, signal key in stats['agentic'], target, is_rate).
# The 7 rate-scored metrics use PER-SESSION targets that mirror scoring/aq.py's rate() targets,
# so the % column matches what AQ actually scores. knowledge_calls is a self-check diagnostic
# only (it feeds the Research signature move, not an AQ axis) -> reported as absolute, is_rate=False.
_TOOLS_DIAG = [
    ("task_tool_calls", "task_tool_calls", 1.0, True),
    ("toolsearch_calls", "toolsearch", 0.30, True),
    ("skills_total", "skills_total", 10, True),
    ("review_skills", "review_skills", 1.5, True),
    ("shell_test_runs", "test_runs", 1.5, True),
    ("compounding_writes", "compounding_writes", 0.25, True),
    ("orchestratable", "orchestratable_sessions", 1.0, False),
    ("knowledge_calls", "knowledge_calls", 200, False),  # gated, absolute (not per-session)
]


def _rolling_aq_bucket_windows(until_dt=None, now=None):
    """Return rolling AQ windows anchored at the effective scoring end."""
    now = now or datetime.now().astimezone()
    anchor = min(until_dt, now) if until_dt is not None else now
    return [
        {
            "id": bucket["id"],
            "configured_weight": bucket["configured_weight"],
            "day_bounds": {"lower": bucket["lower_days"], "upper": bucket["upper_days"]},
            "since": anchor - timedelta(days=bucket["upper_days"]),
            "until": anchor - timedelta(days=bucket["lower_days"]),
        }
        for bucket in AQ_BUCKETS
    ]


def tools_diagnostic(stats):
    """Return (table_lines, json_record) reporting per-session tool usage. The % column matches
    AQ's scoring: rate metrics score count/session vs a per-session target; knowledge is absolute.
    A self-check for the user and the calibration sample for per-session targets. Reads the
    already-computed signals in stats['agentic']; no recomputation."""
    vol = stats.get("volume", {}) or {}
    sessions = vol.get("total_sessions", 0) or 0
    denom = max(sessions, 1)
    sig = {}
    for p in (stats.get("agentic", {}) or {}).get("pillars", []):
        for a in p.get("axes", []):
            sig.update(a.get("signals", {}) or {})
    rates, counts = {}, {}
    lines = [f"{'metric':<20}{'count':>8}{'/session':>10}{'target':>9}{'%':>6}"]
    for label, key, target, is_rate in _TOOLS_DIAG:
        c = sig.get(key, 0) or 0
        per_session = c / denom
        rates[label] = round(per_session, 4)
        counts[label] = c
        # % against the SAME basis AQ uses: per-session rate for rate metrics, absolute otherwise
        scored = per_session if is_rate else c
        pct = min(100, round(100 * scored / target)) if target else 0
        tgt = f"{target:g}/s" if is_rate else f"{target:g}"
        lines.append(f"{label:<20}{c:>8}{per_session:>10.3f}{tgt:>9}{pct:>5}%")
    record = {"sessions": sessions, "prompts": vol.get("total_prompts", 0),
              "active_hours": (stats.get("velocity", {}) or {}).get("active_hours", 0),
              "rates": rates, "counts": counts}
    return lines, record


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

    _t_main_start = time.monotonic()

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
        m = re.match(r"--([a-z]+(?:-[a-z]+)*)-dir=(.+)$", a)
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
    _ide_dir_override = any(a.startswith("--antigravity-dir=") for a in argv)
    _ide_dir_explicit = any(a.startswith("--antigravity-ide-dir=") for a in argv)
    if _ide_dir_override and not _ide_dir_explicit:
        selected = [s for s in selected if s != "antigravity-ide"]
    _t0_disc = time.monotonic()
    sources = discover_sources(selected)
    since_dt, until_dt = parse_window(argv)
    if since_dt or until_dt:
        print(f"  window: {since_dt.date() if since_dt else '...'} -> "
              f"{(until_dt - timedelta(days=1)).date() if until_dt else 'now'}")
    antigravity = None if _ide_dir_override else antigravity_summary()
    # Antigravity IDE fallback: if no IDE SQLite DBs were discovered (older Antigravity
    # versions that only expose data via the Language Server), try the LS CORTEX export.
    # The LS path masks model identity but still captures volume/tools/timestamps.
    _ide_dbs_found = any(s == "antigravity-ide" for s, _, _ in sources)
    if (not _ide_dbs_found and not _ide_dir_override
            and "antigravity-ide" in selected and antigravity
            and ide_window_overlaps(antigravity, since_dt, until_dt)):
        export_path = export_antigravity_ide(os.path.join(_out_dir, "_antigravity_ide"))
        if export_path:
            sources.append(("antigravity-ide", export_path, "antigravity-ide-export"))
            print(f"  Antigravity IDE history folded in via LS ({antigravity['conversations']} conversations)")
    by_src = Counter(s for s, _, _ in sources)
    print(f"Found {len(sources)} transcript files across "
          f"{', '.join(f'{k}:{v}' for k, v in by_src.items()) or 'no sources'}")
    sources, cursor_twins = _cursor_dedup(sources)
    _t_discovery = time.monotonic() - _t0_disc
    if not sources:
        print("\n  No transcripts found in ~/.claude/projects, ~/.codex/sessions, "
              "~/.gemini/tmp, ~/.gemini/antigravity*/..., ~/.pi/agent/sessions, "
              "~/.local/share/opencode/(opencode.db or storage), or ~/.cursor/projects.")
        print("  Nothing to analyze -- run this where you've actually used a coding agent.")
        return

    # Whole-corpus accumulation (all sources pooled, capabilities = union) — this is
    # the legacy/primary stats dict that drives the report, HTML and `profile`.
    _t0_acc = time.monotonic()
    stats, narrative = _accumulate(
        sources, since_dt, until_dt, cursor_twins, antigravity,
        total_file_count=len(sources), verbose=True)
    _t_accumulate_corpus = time.monotonic() - _t0_acc
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

    # ---- per-source scoring inputs (single-pass, from _accumulate) ----------
    # The per-source accumulators were tracked during the corpus _accumulate() run,
    # so we can build scoring_inputs without re-running _accumulate per source.
    stats["scoring_inputs_version"] = SCORING_INPUTS_VERSION
    _t0_si = time.monotonic()
    _per_source_stats = narrative.get("_per_source_stats", {})
    scoring_by_source = {}
    srcs_present = sorted(_per_source_stats.keys())
    single_source = len(srcs_present) == 1
    for src in srcs_present:
        if single_source:
            s_stats = stats  # same as legacy single_source optimization
        else:
            s_stats = _per_source_stats[src]
        window = build_scoring_inputs(s_stats)
        monthly = [
            dict(build_scoring_inputs(entry["stats_full"]), month=entry["month"])
            for entry in s_stats.get("_scoring_monthly_full", [])
        ]
        scoring_by_source[src] = {"window": window, "monthly": monthly}
    stats["scoring_inputs_by_source"] = scoring_by_source

    # ---- rolling bucket scoring (internal raw inputs; only scored AQ is shared) ----
    if RECENCY_BLEND_ENABLED:
        bucket_metadata = [
            {key: bucket[key] for key in ("id", "configured_weight", "day_bounds")}
            for bucket in narrative.get("_aq_bucket_windows", [])
        ]
        bucket_scoring_by_source = {}
        for bucket_id, per_source in narrative.get("_aq_bucket_per_source_stats", {}).items():
            bucket_scoring_by_source[bucket_id] = {}
            for src in srcs_present:
                bucket_stats = per_source.get(src)
                if bucket_stats is not None:
                    bucket_scoring_by_source[bucket_id][src] = {
                        "window": build_scoring_inputs(bucket_stats),
                    }
        stats["_aq_bucket_scoring_inputs_by_source"] = bucket_scoring_by_source
        stats["_aq_bucket_metadata"] = bucket_metadata

        corpus_components = []
        metadata_by_id = {entry["id"]: entry for entry in bucket_metadata}
        for bucket_id, bucket_stats in narrative.get("_aq_bucket_stats", {}).items():
            if (bucket_stats.get("volume", {}).get("total_sessions", 0) or 0) <= 0:
                continue
            metadata = metadata_by_id[bucket_id]
            corpus_components.append(dict(metadata, aq=compute_aq(bucket_stats)))
        if corpus_components:
            full_corpus_aq = stats["agentic"]
            stats["_full_window_agentic"] = full_corpus_aq
            corpus_components.append({
                "id": "full_window",
                "configured_weight": HISTORY_WEIGHT,
                "aq": full_corpus_aq,
            })
            stats["agentic"] = _blend_aq(full_corpus_aq, corpus_components)

    _t_scoring_inputs = time.monotonic() - _t0_si
    # internal-only working field (per-month full stats slices); not part of the payload
    stats.pop("_scoring_monthly_full", None)

    write_report(stats, output_dir=_out_dir)
    write_narrative_input(stats, opening_prompts, longest_prompts, output_dir=_out_dir)
    _t0_scores = time.monotonic()
    scores = compute_scores(stats)
    _t_compute_scores = time.monotonic() - _t0_scores
    archetype_stats = stats
    if stats.get("_full_window_agentic"):
        archetype_stats = dict(stats)
        archetype_stats["agentic"] = stats["_full_window_agentic"]
    archetype, quote = pick_archetype(archetype_stats, scores)

    # ---- assemble timing metadata ------------------------------------------
    _t_compute_aq = stats.pop("_timing_compute_aq_s", 0)
    _timing_per_source = stats.pop("_timing_per_source", {})
    stats["timing"] = {
        "wall_clock_total_s": round(time.monotonic() - _t_main_start, 3),
        "discovery_s": round(_t_discovery, 3),
        "accumulate_corpus_s": round(_t_accumulate_corpus, 3),
        "accumulate_per_source_s": {k: round(v, 3) for k, v in _timing_per_source.items()},
        "scoring_inputs_by_source_s": round(_t_scoring_inputs, 3),
        "compute_aq_s": round(_t_compute_aq, 3),
        "compute_scores_s": round(_t_compute_scores, 3),
    }

    stats_for_disk = {key: value for key, value in stats.items()
                      if key not in {"_aq_bucket_scoring_inputs_by_source",
                                     "_aq_bucket_metadata", "_full_window_agentic"}}
    with open(os.path.join(_out_dir, "stats.json"), "w", encoding="utf-8") as f:
        json.dump(stats_for_disk, f, indent=2, default=str)

    if "--summary" in argv:
        _t0_summ = time.monotonic()
        summary = build_summary(stats)
        stats["timing"]["build_summary_s"] = round(time.monotonic() - _t0_summ, 3)
        summary["timing"] = stats["timing"]
        with open(os.path.join(_out_dir, "summary.json"), "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, default=str)
        print("  wrote summary.json (shareable subset -- measured metrics + monthly progression)")
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
    if "--tools" in argv:
        _tlines, _trec = tools_diagnostic(stats)
        print("\n  tool usage (per session — self-check + rate calibration):")
        for _l in _tlines:
            print("    " + _l)
        print("  json: " + json.dumps(_trec))


def _accumulate(sources, since_dt, until_dt, cursor_twins, antigravity,
                total_file_count=None, verbose=True):
    """Accumulate every per-event signal over `sources` and return (stats, narrative).

    Feeds each event to the corpus Accumulator AND to its source's Accumulator, so
    the whole-corpus stats and the per-source scoring-input slices are produced in a
    single pass over the files and can never drift (they run identical observe code).
    Per-source stats let main() build scoring inputs without re-running _accumulate
    per source partition.

    `narrative` carries the verbatim-quote candidates and opening/longest prompts that
    main() needs for the local HTML page (never serialized into stats.json). They are
    corpus-only, so they're collected here from each genuine prompt observe() surfaces.
    """
    if total_file_count is None:
        total_file_count = len(sources)

    corpus = Accumulator()
    _srcs_present = sorted({s for s, _, _ in sources})
    src_accums = {s: Accumulator() for s in _srcs_present}

    bucket_windows = (_rolling_aq_bucket_windows(until_dt) if RECENCY_BLEND_ENABLED else [])
    bucket_corpora = {bucket["id"]: Accumulator() for bucket in bucket_windows}
    bucket_src_accums = {
        bucket["id"]: {source: Accumulator() for source in _srcs_present}
        for bucket in bucket_windows
    }
    file_scan_since = since_dt
    if since_dt is not None and bucket_windows:
        file_scan_since = min(since_dt, min(bucket["since"] for bucket in bucket_windows))

    # ---- narrative quote candidates (corpus-only, never serialized) ----------
    phrase_counts = Counter()      # normalized short prompt -> times seen
    phrase_repr = {}               # normalized -> first original spelling
    phrase_sess = defaultdict(set)  # normalized -> session ids it appeared in
    cryptic_cands = []             # [(score, verbatim text)] — ranked at the end
    crashout_cands = []            # [(score, verbatim text)]
    opening_prompts = []           # (dt, project, text) first genuine prompt per session
    longest_prompts = []           # kept small via periodic trim
    seen_session_open = set()

    for cur_src, fp, fmt in sources:
        # mtime pre-filter: a file last written before the window start can't contain
        # in-window events — skip the parse entirely (big win on ~38k codex seeds).
        # No mtime skip for --until: old events can live in recently-written files.
        if file_scan_since is not None:
            try:
                if datetime.fromtimestamp(os.path.getmtime(fp)).astimezone() < file_scan_since:
                    continue
            except OSError:
                pass
        sa = src_accums[cur_src]
        corpus.begin_file(cur_src, fp)
        sa.begin_file(cur_src, fp)
        for bucket in bucket_windows:
            bucket_corpora[bucket["id"]].begin_file(cur_src, fp)
            bucket_src_accums[bucket["id"]][cur_src].begin_file(cur_src, fp)
        if verbose and corpus.files_parsed % 300 == 0:
            print(f"  ...{corpus.files_parsed}/{total_file_count}")

        # iter_events() yields Claude-shaped event dicts for every source format,
        # so the per-event logic (Accumulator.observe) is identical across sources.
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
                corpus.skip_file()
                sa.skip_file()
                for bucket in bucket_windows:
                    bucket_corpora[bucket["id"]].skip_file()
                    bucket_src_accums[bucket["id"]][cur_src].skip_file()
                continue
            for ev in _ev_list:
                info = corpus.observe(ev, since_dt, until_dt)
                sa.observe(ev, since_dt, until_dt)
                for bucket in bucket_windows:
                    bucket_corpora[bucket["id"]].observe(
                        ev, bucket["since"], bucket["until"])
                    bucket_src_accums[bucket["id"]][cur_src].observe(
                        ev, bucket["since"], bucket["until"])
                if info is None:
                    continue
                # ---- narrative: verbatim-quote candidates from a genuine prompt ----
                cleaned, dt, sid, cwd = info
                _wc = len(cleaned.split())
                # "In your own words" cards — go-to phrase / most cryptic / biggest
                # crash-out. Pulled VERBATIM, only if safe to surface.
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
                proj = os.path.basename(cwd) if cwd else "?"
                if sid and sid not in seen_session_open:
                    seen_session_open.add(sid)
                    opening_prompts.append((dt, proj, cleaned[:600]))
                longest_prompts.append((len(cleaned), proj, cleaned[:600]))
                if len(longest_prompts) > 400:
                    longest_prompts.sort(key=lambda x: -x[0])
                    del longest_prompts[120:]
        corpus.end_file()
        sa.end_file()
        for bucket in bucket_windows:
            bucket_corpora[bucket["id"]].end_file()
            bucket_src_accums[bucket["id"]][cur_src].end_file()

    # ---- whole-corpus stats (also stashes corpus gc window + null-honesty flag) --
    stats = corpus.to_corpus_stats(since_dt, until_dt, antigravity)

    # ---- per-source stats (single-pass scoring inputs) -------------------------
    # When there's only a single source, main() uses the full corpus stats directly,
    # so we just register the source name (skip the extra git_churn calls). The fast
    # path keys off the DISCOVERED source count so it stays consistent with main()'s
    # `len(_per_source_stats) == 1` decision — keying off the *active* count would let
    # main() take the multi-source path while every entry is None (→ build_scoring_inputs(None)).
    # Each source is shaped fully from its own accumulator (mirrors a per-slice _accumulate).
    _per_source_stats = {}
    _single_source = len(src_accums) == 1
    for _src_name, _sa in src_accums.items():
        if _single_source:
            _per_source_stats[_src_name] = None
            continue
        _per_source_stats[_src_name] = _sa.to_source_stats(_src_name, since_dt, until_dt)

    # ---- rolling AQ bucket stats (internal only) -------------------------------
    bucket_stats = {}
    bucket_per_source_stats = {}
    for bucket in bucket_windows:
        bucket_id = bucket["id"]
        bucket_corpus = bucket_corpora[bucket_id]
        bucket_corpus.project_activity = {}
        for source_accumulator in bucket_src_accums[bucket_id].values():
            source_accumulator.project_activity = {}
        bucket_stats[bucket_id] = bucket_corpus.to_source_stats(
            ",".join(_srcs_present), bucket["since"], bucket["until"])
        # to_source_stats accepts one source name, but this accumulator is the
        # multi-source corpus. Restore the real source keys so capability-aware
        # AQ sees the same union as the full-window corpus.
        bucket_stats[bucket_id]["corpus"]["sources"] = {
            source_name: {}
            for source_name in _srcs_present
        }
        bucket_per_source_stats[bucket_id] = {}
        for source_name, source_accumulator in bucket_src_accums[bucket_id].items():
            if _single_source:
                bucket_per_source_stats[bucket_id][source_name] = bucket_stats[bucket_id]
                continue
            bucket_per_source_stats[bucket_id][source_name] = source_accumulator.to_source_stats(
                source_name, bucket["since"], bucket["until"])

    narrative = {
        "opening_prompts": opening_prompts,
        "longest_prompts": longest_prompts,
        "phrase_counts": phrase_counts,
        "phrase_repr": phrase_repr,
        "phrase_sess": phrase_sess,
        "cryptic_cands": cryptic_cands,
        "crashout_cands": crashout_cands,
        "gc": corpus.gc,
        "source_files": corpus.source_files,
        "source_sessions": corpus.source_sessions,
        "_per_source_stats": _per_source_stats,
        "_aq_bucket_windows": bucket_windows,
        "_aq_bucket_per_source_stats": bucket_per_source_stats,
        "_aq_bucket_stats": bucket_stats,
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
