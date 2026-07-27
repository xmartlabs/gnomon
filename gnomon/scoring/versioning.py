# v6 — Planning practice. All three bump together and last, so every intermediate commit in
# the change stays internally consistent: aggregate._blend_aq raises on any mixed contract,
# so bumping component-by-component would publish three different universes inside one PR.
#   inputs: the qualified planning numerator now admits plan mode, and a planning_dispatch_calls
#           count is subtracted from the explore-to-doing denominator.
#   aq:     Discipline's planning term is a frequency against a target, not a binary
#           skill-presence check, and it is gated on the new planning_signal capability.
#   gstack: the Planning practice target is 0.30 (was an unanchored 0.40), the sub label
#           dropped the now-false "skill", and plan-mode/todo tools plus planning
#           dispatches left both sides of the explore-to-doing ratio.
SCORING_INPUTS_VERSION = 6
AQ_VERSION = 6
GSTACK_VERSION = 6
SCORE_CONTRACT_ID = f"{SCORING_INPUTS_VERSION}:{AQ_VERSION}:{GSTACK_VERSION}"
COMPARISON_POLICY = "same_score_contract_id_only"


class IncompatibleScoreContract(ValueError):
    pass
