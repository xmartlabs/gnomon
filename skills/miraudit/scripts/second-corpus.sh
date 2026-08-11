#!/usr/bin/env bash
# One command, one file. This is the entire ask for someone contributing a second corpus:
#
#   ./second-corpus.sh
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
#
# Nothing is written inside the checkout, and nothing leaves except that one file, which
# carries counts and shares. Read it before sending it.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Pinned, not `main`. Two people cloning `main` a week apart can land on different scoring
# contracts, and comparing across contracts is not a comparison: v17 removed three targets
# outright, so signals the counterfactual cuts simply stop existing.
REF="c6401cc"
REPO_URL="https://github.com/xmartlabs/gnomon.git"

CHECKOUT=""; SINCE=""; UNTIL=""; PUBLISHED=""; CORPUS="$HOME/.claude/projects"
WORK="${TMPDIR:-/tmp}/miraudit-second-corpus.$$"

while [ $# -gt 0 ]; do
  case "$1" in
    --checkout)  CHECKOUT="$2";  shift 2 ;;
    --ref)       REF="$2";       shift 2 ;;
    --since)     SINCE="$2";     shift 2 ;;
    --until)     UNTIL="$2";     shift 2 ;;
    --published) PUBLISHED="$2"; shift 2 ;;
    --corpus)    CORPUS="$2";    shift 2 ;;
    --work)      WORK="$2";      shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

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
if [ -n "$PUBLISHED" ]; then
  bash "$HERE/anchor.sh" --checkout "$CHECKOUT" --since "$SINCE" --until "$UNTIL" \
      --corpus "$CORPUS" --work "$WORK/anchor" --published "$PUBLISHED"
else
  bash "$HERE/anchor.sh" --checkout "$CHECKOUT" --since "$SINCE" --until "$UNTIL" \
      --corpus "$CORPUS" --work "$WORK/anchor"
fi

STATS="$(find "$WORK/anchor" -name 'stats.json' -print -quit)"
COPY="$WORK/anchor/checkout"
OUT="$WORK/miraudit-comparison-$UNTIL.json"

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
      --since "$SINCE" --until "$UNTIL" --stats "$STATS" \
      --saturation "$WORK/saturation.json" --published "$PUBLISHED" --out "$OUT"
else
  python3 "$HERE/emit-comparison.py" --checkout "$COPY" --corpus "$CORPUS" \
      --since "$SINCE" --until "$UNTIL" --stats "$STATS" \
      --saturation "$WORK/saturation.json" --out "$OUT"
fi

echo
echo "=============================================================="
echo "Send this one file back:"
echo "    $OUT"
echo "=============================================================="
