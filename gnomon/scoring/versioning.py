# v7 — Activity-weighted rate denominators + one canonical combined AQ. All three bump
# together and last, so every intermediate commit in the change stays internally consistent:
# aggregate._blend_aq raises on any mixed contract, so bumping component-by-component would
# publish three different universes inside one PR.
#   inputs: unchanged in shape, but the per-source `window` blocks are now SCORING inputs for
#           the corpus AQ (they carry the per-source rate denominators), not only per-source
#           diagnostics — a payload missing them scores differently, so it is a contract change.
#   aq:     per-session rate terms score the tool-volume-weighted mean of PER-SOURCE rates
#           instead of one count pooled over the merged session count, and a source that
#           cannot record a signal is excluded from that mean rather than weighted in at zero.
#   gstack: unchanged logic; it moves with the pair because the published payload now carries
#           exactly ONE combined AQ (`profile.aq`) and demotes the per-source score blend to
#           `profiles_by_source.aggregate.aq_diagnostic`.
SCORING_INPUTS_VERSION = 7
AQ_VERSION = 7
GSTACK_VERSION = 7
SCORE_CONTRACT_ID = f"{SCORING_INPUTS_VERSION}:{AQ_VERSION}:{GSTACK_VERSION}"
COMPARISON_POLICY = "same_score_contract_id_only"


class IncompatibleScoreContract(ValueError):
    pass
