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
      up)      exit "${FAKE_COMPOSE_UP_RC:-0}" ;;
      *)       exit 0 ;;
    esac ;;
  load)  cat > /dev/null; exit "${FAKE_LOAD_RC:-0}" ;;
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
        FAKE_IMAGE_TAGS FAKE_CURL_RC FAKE_LOAD_RC FAKE_COMPOSE_UP_RC
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
assert "$(sed -n 's/^PREVIOUS_TAG=//p' <<<"$env_file")" "" "first deploy leaves PREVIOUS_TAG empty"
assert_contains "$env_file" "DEPLOY_UID=$(id -u)"     ".env carries the deploy user's uid"
assert_contains "$env_file" "DEPLOY_GID=$(id -g)"     ".env carries the deploy user's gid"
assert_contains "$env_file" "HTTP_PORT=80"            "HTTP_PORT defaults to 80"
refute_contains "$env_file" "TEAM_TOKEN"              "deploy metadata never holds app secrets"

run_deploy def456
env_file="$(cat "$box/.env")"
assert_contains "$env_file" "IMAGE_TAG=def456"        "second deploy records the new tag"
assert_contains "$env_file" "PREVIOUS_TAG=abc123"     "second deploy records the prior tag for rollback"

# --- image load --------------------------------------------------------------
new_box
mkdir -p "$box/tmp"
printf 'not-a-real-image' | gzip > "$box/tmp/image.tar.gz"
run_deploy abc123
assert "$rc" 0 "a healthy deploy exits 0"
assert_contains "$(cat "$DOCKER_LOG")" "load" "the tarball is handed to docker load"
# shellcheck disable=SC2015 # deliberate: notok/ok always return 0, so C can never double-fire
[ -f "$box/tmp/image.tar.gz" ] \
  && notok "the tarball is deleted after loading" \
  || ok "the tarball is deleted after loading"

new_box
export FAKE_IMAGE_INSPECT_RC=1
run_deploy abc123
assert "$rc" 1 "no tarball and an unknown tag aborts"
assert_contains "$out" "not in the local store" "the abort explains why"
refute_contains "$(cat "$DOCKER_LOG")" "compose up" "an unknown tag never reaches compose up"

# Rollback usage: no tarball, but the tag already exists locally.
new_box
run_deploy abc123
assert "$rc" 0 "an already-loaded tag deploys with no tarball (the rollback path)"

# --- start and health gate ---------------------------------------------------
new_box
run_deploy abc123
log="$(cat "$DOCKER_LOG")"
assert_contains "$log" "compose up -d --remove-orphans" "the service is started detached"
assert_contains "$out" "healthy" "a passing health gate says so"

new_box
export FAKE_CURL_RC=1
run_deploy abc123
assert "$rc" 1 "a failing health gate fails the deploy"
assert_contains "$(cat "$DOCKER_LOG")" "compose logs --tail=100" "a failing health gate dumps container logs"

# --- docker failures honour the exit-code contract ---------------------------
new_box
mkdir -p "$box/tmp"
printf 'not-a-real-image' | gzip > "$box/tmp/image.tar.gz"
export FAKE_LOAD_RC=1
run_deploy abc123
assert "$rc" 1 "a failed docker load exits 1, not docker's own status"
assert_contains "$out" "deploy:" "a failed load reports in the script's own error format"
refute_contains "$(cat "$DOCKER_LOG")" "compose up" "a failed load never starts the service"

new_box
export FAKE_COMPOSE_UP_RC=1
run_deploy abc123
assert "$rc" 1 "a failed compose up exits 1, not docker's own status"
assert_contains "$out" "deploy:" "a failed start reports in the script's own error format"

# The trap must fire even when the run dies before the normal cleanup point.
new_box
mkdir -p "$box/tmp"
printf 'not-a-real-image' | gzip > "$box/tmp/image.tar.gz"
export FAKE_IMAGE_INSPECT_RC=1
run_deploy abc123
assert "$rc" 1 "an unknown tag still fails"
# shellcheck disable=SC2015 # deliberate: notok/ok always return 0, so C can never double-fire
[ -f "$box/tmp/image.tar.gz" ] \
  && notok "the EXIT trap removes the tarball even on a failed run" \
  || ok "the EXIT trap removes the tarball even on a failed run"

echo
echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ]
