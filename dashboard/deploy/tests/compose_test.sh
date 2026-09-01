#!/usr/bin/env bash
# Renders the host compose file with dummy values and asserts the parts a typo
# would silently break. Requires the Docker Compose plugin; no daemon needed.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
deploy_dir="$(dirname "$here")"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

cp "$deploy_dir/docker-compose.yml" "$work/"
printf 'TEAM_TOKEN=dummy\n' > "$work/app.env"
cat > "$work/.env" <<'EOF'
IMAGE_TAG=testtag
DEPLOY_UID=1234
DEPLOY_GID=5678
HTTP_PORT=8080
EOF

rendered="$(cd "$work" && docker compose config)"

fail=0
check() { # <description> <extended-regex>
  if grep -Eq "$2" <<<"$rendered"; then
    echo "ok   - $1"
  else
    echo "FAIL - $1"
    fail=1
  fi
}
refute() { # <description> <extended-regex>
  if grep -Eq "$2" <<<"$rendered"; then
    echo "FAIL - $1"
    fail=1
  else
    echo "ok   - $1"
  fi
}

check  "image tag is interpolated from IMAGE_TAG"   'image: gnomon-dashboard:testtag'
check  "container runs as the deploy uid:gid"       'user: "?1234:5678'
check  "host port is interpolated from HTTP_PORT"   'published: "?8080'
check  "container port stays 3000"                  'target: "?3000'
check  "data/ is bind-mounted to /data"             'target: /data'
# Compose versions disagree on whether `config` keeps env_file: or inlines it
# into environment:, so accept either as proof the file was read.
check  "app.env supplies the container environment" 'app\.env|TEAM_TOKEN'
check  "restart policy survives a reboot"           'restart: unless-stopped'
check  "project name is pinned to gnomon"           '^name: gnomon'
check  "a healthcheck is defined"                   'healthcheck:'
check  "container logs are capped"                  'max-size'
refute "the host never builds the image"            '^[[:space:]]*build:'
refute "TRUST_PROXY is not set by the deployment"   'TRUST_PROXY'

if [ "$fail" -ne 0 ]; then
  echo "--- rendered config ---"
  echo "$rendered"
fi
exit "$fail"
