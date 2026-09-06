# Contributing to gnomon

Thanks for considering a contribution. This repo hosts both the CLI (Python,
stdlib-only) and the self-hosted team dashboard (Next.js) — see the root
[README](README.md) for what each does.

A Code of Conduct and a security-reporting policy are coming soon; this file
will link them once they exist.

## Development setup

- Python 3.8+ (`pyproject.toml` requires `>=3.8`; CI runs 3.11).
- No install step for the CLI itself:

  ```bash
  git clone https://github.com/xmartlabs/gnomon
  cd gnomon
  python3 paxel.py --help
  ```

- **Hard rule: the CLI has zero runtime dependencies** (`dependencies = []` in
  `pyproject.toml`). "No dependencies, stdlib only" is a headline product
  claim, not an accident — a PR that adds one needs an explicit justification
  in the PR description.
- Dashboard (`dashboard/`): Node 22 + pnpm.

  ```bash
  cd dashboard
  pnpm install --frozen-lockfile
  ```

## Running the tests

```bash
# CLI
python3 -m py_compile paxel.py
python3 -m unittest discover -s tests -v

# Dashboard
cd dashboard
pnpm test                                        # unit
pnpm exec playwright install --with-deps chromium
pnpm test:e2e                                     # e2e, against the standalone build
```

Both suites gate every PR via `.github/workflows/ci.yml`.

### A test that will surprise you

[`tests/test_documentation_contract.py`](tests/test_documentation_contract.py)
reads `README.md`, `docs/metrics-by-source.md`, and `docs/scoring-philosophy.md`
at runtime and asserts exact substrings are present (and a few are absent).
Docs and code ship together here — editing README/docs prose can break CI just
like editing code can. If you touch the scoring contract or its documentation,
run this test explicitly before opening a PR:

```bash
python3 -m unittest tests.test_documentation_contract -v
```

## Changing the scoring contract

`SCORE_CONTRACT_ID` lives in `gnomon/scoring/versioning.py` (currently
`19:19:19`). Any change to scoring inputs, AQ, or GStack requires bumping it
**and** updating the README + `docs/metrics-by-source.md` strings that
`test_documentation_contract.py` checks. Scores are only comparable across
matching contract IDs — that's the entire point of the ID, so silent
recalibration isn't acceptable.

## Code style

No linter or formatter is configured in this repo (no ruff/black/eslint/prettier
config exists) — match the surrounding style rather than assume one:

- 4-space indent, roughly 88-100 column wrap.
- Python 3.8 compatibility in package code: no `match` statements, no PEP 604
  `X | Y` annotations, no `tomllib` (the release workflow uses it, but only
  under 3.11 in CI, not in package code).
- Comments in this codebase explain *why* a rule exists, often citing the bug
  or decision that motivated it — keep that habit rather than describing *what*
  the code does.

## Commit and PR conventions

- Conventional commits, e.g. `feat(dashboard): ...`, `fix(miraudit): ...`,
  `test(miraudit): ...`, `docs: ...`, `chore: ...`.
- PRs target `main`; CI must be green before merge.
- Describe what you tested. For scoring changes, say which contract ID they
  land under.

## Releases (maintainers)

Bump the version in `pyproject.toml`, merge to `main`, then run the "Stable
release" `workflow_dispatch` workflow with the matching `X.Y.Z`. It tags
`vX.Y.Z`, creates the GitHub Release, and moves the `latest` tag.
