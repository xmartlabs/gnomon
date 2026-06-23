from gnomon.scoring.inputs import build_scoring_inputs


def build_scoring_inputs_by_source(
    sources, since_dt, until_dt, cursor_twins, antigravity,
    accumulate_fn, corpus_stats=None,
):
    """Run accumulation per source and shape window + monthly scoring inputs."""
    by_source = {}
    srcs_present = sorted({s for s, _, _ in sources})
    single_source = corpus_stats is not None and len(srcs_present) == 1
    for src in srcs_present:
        if single_source:
            s_stats = corpus_stats
        else:
            src_sources = [(s, fp, fmt) for (s, fp, fmt) in sources if s == src]
            s_stats, _ = accumulate_fn(
                src_sources, since_dt, until_dt, cursor_twins, antigravity,
                total_file_count=len(src_sources), verbose=False)
        window = build_scoring_inputs(s_stats)
        monthly = [
            dict(build_scoring_inputs(entry["stats_full"]), month=entry["month"])
            for entry in s_stats.get("_scoring_monthly_full", [])
        ]
        by_source[src] = {"window": window, "monthly": monthly}
    return by_source
