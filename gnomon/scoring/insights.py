import re

from gnomon.analysis.metrics import _review_skill_uses
from gnomon.scoring.gstack import _clamp


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
        skills = st.get("skills_all") or st.get("top_skills", [])
        return sum(n for k, n in skills if any(nd in str(k).lower() for nd in needles))

    top_tool = (str(t["top_tools"][0][0]) if t["top_tools"] else "")
    deleg = b["delegate_actions"] + b["background_tasks"]
    raw = []   # (strength 0..1, tag, title, evidence_html)

    rev = _review_skill_uses(st.get("skills_all") or st.get("top_skills", []))
    if rev >= 50 and rev >= sess * 0.5:
        raw.append((_clamp(rev / (sess * 2)), "Review",
            "You review more than you write",
            f'<b>{rev:,}</b> code-review passes — one of your most-used skills. '
            f'You don\'t trust a diff until a second set of eyes has seen it.'))

    if b["planning_ratio_explore_to_doing"] >= 0.55 and (b.get("iteration_depth_max") or 0) >= 40:
        raw.append((_clamp((b["iteration_depth_max"] or 0) / 100.0), "Think → Build",
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

    # plan_sessions already folds in both signals per session (plan-mode/todo tools AND
    # planning skills), so use it directly — don't re-add sk() or we'd double-count.
    plan = min(b.get("plan_sessions", 0), sess)
    if plan >= 3 and plan >= sess * 0.35:
        raw.append((_clamp(plan / float(sess)), "Plan",
            "You write the plan before the code",
            f'You opened <b>{plan:,}</b> of {sess:,} sessions with a plan — you scaffold '
            f'the decision before the implementation, gstack-style.'))

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

    knowledge_calls = t.get("mcp_knowledge_calls", 0)
    knowledge_servers = t.get("mcp_knowledge_servers", 0)
    if knowledge_calls >= 100 and knowledge_servers >= 2:
        raw.append((_clamp(knowledge_calls / 500.0), "Research",
            "You research before you write",
            f'<b>{knowledge_calls:,}</b> knowledge-tool calls across '
            f'<b>{knowledge_servers}</b> servers (codegraph, memory, docs) &mdash; '
            f'you ground your edits in indexed context, not guesswork.'))

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
        skills = st.get("skills_all") or st.get("top_skills", [])
        return sum(n for k, n in skills if any(nd in str(k).lower() for nd in needles))

    rev = _review_skill_uses(st.get("skills_all") or st.get("top_skills", []))
    tdd = sk("test", "tdd", "qa") + b.get("shell_test_runs", 0)   # named test skills + CLI test runs
    err = b.get("error_rate_per_100_tools") or 0  # None (unmeasured) treated as 0 for edge thresholds
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
    if ((b.get("iteration_depth_max") or 0) >= 40 or (b.get("files_hammered_over_15x") or 0) >= 10) and err >= 5:
        raw.append((2.0, "Stop the grind",
            "When a file fights back, root-cause it",
            f'<b>{b.get("iteration_depth_max") or 0}×</b> on one file and <b>{b.get("files_hammered_over_15x") or 0}</b> files '
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

    eng_skills = _review_skill_uses(st.get("skills_all") or st.get("top_skills", [])) + sk("qa", "investigate", "retro")
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
            freq = sig.get("frequency")
            freq_note = (f' Frequency: <b>{round(freq * 100)}%</b> of orchestratable sessions delegated.'
                         if freq is not None else '')
            return ("Multiply yourself", "Run agents in parallel, not in series",
                lead + f'<b>{sig.get("subagent_types", 0)}</b> distinct subagent types with a median '
                f'fan-out of <b>{sig.get("fanout_median") or 0}</b>.{freq_note} When a task splits into '
                f'independent pieces, hand them to parallel subagents in one orchestrating session '
                f'instead of grinding through them serially.')
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
