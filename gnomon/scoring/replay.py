"""Recompute `profile.aq` from a persisted summary payload alone -- with zero
access to local transcripts.

Composition only, over the exact scorers `gnomon/cli/local.py` calls: no
duplicated formula constants, no reimplemented scoring path
(`stats_from_scoring_block`, `compute_aq`, `_blend_aq`, `score_by_source`).

`replay()` raises `ReplayError` rather than silently guessing whenever the
payload lacks data the original run genuinely depended on -- a
plausible-but-wrong number is worse than a loud failure. See
gnomon/output/summary.py's `payload_features` marker for what a given
payload actually shipped, and tests/test_payload_budget.py for why
`bucket_scoring_inputs.by_source` is omitted from the shipped payload (the
cheapest available payload-budget lever).

Coverage contract -- READ THIS before trusting a replay() result. Exactness
is NOT uniform across payload shapes; the return value's `aq_exactness`
field tells a caller which regime it got:

  - **Single-source payloads are EXACT.** The source's own
    `scoring_inputs_by_source[<source>].window` block IS the corpus block --
    there is only one source, so nothing was pooled away. `replay()`
    reproduces `payload["profile"]["aq"]` bit-for-bit (`aq_exactness ==
    "exact"`), including its 65/35 recency blend when
    `bucket_scoring_inputs` carries one.

  - **Multi-source payloads are APPROXIMATE (`aq_exactness ==
    "approximate_weighted_mean"`).** An earlier revision of this module also
    shipped a `scoring_inputs_corpus` merged-corpus block so multi-source
    replay could be exact too, but that block costs ~487 KB on real 8-source
    data -- measured to push a real payload from ~89% to ~149% of the
    mirdash ingest cap -- and exactness was its ONLY value: the same
    approximate combined AQ this module now returns was already
    reconstructible from the per-source blocks that ship regardless (see
    `gnomon.scoring.aggregate.score_by_source`'s `aggregate.aq_diagnostic`,
    which IS this computation). The requirement was relaxed: approximate
    multi-source recompute is acceptable, so the merged-corpus block is
    never shipped, for any source count. `replay()` derives the combined AQ
    as the tool-volume-weighted mean of each source's OWN scored AQ --
    exactly `score_by_source`'s documented aggregation rule (see
    `aggregate.py`'s module docstring) -- rather than compute_aq over a
    pooled corpus. This is NOT expected to equal `payload["profile"]["aq"]`
    (which is scored from the merged corpus so distinct counts stay unions,
    not per-source means; see `aggregate.py` for measured gaps of several
    points on real corpora). Model-less sources are simply weighted in
    normally (`score_by_source`'s aggregation already treats missing
    per-axis capability as N/A, not a penalty) -- there is no raise for a
    model-less source in this path, unlike the retired exact reconstruction.

  - **`profiles_by_source` is a SEPARATE, secondary surface with its own
    coverage limit, independent of `aq_exactness` above.** It is exact
    (`profiles_by_source_status == "exact"`) whenever the payload either
    carries `bucket_scoring_inputs.by_source` or never blended a recency
    bucket for this corpus in the first place. When the payload trimmed
    `bucket_scoring_inputs.by_source` (see `payload_features.omitted`) AND a
    real recency blend fired for at least one bucket, the per-source blend
    cannot be reconstructed from this payload alone -- `replay()` returns
    `profiles_by_source: None` and `profiles_by_source_status:
    "not_replayable_by_source_bucket_trimmed"` rather than silently
    returning an unblended (wrong) dict.
"""
from gnomon.scoring.aggregate import HISTORY_WEIGHT, _blend_aq, score_by_source
from gnomon.scoring.aq import compute_aq
from gnomon.scoring.profiles import model_usage_from_models, stats_from_scoring_block


class ReplayError(ValueError):
    """Raised when a payload cannot be replayed at all: missing, empty, or
    structurally incompatible data that would force replay() to guess rather
    than compose from the scorers directly."""


# profiles_by_source_status values -- callers should branch on this single
# field rather than inferring replayability from other payload shape.
PROFILES_BY_SOURCE_EXACT = "exact"
PROFILES_BY_SOURCE_NOT_REPLAYABLE_TRIMMED = "not_replayable_by_source_bucket_trimmed"

# aq_exactness values -- callers should branch on this to know whether
# result["aq"] reproduces payload["profile"]["aq"] bit-for-bit or is a
# best-effort approximation. See the module docstring's Coverage contract.
AQ_EXACT = "exact"
AQ_APPROXIMATE_WEIGHTED_MEAN = "approximate_weighted_mean"


def _profiles_by_source(sibs, bucket_by_source, bucket_metadata):
    """Mirrors gnomon/output/summary.py::_profiles_by_source exactly (including
    the per-source model_usage population score_by_source itself leaves empty).

    Only call this once `_profiles_by_source_status` has confirmed the result
    will actually be exact -- see that function's docstring for the payload
    shapes where this composition would otherwise silently return an
    unblended (wrong) per-source profile."""
    sbs = score_by_source(
        sibs,
        bucket_scoring_inputs_by_source=bucket_by_source or None,
        bucket_metadata=bucket_metadata or None,
    )
    for src, profile in (sbs.get("by_source") or {}).items():
        window = (sibs.get(src) or {}).get("window") or {}
        models = (window.get("stack") or {}).get("models") or []
        tok_by_model = {e["model_id"]: e
                        for e in ((window.get("token_usage") or {}).get("by_model") or [])}
        profile["model_usage"] = model_usage_from_models(models, tok_by_model)
    return sbs


def _profiles_by_source_status(bucket_by_source, bucket_corpus, payload_features):
    """Return one of the PROFILES_BY_SOURCE_* constants for this payload.

    profiles_by_source can only diverge from the real payload's value when the
    payload BOTH:
      (a) trimmed the per-source bucket breakdown needed to replay a recency
          blend per source -- signalled by payload_features.omitted naming
          "bucket_scoring_inputs.by_source" (see gnomon/cli/local.py, which
          always trims this field once RECENCY_BLEND_ENABLED is on), AND
      (b) a recency blend genuinely fired for at least one bucket in this
          payload, i.e. some
          bucket_scoring_inputs.corpus[<id>].window.volume.total_sessions > 0
          (a bucket with zero sessions never contributes to the blend --
          see local.py's own zero-session skip, mirrored in replay()).

    When the per-source breakdown IS present, or no blend ever fired for this
    corpus, the existing profiles_by_source composition is exact -- score_by_source
    with an empty/None bucket_scoring_inputs_by_source correctly falls back to the
    unblended full-window profile, which in that case IS the real value.
    """
    if bucket_by_source:
        return PROFILES_BY_SOURCE_EXACT
    omitted = (payload_features or {}).get("omitted") or []
    trimmed = any(
        isinstance(entry, dict) and entry.get("feature") == "bucket_scoring_inputs.by_source"
        for entry in omitted
    )
    if not trimmed:
        return PROFILES_BY_SOURCE_EXACT
    for entry in (bucket_corpus or {}).values():
        window = (entry or {}).get("window") or {}
        sessions = (window.get("volume") or {}).get("total_sessions", 0) or 0
        if sessions > 0:
            return PROFILES_BY_SOURCE_NOT_REPLAYABLE_TRIMMED
    return PROFILES_BY_SOURCE_EXACT


def _replay_single_source_aq(window_block, sibs, bucket_metadata, bucket_corpus):
    """EXACT combined-AQ replay for a single-source payload.

    A single source's own window block IS the corpus block (nothing was
    pooled away), so this mirrors local.py's own full-window + recency-blend
    computation exactly: compute_aq over the source's window, optionally
    blended (65/35) against the recent_30d bucket -- both read straight from
    the payload, no approximation involved."""
    full_stats = stats_from_scoring_block(window_block)
    full_stats["scoring_inputs_by_source"] = sibs
    full_aq = compute_aq(full_stats)

    if not bucket_metadata and not bucket_corpus:
        # No recency blend was shipped for this payload -- full_aq IS profile.aq.
        return full_aq

    if not bucket_metadata or not bucket_corpus:
        # aggregate.py's score_by_source silently falls back to the full-window
        # profile when bucket metadata/inputs are inconsistent (aggregate.py:674).
        # replay() must not repeat that silent fallback -- a payload advertising
        # a bucket without the data to blend it is a corrupted/incompatible
        # payload, not a legitimate no-blend state.
        raise ReplayError(
            "bucket_scoring_inputs is present without both metadata and corpus "
            "blocks -- cannot replay the recency blend exactly")

    components = []
    for meta in bucket_metadata:
        entry = bucket_corpus.get(meta["id"])
        if not entry or not entry.get("window"):
            continue  # this bucket genuinely carried no data in this payload
        bblock = entry["window"]
        if (bblock.get("volume", {}).get("total_sessions", 0) or 0) <= 0:
            continue  # mirrors local.py's own zero-session skip -- a bucket with
            # genuinely zero recent sessions needs no blend contribution.

        configured_weight = meta.get("configured_weight", 0)
        if not isinstance(configured_weight, (int, float)) or configured_weight <= 0:
            raise ReplayError(
                f"bucket {meta.get('id')!r} has invalid configured_weight "
                f"{configured_weight!r} -- cannot replay the blend exactly")

        bstats = stats_from_scoring_block(bblock)
        components.append(dict(meta, aq=compute_aq(bstats)))

    if not components:
        return full_aq

    components.append({
        "id": "full_window",
        "configured_weight": HISTORY_WEIGHT,
        "aq": full_aq,
    })
    return _blend_aq(full_aq, components)


def _replay_multisource_approximate_aq(sibs, bucket_by_source, bucket_metadata):
    """APPROXIMATE combined-AQ replay for a multi-source payload.

    There is no merged-corpus block to compose an exact AQ from (see the
    module docstring's Coverage contract), so this composes the same
    tool-volume-weighted mean of per-source scored AQs that
    `score_by_source`'s `aggregate.aq_diagnostic` already implements and the
    payload already publishes under `profiles_by_source.aggregate` --
    reconstructed here straight from the payload's own per-source blocks,
    with no reimplemented aggregation math."""
    sbs = score_by_source(
        sibs,
        bucket_scoring_inputs_by_source=bucket_by_source or None,
        bucket_metadata=bucket_metadata or None,
    )
    aggregate = sbs.get("aggregate")
    if not aggregate:
        raise ReplayError(
            "no per-source profiles available to approximate a combined AQ")
    return aggregate["aq_diagnostic"]


def replay(payload):
    """Return {"aq": <combined AQ dict>,
               "aq_exactness": "exact" | "approximate_weighted_mean",
               "profiles_by_source": <dict | None>,
               "profiles_by_source_status": <PROFILES_BY_SOURCE_* str>}
    using only the raw scoring-input blocks the payload carries. See the
    module docstring's Coverage contract for exactly what "exact" and
    "approximate" mean here, and for profiles_by_source's independent
    coverage limit."""
    payload_features = payload.get("payload_features")
    if not payload_features:
        raise ReplayError(
            "payload_features absent -- this payload predates the "
            "recompute-grade-payload capability and cannot be replayed")

    sibs = payload.get("scoring_inputs_by_source")
    if not sibs:
        raise ReplayError("scoring_inputs_by_source is empty or missing")
    sources = sorted(sibs.keys())

    bucket = payload.get("bucket_scoring_inputs") or {}
    bucket_metadata = bucket.get("metadata") or []
    bucket_corpus = bucket.get("corpus") or {}
    bucket_by_source = bucket.get("by_source") or {}

    # (a) per-source profiles + per-source 65/35 blend -- payload["profiles_by_source"].
    # See _profiles_by_source_status's docstring: this is NOT always replayable,
    # independent of the combined-AQ exactness computed below.
    profiles_by_source_status = _profiles_by_source_status(
        bucket_by_source, bucket_corpus, payload_features)
    if profiles_by_source_status == PROFILES_BY_SOURCE_NOT_REPLAYABLE_TRIMMED:
        profiles_by_source = None
    else:
        profiles_by_source = _profiles_by_source(sibs, bucket_by_source, bucket_metadata)

    # (b) combined AQ -- exact for single-source, approximate for multi-source.
    if len(sources) == 1:
        aq = _replay_single_source_aq(
            sibs[sources[0]]["window"], sibs, bucket_metadata, bucket_corpus)
        aq_exactness = AQ_EXACT
    else:
        aq = _replay_multisource_approximate_aq(sibs, bucket_by_source, bucket_metadata)
        aq_exactness = AQ_APPROXIMATE_WEIGHTED_MEAN

    return {
        "aq": aq,
        "aq_exactness": aq_exactness,
        "profiles_by_source": profiles_by_source,
        "profiles_by_source_status": profiles_by_source_status,
    }
