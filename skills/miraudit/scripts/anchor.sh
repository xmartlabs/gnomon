#!/usr/bin/env bash
# Phase 0 in one command: copy the checkout, reproduce the published number over the
# report's own window, print the corpus fingerprint, and leave stats.json where the other
# checks can read it with --stats.
#
# Doing this by hand is the friction that cost a cold run the most: it involves a throwaway
# copy, an entry point that is not the documented one, and a window that must not roll.
#
#   ./anchor.sh --checkout <path> --since YYYY-MM-DD --until YYYY-MM-DD [--corpus <path>]
#               [--published <N>] [--expect-contract <X>]
#
# --published and --expect-contract turn Phase 0 into an actual gate: without them the
# script prints the number and trusts you to compare it, which is what it used to do.
#
# Never runs against the original checkout. Everything happens on a copy under --work.
set -euo pipefail

DEFAULT_CORPUS="$HOME/.claude/projects"
CHECKOUT=""; SINCE=""; UNTIL=""; CORPUS="$DEFAULT_CORPUS"
PUBLISHED=""; EXPECT=""
WORK="${TMPDIR:-/tmp}/miraudit-anchor.$$"

while [ $# -gt 0 ]; do
  case "$1" in
    --checkout) CHECKOUT="$2"; shift 2 ;;
    --since)    SINCE="$2";    shift 2 ;;
    --until)    UNTIL="$2";    shift 2 ;;
    --corpus)   CORPUS="$2";   shift 2 ;;
    --work)     WORK="$2";     shift 2 ;;
    --published)       PUBLISHED="$2"; shift 2 ;;
    --expect-contract) EXPECT="$2";    shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

# Written for bash 3.2, which is what stock macOS still ships. No ${var,,}, no ${!var}.
missing=""
[ -z "$CHECKOUT" ] && missing="$missing --checkout"
[ -z "$SINCE" ]    && missing="$missing --since"
[ -z "$UNTIL" ]    && missing="$missing --until"
if [ -n "$missing" ]; then
  echo "error: required and missing:$missing" >&2
  echo "The window must be the report's own. A rolling window drifts daily and" >&2
  echo "includes the audit session itself, so it cannot reproduce a published number." >&2
  exit 2
fi

if [ ! -d "$CHECKOUT/gnomon" ]; then
  echo "error: $CHECKOUT does not look like a checkout (no gnomon/ package inside)." >&2
  exit 2
fi

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COPY="$WORK/checkout"
OUT="$WORK/report"
mkdir -p "$WORK" "$OUT"

echo "==> copying the checkout (the original is never written to)"
cp -R "$CHECKOUT" "$COPY"

# --corpus used to reach only contract-probe.py and fingerprint.py, never the pipeline. So
# `--corpus X` fingerprinted X and SCORED the default corpus, and the resulting payload and
# fingerprint described different corpora with nothing saying so. On the default corpus the
# two happen to agree, which is why it survived every run here.
#
# The scoring tool's own flag is --claude-dir=PATH (sources/discovery.py:48). Its resolver
# takes either the config root or the transcripts subdir (discovery.py:92-98), so --corpus
# passes straight through. Only when it differs from the default, so existing runs are
# byte-identical. The ${VAR+"${VAR[@]}"} form is the bash 3.2 + `set -u` idiom: a bare
# "${ARR[@]}" on an empty array is an unbound-variable error there.
#
# IT OVERRIDES THE CLAUDE SOURCE ONLY. Codex, Gemini, Cursor and the rest keep resolving to
# their own default locations, so on a machine where any of those clears the source-volume
# threshold the run is a mix: overridden Claude plus default everything else. Read the
# "Found N transcript files across ..." line, and `sources_scored` in the payload, which is
# what makes the mix visible. Measured here: 62 files discovered across four tools, only
# `claude` scored, so the toy-corpus arm was clean.
DIRFLAG=()
if [ "$CORPUS" != "$DEFAULT_CORPUS" ]; then
  DIRFLAG=(--claude-dir="$CORPUS")
  echo "    corpus override: --claude-dir=$CORPUS"
fi

# Before the pipeline, not after: this takes a second and the pipeline takes minutes, and a
# checkout whose predicates have moved makes every later number unsafe to read anyway.
# The pin is what a second corpus and this run have to share, and it was stated in three
# places that nothing compared. Before the pipeline, like the probe, because it costs
# milliseconds.
echo "==> checking the pin agrees with itself and with the checkout"
python3 "$HERE/pin-consistency.py" --checkout "$COPY" --corpus "$CORPUS" \
    --since "$SINCE" --until "$UNTIL"

# Default it from the pin block rather than making the operator carry the value across from
# a markdown file by hand. An unpassed flag used to mean no comparison at all, which is how
# a gate ends up documented and unenforced.
if [ -z "$EXPECT" ]; then
  EXPECT="$(python3 "$HERE/pin-consistency.py" --field contract)"
  echo "    --expect-contract defaulted to $EXPECT from the pin block"
fi

echo
echo "==> probing the predicates the checks are built on"
python3 "$HERE/contract-probe.py" --checkout "$COPY" --corpus "$CORPUS" \
    --since "$SINCE" --until "$UNTIL" | tail -n +5

echo
echo "==> reproducing the published number: $SINCE -> $UNTIL"
# NOT `python3 xl_ai_insights.py`: that is an import shim with no __main__ guard. It exits 0,
# prints nothing, writes nothing, and looks exactly like success.
# `xl-ai-insights`, the packaged console script -- NOT `python -m gnomon.cli.insights`.
# `-m` puts the CURRENT DIRECTORY on sys.path first, so it imports whatever ./gnomon/ the
# caller happened to be standing in and `--project` only supplies the environment. Measured:
# from a directory holding a v16 fork the pipeline scored 16:16:16 while --project pointed at
# a v17 copy. Every earlier run of this script was launched from the directory that holds the
# read-only clone, so it measured the CLONE and reported the right number by coincidence.
#
# A console script is a FILE, so sys.path starts at its own directory and the caller's
# location cannot shadow the package. Same entry point either way -- pyproject maps it to
# gnomon.cli.insights:main and the module's __main__ block calls the same main() with the
# same argv -- so --since/--until behave identically, though `--help` documents them in
# discovery.py rather than in its own usage block.
#
# The `cd` is belt and braces: redundant with the console script, and cheap insurance
# against anyone restoring the `-m` form. In a subshell, so the caller's directory is
# untouched.
(cd "$COPY" && uv run --project "$COPY" xl-ai-insights \
    --local --console --no-open \
    --since="$SINCE" --until="$UNTIL" --output-dir="$OUT" ${DIRFLAG+"${DIRFLAG[@]}"})

STATS="$(find "$OUT" -name 'stats.json' -print -quit)"
if [ -z "$STATS" ]; then
  echo >&2
  echo "error: the run produced no stats.json under $OUT." >&2
  echo "Phase 0 is a gate: without a reproduced number, no finding is safe to read." >&2
  exit 1
fi

# Print the number the gate is ABOUT. The console run emits a GStack archetype line that
# says "Elite", which is a different scoring system and has been misread as satisfying this
# gate. Nothing else here prints the AQ, so a run could not check what it was told to check.
echo
python3 - "$HERE" "$STATS" "$PUBLISHED" "$EXPECT" <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
from _common import load_stats, find_key

stats = load_stats(sys.argv[2])
published, expect = sys.argv[3], sys.argv[4]
aq = find_key(stats, "aq_0_100")
tier = find_key(stats, "tier")
contract = find_key(stats, "score_contract_id")

print("=" * 62)
print("THE NUMBER TO COMPARE  (this, not the archetype line above)")
print("=" * 62)
if aq is None:
    print("  aq_0_100 not found in stats.json.")
    print("  Do NOT proceed: the gate cannot be checked, which is the same as failing it.")
    raise SystemExit(1)
print(f"  AQ        {aq}")
print(f"  tier      {tier}")
print(f"  contract  {contract}")

# Phase 0 is described as a gate that stops the run. Until these two flags existed it only
# printed a number and asked the operator to compare it, which is not a gate.
failed = []
if published:
    same = str(aq).strip() == published.strip()
    print(f"\n  published {published}   ->  {'reproduced' if same else 'DOES NOT MATCH'}")
    if not same:
        failed.append(f"the run gives {aq}, the published number is {published}")
if expect:
    same = str(contract).strip() == expect.strip()
    print(f"  expected contract {expect}   ->  {'match' if same else 'DOES NOT MATCH'}")
    if not same:
        failed.append(f"the checkout is on {contract}, not {expect}")
if failed:
    print("\n  GATE FAILED: " + "; ".join(failed) + ".")
    print("  The method is wrong before any finding is. Do not run the checks.")
    raise SystemExit(1)
# Per flag, not on the conjunction. `if not published and not expect` stayed silent whenever
# EITHER was given, so passing --published alone skipped the contract gate with nothing on
# screen saying a gate had been skipped. Half a gate reads exactly like a whole one.
if not published:
    print("\n  The NUMBER was not gated. Pass --published <N> to have this script compare")
    print("  it instead of asking you to.")
if not expect:
    print("\n  The CONTRACT was not gated. Pass --expect-contract <X>; the value is the")
    print("  `contract` field of the block at the top of references/known-state.md.")
PY

echo
python3 "$HERE/fingerprint.py" --checkout "$COPY" --corpus "$CORPUS" --until "$UNTIL" \
    --stats "$STATS"

echo
echo "==> anchored"
echo "    stats.json : $STATS"
echo "    copy       : $COPY"
echo
if [ -n "$PUBLISHED" ]; then
  echo "The gate passed: this run reproduced $PUBLISHED. Pass the same window, and the COPY —"
else
  echo "Compare that AQ against the published one BEFORE measuring anything. If they differ,"
  echo "the method is wrong before any finding is. Then pass the same window, and the COPY —"
fi
echo "never the original, which the checks would write __pycache__ into:"
echo
echo "    python3 $HERE/<check>.py --checkout $COPY \\"
echo "        --since $SINCE --until $UNTIL --stats $STATS"
echo
echo "Every check takes that exact shape. Checks that do not read stats.json accept --stats"
echo "and ignore it, so one command works for all of them."
