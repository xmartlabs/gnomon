#!/usr/bin/env python3
"""Regenerate tests/fixtures/scoring_vectors.json — the cross-language parity contract.

Each case is { name, scoring_inputs_version, scoring_inputs_by_source, expected } where
`expected` = { by_source: {<source>: <profile>}, aggregate: <profile> }, snapshotted from
the Python scoring implementation (gnomon.scoring.aggregate.score_by_source).

mirdash reimplements scoring in TS and tests against this same file. test_scoring_vectors.py
re-derives `expected` from the Python impl and asserts it matches the committed file, so the
snapshot can never silently drift from the code.

Run:  python3 tests/gen_scoring_vectors.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gnomon.output.summary import SCORING_INPUTS_VERSION
from gnomon.scoring.aggregate import score_by_source
from tests._scoring_vectors_cases import cases

OUT = os.path.join(os.path.dirname(__file__), "fixtures", "scoring_vectors.json")


def build():
    out = []
    for name, sibs in cases():
        out.append({
            "name": name,
            "scoring_inputs_version": SCORING_INPUTS_VERSION,
            "scoring_inputs_by_source": sibs,
            "expected": score_by_source(sibs),
        })
    return out


if __name__ == "__main__":
    data = build()
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str, sort_keys=True)
        f.write("\n")
    print(f"wrote {len(data)} cases to {OUT}")
