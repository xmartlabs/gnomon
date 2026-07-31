# v8 — Honest AQ series: skill-counting dedup (a Skill invocation now counts once per
# invocation, not once per assistant/sidechain turn carrying attributionSkill -- a real
# corpus previously inflated e.g. judgment-day from 1 to 196) + the review-skill matcher's
# exact-tail "verify" fix + git_churn scoped to the corpus's observed span. All three
# component versions bump together and last, so no intermediate commit in the change
# publishes a payload whose score_contract_id claims v7 semantics while the counting
# logic underneath has already changed (aggregate._blend_aq raises on any mixed
# contract). Reverting the dedup fix alone (keeping the v8 stamp) is a harmless cohort
# split; reverting the version bump alone (keeping the dedup fix) is FORBIDDEN -- it
# would silently stamp new-behavior rows with the old contract. See
# tests/test_score_contract_atomicity.py, which asserts both facts in one test so a
# partial revert is caught mechanically.
#
# v7 — Per-tool-call rate denominators + one canonical combined AQ. All three bump together
# and last, so every intermediate commit in the change stays internally consistent:
# aggregate._blend_aq raises on any mixed contract, so bumping component-by-component would
# publish three different universes inside one PR.
#   inputs: `volume.tool_calls_total` becomes load-bearing for scoring — it is now the
#           denominator of every rate term, so a payload that OMITS it scores differently
#           (those terms drop to N/A and renormalize) rather than merely losing a diagnostic.
#           No field is added or renamed; what changed is which existing field is required.
#   aq:     the six rate terms score count-per-TOOL-CALL instead of count-per-SESSION, against
#           targets recalibrated into per-tool-call units. One session is not one unit of work
#           across tools: a batch of 2-minute one-shot CLI sessions acted as near-pure
#           denominator and collapsed the rate of a habit genuinely practised elsewhere.
#           Pooling numerator and denominator over the same unit is what makes this safe —
#           Sigma x / Sigma c is the tool-call-share-weighted mean of the per-source rates, so
#           the corpus rate can never land outside the range its sources span.
#   gstack: unchanged logic; it moves with the pair because the published payload now carries
#           exactly ONE combined AQ (`profile.aq`) and demotes the per-source score blend to
#           `profiles_by_source.aggregate.aq_diagnostic`.
# NOTE for whoever recalibrates next: there is NO per-source rate weighting and no
# capability-based exclusion from a rate denominator. An earlier draft of v7 weighted
# per-session rates by each source's tool volume; review rejected it because the resulting
# mean mixes units (tool_calls x things/session is not a quantity) and inverts. Do not
# reintroduce it — see the comment above `rate()` in aq.py for the measured counter-example.
SCORING_INPUTS_VERSION = 8
AQ_VERSION = 8
GSTACK_VERSION = 8
SCORE_CONTRACT_ID = f"{SCORING_INPUTS_VERSION}:{AQ_VERSION}:{GSTACK_VERSION}"
COMPARISON_POLICY = "same_score_contract_id_only"


class IncompatibleScoreContract(ValueError):
    pass
