import json
import os

from gnomon.config import OUT_DIR, _pretty_model
from gnomon.scoring.gstack import _d10


def bar(n, mx, width=28):
    if mx <= 0:
        return ""
    return "█" * max(1, round(n / mx * width)) if n else ""


def write_report(s, output_dir=None):
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
                f"commits under your git email, or were too large to scan in time)")
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
    _err_rate = b['error_rate_per_100_tools']
    _err_recov = b['error_recovery_ratio']
    _err_recov_pct = f"{_err_recov*100:.0f}%" if _err_recov is not None else "—"
    _err_rate_str = f"{_err_rate}" if _err_rate is not None else "—"
    A(f"- Errors: **{b['tool_errors']:,} tool errors** ({_err_rate_str} per 100 tool calls); "
      f"{b['recovered_errors']:,} recovered ({_err_recov_pct}); {b['api_errors_retries']} API retries")
    _idm = b['iteration_depth_mean']; _idmed = b['iteration_depth_median']
    _idp90 = b['iteration_depth_p90']; _idmax = b['iteration_depth_max']
    _heavy = b['files_hammered_over_15x']
    if _idm is None:
        A("- Iteration depth (edits/file before commit): — (not measured for this source)")
    else:
        A(f"- Iteration depth (edits/file before commit): mean **{_idm:.1f}**, "
          f"median {_idmed:.0f}, p90 {_idp90}, "
          f"**max {_idmax}** — {_heavy} files hammered >15× in one session")
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
    with open(os.path.join(output_dir or OUT_DIR, "report.md"), "w") as f:
        f.write("\n".join(L))
