# Why the gate is a checklist and not a review panel

Written for the next person who asks "shouldn't an adversarial reviewer re-judge the
findings before we report them?" It is a good question. This is the answer, with the
evidence behind it, so nobody has to reconstruct it.

## Refuter and adversarial are not the same thing

**Adversarial** is a stance: assume the claim is wrong and try to make it fall.
**Refuter** is one implementation of that stance, the one where an LLM reads a finding and
gives an opinion about it.

The distinction matters because this skill is already adversarial everywhere. Phase 3 exists
only to kill findings. The anchor in Phase 0 is a gate that stops the run. Every synthetic
fixture must carry a control. `not_checked` is mandatory and non-empty. None of those use an
agent, and all of them are adversarial.

So the question was never whether to be adversarial. It was which adversarial mechanism to
add, and a refuter is the weakest member of the family: it is the only one whose verdict
comes from an opinion instead of a number.

## Three reasons a panel is not it

**An agent asked to check an agent's finding shares its blind spot.** A deterministic
re-measure does not. Of the six findings in `refutation.md` that died before shipping, five
were killed by re-running a measurement a slightly different way, and one by reading our own
earlier correspondence. None needed a second opinion.

**A panel breaks comparability, which is the point of the JSON.** One person's corpus is an
anecdote; the same gap on five machines is a defect in the axis. That comparison only works
if the verdict is deterministic. With a stochastic panel you cannot tell whether machine
three lacks a finding because its corpus differs or because the panel disagreed that day.

**Findings that survive a panel read as stronger than findings that survive a grep**, and
they are not. That inverts the evidence hierarchy the whole skill rests on.

## The real gap, and why it is not filled by imagination

Phase 3 has a fixed number of rows, each one written after a real finding died there. A
false finding whose flaw is a shape not on the list passes the gate clean. That is a genuine
limitation and it is worth stating plainly.

The tempting fix is to ask an agent "what row is missing?". That produces plausible rows
nobody has validated, which is exactly what the skill's own `Never` list forbids.

**A row is earned by a death, not invented.** Two ways one arrives:

1. A finding ships, and the people who own the audited tool refute it. Their refutation is
   the row. As of this writing three findings shipped and three were accepted, so this well
   is dry — which is a good outcome, and not a reason to invent rows to fill it.
2. A finding dies during the audit itself, killed by something none of the existing rows
   would have caught.

The `truncated-evidence` row came from the second path, and it is the worked example of why
this design holds. The claim was that the audited tool counted a bare `cd` as a test run.
It used their predicate, on their corpus, with no invented denominator: it passed every
existing row. It died because someone re-ran the predicate on the exact string and got
`False` — the comparison script had truncated the command to 70 characters before printing
it. No panel would have caught that. Re-running the measurement did.

## Where an agent genuinely helps

This document argues against one use of an agent. Read alone it suggests a stronger claim —
no agents anywhere — which is wrong, so here is the use that works.

Split the work by what each side is actually good at:

**Conceiving the counter-measurement is the hard part, and it is not mechanical.** Look at
how the candidates in `refutation.md` died: five of six by re-running a measurement a
slightly different way. Running it is trivial. Thinking of it is not. Someone had to ask
"what if I pair `tool_use` with its `tool_result` and look for a later successful retry,
instead of taking the next call?" — and, for the seventh row, to notice that the path was 69
characters long and the display cut at 70. No checklist produces those.

**Deciding is mechanical, and must stay that way.** The agent proposes the check; the machine
runs it; the number rules. The artifact left behind is a command and its output, which anyone
can inspect and re-run — not "three of five reviewers disagreed". Determinism, reproducibility
and cross-machine comparison all survive intact, because none of them ever depended on who
generated the hypothesis.

The existing gate already protects this. Row six requires a control on every fixture, so a
counter-check quietly rigged to confirm its own finding fails before its verdict is read.

**This is observed, not proposed.** A cold run of this skill produced it without being told
to, three times over:

- It wrote an instrumented probe to test whether a term was being dropped, then ran two
  controls — forcing the term's score to 1.0 left the total unchanged, forcing it to 0.0
  moved it by two points. The controls, not the agent's judgement, established that the drop
  could only ever cost the person points.
- It tested a saturation hypothesis by cutting every saturated signal to exactly its target.
  The total did not move. Two further controls at half and a quarter moved it by 27 and 38
  points, which is what turned "the total did not move" from a possible broken fixture into
  a measured plateau.
- Its own first diagnostic lied. A snapshot function ran once globally and once per source,
  and the second pass overwrote the first, so the file reported the exact opposite of the
  truth. Re-running caught it. Had the agent trusted its own output, it would have dropped a
  real finding.

That third case is the argument in miniature. The agent was indispensable for conceiving the
probe and unreliable as a judge of its own result — which is precisely the division this
section describes, and precisely why the verdict never comes from an opinion.

## Where the division was only an argument, and now is not

This document described the split for a while before anything enforced it, and two places
kept the agent doing machine work. Both produced the mistake the division predicts.

Phase 4 wrote its JSON from a blank file. That is where a candidate which had failed a
refutation row got typed into `findings[]`, and where a sentence of prose got typed into
`confidence`, a field the schema defines as two words. `new-run.py` writes the skeleton
instead, with the eight rows keyed and the numbers read from the anchored run rather than
retyped. Phase 5 had a structure in `reporting.md` and nothing to assemble it, so the one
shape known to work was retyped by hand each time. `render-issue.py` assembles it and leaves
markers only where the argument has to come from reading the audited tool's code.

What stays with the agent is unchanged and is the harder half: conceiving the
counter-measurement, and building the argument out of the author's own words. Following the
argument marker on a real finding produced a stronger claim than writing it free-hand had,
because the marker sends you to their comment first and their comment turned out to say they
intended the measured ratio to keep being published. That is the division paying off, not a
new use for an agent.

## What would change this

If a shipped finding gets refuted by the tool's owners, write the row. If a run produces a
false finding that survives the whole gate and is caught later, write the row. Both are
cheap and both are grounded.

Escalating a single finding to an adversarial panel is still reasonable in one narrow case:
a finding that has already survived the gate and is about to leave the team, where the cost
of being wrong in public is higher than the cost of a slower check. That is an exception
someone chooses deliberately, not a phase.
