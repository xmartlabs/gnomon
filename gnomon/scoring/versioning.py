# v9 — The v8 dedup's calibration debt paid off. v8 made a Skill invocation count once per
# (session, skill) span, which is correct, but left SKILLS_TOTAL_PER_CALL_TARGET (0.25) and
# REVIEW_SKILLS_PER_CALL_TARGET (0.060) fitted against the PRE-dedup counter, so every
# post-v8 row scored heavy skill practice near zero. Two changes ship together because they
# are the same measurement:
#   inputs: `stack.skills_all` / `stack.skills_total` are unchanged in SHAPE, but the review
#           numerator derived from them moves: `_is_review_skill_name` now admits a
#           `verif`-LEADING tail (`verify-frontend`, `verify_changes`,
#           `verification-before-completion`) instead of only `verify` / `*-verify`. v8's
#           narrowing had dropped the prefix forms along with the false positive it targeted
#           (`email-verify-flow`), worth 2.2% of the pooled review numerator over 16 real
#           corpora and up to 59.5% for one user. The noun form was missed by v7 too, so
#           part of this is a new fix rather than a restoration.
#   aq:     SKILLS_TOTAL_PER_CALL_TARGET 0.25 -> 0.009 and REVIEW_SKILLS_PER_CALL_TARGET
#           0.060 -> 0.004, re-fitted/anchored on the post-dedup distribution (see the rate
#           rationale block at the top of aq.py for the sample, the projection model and its
#           uncertainty). The other four rate targets were re-measured and deliberately left
#           alone — the reasoning is written down there, because "the six move together" is
#           a denominator argument and the dedup only moved numerators.
#   gstack: unchanged logic; it moves with the pair for the same reason it did in v7 and v8
#           — aggregate._blend_aq raises on any mixed contract, so a partial bump would
#           publish two universes inside one PR.
# The matcher change and the re-fit MUST NOT be split: re-fitting the review target against
# a numerator that is still lossy would bake the matcher's gap into the calibration, and
# widening the matcher without the re-fit moves a published score with no contract move.
# gnomon/scoring/calibration.py registers 9:9:9's fingerprint; the 8:8:8 entry stays as the
# audit trail of what the pre-dedup calibration published.
#
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
SCORING_INPUTS_VERSION = 9
AQ_VERSION = 9
GSTACK_VERSION = 9
# The first SCORING_INPUTS_VERSION whose skill counters are DEDUPED: v8 (28d3bda) made a
# Skill invocation count once per (session, skill) span instead of once per assistant/
# sidechain turn carrying attributionSkill. That changed what the persisted counter MEANS,
# not just how it is scored -- measured on one full corpus, skills_total 17781 -> 4427
# (25.8x on Claude alone) and review_skills 4981 -> 597. Anything captured before it is a
# different quantity and cannot be re-scored against post-dedup targets; replay() refuses
# such a payload rather than publishing an over-saturated number (gnomon/scoring/replay.py).
SKILL_DEDUP_INPUTS_VERSION = 8
SCORE_CONTRACT_ID = f"{SCORING_INPUTS_VERSION}:{AQ_VERSION}:{GSTACK_VERSION}"
COMPARISON_POLICY = "same_score_contract_id_only"


class IncompatibleScoreContract(ValueError):
    pass
