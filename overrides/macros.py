"""mkdocs-macros entry point for the gnomon docs site.

Every number a reader sees on a metrics page is rendered from
docs/data/metrics.json by the functions in this module. The pure helpers at the
top take the parsed data as an argument so tests can call them without MkDocs.
"""

from html import escape as _e


def find_axis(data, axis_id):
    """The axis dict with this id, from any pillar."""
    for pillar in data["pillars"]:
        for axis in pillar["axes"]:
            if axis["id"] == axis_id:
                return axis
    raise KeyError(f"unknown axis: {axis_id}")


def _available_terms(axis, caps):
    return [t for t in axis["terms"] if set(t["requires"]) <= caps]


def partial_terms(data, axis_id, source_id):
    """Names of the axis terms this source can measure."""
    caps = set(data["sources"][source_id]["caps"])
    return [t["name"] for t in _available_terms(find_axis(data, axis_id), caps)]


def coverage(data, axis_id):
    """Per source: "full", "partial" or "none", from source capabilities only.

    An axis whose own requirement is missing is dropped for that source ("none");
    otherwise terms the source cannot measure are dropped and the rest carry the
    axis ("partial"). Data-dependent gates (minimum sessions, timestamps) are not
    source properties and are documented in each axis's eligibility text instead.
    """
    axis = find_axis(data, axis_id)
    states = {}
    for source_id, source in data["sources"].items():
        caps = set(source["caps"])
        available = _available_terms(axis, caps)
        if not set(axis["requires"]) <= caps or not available:
            states[source_id] = "none"
        elif len(available) < len(axis["terms"]):
            states[source_id] = "partial"
        else:
            states[source_id] = "full"
    return states


def find_pillar(data, pillar_id):
    """The pillar dict with this id."""
    for pillar in data["pillars"]:
        if pillar["id"] == pillar_id:
            return pillar
    raise KeyError(f"unknown pillar: {pillar_id}")


def _scored(axis):
    return axis["status"] != "not_scored"


def effective_weight(data, axis_id):
    """The axis's weight inside its pillar (0-100) after withheld siblings are dropped."""
    axis = find_axis(data, axis_id)
    if not _scored(axis):
        return 0.0
    siblings = find_pillar(data, axis["pillar"])["axes"]
    total = sum(a["base_weight"] for a in siblings if _scored(a))
    return round(100.0 * axis["base_weight"] / total, 1)


def share_of_aq(data, axis_id):
    """The axis's share of the total AQ score, in whole percent."""
    axis = find_axis(data, axis_id)
    pillar = find_pillar(data, axis["pillar"])
    return round(pillar["weight"] * effective_weight(data, axis_id) / 100)


# ---- HTML renderers -------------------------------------------------------------------

_STATE_WORDS = {"full": "Full", "none": "Not scored"}


def _pct(x):
    value = round(x * 100) if x <= 1 else round(x)
    return f"{value}%"


def _fmt_weight(value):
    return f"{value:g}"


def render_formula(data, axis_id):
    """Spec-sheet table: one row per term with its share, definition and target."""
    axis = find_axis(data, axis_id)
    provisional = axis["status"] == "provisional"
    rows = []
    for term in axis["terms"]:
        tag = ' <span class="gn-tag">Provisional</span>' if provisional else ""
        rows.append(
            '<div class="gn-formula__row" role="row">'
            f'<span class="gn-formula__w gn-fig" role="cell">{_pct(term["share"])}</span>'
            f'<span class="gn-formula__t" role="cell">{_e(term["name"])}'
            f'<small>{_e(term["definition"])}</small></span>'
            f'<span class="gn-formula__target gn-fig" role="cell">{_e(term["target_label"])}{tag}</span>'
            "</div>")
    note = (f'<p class="gn-note">{_e(axis["eligibility"])} '
            f'Source: <code>{_e(axis["code_ref"])}</code></p>')
    return (f'<div class="gn-formula" role="table" aria-label="{_e(axis["name"])} formula">'
            + "".join(rows) + "</div>" + note)


def render_rubric_scale(data, axis_id):
    """The calibrated 0-100 scale with one band per level."""
    axis = find_axis(data, axis_id)
    if not axis["rubric"]:
        return ('<div class="gn-not-scored"><span class="gn-label">Not scored yet</span>'
                "<p>Levels appear here once the band is validated against production data.</p></div>")
    floors = [lvl["floor"] for lvl in data["levels"]]
    edges = floors + [100]
    ticks = []
    for x in range(0, 101, 5):
        cls = "cut" if x in floors[1:] else "major" if x % 25 == 0 else ""
        ticks.append(f'<i class="{cls}" style="left:{x}%"></i>')
    for x in floors[1:]:
        if x % 5:
            ticks.append(f'<i class="cut" style="left:{x}%"></i>')
        ticks.append(f'<b style="left:{x}%">{x}</b>')
    ramp = ["var(--chart-track)", "var(--chart-3)", "var(--chart-3)",
            "var(--chart-2)", "var(--chart-2)", "var(--chart-1)"]
    track, bands = [], []
    for i, band in enumerate(axis["rubric"]):
        lo, hi = edges[i], edges[i + 1]
        width = hi - lo
        upper = hi if hi == 100 else hi - 1
        track.append(f'<span style="width:{width}%;background:{ramp[i]}"></span>')
        nxt = f'<p class="gn-band__next">{_e(band["next"])}</p>' if band["next"] else ""
        bands.append(
            '<div class="gn-band">'
            f'<div class="gn-label gn-band__name">{_e(band["level"])}</div>'
            f'<div class="gn-band__range gn-fig">{lo}–{upper}</div>'
            f'<p class="gn-band__look">{_e(band["looks_like"])}</p>{nxt}</div>')
    return (f'<div class="gn-scale" role="group" aria-label="{_e(axis["name"])} rubric, 0 to 100">'
            f'<div class="gn-scale__ticks" aria-hidden="true">{"".join(ticks)}</div>'
            f'<div class="gn-scale__track" aria-hidden="true">{"".join(track)}</div>'
            f'<div class="gn-scale__bands">{"".join(bands)}</div></div>'
            '<p class="gn-note">Levels use the same cut-offs as the overall AQ tiers, '
            "so a level means the same thing on every axis.</p>")


def render_axis_rail(data, axis_id):
    """Right-hand 'at a glance' rail: weights and per-source coverage."""
    axis = find_axis(data, axis_id)
    pillar = find_pillar(data, axis["pillar"])
    if _scored(axis):
        eff = effective_weight(data, axis_id)
        detail = "" if eff == axis["base_weight"] else f' (effective; base {axis["base_weight"]}%)'
        stats = (f'<div class="gn-stat"><div class="gn-stat__v gn-fig">{_fmt_weight(eff)}<small>%</small></div>'
                 f'<div class="gn-stat__k">of the {_e(pillar["name"])} pillar{detail}</div></div>'
                 f'<div class="gn-stat"><div class="gn-stat__v gn-fig">{share_of_aq(data, axis_id)}<small>%</small></div>'
                 '<div class="gn-stat__k">of the total AQ score</div></div>')
    else:
        stats = ('<div class="gn-stat"><div class="gn-stat__v gn-stat__v--muted">Not scored yet</div>'
                 f'<div class="gn-stat__k">base weight {axis["base_weight"]}% of {_e(pillar["name"])}, '
                 "carried by its sibling while withheld</div></div>")
    if not _scored(axis):
        return f'<aside class="gn-rail" aria-label="At a glance">{stats}</aside>'
    states = coverage(data, axis_id)
    items = []
    for source_id, source in data["sources"].items():
        state = states[source_id]
        if state == "partial":
            word = f'Partial ({", ".join(partial_terms(data, axis_id, source_id))})'
        else:
            word = _STATE_WORDS[state]
        items.append(f'<li><span class="gn-cov__s">{_e(source["label"])}</span>'
                     f'<span class="gn-cov gn-cov--{state}">{_e(word)}</span></li>')
    return (f'<aside class="gn-rail" aria-label="At a glance">{stats}'
            '<span class="gn-label">Measured in</span>'
            f'<ul class="gn-cov-list">{"".join(items)}</ul>'
            '<p class="gn-note">Not scored removes the axis from the profile. '
            "It never counts as a zero.</p></aside>")


def _axis_link(axis, base_url):
    href = f'{base_url}/{axis["page"][:-len(".md")]}/'
    return f'<a href="{_e(href)}">{_e(axis["name"])}</a>'


def render_rubric_matrix(data, base_url=""):
    """Every scored axis x level, using each band's 'looks like' text."""
    head = "".join(f'<th scope="col">{_e(lvl["name"])}</th>' for lvl in data["levels"])
    rows = []
    for pillar in data["pillars"]:
        for axis in pillar["axes"]:
            if not axis["rubric"]:
                continue
            cells = "".join(f"<td>{_e(b['looks_like'])}</td>" for b in axis["rubric"])
            rows.append(f'<tr><th scope="row">{_axis_link(axis, base_url)}'
                        f'<span class="gn-label">{_e(pillar["name"])}</span></th>{cells}</tr>')
    return (f'<div class="gn-matrix"><table><thead><tr><th scope="col">Axis</th>{head}</tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>')


def render_pillar_axes(data, pillar_id, base_url=""):
    """The pillar's axes with their weights and one-line theses."""
    pillar = find_pillar(data, pillar_id)
    items = []
    for axis in pillar["axes"]:
        weight = (f'{_fmt_weight(effective_weight(data, axis["id"]))}%'
                  if _scored(axis) else "Not scored yet")
        items.append(f'<li><span class="gn-axes__w gn-fig">{weight}</span>'
                     f'<span class="gn-axes__t">{_axis_link(axis, base_url)}'
                     f'<small>{_e(axis["thesis"])}</small></span></li>')
    return (f'<p class="gn-thesis">{_e(pillar["summary"])}</p>'
            f'<p class="gn-note">{pillar["weight"]}% of the AQ score.</p>'
            f'<ul class="gn-axes">{"".join(items)}</ul>')


def render_pillars_table(data, base_url=""):
    """The AQ formula as one row per pillar."""
    formula = " + ".join(f'{p["weight"] / 100:.2f}·{p["name"]}' for p in data["pillars"])
    rows = "".join(
        '<div class="gn-formula__row" role="row">'
        f'<span class="gn-formula__w gn-fig" role="cell">{p["weight"]}%</span>'
        f'<span class="gn-formula__t" role="cell"><a href="{_e(base_url)}/metrics/{p["id"]}/">{_e(p["name"])}</a>'
        f'<small>{_e(p["summary"])}</small></span>'
        f'<span class="gn-formula__target gn-fig" role="cell">{len(p["axes"])} axes</span></div>'
        for p in data["pillars"])
    return (f'<p class="gn-equation gn-fig">AQ = {formula}</p>'
            f'<div class="gn-formula" role="table" aria-label="AQ pillars">{rows}</div>')


def render_coverage_matrix(data, base_url=""):
    """Source x axis matrix of what each source can measure."""
    sources = list(data["sources"].items())
    head = "".join(f'<th scope="col">{_e(s["label"])}</th>' for _, s in sources)
    rows = []
    for pillar in data["pillars"]:
        for axis in pillar["axes"]:
            if not _scored(axis):
                continue
            states = coverage(data, axis["id"])
            cells = []
            for source_id, _ in sources:
                state = states[source_id]
                word = "Partial" if state == "partial" else _STATE_WORDS[state]
                title = (f' title="{_e(", ".join(partial_terms(data, axis["id"], source_id)))}"'
                         if state == "partial" else "")
                cells.append(f'<td class="gn-cov gn-cov--{state}"{title}>{word}</td>')
            rows.append(f'<tr><th scope="row">{_axis_link(axis, base_url)}</th>{"".join(cells)}</tr>')
    return (f'<div class="gn-matrix"><table><thead><tr><th scope="col">Axis</th>{head}</tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>')


def define_env(env):
    """Register the site's macros with mkdocs-macros."""
    import json
    from pathlib import Path

    with (Path(env.project_dir) / "docs" / "data" / "metrics.json").open(encoding="utf-8") as f:
        data = json.load(f)
    env.variables["metrics"] = data

    def base_url():
        return _rel_root(env)

    @env.macro
    def axis_info(axis_id):
        return find_axis(data, axis_id)

    @env.macro
    def formula(axis_id):
        return render_formula(data, axis_id)

    @env.macro
    def rubric_scale(axis_id):
        return render_rubric_scale(data, axis_id)

    @env.macro
    def axis_rail(axis_id):
        return render_axis_rail(data, axis_id)

    @env.macro
    def rubric_matrix():
        return render_rubric_matrix(data, base_url())

    @env.macro
    def pillar_axes(pillar_id):
        return render_pillar_axes(data, pillar_id, base_url())

    @env.macro
    def pillars_table():
        return render_pillars_table(data, base_url())

    @env.macro
    def coverage_matrix():
        return render_coverage_matrix(data, base_url())


def _rel_root(env):
    """Relative path from the current page to the site root, without a trailing slash."""
    depth = env.page.url.rstrip("/").count("/") + (1 if env.page.url.strip("/") else 0)
    return "/".join([".."] * depth) or "."
