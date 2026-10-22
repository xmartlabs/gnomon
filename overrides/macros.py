"""mkdocs-macros entry point for the gnomon docs site.

Every number a reader sees on a metrics page is rendered from
docs/data/metrics.json by the functions in this module. The pure helpers at the
top take the parsed data as an argument so tests can call them without MkDocs.
"""


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


def define_env(env):
    """Register the site's macros with mkdocs-macros."""
