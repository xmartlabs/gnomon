# Current scoring contract (14:14:14).
#
# v14 unions active_hours across concurrent/overlapping sessions instead of summing
# independently-capped per-session durations (H10) -- summed hours over-counted engaged
# wall-clock time whenever two sessions ran concurrently. active_hours feeds gstack
# Execution's out_rate denominator (out_rate = tool_churn_edit_write / active_hours);
# `_EXECUTION_OUTPUT_TARGET` (1000, absolute tool-authored-lines/active-hour) is
# untouched -- it was never fitted against summed hours (absent from
# CALIBRATION_CONSTANT_NAMES), so union is the correct yardstick with no re-fit needed.
#
# v14 also replaces the literal `name == "Agent"` orchestration gate with membership in
# `taxonomy.ORCHESTRATION_TOOLS` ({"Agent", "Task", "Workflow"}), so bare Task/Workflow
# dispatches now feed agents_per_session / _delegated_orchestratable / o_frequency the
# same way Agent dispatches always did. Fanout stays behind the existing
# `sat(fanout, FANOUT_CEILING)` saturation -- no raw fanout ever reaches a score.
#
# v13 distinguishes unmeasured delegation from a measured zero in the harness
# taxonomy. Unmeasured harness terms drop and renormalize; measured zero remains
# 0.0. `HARNESS_TEAM_SESSION_TYPES` and `HARNESS_BELOW_TEAM_CREDIT` name existing
# values so the calibration fingerprint covers them.
#
# `actions_per_prompt` uses top-level calls over `total_instructions`; sidechain
# calls remain observable in `volume.sidechain_tool_calls`. Steering is withheld
# while its band is unvalidated, and an observed unlabelled delegation also drops
# the term. `TOP_LEVEL_ACTIONS_INPUTS_VERSION` is a replay boundary because stored
# ratios before that version have a different basis.
#
# Contract IDs are comparison boundaries. Calibration fingerprints are append-only:
# a score-affecting change requires a new ID and fingerprint entry.
SCORING_INPUTS_VERSION = 14
AQ_VERSION = 14
GSTACK_VERSION = 14
# First input version with deduplicated per-session skill counters. Earlier
# payloads use different persisted quantities and cannot be replayed against these targets.
SKILL_DEDUP_INPUTS_VERSION = 8
# First input version whose `actions_per_prompt` is top-level-only over
# `total_instructions`. Earlier payloads lack the sidechain breakdown required to
# reconstruct that ratio, so replay rejects them at this boundary.
TOP_LEVEL_ACTIONS_INPUTS_VERSION = 12
SCORE_CONTRACT_ID = f"{SCORING_INPUTS_VERSION}:{AQ_VERSION}:{GSTACK_VERSION}"
COMPARISON_POLICY = "same_score_contract_id_only"


class IncompatibleScoreContract(ValueError):
    pass
