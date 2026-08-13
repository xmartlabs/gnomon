"""Assembles the issue draft from a run's findings, and leaves the argument to a person.

    python3 render-issue.py <miraudit-<date>.json> [<draft.md>] [--include-dismissed <id>]

The structure it writes is not a guess about what maintainers like. It is the structure of
the one report that landed on this tool's own repository, whose first line back was "the
reproduction detail made these fast to verify". That structure lived in reporting.md as a
skeleton to be copied by hand, which is how a format degrades from one person to the next.

The split follows the skill's doctrine: the machine assembles what the JSON already asserts,
and the agent supplies what needs judgement. Everything mechanical is filled in here.
Everything that requires reading the audited tool's code is left as a marker that says what
the section must do and what makes it fail.

Refuses to write when findings[] is empty, when anchor.ok is false, or when a finding is
missing what the structure requires. Those were prose rules in Phase 5 and are checks here.

Exit codes: 0 drafted, 1 refused, 2 the file could not be read.
"""
import argparse
import json
import os
import sys

# Markers are prompt, not labels. Each one names what the section has to do, the failure it
# prevents, and the case that produced the rule -- the same three parts every rule in
# SKILL.md carries, because "a rule you can follow in good faith and break anyway needs its
# case named". A marker that says WRITE THE ARGUMENT gets a plausible paragraph nobody
# checked, which is the exact output the skill's Never list forbids.
#
# They are VISIBLE text and not HTML comments. The first draft used comments and read fine
# in an editor, but a comment renders to nothing on GitHub: a half-filled draft pasted into
# an issue would have shown an empty title rather than an obvious hole. A marker whose
# failure mode is silence is the wrong marker.
MARK = "[UNFILLED:"

TITLE_MARK = f"""**{MARK} title. Name the number of claims and what you measured, and make it a
     question when it is one: "Three questions about intent, from a five-corpus comparison"
     invites an answer, "Bug: the Grounding axis is wrong" invites a defense. Half the time
     the defense is correct, because the behaviour was deliberate and documented somewhere
     you had not read yet.]**"""

TOPIC_MARK = f"""**{MARK} what these claims have in common, in one clause. If they have nothing
     in common, that is worth knowing before you send: separate issues get separate answers,
     and a bundle of unrelated claims gets one reply about the easiest of them.]**"""

ARGUMENT_MARK = f"""**{MARK} the argument, built from THEIR code and THEIR comments, quoting
     file:line. Not from your reasoning about what the axis ought to measure.
     Read the code around the behaviour before writing this. If their comment says the
     behaviour is deliberate, you have no claim and you have just saved yourself the send:
     that is how Grounding died in this project, where accumulator.py:1547-1564 already
     documented the decision and published the 59-81% range this run reproduced at 81.6%.
     An argument made out of the author's own words is harder to wave off and faster for
     them to check, which is the whole reason the format works.]**"""

PREAMBLE = """<!-- DELETE THIS BLOCK BEFORE SENDING.

Phase 5 rules, carried here so they do not depend on remembering:

  Only findings[] goes. not_raised does not go, by definition. process_friction never goes:
  it is about your tooling, not theirs. If anchor.ok is false, nothing goes at all.

  Every figure is a published field of their payload or a derivation you state. A number
  whose denominator you invented is true and meaningless, which is how this project produced
  a "93% coverage" figure that collapsed to 34% under their own eligibility rule.

  No claim without the command that reproduces it. That is the part their maintainer said
  made the last report fast to verify.

  Read what you are about to publish. It quotes paths and repository names out of your
  corpus, and a public issue is a poor place to discover that.
-->"""


def refuse(reason, detail=""):
    print(f"render-issue: refusing to draft.\n  {reason}")
    if detail:
        print(f"  {detail}")
    return 1


def provenance(doc):
    t, c, a = doc.get("tool", {}), doc.get("corpus", {}), doc.get("anchor", {})
    out = [f"Measured against `{t.get('name', 'the tool')}` at `{t.get('ref', '?')}`, "
           f"contract `{t.get('contract', '?')}`, over {c.get('window', 'an unstated window')}."]
    bits = []
    if c.get("tool_calls") is not None:
        bits.append(f"{c['tool_calls']:,} tool calls")
    if c.get("sessions") is not None:
        bits.append(f"{c['sessions']} sessions")
    if c.get("sidechain_share") is not None:
        bits.append(f"sidechain share {c['sidechain_share']}")
    if bits:
        out.append("Corpus: " + ", ".join(bits) +
                   f", sources {', '.join(c.get('sources') or ['unstated'])}.")
    ok = a.get("ok")
    if ok is True:
        out.append(f"The base run reproduced the published number ({a.get('published')}), "
                   "so the figures below sit on an anchored run.")
    else:
        out.append(f"**`anchor.ok` is `{json.dumps(ok)}`.** The run reproduced "
                   f"{a.get('reproduced')} locally but did not compare it against a published "
                   "number, so this is evidence about composition and shape rather than a "
                   "reproduction of a figure you published. Saying so here rather than "
                   "letting you find it at the third number.")
    return "\n\n".join(out)


def render(doc, dismissed_ids):
    f_list = doc["findings"]
    single = len(f_list) == 1
    out = [PREAMBLE, "", f"# {TITLE_MARK}", "",
           ("This is not a bug report. It is a question where the answer decides whether "
            "there is anything to do at all, and it says what would close it." if single
            else "None of these is a bug report. Each is a question where the answer "
                 "decides whether there is anything to do at all, and each says what would "
                 "close it."), ""]
    # The topic marker asks what the claims have in common, which has no answer when there
    # is one claim. Filling a single-finding draft was what showed it: the marker demanded
    # a sentence that could only be padding, and padding in the opening paragraph is what
    # makes a reader skim the rest.
    if not single:
        out += [f"They share this: {TOPIC_MARK}", ""]
    out += ["## How the numbers were produced", "",
            provenance(doc), "",
            "Every figure below is a published field of your own payload, or is derived from "
            "one with the derivation stated.", "", "---", ""]

    for i, f in enumerate(f_list, 1):
        ev = f["evidence"]
        out += [f"## {i}. {f['id']}", "",
                f"Axes: {', '.join(f['axes'])}. Direction: **{f['direction']}**. "
                f"Confidence: {f['confidence']}.", "",
                ev["output"], "", ARGUMENT_MARK, "",
                f"**Reproduce:** `{ev['command']}`", "",
                f"**Control:** {ev['control']}", "",
                "**Not checked:**", ""] + [f"- {n}" for n in f["not_checked"]] + ["",
                f"**What would close this:** {f['what_would_close_it']}", "", "---", ""]

    if dismissed_ids:
        out += ["## Already considered and dropped", "",
                "Included because you raised it, not as a claim of ours.", ""]
        for d in doc.get("dismissed", []):
            if d.get("id") in dismissed_ids:
                out.append(f"- **{d['id']}**: {d['killed_by']}")
        out.append("")
    return "\n".join(out)


def main(argv=None):
    p = argparse.ArgumentParser(prog="render-issue", description=__doc__,
                               formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("run")
    p.add_argument("out", nargs="?")
    p.add_argument("--include-dismissed", action="append", default=[], metavar="ID")
    args = p.parse_args(argv)

    try:
        with open(args.run) as fh:
            doc = json.load(fh)
    except (OSError, ValueError) as exc:
        print(f"error: cannot read {args.run}: {exc}")
        return 2

    findings = doc.get("findings") or []
    if not findings:
        return refuse(
            "findings[] is empty, so there is nothing to send.",
            "not_raised and dismissed do not go to a maintainer. An audit that raised "
            "nothing is a normal result, not a message.")
    if (doc.get("anchor") or {}).get("ok") is False:
        return refuse(
            "anchor.ok is false.",
            "The base run did not reproduce the published number, so the method was wrong "
            "before any finding was. Fix the anchor, not the draft.")

    missing = []
    for i, f in enumerate(findings):
        for key in ("id", "axes", "direction", "confidence", "not_checked",
                    "what_would_close_it"):
            if not f.get(key):
                missing.append(f"findings[{i}].{key}")
        for key in ("command", "control", "output"):
            if not (f.get("evidence") or {}).get(key):
                missing.append(f"findings[{i}].evidence.{key}")
    if missing:
        return refuse("a finding is missing what the structure requires: "
                      + ", ".join(missing),
                      "`what_would_close_it` is the one the audit JSON does not require. It "
                      "is required here because a claim that cannot be closed produces three "
                      "replies instead of one.")

    text = render(doc, set(args.include_dismissed))
    dst = args.out or os.path.splitext(args.run)[0] + "-issue.md"
    with open(dst, "w") as fh:
        fh.write(text + "\n")

    unfilled = text.count(MARK)
    print(f"render-issue: wrote {dst}")
    print(f"  {len(findings)} finding(s) assembled, {unfilled} marker(s) left to fill.")
    if unfilled:
        print("  It is a draft until that count is zero. Search the file for UNFILLED.")
    print("  NOT CHECKED: whether the argument holds, whether the tone suits the person "
          "reading it, or whether the claim is worth their attention at all. This assembles "
          "what the JSON already asserts and cannot judge any of that.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
