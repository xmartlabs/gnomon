#!/usr/bin/env bash
# One command, one file. This is the entire ask for someone contributing a second corpus:
#
#   uvx --from "git+https://github.com/ftrinidad/gnomon@feat/miraudit-skill#subdirectory=skills/miraudit" \
#       miraudit-second-corpus
#
# Nothing is installed and nothing is left behind. From a clone, the equivalent is
# `bash <clone>/skills/miraudit/scripts/second-corpus.sh` -- spelled out because a bare
# `scripts/second-corpus.sh` is relative to this directory and is the first thing a new
# runner trips over, before they have any reason to trust the rest.
#
# No arguments. It clones the scoring tool at a pinned commit, scores the last 30 complete
# days of your local transcripts, and writes ONE file to send back.
#
# Every default is printed and recorded in the file, so nothing about the run is implicit.
# Override any of them if you have a reason:
#
#   --since / --until   your own report's window, if you have a published report to match
#   --published <N>     the number that report shows, to make the anchor check itself
#   --checkout <path>   an existing checkout instead of cloning
#   --ref <commit>      a different commit to pin to
#   --out-dir <path>    where the result file goes (default: the working directory)
#   --keep              do not delete the scratch directory on success
#
# It uses about 16 MB of scratch and under two minutes. The scratch is deleted when the run
# succeeds and kept when it does not.
#
# Nothing is written inside the checkout, and nothing leaves except that one file, which
# carries counts and shares. Read it before sending it.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Pinned, not `main`. Two people cloning `main` a week apart can land on different scoring
# contracts, and comparing across contracts is not a comparison: v17 removed three targets
# outright, so signals the counterfactual cuts simply stop existing.
#
# NOT a second home of the pin any more. This used to be a literal beside another literal in
# references/known-state.md, kept equal by a step in a written procedure -- and that
# procedure was already incomplete when it was written, because it named two of the three
# places. Now there is one source and this reads it. `--ref` still overrides.
REF="$(python3 "$HERE/pin-consistency.py" --field ref)"
REPO_URL="https://github.com/xmartlabs/gnomon.git"

CHECKOUT=""; SINCE=""; UNTIL=""; PUBLISHED=""; CORPUS="$HOME/.claude/projects"
WORK=""; OUTDIR="$PWD"; KEEP=""

while [ $# -gt 0 ]; do
  case "$1" in
    --checkout)  CHECKOUT="$2";  shift 2 ;;
    --ref)       REF="$2";       shift 2 ;;
    --since)     SINCE="$2";     shift 2 ;;
    --until)     UNTIL="$2";     shift 2 ;;
    --published) PUBLISHED="$2"; shift 2 ;;
    --corpus)    CORPUS="$2";    shift 2 ;;
    --out-dir)   OUTDIR="$2";    shift 2 ;;
    --work)      WORK="$2";      shift 2 ;;
    --keep)      KEEP="yes";     shift 1 ;;
    -h|--help)
      # It is an entry point now, so it answers the first thing anyone types at one.
      sed -n '2,25p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *) echo "unknown argument: $1" >&2
       echo "run with --help for the list." >&2
       exit 2 ;;
  esac
done

# The scratch directory holds a clone, a copy of it, and the copy's virtualenv: about 16 MB
# per run. Nothing used to delete it, and the file worth keeping lived inside it, so every
# run left the whole thing behind. The result file now goes to --out-dir (the working
# directory by default) and the scratch is removed on success.
#
# On FAILURE it is kept, and the path is printed. A run that broke is the one where the
# intermediate files are worth having, and deleting the evidence at exactly that moment is
# how a failure becomes unexplainable. --keep forces it either way; an explicit --work is
# treated as the caller's directory and never removed.
AUTO_WORK=""
if [ -z "$WORK" ]; then
  WORK="${TMPDIR:-/tmp}"; WORK="${WORK%/}/miraudit-second-corpus.$$"
  AUTO_WORK="yes"
fi

cleanup() {
  status=$?
  if [ "$status" -eq 0 ] && [ -n "$AUTO_WORK" ] && [ -z "$KEEP" ]; then
    rm -rf "$WORK"
  elif [ -d "$WORK" ]; then
    echo
    echo "scratch kept at $WORK  ($(du -sh "$WORK" 2>/dev/null | cut -f1)) -- delete it when done."
  fi
}
trap cleanup EXIT

# The window ends YESTERDAY, not today. A window ending now includes the session running the
# audit, which is then measuring itself while it is still being written. python3 rather than
# `date`, whose arithmetic flags differ between macOS and GNU.
if [ -z "$UNTIL" ]; then
  UNTIL="$(python3 -c "import datetime;print(datetime.date.today()-datetime.timedelta(days=1))")"
  DEFAULTED_UNTIL="yes"
fi
if [ -z "$SINCE" ]; then
  SINCE="$(python3 -c "
import datetime
print(datetime.date.fromisoformat('$UNTIL') - datetime.timedelta(days=30))")"
  DEFAULTED_SINCE="yes"
fi

mkdir -p "$WORK"

if [ -z "$CHECKOUT" ]; then
  CHECKOUT="$WORK/gnomon"
  echo "==> cloning the scoring tool at $REF (nothing is written to it afterwards)"
  git clone --quiet "$REPO_URL" "$CHECKOUT"
  git -C "$CHECKOUT" checkout --quiet "$REF"
fi

RESOLVED="$(git -C "$CHECKOUT" rev-parse --short HEAD 2>/dev/null || echo "unknown")"

echo
echo "=============================================================="
echo "  scoring tool   $RESOLVED"
echo "  corpus         $CORPUS"
echo "  window         $SINCE -> $UNTIL${DEFAULTED_SINCE:+   (default: the last 30 complete days)}"
echo "  published      ${PUBLISHED:-not given, so the anchor records ok=null rather than true}"
echo "=============================================================="
echo

if [ ! -d "$CORPUS" ]; then
  echo "error: no transcript corpus at $CORPUS. Pass --corpus." >&2
  exit 2
fi

echo "==> anchoring"
echo "    (the scoring tool will warn that --output-dir is an 'unknown flag ignored'."
echo "     It is not ignored: the flag is real and documented, and the run writes exactly"
echo "     where it says at the end. Its source-directory parser claims every --*-dir="
echo "     argument and warns about the ones it does not own.)"
if [ -n "$PUBLISHED" ]; then
  bash "$HERE/anchor.sh" --checkout "$CHECKOUT" --since "$SINCE" --until "$UNTIL" \
      --corpus "$CORPUS" --work "$WORK/anchor" --published "$PUBLISHED"
else
  bash "$HERE/anchor.sh" --checkout "$CHECKOUT" --since "$SINCE" --until "$UNTIL" \
      --corpus "$CORPUS" --work "$WORK/anchor"
fi

STATS="$(find "$WORK/anchor" -name 'stats.json' -print -quit)"
COPY="$WORK/anchor/checkout"
# Outside the scratch, so cleaning up cannot take the deliverable with it.
mkdir -p "$OUTDIR"
OUT="$(cd "$OUTDIR" && pwd)/miraudit-comparison-$UNTIL.json"

echo
echo "==> saturation counterfactual"
# Non-zero here means a control did not move, which makes the headline untrustworthy -- but
# the emitted json records exactly that, so finish the run and let the reader see
# `controls_moved: false` instead of getting no file and no explanation.
python3 "$HERE/saturation-counterfactual.py" --checkout "$COPY" --corpus "$CORPUS" \
    --since "$SINCE" --until "$UNTIL" --stats "$STATS" \
    --emit "$WORK/saturation.json" || echo "  (a control did not move; recorded in the file)"

echo
echo "==> writing the payload"
if [ -n "$PUBLISHED" ]; then
  python3 "$HERE/emit-comparison.py" --checkout "$COPY" --corpus "$CORPUS" \
      --since "$SINCE" --until "$UNTIL" --stats "$STATS" --ref "$RESOLVED" \
      --saturation "$WORK/saturation.json" --published "$PUBLISHED" --out "$OUT"
else
  python3 "$HERE/emit-comparison.py" --checkout "$COPY" --corpus "$CORPUS" \
      --since "$SINCE" --until "$UNTIL" --stats "$STATS" --ref "$RESOLVED" \
      --saturation "$WORK/saturation.json" --out "$OUT"
fi

echo
echo "=============================================================="
echo "Send this one file back:"
echo "    $OUT"
echo "=============================================================="
