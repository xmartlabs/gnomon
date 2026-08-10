# Refutation: five findings that did not survive

Every row of the Phase 3 gate exists because a real finding died there. These are those
findings, written up so the shape is recognisable when a new one has it. All five were
about to be sent to the team that owns the scoring tool.

Read this when you have a candidate finding and are deciding whether it ships.

<examples>

<example id="window-artifact">
<claim>
"ToolSearch calls started on 2026-07-01, so the harness rolled out deferred tool loading
that day — the axis has been crediting a harness change ever since."
</claim>
<what_made_it_look_real>
603 calls, none before July 1, then a steady daily rate. A clean step change.
</what_made_it_look_real>
<what_killed_it>
The corpus itself. Claude Code transcripts start July 1 too, because transcript retention
prunes older files: total tool calls before July were 42, across the whole corpus.
</what_killed_it>
<verdict>Dismissed. The step was the observation window, not the phenomenon.</verdict>
<generalisation>
When a pattern begins exactly at the edge of your data, the edge is the first suspect. Test
it by measuring the total activity before that boundary, not the signal you care about.
</generalisation>
</example>

<example id="invented-denominator">
<claim>
"14 of 15 code-editing sessions ran tests — 93% coverage — so the axis underrates us."
</claim>
<what_made_it_look_real>
The arithmetic was correct and the sessions were real.
</what_made_it_look_real>
<what_killed_it>
The denominator was ours. The filter selected only two repositories, both of which have a
test suite. Under the tool's own eligibility predicate the same window gives 17 of 50 —
34%. The number was true and meaningless.
</what_killed_it>
<verdict>Withdrawn in writing, before they had to point it out.</verdict>
<generalisation>
When measuring something the audited tool also measures, find its predicate and call it.
A denominator you chose yourself cannot support a claim about their number.
</generalisation>
</example>

<example id="flattering-operationalization">
<claim>
"Recovery is near-tautological: it counts any tool call after an error. Measured properly
it is 46.8%, not the 96.7% reported."
</claim>
<what_made_it_look_real>
The code genuinely does clear the error flag on any subsequent tool use — that part was
verified and is still true.
</what_made_it_look_real>
<what_killed_it>
The 46.8% came from checking only the *immediately* next tool call. After an error you
usually read a file before retrying. Pairing tool_use with its tool_result and looking for
a later successful retry of the same tool gives 90.2% against their 96.7%.
</what_killed_it>
<verdict>
Dismissed as a finding. The definition is loose; the number it produces is nearly right,
and a ~2 point gap is not worth a report.
</verdict>
<generalisation>
A loose definition and a wrong number are different claims. Prove the second separately,
with the operationalization you would accept if it were used against you.
</generalisation>
</example>

<example id="self-contradiction">
<claim>
"Subagent tool calls should be excluded from the rate denominator — they inflate it by
almost half."
</claim>
<what_made_it_look_real>
The inflation is real and measurable.
</what_made_it_look_real>
<what_killed_it>
We had already conceded the opposite in writing, in an earlier exchange with the same team:
their numerators are sidechain-inclusive too, so the populations match, and their own docs
state the denominator is deliberately sidechain-inclusive. Sending it would have re-opened
a settled point.
</what_killed_it>
<verdict>Dropped. The surviving argument holds the numerator fixed instead.</verdict>
<generalisation>
Before proposing a change, search your own prior correspondence for the opposite position.
The cheapest refutation available to the other side is your own signature.
</generalisation>
</example>

<example id="stale-paths">
<claim>
"Only 13% of the code files you touched have a co-located test."
</claim>
<what_made_it_look_real>
A file-existence check over every touched path. Mechanical, no judgement involved.
</what_made_it_look_real>
<what_killed_it>
Many paths pointed into git worktrees that had since been deleted, so the sibling test file
"did not exist" because nothing there existed. Resolving the same paths against a named ref
gives 21%, and by area: services 66%, helpers 60%, one-off scripts 16%.
</what_killed_it>
<verdict>Corrected before sending. The corrected version found something real.</verdict>
<generalisation>
A path that was valid when the transcript was written may not be valid now. Resolve against
a ref, or verify the container still exists before reading a negative result as a fact.
</generalisation>
</example>

<example id="truncated-evidence">
<claim>
"Their test-detection predicate counts a bare `cd` as a test run — nine times in this
corpus. The Verification numerator is inflated."
</claim>
<what_made_it_look_real>
The comparison output showed the two predicates disagreeing on
`cd /Users/…/5S_clientportal_BE`, with their predicate returning true. Their predicate,
their corpus, no invented denominator: it passed every other row of the gate.
</what_made_it_look_real>
<what_killed_it>
Running the predicate on that exact string returns `False`. The comparison script printed
`cmd[:70]`, and the path is 69 characters long, so what looked like a whole command was the
head of a longer one. The evidence had been reshaped by the tool that gathered it.
</what_killed_it>
<verdict>Dismissed. The bug was in the audit's display, not in the audited code.</verdict>
<generalisation>
Before believing what a comparison shows you, check what it did to the data on the way:
truncation, sampling, `head`, deduplication, formatting. Re-run the predicate on the raw
value, not on the rendered one. This is the row none of the five above would have caught,
and it is why the gate grows only from real deaths.
</generalisation>
</example>

</examples>

## The pattern across all six

Five of the six were killed by re-running a measurement a slightly different way. One was
killed by reading our own earlier words. **None needed a second opinion from another
agent** — which is why the Phase 3 gate is a fixed checklist and not a review panel. An
agent asked to check an agent's finding shares its blind spot; a deterministic re-measure
does not. The reasoning behind that choice, and the one condition under which a row gets
added, is in `design-rationale.md`.
