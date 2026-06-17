# ADR-0001 — paxel.py stays a single self-contained file

- **Status:** Accepted
- **Date:** 2026-06-17

## Context

`paxel.py` is ~4000 lines and fuses four stages (ingest, accumulate, score, render).
Its size invites the reflex suggestion: "split it into a package." But the tool's primary
install path is running the file directly over the network:

```
python3 <(curl -sL https://raw.githubusercontent.com/xmartlabs/gnomon/main/paxel.py)
```

(README "Option A: run directly (no install)"). This works only because `paxel.py` is one
file with zero imports outside the standard library (`pyproject.toml` declares
`dependencies = []`). Splitting it into multiple modules would break the curl path — the
piped single file could not `import accumulator` etc.

## Decision

`paxel.py` stays one self-contained, stdlib-only file. Architectural deepenings happen
**in place** — as classes, dataclasses, and functions within `paxel.py` — never by
extracting new importable modules.

This does not forbid internal structure. Deep modules (e.g. `EventAccumulator`, the `Stats`
dataclasses) are encouraged; they just live in the same file.

## Consequences

- Deepening is constrained to in-file organisation. The interface/depth wins still apply
  (small interface, hidden implementation, testable seam) — only the file boundary is off
  the table.
- Tests import from the single module (`from paxel import EventAccumulator`), which works
  because it is still a normal importable module when on disk.
- Future architecture reviews should not re-propose splitting `paxel.py` into a package.
  See `CONTEXT.md` → "Hard constraint".
- If the file ever truly must split, the curl install path must be redesigned first (e.g.
  a bundler that inlines modules into one shipped file), and this ADR superseded.
