"""The local profile's activity counts and model composition."""

import html

from gnomon.config import _pretty_model


CSS = """
#activity {
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) auto minmax(0, 1fr);
  align-items: start;
  column-gap: 40px;
}
#activity::after {
  content: "";
  grid-column: 2;
  grid-row: 2;
  width: 1px;
  align-self: stretch;
  margin-top: 32px;
  background: var(--rule-default);
}
.activity-top {
  grid-column: 1 / -1;
  min-width: 0;
}
.activity-heading {
  display: flex;
  align-items: baseline;
  gap: 16px;
  min-width: 0;
  margin-bottom: 4px;
}
.activity-volume-line {
  margin-left: auto;
  color: var(--text-secondary);
  font: 400 13px/1.3 var(--font-figure);
  text-align: right;
}
.activity-hint {
  margin-bottom: 28px;
}
.activity-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  column-gap: 40px;
  min-width: 0;
}
.activity-count,
.activity-ship {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
  padding: 16px 0 20px;
  border-top: 1px solid var(--rule-subtle);
}
.activity-ship {
  display: block;
}
.activity-ship .gn-label {
  margin-bottom: 8px;
}
.activity-value {
  min-width: 0;
  overflow-wrap: anywhere;
  color: var(--text-primary);
  font: 500 28px/1.15 var(--font-figure);
  letter-spacing: -.025em;
}
.activity-label {
  min-width: 0;
  overflow-wrap: anywhere;
  color: var(--text-primary);
  font-size: 13px;
  line-height: 1.5;
}
.activity-count[data-group="volume"] .activity-label {
  color: var(--text-secondary);
}
.activity-detail,
.activity-ship p {
  margin: 0;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.5;
  text-wrap: pretty;
}
.models-section {
  grid-column: 1;
  grid-row: 2;
  min-width: 0;
  margin-top: 32px;
}
.models-heading {
  display: flex;
  align-items: baseline;
  gap: 12px;
  min-width: 0;
  margin-bottom: 20px;
}
.models-total {
  margin-left: auto;
  color: var(--text-tertiary);
  font: 400 11px/1.2 var(--font-figure);
  letter-spacing: .1em;
}
#models-used {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.model-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}
.model-line {
  display: flex;
  align-items: baseline;
  gap: 12px;
  min-width: 0;
}
.model-name {
  min-width: 0;
  overflow-wrap: anywhere;
  color: var(--text-primary);
  font-size: 15px;
}
.model-turns {
  flex: none;
  color: var(--text-tertiary);
  font: 400 11px/1.2 var(--font-figure);
  letter-spacing: .1em;
}
.model-pct {
  margin-left: auto;
  flex: none;
  color: var(--text-primary);
  font: 500 15px/1.3 var(--font-figure);
}
.model-bar {
  position: relative;
  height: 8px;
  background: var(--chart-track);
}
.model-fill {
  position: absolute;
  top: 0;
  bottom: 0;
  left: 0;
}
.model-fill.model-1 { background: var(--chart-1); }
.model-fill.model-2 { background: var(--chart-2); }
.model-fill.model-3 { background: var(--chart-3); }
.model-fill.model-4 { background: var(--chart-4); }
.models-note {
  margin: 16px 0 0;
  color: var(--text-tertiary);
  font-size: 13px;
  line-height: 1.5;
}
.model-empty {
  margin: 0;
  font-size: 15px;
}
@media (max-width: 960px) {
  .activity-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 760px) {
  #activity { grid-template-columns: 1fr; }
  #activity::after { display: none; }
  .activity-heading { flex-wrap: wrap; }
  .activity-volume-line { margin-left: 0; text-align: left; }
}
@media (max-width: 480px) {
  .activity-grid { grid-template-columns: 1fr; }
}
"""


def _text(value):
    return html.escape(str(value), quote=True)


def _number(value, default=0):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return int(number) if number.is_integer() else number


def _count(value):
    number = _number(value, 0)
    return int(number) if isinstance(number, (int, float)) else 0


def _number_text(value):
    number = _number(value, 0)
    if isinstance(number, float) and not number.is_integer():
        return "{:g}".format(number)
    return "{:,}".format(int(number))


def _metric_text(value, suffix=""):
    if value is None:
        return "not measured for this source"
    return _number_text(value) + suffix


def _pct(value):
    if value is None:
        return None
    number = _number(value, 0)
    if number <= 1:
        number *= 100
    return int(round(number))


def _period_label(period):
    kind = getattr(period, "kind", "all_history")
    month_key = getattr(period, "month_key", None)
    if month_key:
        try:
            year, month = month_key.split("-")
            months = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
                      "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
            return "{} {}".format(months[int(month) - 1], year)
        except (ValueError, IndexError):
            pass
    if kind == "custom":
        return "this window"
    return "all history"


def _period_heading(period):
    return "Activity · {}".format(_period_label(period))


def _count_html(key, label, value, detail="", value_override=None, group="count"):
    shown = value_override if value_override is not None else _metric_text(value)
    return (
        '<div class="activity-count" data-key="{key}" data-value="{value}" data-group="{group}">'
        '<strong class="activity-value">{shown}</strong>'
        '<span class="activity-label">{label}</span>'
        '{detail_html}'
        '</div>'
    ).format(
        key=_text(key),
        value=_text("" if value is None else value),
        group=_text(group),
        label=_text(label),
        shown=_text(shown),
        detail_html=(
            '<p class="activity-detail">{}</p>'.format(_text(detail))
            if detail else ""),
    )


def _top_tool(tools):
    entries = (tools or {}).get("top_tools") or []
    if not entries:
        return None, None
    first = entries[0]
    if isinstance(first, (list, tuple)) and len(first) >= 2:
        return first[0], first[1]
    return None, None


_TOP_MODELS = 5


def _model_counts(stats):
    """(raw name, turns) per model, most-used first, without internal "<…>" entries."""
    counts = []
    for entry in (stats.get("stack") or {}).get("models") or []:
        if isinstance(entry, (list, tuple)) and len(entry) >= 2:
            name = str(entry[0])
            if name.startswith("<"):   # e.g. "<synthetic>": harness bookkeeping, not a model
                continue
            counts.append((name, _count(entry[1])))
    return sorted(counts, key=lambda item: -item[1])


def _models_html(stats, period):
    counts = _model_counts(stats)
    total = sum(turns for _, turns in counts)
    if not counts or not total:
        return '<p class="gn-empty model-empty">not measured for this source</p>'

    shown = [(_pretty_model(name), turns) for name, turns in counts[:_TOP_MODELS]]
    rest = counts[_TOP_MODELS:]
    if rest:
        shown.append(("Others", sum(turns for _, turns in rest)))

    rows = []
    for index, (name, turns) in enumerate(shown):
        is_others = bool(rest) and index == len(shown) - 1
        share = turns * 100.0 / total
        pct = int(round(share))
        color_index = 4 if is_others else min(index + 1, 4)
        turns_text = "{:,} turns".format(turns)
        if is_others:
            turns_text += " · {} {}".format(len(rest), "model" if len(rest) == 1 else "models")
        rows.append(
            '<div class="model-row" data-model="{model}" data-turns="{turns}" '
            'data-pct="{pct}">'
            '<div class="model-line">'
            '<span class="model-name">{model}</span>'
            '<span class="model-turns">{turns_text}</span>'
            '<span class="model-pct">{pct}%</span>'
            '</div>'
            '<div class="model-bar" role="img" aria-label="{model}: {pct}% of turns">'
            '<span class="model-fill model-{color}" style="width:{width}%"></span>'
            '</div>'
            '</div>'.format(
                model=_text(name), turns=turns, turns_text=_text(turns_text), pct=pct,
                color=color_index, width="{:.1f}".format(max(0.0, min(100.0, share)))))
    return '<div id="models-used">{}</div>'.format("".join(rows))


def _models_note(stats, period):
    if len(_model_counts(stats)) > _TOP_MODELS:
        return "Your {} most-used models in {}; the rest are grouped in Others.".format(
            _TOP_MODELS, _period_label(period))
    return "Every model you used in {}, largest first.".format(_period_label(period))


def _models_total(stats):
    total = sum(turns for _, turns in _model_counts(stats))
    return "{:,} turns".format(total) if total else ""


def render(ctx) -> str:
    """Render the period-scoped activity metrics published in ``stats``."""
    stats = getattr(ctx, "stats", None) or {}
    period = getattr(ctx, "period", None)
    volume = stats.get("volume") or {}
    velocity = stats.get("velocity") or {}
    behavior = stats.get("behavior") or {}
    tools = stats.get("tools") or {}

    sessions = _count(volume.get("total_sessions"))
    prompts = _count(volume.get("total_prompts"))
    tool_calls = _count(volume.get("tool_calls_total"))
    recovery_pct = _pct(behavior.get("error_recovery_ratio"))
    recovery_text = (
        "{}% recovered".format(recovery_pct)
        if recovery_pct is not None else "not measured for this source")
    error_rate = behavior.get("error_rate_per_100_tools")
    error_detail = (
        "Roughly {} per 100 tool calls — and you kept going after almost all of them.".format(
            _number_text(error_rate))
        if error_rate is not None else "Error rate not measured for this source.")
    delegate_actions = _count(behavior.get("delegate_actions"))
    per_session = round(delegate_actions / float(max(sessions, 1)), 1)
    background = _count(behavior.get("background_tasks"))
    scheduled = _count(behavior.get("scheduled_actions"))
    depth_max = behavior.get("iteration_depth_max")
    depth_mean = behavior.get("iteration_depth_mean")
    depth_detail = (
        "{} files went past 15 edits. Your typical file, though? About {:.1f}.".format(
            _number_text(behavior.get("files_hammered_over_15x")), float(depth_mean))
        if depth_mean is not None else "Iteration depth not measured for this source.")
    top_tool, top_tool_calls = _top_tool(tools)
    if top_tool is None:
        top_tool_label = "not measured for this source"
        top_tool_detail = ""
    else:
        top_tool_label = top_tool
        top_tool_detail = "{} calls — more than any other tool.".format(
            _number_text(top_tool_calls))
    shell_lines = velocity.get("shell_authored_lines_est")

    return (
        '<div class="activity-top">'
        '<div class="activity-heading">'
        '<h2 class="gn-section-title" id="act-h">{heading}</h2>'
        '<span class="activity-volume-line">{sessions} sessions · {prompts} prompts · '
        '{tool_calls} tool calls</span>'
        '</div>'
        '<p class="gn-section-hint activity-hint">Counts and readings — none of these are '
        'graded.</p>'
        '<div class="activity-grid">{volume_html}'
        '<div class="activity-ship"><div class="gn-label">How much did you ship?</div>'
        '<p>Edit/Write touched {edit_write_lines} lines and the shell ~{shell_text} more — '
        'but only {git_lines} actually landed in committed git history. That committed '
        'number is the honest one.</p></div>'
        '{counts_html}</div>'
        '</div>'
        '<div class="models-section">'
        '<div class="models-heading"><h3 class="gn-label">Models used · share of turns</h3>'
        '<span class="models-total">{models_total}</span></div>'
        '{models_html}{models_note}'
        '</div>'
    ).format(
        heading=_text(_period_heading(period)),
        sessions=_number_text(sessions), prompts=_number_text(prompts),
        tool_calls=_number_text(tool_calls),
        volume_html="".join((
            _count_html("git_lines", "lines committed to git",
                        velocity.get("git_churn_total"), group="volume"),
            _count_html("edit_write_lines", "lines via Edit/Write",
                        velocity.get("tool_churn_edit_write"), group="volume"),
            _count_html("shell_lines", "lines in the shell", shell_lines, group="volume",
                        value_override=(
                            "~" + _number_text(shell_lines) if shell_lines is not None
                            else None)),
        )),
        counts_html="".join((
            _count_html(
                "subagents", "subagents", delegate_actions,
                "About {} per session, plus {} background tasks and {} scheduled "
                "runs.".format(
                    per_session, _number_text(background), _number_text(scheduled))),
            _count_html(
                "errors", "errors · {}".format(recovery_text),
                behavior.get("tool_errors"), error_detail),
            _count_html(
                "max_edits", "max edits on one file", depth_max, depth_detail,
                value_override=(_number_text(depth_max) + "×" if depth_max is not None
                                else None)),
            _count_html("go_to_tool", "go-to tool", top_tool, top_tool_detail,
                        value_override=top_tool_label),
        )),
        edit_write_lines=_number_text(velocity.get("tool_churn_edit_write")),
        shell_text=_number_text(shell_lines),
        git_lines=_number_text(velocity.get("git_churn_total")),
        models_total=_text(_models_total(stats)),
        models_note=(
            '<p class="models-note">{}</p>'.format(_text(
                _models_note(stats, period)))
            if _models_total(stats) else ""),
        models_html=_models_html(stats, period),
    )
