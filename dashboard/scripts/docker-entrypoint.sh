#!/usr/bin/env sh
set -e

# Runs at container start, never at build: the image must build without any
# runtime secrets present, but must refuse to serve without the shared token.
if [ -z "${TEAM_TOKEN:-}" ]; then
  echo "FATAL: TEAM_TOKEN env var is required — set it in .env (see .env.example)" >&2
  exit 1
fi

exec node server.js
