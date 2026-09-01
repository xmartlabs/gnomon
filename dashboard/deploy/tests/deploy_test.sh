#!/usr/bin/env bash
# Exercises deploy.sh against stubbed `docker` and `curl` binaries, so the
# decision logic (preflight, tag bookkeeping, health gate, rollback, prune) is
# testable deterministically and without a Docker daemon.
set -uo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
deploy_dir="$(dirname "$here")"

pass=0
fail=0

ok()      { echo "ok   - $1"; pass=$((pass + 1)); }
notok()   { echo "FAIL - $1"; fail=$((fail + 1)); }
assert()  { if [ "$1" = "$2" ]; then ok "$3"; else notok "$3 (want '$2', got '$1')"; fi; }
assert_contains() {
  if grep -Fq "$2" <<<"$1"; then ok "$3"; else notok "$3 (missing '$2')"; fi
}
refute_contains() {
  if grep -Fq "$2" <<<"$1"; then notok "$3 (unexpected '$2')"; else ok "$3"; fi
}

# Builds a throwaway "box": a directory holding deploy.sh + the compose file,
# plus a bin/ of stubs that shadow the real docker and curl.
new_box() {
  box="$(mktemp -d)"
  BOXES+=("$box")
  cp "$deploy_dir/deploy.sh" "$deploy_dir/docker-compose.yml" "$box/"
  chmod +x "$box/deploy.sh"
  mkdir -p "$box/bin"

  cat > "$box/bin/docker" <<'STUB'
#!/usr/bin/env bash
echo "$*" >> "$DOCKER_LOG"
case "$1" in
  version) exit "${FAKE_DOCKER_VERSION_RC:-0}" ;;
  compose)
    case "$2" in
      version) exit "${FAKE_COMPOSE_VERSION_RC:-0}" ;;
      *)       exit 0 ;;
    esac ;;
  load)  cat > /dev/null; exit 0 ;;
  image)
    case "$2" in
      inspect) exit "${FAKE_IMAGE_INSPECT_RC:-0}" ;;
      # shellcheck disable=SC2086 # deliberate: splits FAKE_IMAGE_TAGS into lines
      ls)      printf '%s\n' ${FAKE_IMAGE_TAGS:-}; exit 0 ;;
      rm)      exit 0 ;;
    esac ;;
esac
exit 0
STUB

  cat > "$box/bin/curl" <<'STUB'
#!/usr/bin/env bash
exit "${FAKE_CURL_RC:-0}"
STUB

  chmod +x "$box/bin/docker" "$box/bin/curl"
  export DOCKER_LOG="$box/docker.log"
  : > "$DOCKER_LOG"
  # Every scenario starts clean. The stubs read these from the environment, so
  # tests `export` them — do NOT write `FAKE_X=1 run_deploy ...`, because bash
  # does not reliably scope an assignment prefixed to a *function* call, and a
  # leaked value silently corrupts every later scenario.
  unset FAKE_DOCKER_VERSION_RC FAKE_COMPOSE_VERSION_RC FAKE_IMAGE_INSPECT_RC \
        FAKE_IMAGE_TAGS FAKE_CURL_RC
}

# Runs deploy.sh inside the current box with the stubs first on PATH.
# Captures combined output in $out and the exit code in $rc.
run_deploy() {
  out="$(cd "$box" && PATH="$box/bin:$PATH" HEALTH_TIMEOUT=1 HEALTH_INTERVAL=0.1 \
        ./deploy.sh "$@" 2>&1)"
  rc=$?
}

BOXES=()
cleanup() { for b in "${BOXES[@]}"; do rm -rf "$b"; done; }
trap cleanup EXIT

# --- usage -------------------------------------------------------------------
new_box
run_deploy
assert "$rc" 2 "no tag argument exits 2"
assert_contains "$out" "usage:" "no tag argument prints usage"

# --- preflight ---------------------------------------------------------------
new_box
export FAKE_DOCKER_VERSION_RC=1
run_deploy abc123
assert "$rc" 1 "unreachable Docker daemon fails the deploy"
assert_contains "$out" "docker" "daemon failure names docker in the remedy"

new_box
export FAKE_COMPOSE_VERSION_RC=1
run_deploy abc123
assert "$rc" 1 "missing Compose plugin fails the deploy"
assert_contains "$out" "Compose" "compose failure names the plugin"

# Skipped as root, where the write bit is advisory and the case cannot be built.
if [ "$(id -u)" -eq 0 ]; then
  echo "skip - unwritable data/ (running as root)"
else
  new_box
  mkdir -p "$box/data"
  chmod a-w "$box/data"
  run_deploy abc123
  chmod u+w "$box/data"
  assert "$rc" 1 "an unwritable data/ fails BEFORE the container starts"
  refute_contains "$(cat "$DOCKER_LOG")" "compose up" "unwritable data/ never reaches compose up"
fi

# --- .env generation ---------------------------------------------------------
new_box
run_deploy abc123
env_file="$(cat "$box/.env")"
assert_contains "$env_file" "IMAGE_TAG=abc123"        "first deploy records the new tag"
assert_contains "$env_file" "PREVIOUS_TAG="           "first deploy leaves PREVIOUS_TAG empty"
assert_contains "$env_file" "DEPLOY_UID=$(id -u)"     ".env carries the deploy user's uid"
assert_contains "$env_file" "DEPLOY_GID=$(id -g)"     ".env carries the deploy user's gid"
assert_contains "$env_file" "HTTP_PORT=80"            "HTTP_PORT defaults to 80"
refute_contains "$env_file" "TEAM_TOKEN"              "deploy metadata never holds app secrets"

run_deploy def456
env_file="$(cat "$box/.env")"
assert_contains "$env_file" "IMAGE_TAG=def456"        "second deploy records the new tag"
assert_contains "$env_file" "PREVIOUS_TAG=abc123"     "second deploy records the prior tag for rollback"

echo
echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ]
