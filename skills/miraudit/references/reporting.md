# Sending a finding

The run produces a JSON and a markdown report. Neither is a message to a person. This is
the part that turns one into the other, and it exists because the skill used to stop at the
file: somebody ran an audit, got a confirmed finding, and had nothing telling them where it
went or what shape it took.

The structure below is not a guess about what maintainers like. It is the structure of one
report that worked, on a tool whose authors had already pushed back on an earlier one, and
their first line back was: "the reproduction detail made these fast to verify."

## What goes, and what does not

Only `findings[]` goes. That list already means "survived every row of the refutation
table", which is the entire claim you are making when you take somebody's time.

`not_raised[]` does not go, by definition. `dismissed[]` does not go either, with one
exception worth knowing: if you are answering a maintainer who raised the same idea, the
`killed_by` line is the fastest way to close it, because it is a fact and not an opinion.

`process_friction[]` never goes. It is about your tooling, not theirs.

If `anchor.ok` is false, nothing goes. The base run did not reproduce the published number,
so the method was wrong before any finding was.

## The shape

**Title it as a question when it is one.** "Three questions about intent, from a five-corpus
comparison" invites an answer. "Bug: Grounding axis is wrong" invites a defense, and half
the time the answer is that the behaviour was deliberate and documented somewhere you had
not read.

**Open by saying what it is not.** One line: none of this is a bug report, each is a
question whose answer decides whether there is anything to do, and each says what would
close it. This costs a sentence and changes how the whole page is read.

**Put provenance before the first number.** How many corpora, over what window, against
which pinned commit and contract, and the state of the anchor. State `anchor.ok: null`
plainly when that is what you have. A reader who finds out later that nothing was anchored
stops trusting the numbers they already read.

**Say where every figure came from.** The sentence that did the most work in the report
that landed: every figure below is a published field of your own payload, or is derived
from one with the derivation stated. It is a promise the reader can spot-check on the first
number they care about, and it forecloses the most common objection, which is that you
invented a denominator.

**Build each claim from their code, not yours.** Quote the file and line. Where their own
comment states the intent, quote the comment: an argument made out of the author's words is
harder to wave off and faster to check. If the code says the behaviour is deliberate, you
have no claim, and you find that out before sending rather than after.

**Give the command.** Per claim, the exact invocation that reproduces it, and the control
that shows the fixture is not empty.

**Say what you did not check.** Every claim carries its blind spots in `not_checked`. Move
them across. A claim that arrives with its own limits reads as measurement; one that
arrives without them reads as advocacy, and invites the reader to go looking for the limit
you hid.

**Say what would close it.** For each point, the observation that would settle it either
way. This is what makes a question answerable in one reply instead of three.

## The skeleton

```markdown
# <N> questions about <topic>, from <what you measured>

None of these is a bug report. Each is a question where the answer decides whether there
is anything to do at all, and each says what would close it.

## How the numbers were produced

<corpora, window, pinned commit, contract, anchor state>

Every figure below is a published field of your own payload, or is derived from one with
the derivation stated.

---

## 1. <claim, quantified>

<the code, quoted, with file:line>

<the table or the number, with the derivation if it is derived>

<the argument, built from their code and their comments>

**Reproduce:** `<command>`
**Control:** <the case that must come out non-zero, and that did>
**Not checked:** <the blind spots, moved from not_checked>
**What would close this:** <the observation that settles it>
```

## Before you send

Read the diff of what you are about to publish. A report quotes paths, session ids and
repository names out of a corpus that is yours and sometimes your employer's, and a public
issue is not a place to discover that. The rule that works is to scan the text with the
same eyes you would use on a commit, because it is the same exposure.

## For gnomon specifically

Findings go to issues on `xmartlabs/gnomon`. Two things about that repo in particular:
the maintainers answer questions about intent quickly and in detail, and they ship fixes
from them, so the question format is not a courtesy that costs you traction. And a report
that spans several corpora is worth more to them than one that does not, because the
open questions on their side are about distributions rather than about mechanisms.
