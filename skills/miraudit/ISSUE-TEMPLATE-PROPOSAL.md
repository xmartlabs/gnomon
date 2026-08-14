<!-- A question for the maintainers of this repository, not reference material for
     running the skill. It ships with the skill because that is where the PR carrying
     it lives; the reporting structure it argues from is in reporting.md, which is the
     file a runner actually needs. -->

## Would an issue template help, or get in the way?

Asking before building it, because it would apply to every issue in this repo and not just
the ones that come out of the skill in #64.

The case for one is narrow and specific. Both of the reports we sent you landed because
they carried the same four things, and we only learned that they were the load-bearing
ones from your reply to #72: "the reproduction detail made these fast to verify." A
template would ask a stranger for those four up front instead of hoping they think of them.

1. **Provenance before the first number.** Window, pinned commit, contract, and the state
   of the anchor. `anchor.ok: null` said plainly, rather than a reader discovering on the
   third number that nothing was reproduced.
2. **Where each figure came from.** Whether it is a published field of the payload or a
   derivation, with the derivation stated. This is the one that forecloses the most common
   way a report wastes your time, which is an invented denominator. We produced a "93%
   coverage" figure that way once. It was true and it meant nothing, because the
   eligibility rule behind it was ours and not yours.
3. **The command that reproduces it**, and the control that shows the fixture is not
   empty. A zero from a broken fixture looks exactly like a real absence.
4. **What the reporter did not check.** Blind spots named by the person who has them,
   which is cheaper for you than finding them yourself in the reply.

The case against is that templates add friction to every issue, most of which are not
audits, and a bad template teaches people to fill fields rather than to think. If most of
your issues are feature requests and questions, this is probably noise.

Three ways to go, and we are happy with any of them including the last:

- We open a small separate PR adding `.github/ISSUE_TEMPLATE/scoring-fidelity.md`, scoped
  to scoring and fidelity reports only, so ordinary issues keep the blank editor.
- You take the four items and write your own, which you are better placed to word than we
  are.
- Nothing. The structure lives in `references/reporting.md` in #64, so anyone running the
  skill gets it whether or not this repo has a template. That file is where we wrote down
  what your #72 reply taught us.

One thing we would not do without asking: change the default template for all issues. That
is a call about your inbox, not ours.
