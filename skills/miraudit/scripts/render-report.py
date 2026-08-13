"""Renders miraudit-<date>.md from miraudit-<date>.json, after gating it.

    python3 render-report.py <miraudit-<date>.json> [<output.md>]

Why this ships instead of being written per run: the schema said "render the markdown FROM
it" and gave ordering rules, then shipped no renderer. A cold run wrote its own in the run
directory, which meant the report format was whatever that run's author invented that
afternoon. Two people auditing the same tool would hand its maintainers two different
documents, and the maintainers would learn the shape of neither.

It runs emit-gate.py first and refuses to write anything when the gate fails. Phase 4 says
to gate and then render, in that order, and an order written in prose is an order somebody
eventually reverses. Here the two cannot be separated.

The output is deliberately plain. It goes to a person deciding whether to spend an hour on
a claim, and every section answers one of the three questions they will ask: what did you
find, how do I reproduce it, and what did you not check.

Exit codes: 0 rendered, 1 the gate refused the file, 2 the file could not be read.
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _fmt_magnitude(mag):
    if not mag:
        return ""
    bound = mag.get("bound")
    where = f" ({bound} bound)" if bound else ""
    return f" · magnitude {mag.get('value')} {mag.get('unit')}{where}"


def _claim_body(out, f, kind):
    """The shared shape of a claim. A finding and a not_raised entry differ in what happens
    next, not in what was measured, so they render the same evidence in the same order."""
    out.append(f"### {f['id']}\n")
    out.append(f"`{f['shape']}` · {', '.join(f['axes'])} · **{f['direction']}** · "
               f"{f['confidence']}{_fmt_magnitude(f.get('magnitude'))}\n")
    ev = f.get("evidence") or {}
    out.append(f"{ev.get('output', '')}\n")
    out.append(f"Reproduce it with:\n\n```\n{ev.get('command', '')}\n```\n")
    out.append(f"**Control.** {ev.get('control', '')}\n")
    if kind == "not_raised":
        out.append(f"**Not raised because.** {f.get('why_not', '')}\n")
        out.append(f"**Reconsider if.** {f.get('reconsider_if', '')}\n")
    nc = f.get("not_checked") or []
    if nc:
        out.append("**Not checked.**\n")
        for item in nc:
            out.append(f"- {item}\n")


def render(doc):
    out = []
    t, c, a = doc.get("tool", {}), doc.get("corpus", {}), doc.get("anchor", {})

    out.append(f"# miraudit: {t.get('name', 'unknown tool')} at `{t.get('ref', '?')}` "
               f"(contract `{t.get('contract', '?')}`)\n")

    sources = ", ".join(c.get("sources") or []) or "unstated"
    side = c.get("sidechain_share")
    out.append("## Corpus fingerprint\n")
    out.append("Counts compared across machines mean nothing without this, so it comes "
               "before any other number.\n")
    out.append(f"- Window: {c.get('window', 'unstated')}\n")
    out.append(f"- {c.get('files', '?')} files, {c.get('lines', '?')} lines, "
               f"{c.get('tool_calls', '?')} tool calls, {c.get('sessions', '?')} sessions\n")
    if side is not None:
        out.append(f"- Sidechain share: {side}\n")
    out.append(f"- Sources scored: {sources}\n")

    ok = a.get("ok")
    verdicts = {True: "PASSED", False: "FAILED", None: "PARTIAL"}
    out.append(f"\n## Anchor: {verdicts.get(ok, 'UNKNOWN')}\n")
    out.append(f"Reproduced {a.get('reproduced')}, published {a.get('published')}.\n")
    if a.get("note"):
        out.append(f"{a['note']}\n")
    if ok is None:
        out.append("An anchor that did not compare against a published number is weaker "
                   "than one that did. Every claim below inherits that.\n")

    findings = doc.get("findings") or []
    not_raised = doc.get("not_raised") or []
    dismissed = doc.get("dismissed") or []
    reported = doc.get("reported") or []

    out.append("\n## Verdict\n")
    out.append(f"{len(findings)} raised, {len(not_raised)} confirmed and deliberately not "
               f"raised, {len(dismissed)} killed in refutation, {len(reported)} already "
               "reported.\n")
    if not findings:
        out.append("Nothing is being raised. An empty findings list with a populated "
                   "dismissed list is a normal result: it is the evidence that what "
                   "survived went through a filter.\n")

    if findings:
        out.append("\n## Raised\n")
        out.append("Each of these survived every row of the refutation table. The rows and "
                   "the fact behind each verdict are in the JSON beside this file.\n")
        for f in findings:
            _claim_body(out, f, "findings")

    if not_raised:
        out.append("\n## Confirmed, deliberately not raised\n")
        out.append("True, reproduced, and not sent. Recorded so that not sending it stays "
                   "a decision with a reason rather than an oversight, and so nobody "
                   "re-derives it later.\n")
        for f in not_raised:
            _claim_body(out, f, "not_raised")

    if doc.get("axes"):
        out.append("\n## Axes re-measured\n")
        out.append("Gaps that belong to one axis and map to none of the structural shapes. "
                   "Ground truth came from the transcripts, never from the tool's own "
                   "aggregates.\n")
        out.append("\n| axis | score | direction | what the re-measurement found |\n")
        out.append("|---|---|---|---|\n")
        for x in doc["axes"]:
            found = (x.get("evidence") or {}).get("output", "").replace("|", "\\|")
            out.append(f"| {x.get('name')} | {x.get('score')}/{x.get('max')} | "
                       f"{x.get('direction')} | {found} |\n")

    if reported:
        out.append("\n## Already reported\n")
        for r in reported:
            out.append(f"- **{r.get('id')}**: {r.get('state')}\n")
            out.append(f"  - {r.get('confirmed_by')}\n")

    if dismissed:
        out.append("\n## Killed in refutation\n")
        out.append("Not filler. This section is why the section above it can be trusted, "
                   "and it is what stops a dead claim from being reopened next month.\n")
        for x in dismissed:
            out.append(f"- **{x.get('id')}**: {x.get('killed_by')}\n")

    if doc.get("process_friction"):
        out.append("\n## What the audit cost\n")
        out.append("Costs the audited tool did not cause. These improve the auditor, not "
                   "the tool.\n")
        for p in doc["process_friction"]:
            out.append(f"- Phase {p.get('phase')}: {p.get('what')} (Cost: {p.get('cost')})\n")

    return "\n".join(out) + "\n"


def main(argv):
    if len(argv) not in (2, 3):
        sys.exit(__doc__)
    src = argv[1]
    dst = argv[2] if len(argv) == 3 else os.path.splitext(src)[0] + ".md"

    gate = subprocess.run([sys.executable, os.path.join(HERE, "emit-gate.py"), src],
                          check=False)
    if gate.returncode != 0:
        print("\nrender-report: the gate refused this file, so nothing was written.")
        print("Fix what it listed. A report that drifted from its evidence is the defect "
              "this skill exists to catch.")
        return 1

    try:
        with open(src) as fh:
            doc = json.load(fh)
    except (OSError, ValueError) as exc:
        print(f"error: cannot read {src}: {exc}")
        return 2

    with open(dst, "w") as fh:
        fh.write(render(doc))
    print(f"\nrender-report: wrote {dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
