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

Which payloads can be replayed -- FORMULA vs COUNTER. Re-applying the LIVE
scorers to an old payload is the feature (that is why the inputs are
persisted at all), so a payload scored under an older `score_contract_id`,
`aq_version` or `gstack_version` replays normally and deliberately gets the
new formula. `scoring_inputs_version` is the one field that cannot be
replayed across: it versions what the stored numbers MEAN, and
`stats_from_scoring_block` reads them verbatim. A payload from before the
v8 skill-counting dedup carries PRE-dedup counters that no live formula can
repair, so `replay()` raises `IncompatibleScoringInputs` (a `ReplayError`
AND an `IncompatibleScoreContract`) for anything outside
[`SKILL_DEDUP_INPUTS_VERSION`, `SCORING_INPUTS_VERSION`] -- see
`_require_comparable_scoring_inputs` for the full argument.

Coverage contract -- READ THIS before trusting a replay() result. Exactness
is NOT uniform across payload shapes; the return value's `aq_exactness`
field tells a caller which regime it got:

  - **Single-source payloads are EXACT.** The source's own
    `scoring_inputs_by_source[<source>].window` block IS the corpus block --
    there is only one source, so nothing was pooled away. `replay()`
    reproduces `payload["profile"]["aq"]` bit-for-bit (`aq_exactness ==
    "exact"`), including its 65/35 recency blend when
    `bucket_scoring_inputs` carries one. The same corpus-IS-the-source
    equivalence also makes `profiles_by_source` exact for single-source
    payloads (see below) even though `bucket_scoring_inputs.by_source` is
    always trimmed from the shipped payload.

  - **Multi-source payloads are APPROXIMATE.** An earlier revision of this
    module also shipped a `scoring_inputs_corpus` merged-corpus block so
    multi-source replay could be exact too, but that block costs ~487 KB on
    real 8-source data -- measured to push a real payload from ~89% to ~149%
    of the mirdash ingest cap -- and exactness was its ONLY value. The
    requirement was relaxed: approximate multi-source recompute is
    acceptable, so the merged-corpus `.window` block is never shipped, for
    any source count. Two distinct approximate regimes exist, and callers
    MUST branch on `aq_exactness` to tell them apart -- silently treating
    them as interchangeable reproduces the exact window-semantics bug this
    fix addressed:

    - `aq_exactness == "approximate_weighted_mean_unblended"`: the base
      value -- the tool-volume-weighted mean of each source's OWN
      full-window scored AQ (`score_by_source`'s documented aggregation
      rule; see `aggregate.py`'s module docstring). No recency blend of any
      kind is reflected: every source is scored 100% full-window, even
      though live/canonical scoring blends 65% recent + 35% full-window.
      This is the value returned when no bucket data is available to blend
      at all (no recency blend was ever shipped for this payload, or the
      shipped merged-corpus bucket genuinely carried zero sessions).

    - `aq_exactness == "approximate_weighted_mean"`: the base value above,
      further blended (65/35) against `bucket_scoring_inputs.corpus` -- the
      one merged-corpus recency bucket the payload DOES ship unconditionally
      whenever the recency blend is enabled (`bucket_scoring_inputs.by_source`,
      the per-SOURCE breakdown, is what gets trimmed; the merged corpus
      bucket does not). This recovers PART of the recency signal missing
      from the unblended base value, at zero additional payload bytes, but
      it is still an approximation: it blends one merged-corpus recent
      reading against a MEAN of per-source full-window readings, not the
      canonical per-source-then-aggregate blend `payload["profile"]["aq"]`
      itself uses. **Do not assume this equals
      `payload["profiles_by_source"]["aggregate"]["aq_diagnostic"]`** --
      that field is computed by `gnomon/output/summary.py` from the FULL,
      untrimmed per-source bucket breakdown (a real per-source blend for
      each source), which this module cannot reconstruct from a shipped
      payload at all; the two are expected to diverge whenever a blend
      fired. Nor does either approximate value equal
      `payload["profile"]["aq"]` (the merged-corpus canonical value, where
      distinct counts stay unions rather than per-source means; see
      `aggregate.py` for measured gaps of several points on real corpora).

    Model-less sources are simply weighted in normally in both regimes
    (`score_by_source`'s aggregation already treats missing per-axis
    capability as N/A, not a penalty) -- there is no raise for a model-less
    source in this path, unlike the retired exact reconstruction.

  - **`profiles_by_source` is a SEPARATE, secondary surface with its own
    coverage limit, independent of `aq_exactness` above.** It is exact
    (`profiles_by_source_status == "exact"`) whenever the payload either
    carries `bucket_scoring_inputs.by_source`, is single-source (the
    corpus-IS-the-source equivalence above applies here too, so a
    single-source payload is ALWAYS exact regardless of the by_source trim),
    or never blended a recency bucket for this corpus in the first place.
    For multi-source payloads where `bucket_scoring_inputs.by_source` is
    absent AND a real recency blend fired for at least one bucket, the
    per-source blend genuinely cannot be reconstructed from this payload
    alone -- `replay()` returns `profiles_by_source: None` and
    `profiles_by_source_status: "not_replayable_by_source_bucket_trimmed"`
    rather than silently returning an unblended (wrong) dict. This check is
    STRUCTURAL (it inspects the payload's own bucket data directly), never
    dependent on a self-reported `payload_features.omitted` marker string.
"""
from gnomon.config import SOURCE_CAPS
from gnomon.scoring.aggregate import HISTORY_WEIGHT, _blend_aq, score_by_source
from gnomon.scoring.aq import compute_aq
from gnomon.scoring.profiles import model_usage_from_models, stats_from_scoring_block
from gnomon.scoring.versioning import (
    IncompatibleScoreContract, SCORING_INPUTS_VERSION, SKILL_DEDUP_INPUTS_VERSION,
)


class ReplayError(ValueError):
    """Raised when a payload cannot be replayed at all: missing, empty, or
    structurally incompatible data that would force replay() to guess rather
    than compose from the scorers directly."""


class IncompatibleScoringInputs(ReplayError, IncompatibleScoreContract):
    """Raised when the payload's persisted COUNTERS are not comparable to the
    live targets, whatever the formula does with them -- see
    `_require_comparable_scoring_inputs`.

    Deliberately BOTH a ReplayError and an IncompatibleScoreContract: a caller
    walking a store of payloads already catches ReplayError and skips the ones
    it cannot recompute, and a contract-aware caller (COMPARISON_POLICY is
    `same_score_contract_id_only`) already catches IncompatibleScoreContract.
    Neither has to learn a new exception type to stay correct, and neither can
    end up holding a silently wrong number."""


# profiles_by_source_status values -- callers should branch on this single
# field rather than inferring replayability from other payload shape.
PROFILES_BY_SOURCE_EXACT = "exact"
PROFILES_BY_SOURCE_NOT_REPLAYABLE_TRIMMED = "not_replayable_by_source_bucket_trimmed"

# aq_exactness values -- callers should branch on this to know whether
# result["aq"] reproduces payload["profile"]["aq"] bit-for-bit or is a
# best-effort approximation. See the module docstring's Coverage contract.
AQ_EXACT = "exact"
AQ_APPROXIMATE_WEIGHTED_MEAN = "approximate_weighted_mean"
# The multi-source base value (tool-volume-weighted mean of per-source AQs)
# could NOT be blended against the merged-corpus recency bucket -- either no
# recency blend was ever shipped for this payload, or the corpus bucket
# genuinely carried zero sessions. A caller that needs to know whether window
# semantics stayed 100% full-window (this value) or partially recovered the
# recency blend (AQ_APPROXIMATE_WEIGHTED_MEAN) should branch on this.
AQ_APPROXIMATE_WEIGHTED_MEAN_UNBLENDED = "approximate_weighted_mean_unblended"


def _claimed_source_ids(block):
    """The source id(s) a scoring-input block declares, preferring
    corpus.sources over the composite `source` string -- mirrors
    stats_from_scoring_block's own preference (profiles.py:33-34)."""
    corpus_sources = (block.get("corpus") or {}).get("sources")
    if corpus_sources:
        return set(corpus_sources.keys())
    source = block.get("source")
    return set(str(source).split(",")) if source else set()


def _require_comparable_scoring_inputs(payload):
    """Refuse payloads whose persisted COUNTERS cannot be scored by this code.

    Replay exists so a METRIC change can be re-applied to old raw inputs -- that
    is the whole point of persisting them (commit be07bf5), and it is why this
    function does NOT compare `score_contract_id`, `aq_version` or
    `gstack_version`: a payload scored under an older FORMULA is exactly the
    case replay is for, and refusing on a contract mismatch would delete the
    feature.

    `scoring_inputs_version` is different in kind. It versions what the numbers
    in the block MEAN, and `profiles.py::stats_from_scoring_block` reads that
    block verbatim -- it never re-derives a counter from transcripts, which it
    could not do anyway (a payload carries no transcripts). So when a counter's
    definition changes, no live formula can repair the stored value:

      - Below SKILL_DEDUP_INPUTS_VERSION the skill counters are PRE-dedup, i.e.
        one count per attributed turn rather than one per (session, skill) span
        -- 4.0x larger pooled, 25.8x on Claude. Dividing that by v9's 28x
        smaller SKILLS_TOTAL_PER_CALL_TARGET saturates Skill fluency and
        Verification on arithmetic alone, and the result looks like a score.
      - Above SCORING_INPUTS_VERSION the counters were produced by an inputs
        version this code does not implement, so their semantics are simply
        unknown. Same fail-closed answer.
      - Absent or non-integer: gnomon stamps this field unconditionally
        (gnomon/output/summary.py), so a payload without it is foreign or
        hand-built and its counter semantics are equally unknown. `bool` is
        rejected explicitly -- `True` is an int in Python and would otherwise
        read as version 1.

    Raising, rather than returning a "non-comparable" flag: every existing
    result regime (exact / approximate) means "usable, with known error bars",
    and this is not an error-bar problem -- the numerator is a different
    quantity, so no band covers it. A new flag would also be silently ignorable
    by the callers that most need it, whereas an exception cannot be, and
    replay()'s stated contract is already to fail loudly rather than let a
    caller hold a plausible-but-wrong number. A caller that wants to enumerate
    old payloads catches it and skips.
    """
    version = payload.get("scoring_inputs_version")
    if isinstance(version, bool) or not isinstance(version, int):
        raise IncompatibleScoringInputs(
            f"payload declares no usable scoring_inputs_version ({version!r}) -- "
            f"replay() cannot tell whether its counters are comparable to this "
            f"code's targets (expected an int in "
            f"[{SKILL_DEDUP_INPUTS_VERSION}, {SCORING_INPUTS_VERSION}])")
    if version < SKILL_DEDUP_INPUTS_VERSION:
        raise IncompatibleScoringInputs(
            f"payload scoring_inputs_version {version} predates the skill-counting "
            f"dedup (v{SKILL_DEDUP_INPUTS_VERSION}), so its skill counters are "
            f"PRE-dedup (4.0x larger pooled, 25.8x on Claude) while this code scores "
            f"them against post-dedup targets -- replay() refuses rather than "
            f"publishing an over-saturated number. The formula can be replayed on old "
            f"inputs; a changed COUNTER cannot.")
    if version > SCORING_INPUTS_VERSION:
        raise IncompatibleScoringInputs(
            f"payload scoring_inputs_version {version} is newer than this code's "
            f"v{SCORING_INPUTS_VERSION} -- its counters were produced by an inputs "
            f"version not implemented here, so their meaning is unknown")


def _require_known_source_identity(src_key, window_block):
    """gnomon/config.py::available_caps([]) and available_caps(["unknown"])
    both fail OPEN to the full capability set (unknown sources are assumed
    fully capable, by design, for sources gnomon simply hasn't mapped yet in
    SOURCE_CAPS). That is safe for gnomon's OWN emitted payloads, where every
    block's declared source is always a real, mapped source id -- but
    replay() is explicitly a foreign-payload entry point (see the module
    docstring), so a block that resolves to no KNOWN source id must not
    silently score with full capabilities and still get labelled exact/
    approximate as if it were a real, capability-bounded source."""
    claimed = _claimed_source_ids(window_block)
    if not (claimed & SOURCE_CAPS.keys()):
        raise ReplayError(
            f"scoring_inputs_by_source[{src_key!r}].window resolves to no "
            f"KNOWN source id ({sorted(claimed) or 'none'}) -- available_caps() "
            f"would fail OPEN (full capabilities) for an unrecognized source, "
            f"so replay() refuses rather than silently over-crediting a "
            f"foreign payload")


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


def _profiles_by_source_status(bucket_by_source, bucket_corpus):
    """Return one of the PROFILES_BY_SOURCE_* constants for this payload.

    This is a STRUCTURAL check -- it never trusts a payload's self-reported
    payload_features.omitted list to decide whether the per-source recency
    blend is reconstructable. A previous revision short-circuited on a literal
    {"feature": "bucket_scoring_inputs.by_source"} marker instead of the real
    condition below; that meant a future rename of the marker string, or any
    hand-built/foreign payload that never emits one, would silently label a
    genuinely non-replayable payload "exact" -- reintroducing the exact
    silently-wrong-dict bug the previous review round fixed, just without the
    marker present to trigger the guard.

    profiles_by_source can only diverge from the real payload's value when the
    payload BOTH:
      (a) has no per-source bucket breakdown to replay a recency blend per
          source (bucket_by_source empty/missing), AND
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


def _replay_multisource_approximate_aq(sibs, bucket_by_source, bucket_metadata, bucket_corpus):
    """APPROXIMATE combined-AQ replay for a multi-source payload. Returns
    (aq, aq_exactness) -- see AQ_APPROXIMATE_WEIGHTED_MEAN vs
    AQ_APPROXIMATE_WEIGHTED_MEAN_UNBLENDED below.

    There is no merged-corpus block to compose an EXACT AQ from (see the
    module docstring's Coverage contract), so the base value is the same
    tool-volume-weighted mean of per-source scored AQs that
    `score_by_source`'s `aggregate.aq_diagnostic` already implements -- built
    here straight from the payload's own per-source window blocks, with no
    reimplemented aggregation math. `bucket_by_source` is always empty in a
    shipped payload (see local.py's unconditional trim), so this base value
    never carries a per-source recency blend.

    bucket_scoring_inputs.corpus -- the merged-corpus recency bucket -- DOES
    ship unconditionally whenever the recency blend is enabled, and is
    otherwise unused by this path. Blending the base value against it recovers
    PART of the corpus-level recency signal the per-source base value is
    missing (see the module docstring): this is a coarser blend than the
    canonical one (one merged bucket vs one full-corpus AQ, not per-source),
    but it is strictly closer to `payload["profile"]["aq"]` than ignoring the
    shipped bucket entirely, at zero additional payload bytes."""
    sbs = score_by_source(
        sibs,
        bucket_scoring_inputs_by_source=bucket_by_source or None,
        bucket_metadata=bucket_metadata or None,
    )
    aggregate = sbs.get("aggregate")
    if not aggregate:
        raise ReplayError(
            "no per-source profiles available to approximate a combined AQ")
    diag = aggregate["aq_diagnostic"]

    components = []
    for meta in (bucket_metadata or []):
        entry = (bucket_corpus or {}).get(meta.get("id"))
        if not entry or not entry.get("window"):
            continue  # this bucket genuinely carried no merged-corpus data in this payload
        bblock = entry["window"]
        if (bblock.get("volume", {}).get("total_sessions", 0) or 0) <= 0:
            continue  # mirrors local.py's own zero-session skip

        configured_weight = meta.get("configured_weight", 0)
        if not isinstance(configured_weight, (int, float)) or configured_weight <= 0:
            raise ReplayError(
                f"bucket {meta.get('id')!r} has invalid configured_weight "
                f"{configured_weight!r} -- cannot blend the merged-corpus "
                f"recency bucket into the approximate multi-source AQ")

        bstats = stats_from_scoring_block(bblock)
        components.append(dict(meta, aq=compute_aq(bstats)))

    if not components:
        return diag, AQ_APPROXIMATE_WEIGHTED_MEAN_UNBLENDED

    components.append({
        "id": "full_window",
        "configured_weight": HISTORY_WEIGHT,
        "aq": diag,
    })
    return _blend_aq(diag, components), AQ_APPROXIMATE_WEIGHTED_MEAN


def replay(payload):
    """Return {"aq": <combined AQ dict>,
               "aq_exactness": "exact" | "approximate_weighted_mean"
                                | "approximate_weighted_mean_unblended",
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

    # Before any scoring: are this payload's COUNTERS even comparable to the live
    # targets? A formula change is replayable by design; a counter-definition change
    # is not. See _require_comparable_scoring_inputs.
    _require_comparable_scoring_inputs(payload)

    sibs = payload.get("scoring_inputs_by_source")
    if not sibs:
        raise ReplayError("scoring_inputs_by_source is empty or missing")
    sources = sorted(sibs.keys())

    for src in sources:
        _require_known_source_identity(src, (sibs.get(src) or {}).get("window") or {})

    # Prefer source ACTIVITY over raw key count for the single/multi decision:
    # a payload can carry a key for every source gnomon discovers, even ones
    # with zero sessions this window, and the merged corpus equals the ONE
    # genuinely active source exactly in that case (the same equivalence
    # _replay_single_source_aq already exploits). Falls back to the raw key
    # set when nothing is active at all (nothing to blend either way).
    active_sources = sorted(
        src for src in sources
        if ((sibs.get(src) or {}).get("window") or {}).get(
            "volume", {}).get("total_sessions", 0) > 0
    ) or sources

    bucket = payload.get("bucket_scoring_inputs") or {}
    bucket_metadata = bucket.get("metadata") or []
    bucket_corpus = bucket.get("corpus") or {}
    bucket_by_source = bucket.get("by_source") or {}

    # Single-source equivalence: a single source's own bucket_corpus window
    # block IS that one source's per-source bucket block -- nothing was pooled
    # away, exactly the equivalence _replay_single_source_aq already exploits
    # for `aq` (see local.py's own single_source optimization). by_source is
    # trimmed unconditionally today, so without this a single-source payload
    # would needlessly fall back to profiles_by_source: None even though the
    # data to replay it exactly is right there in bucket_corpus.
    if len(sources) == 1 and not bucket_by_source and bucket_corpus:
        bucket_by_source = {
            bucket_id: {sources[0]: {"window": entry["window"]}}
            for bucket_id, entry in bucket_corpus.items()
            if entry.get("window")
        }

    # (a) per-source profiles + per-source 65/35 blend -- payload["profiles_by_source"].
    # See _profiles_by_source_status's docstring: this is NOT always replayable,
    # independent of the combined-AQ exactness computed below.
    profiles_by_source_status = _profiles_by_source_status(
        bucket_by_source, bucket_corpus)
    if profiles_by_source_status == PROFILES_BY_SOURCE_NOT_REPLAYABLE_TRIMMED:
        profiles_by_source = None
    else:
        profiles_by_source = _profiles_by_source(sibs, bucket_by_source, bucket_metadata)

    # (b) combined AQ -- exact for single-source, approximate for multi-source.
    if len(active_sources) == 1:
        aq = _replay_single_source_aq(
            sibs[active_sources[0]]["window"], sibs, bucket_metadata, bucket_corpus)
        aq_exactness = AQ_EXACT
    else:
        aq, aq_exactness = _replay_multisource_approximate_aq(
            sibs, bucket_by_source, bucket_metadata, bucket_corpus)

    return {
        "aq": aq,
        "aq_exactness": aq_exactness,
        "profiles_by_source": profiles_by_source,
        "profiles_by_source_status": profiles_by_source_status,
    }
