# Current scoring contract (17:17:17).
#
# v17 removes the `toolsearch_calls` per-tool-call rate term from BOTH scoring axes it fed
# -- Tool command (weight .20) and Token economy (weight .50). ToolSearch is a
# Claude-Code-only signal that is ~94% `select:`-prefixed deterministic tool-loading the
# deferred-tool harness forces (not a developer virtue), and its deliberate remainder is too
# sparse to calibrate as a per-tool-call rate. The existing wsum renormalization absorbs the
# dropped weight (Tool command -> mcp .5 / cli .5; Token economy -> cli_share at full weight),
# exactly as it already does for non-Claude sources that cannot record ToolSearch. The raw
# `toolsearch_calls` field stays emitted by the accumulator (unchanged) and is republished as
# a non-scored diagnostic on the Tool command axis. This is a REAL score delta (Tool command
# and Token economy renormalize -> AQ moves) AND -- unlike v14/v15/v16 -- a REAL calibration
# delta: TOOLSEARCH_PER_CALL_TARGET leaves CALIBRATION_CONSTANT_NAMES, so the fingerprint
# genuinely changes. 17:17:17 therefore carries a NEW fingerprint and is NOT in
# ZERO_CALIBRATION_DELTA_CONTRACT_IDS -- see calibration.py's CALIBRATION_FINGERPRINTS.
#
# v16 credits the Compounding axis for MCP knowledge-write persistence calls
# (mem0 add_memory/update_memory, engram mem_save/mem_update) that were
# previously invisible to `compounding_counter` -- only filesystem writes
# matching `_COMPOUNDING_RX` credited before this change, even though the SAME
# MCP call already arms Context Intelligence grounding (accumulator.py's
# knowledge-subcategory arm fires unconditionally). Gated by an explicit
# positive write-verb predicate, `taxonomy.is_mcp_knowledge_write`
# (knowledge-subcategory AND not a fetch-only server AND no read-hint match AND
# a write-hint match), so reads/deletes/context7-class fetchers stay at zero.
# Anti-saturation is a corpus-lifetime per-(session, distinct-target) dedup set
# (`_mcp_compounding_credited`), mirroring `_fanout_credited_agents`: target-less
# or same-target repeat calls within a session collapse to one credit, while
# genuinely distinct persisted targets each still earn their own credit. This is
# a REAL score delta (compounding_writes / Compounding axis / AQ move for
# corpora with MCP knowledge-writes) but a ZERO calibration delta: no
# `PER_CALL_TARGET` (including `COMPOUNDING_WRITES_PER_CALL_TARGET`), weight, or
# denominator moved, and `tool_calls_total`/`tool_use_total` are unaffected --
# see calibration.py's `CALIBRATION_FINGERPRINTS["16:16:16"]` and
# `ZERO_CALIBRATION_DELTA_CONTRACT_IDS`.
#
# v15 fixes the Workflow fan-out under-credit that v14 introduced: `ORCHESTRATION_TOOLS`
# membership (Agent/Task/Workflow) still drives agents_per_session/_fanouts/
# delegating_sessions/o_frequency, but a `Workflow` tool_use event no longer increments
# agents_per_session/month_fanouts directly -- one Workflow call can dispatch anywhere from
# one to dozens of real agents, so counting the call itself under-counted real dispatch.
# Fan-out for Workflow is instead sourced from the real dispatched-agent transcripts under
# `.../subagents/workflows/wf_*/agent-*.jsonl` that the walker already visits: one distinct
# `(parent_session, agentId)` transcript = one credited dispatch to the parent session,
# deduped so a `resumeFromRunId` resume never double-counts. Agent/Task calls are unchanged
# (1 call == 1 agent). Workflow-only sessions still count as delegating sessions because the
# transcript attribution increments the SAME accumulators that used to be fed by the per-call
# increment -- no separate membership special-case. This is a REAL score delta (fanout_median,
# Orchestration, Breadth, AQ move) but a ZERO calibration delta: no rate target,
# `PER_CALL_TARGET`, axis weight, cross-source weight, or denominator moved, and
# `FANOUT_CEILING` stays 5 -- see calibration.py's `CALIBRATION_FINGERPRINTS["15:15:15"]`
# and `ZERO_CALIBRATION_DELTA_CONTRACT_IDS`.
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
SCORING_INPUTS_VERSION = 17
AQ_VERSION = 17
GSTACK_VERSION = 17
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
