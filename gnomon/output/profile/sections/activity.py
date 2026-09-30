"""The local profile's activity counts and model composition."""

import html

from gnomon.config import _pretty_model


CSS = """
.activity-heading {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 24px;
  min-width: 0;
  margin-bottom: 8px;
}
.activity-heading h2 {
  min-width: 0;
  margin: 0;
  color: var(--text-primary);
  font-size: 24px;
  line-height: 1.2;
}
.activity-hint {
  flex: 0 1 auto;
  min-width: 0;
  margin: 0;
  color: var(--text-tertiary);
  font-size: 13px;
  text-align: right;
}
.activity-summary {
  margin: 0 0 32px;
  color: var(--text-secondary);
  font-size: 14px;
}
.activity-volume,
.activity-counts {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 24px;
  min-width: 0;
}
.activity-count {
  min-width: 0;
  padding-top: 12px;
  border-top: 1px solid var(--rule-strong);
}
.activity-label {
  display: block;
  min-width: 0;
  overflow-wrap: anywhere;
  color: var(--text-secondary);
  font-size: 13px;
}
.activity-value {
  display: block;
  min-width: 0;
  margin-top: 8px;
  overflow-wrap: anywhere;
  color: var(--text-primary);
  font-family: var(--font-figure);
  font-size: 28px;
  font-variant-numeric: tabular-nums;
  font-weight: 500;
  line-height: 1.1;
}
.activity-detail {
  min-width: 0;
  margin: 8px 0 0;
  color: var(--text-tertiary);
  font-size: 13px;
  line-height: 1.45;
}
.activity-note {
  margin: 28px 0 32px;
  color: var(--text-secondary);
  font-size: 14px;
  line-height: 1.5;
}
.activity-note strong {
  color: var(--text-primary);
  font-weight: 600;
}
.activity-counts {
  grid-template-columns: repeat(4, minmax(0, 1fr));
  row-gap: 32px;
}
.models-section {
  min-width: 0;
  margin-top: 56px;
}
.models-heading {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 24px;
  min-width: 0;
  margin-bottom: 20px;
}
.models-heading h3 {
  margin: 0;
  color: var(--text-primary);
  font-size: 18px;
  line-height: 1.2;
}
.models-note {
  min-width: 0;
  margin: 0;
  color: var(--text-tertiary);
  font-size: 13px;
  text-align: right;
}
.model-row {
  display: grid;
  grid-template-columns: minmax(0, 180px) minmax(0, 1fr) 90px;
  align-items: center;
  gap: 16px;
  min-width: 0;
  padding: 12px 0;
  border-top: 1px solid var(--rule-subtle);
}
.model-name,
.model-meta {
  min-width: 0;
  overflow-wrap: anywhere;
  color: var(--text-primary);
  font-size: 14px;
}
.model-meta {
  color: var(--text-secondary);
  font-family: var(--font-mono);
  font-size: 12px;
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.model-bar {
  min-width: 0;
  height: 8px;
  overflow: hidden;
  background: var(--chart-track);
}
.model-fill {
  height: 100%;
}
.model-fill.model-1 { background: var(--chart-1); }
.model-fill.model-2 { background: var(--chart-2); }
.model-fill.model-3 { background: var(--chart-3); }
.model-fill.model-4 { background: var(--chart-4); }
.model-empty {
  margin: 0;
  font-size: 14px;
}
@media (max-width: 820px) {
  .activity-heading,
  .models-heading { display: block; }
  .activity-hint,
  .models-note { margin-top: 8px; text-align: left; }
  .activity-volume { grid-template-columns: 1fr; }
  .activity-counts { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 560px) {
  .activity-counts { grid-template-columns: 1fr; }
  .model-row { grid-template-columns: minmax(0, 1fr) 72px; }
  .model-bar { grid-column: 1 / -1; grid-row: 2; }
  .model-meta { grid-column: 2; grid-row: 1; }
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
    if kind == "current_month" and month_key:
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


def _count_html(key, label, value, detail="", value_override=None):
    shown = value_override if value_override is not None else _metric_text(value)
    return (
        '<div class="activity-count" data-key="{key}" data-value="{value}">'
        '<span class="activity-label">{label}</span>'
        '<strong class="activity-value">{shown}</strong>'
        '{detail_html}'
        '</div>'
    ).format(
        key=_text(key),
        value=_text("" if value is None else value),
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


def _models_html(stats, period):
    stack = stats.get("stack") or {}
    models = stack.get("models") or []
    normalized = []
    for entry in models:
        if isinstance(entry, (list, tuple)) and len(entry) >= 2:
            name, turns = entry[0], _count(entry[1])
            normalized.append((_pretty_model(name), turns))
    total = sum(turns for _, turns in normalized)
    if not normalized or not total:
        return '<p class="gn-empty model-empty">not measured for this source</p>'

    rows = []
    for index, (name, turns) in enumerate(normalized):
        pct = int(round(turns * 100.0 / total))
        color_index = min(index + 1, 4)
        rows.append(
            '<div class="model-row" data-model="{model}" data-turns="{turns}" '
            'data-pct="{pct}">'
            '<span class="model-name">{model}</span>'
            '<div class="model-bar" role="img" aria-label="{pct}% of turns">'
            '<span class="model-fill model-{color}" style="width:{width}%"></span>'
            '</div>'
            '<span class="model-meta">{pct}% · {turns} turns</span>'
            '</div>'.format(
                model=_text(name), turns=turns, pct=pct, color=color_index,
                width=max(0, min(100, pct))))
    return '<div id="models-used">{}</div>'.format("".join(rows))


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
    error_rate = _metric_text(behavior.get("error_rate_per_100_tools"), " per 100 tools")
    delegate_actions = _count(behavior.get("delegate_actions"))
    per_session = round(delegate_actions / float(max(sessions, 1)), 1)
    background = _count(behavior.get("background_tasks"))
    scheduled = _count(behavior.get("scheduled_actions"))
    top_tool, top_tool_calls = _top_tool(tools)
    if top_tool is None:
        top_tool_label = "not measured for this source"
        top_tool_detail = ""
    else:
        top_tool_label = top_tool
        top_tool_detail = "{} calls".format(_number_text(top_tool_calls))

    return (
        '<div class="activity-heading">'
        '<h2>{heading}</h2>'
        '<p class="activity-hint">Counts and readings — none of these are graded.</p>'
        '</div>'
        '<p class="activity-summary">{sessions} sessions · {prompts} prompts · '
        '{tool_calls} tool calls</p>'
        '<div class="activity-volume">{volume_html}</div>'
        '<p class="activity-note"><strong>How much did you ship?</strong> '
        'Edit/Write touched <b>{edit_write_lines}</b> lines and the shell '
        '~{shell_lines} more — but only <b>{git_lines}</b> actually landed in '
        'committed git history. That committed number is the honest one.</p>'
        '<div class="activity-counts">{counts_html}</div>'
        '<div class="models-section">'
        '<div class="models-heading"><h3>Models used</h3>'
        '<p class="models-note">{models_note}</p></div>'
        '{models_html}'
        '</div>'
    ).format(
        heading=_text(_period_heading(period)),
        sessions=_number_text(sessions), prompts=_number_text(prompts),
        tool_calls=_number_text(tool_calls),
        volume_html="".join((
            _count_html("git_lines", "git lines", velocity.get("git_churn_total")),
            _count_html("edit_write_lines", "Edit/Write lines",
                        velocity.get("tool_churn_edit_write")),
            _count_html("shell_lines", "shell lines",
                        velocity.get("shell_authored_lines_est")),
        )),
        counts_html="".join((
            _count_html(
                "subagents", "subagents", delegate_actions,
                "About {} per session, plus {} background tasks and {} scheduled "
                "runs.".format(
                    per_session, _number_text(background), _number_text(scheduled))),
            _count_html(
                "errors", "errors · {}".format(recovery_text),
                behavior.get("tool_errors"), error_rate),
            _count_html(
                "max_edits", "max edits on one file",
                behavior.get("iteration_depth_max"),
                "mean {} edits · {} files hammered >15×".format(
                    _metric_text(behavior.get("iteration_depth_mean")),
                    _number_text(behavior.get("files_hammered_over_15x")))),
            _count_html("go_to_tool", "go-to tool", top_tool, top_tool_detail,
                        value_override=top_tool_label),
        )),
        edit_write_lines=_number_text(velocity.get("tool_churn_edit_write")),
        shell_lines=_number_text(velocity.get("shell_authored_lines_est")),
        git_lines=_number_text(velocity.get("git_churn_total")),
        models_note=_text(
            "Every model you used in {}, largest first.".format(_period_label(period))),
        models_html=_models_html(stats, period),
    )
