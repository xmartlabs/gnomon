# Dashboard VM Deploy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A manual GitHub Actions workflow that builds the dashboard image, ships it to a Linux VM over SSH, and starts it with a health gate and automatic rollback — with every byte of dashboard state confined to `~/gnomon` on that VM.

**Architecture:** Actions builds `gnomon-dashboard:<sha12>`, `docker save`s it to a gzipped tarball, and `scp`s that plus a compose file, a `deploy.sh`, and a rendered secrets file to `~/gnomon/`. `deploy.sh` runs on the host: it loads the image, records the outgoing tag as a rollback target, brings the service up with `docker compose`, polls `/` for health, and on failure restores the previous tag. No registry credentials ever touch the VM.

**Tech Stack:** GitHub Actions, Docker + Compose v2 plugin, Bash, shellcheck. No new runtime dependencies in the dashboard itself.

**Spec:** `docs/specs/2026-09-01-dashboard-vm-deploy-design.md`

## Global Constraints

Every task's requirements implicitly include these. Values are verbatim from the spec.

- Image repository name is exactly `gnomon-dashboard`. Tag is `${GITHUB_SHA::12}` (first 12 hex chars).
- Host directory is `~/gnomon`. Nothing this work creates may live outside it. (Docker's own `/var/lib/docker` store is out of scope and is not relocated.)
- Host port defaults to `80`, container port is always `3000`.
- `.env` in `~/gnomon` is **generated on the host by `deploy.sh`** and holds deploy metadata only (`IMAGE_TAG`, `PREVIOUS_TAG`, `DEPLOY_UID`, `DEPLOY_GID`, `HTTP_PORT`). `app.env` is **rendered by the workflow** and holds application secrets only, mode 0600.
- `TRUST_PROXY` must **not** be set anywhere in this work. It is only safe once port 80 is firewalled to Cloudflare's ranges; see the comment block in `dashboard/src/lib/rate-limit.ts`.
- `StrictHostKeyChecking=no` must **never** appear. Host keys are pinned from the `DEPLOY_SSH_KNOWN_HOSTS` secret and the job fails when it is unset.
- Secrets are written to a file and copied; they never appear in an `ssh` command line.
- The workflow trigger is `workflow_dispatch` only — no `push`, no `pull_request`, no `schedule`.
- The compose project name is pinned to `gnomon`. The host compose file must have no `build:` key.
- Plans live in `docs/plans/`, specs in `docs/specs/`. `docs/superpowers/` is gitignored in this repo — do not write there.

## File Structure

| Path | Responsibility |
|---|---|
| `dashboard/deploy/docker-compose.yml` | The host service definition. Nothing else. |
| `dashboard/deploy/deploy.sh` | All host-side switch logic: preflight, load, tag bookkeeping, health gate, rollback, prune. Runnable by hand — that is the rollback path. |
| `dashboard/deploy/tests/compose_test.sh` | Asserts the rendered compose config. |
| `dashboard/deploy/tests/deploy_test.sh` | Exercises `deploy.sh` against stubbed `docker`/`curl` binaries. No real Docker needed. |
| `dashboard/deploy/tests/workflow_test.sh` | Locks the security invariants of the workflow YAML. |
| `dashboard/deploy/README.md` | Operator doc: VM prep, secrets, rollback, backup. |
| `.github/workflows/dashboard-deploy.yml` | The CI driver. Thin — it builds, copies, and invokes `deploy.sh`. |
| `.github/workflows/ci.yml` | Gains a `deploy-checks` job. |
| `dashboard/.dockerignore` | Gains `deploy/`. |
| `README.md` | Gains a pointer to the deploy doc. |

The split that matters: **`deploy.sh` holds the logic, the workflow holds the plumbing.** Debugging happens in the script, and the script must be runnable without GitHub.

---

### Task 1: Compose definition and build-context exclusion

**Files:**
- Create: `dashboard/deploy/docker-compose.yml`
- Create: `dashboard/deploy/tests/compose_test.sh`
- Modify: `dashboard/.dockerignore`

**Interfaces:**
- Consumes: nothing.
- Produces: a compose file interpolating `IMAGE_TAG`, `DEPLOY_UID`, `DEPLOY_GID`, `HTTP_PORT` from `.env` in its own directory, reading container env from `./app.env`, and bind-mounting `./data` to `/data`. Task 2's `deploy.sh` writes exactly those four variables.

- [ ] **Step 1: Write the failing test**

Create `dashboard/deploy/tests/compose_test.sh`:

```bash
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
refute "the host never builds the image"            '^[[:space:]]*build:'
refute "TRUST_PROXY is not set by the deployment"   'TRUST_PROXY'

if [ "$fail" -ne 0 ]; then
  echo "--- rendered config ---"
  echo "$rendered"
fi
exit "$fail"
```

Make it executable: `chmod +x dashboard/deploy/tests/compose_test.sh`

- [ ] **Step 2: Run test to verify it fails**

Run: `./dashboard/deploy/tests/compose_test.sh`
Expected: FAIL — `cp: cannot stat '.../docker-compose.yml': No such file or directory`

- [ ] **Step 3: Write the compose file**

Create `dashboard/deploy/docker-compose.yml`:

```yaml
# Host-side service definition for the self-hosted dashboard. Copied to
# ~/gnomon by .github/workflows/dashboard-deploy.yml; deploy.sh drives it.
#
# Interpolated from ~/gnomon/.env, which deploy.sh generates on the box.
# Container secrets come from ~/gnomon/app.env, which the workflow renders.
name: gnomon

services:
  dashboard:
    image: gnomon-dashboard:${IMAGE_TAG}
    # The image declares USER node (uid 1000), but with a bind mount the HOST
    # directory's ownership wins — the Dockerfile's `chown node:node /data`
    # only touched the image layer. Running as the deploy user's own uid:gid
    # keeps ~/gnomon/data writable by the container and readable (and
    # backup-able) by the operator without sudo, whatever uid they happen to be.
    user: "${DEPLOY_UID}:${DEPLOY_GID}"
    ports:
      - "${HTTP_PORT}:3000"
    env_file: app.env
    # One mount covers ALL dashboard state: src/lib/paths.ts routes the SQLite
    # DB and its WAL sidecars, the persisted jwt-secret, and the coach cache
    # through a single dataDir().
    volumes:
      - ./data:/data
    restart: unless-stopped
    healthcheck:
      # node is the only HTTP-capable binary in node:22-bookworm-slim — there
      # is no curl and no wget — so `docker compose ps` can still tell the
      # truth about this container months from now.
      test:
        - CMD
        - node
        - -e
        - "fetch('http://127.0.0.1:3000/').then(r => process.exit(r.ok ? 0 : 1)).catch(() => process.exit(1))"
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 20s
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./dashboard/deploy/tests/compose_test.sh`
Expected: eleven `ok   -` lines, exit 0.

- [ ] **Step 5: Keep the deploy files out of the image build context**

Modify `dashboard/.dockerignore` — append after the existing `playwright-report` line:

```
# Host deployment files. They sit in the build context otherwise, where they
# are never used but do bust the layer cache on every deploy-script edit.
deploy
```

- [ ] **Step 6: Verify the image still builds and the deploy dir is absent from it**

Run:
```bash
docker build -t gnomon-dashboard:ctxcheck ./dashboard
docker run --rm --entrypoint sh gnomon-dashboard:ctxcheck -c 'ls /app | grep -c deploy || echo "absent (expected)"'
```
Expected: build succeeds; second command prints `absent (expected)`.

- [ ] **Step 7: Commit**

```bash
git add dashboard/deploy/docker-compose.yml dashboard/deploy/tests/compose_test.sh dashboard/.dockerignore
git commit -m "feat(deploy): host compose definition for the dashboard VM"
```

---

### Task 2: deploy.sh — test harness, usage, preflight, and .env generation

**Files:**
- Create: `dashboard/deploy/deploy.sh`
- Create: `dashboard/deploy/tests/deploy_test.sh`

**Interfaces:**
- Consumes: `dashboard/deploy/docker-compose.yml` from Task 1 (the four interpolated variables).
- Produces:
  - `deploy.sh <image-tag>` — exit 2 on missing argument, exit 1 on any preflight or deploy failure, exit 0 on a healthy deploy.
  - Environment knobs: `HTTP_PORT` (default `80`), `HEALTH_TIMEOUT` (default `60`), `HEALTH_INTERVAL` (default `2`).
  - Shell functions `die`, `preflight`, `current_tag`, `write_env`. Tasks 3 and 4 add `load_image`, `healthy`, `prune_images` to the same file.
  - `dashboard/deploy/tests/deploy_test.sh` — a self-contained runner; Tasks 3 and 4 append cases to it.

- [ ] **Step 1: Write the failing test**

Create `dashboard/deploy/tests/deploy_test.sh`:

```bash
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
```

Make it executable: `chmod +x dashboard/deploy/tests/deploy_test.sh`

- [ ] **Step 2: Run test to verify it fails**

Run: `./dashboard/deploy/tests/deploy_test.sh`
Expected: FAIL — `cp: cannot stat '.../deploy.sh': No such file or directory`

- [ ] **Step 3: Write the minimal implementation**

Create `dashboard/deploy/deploy.sh`:

```bash
#!/usr/bin/env bash
# Host-side deploy for the self-hosted gnomon dashboard.
#
#   ./deploy.sh <image-tag>
#
# Copied to ~/gnomon by .github/workflows/dashboard-deploy.yml, but designed to
# be run by hand — that is the rollback path. With tmp/image.tar.gz present the
# tag is loaded from it; without, the tag must already be in the local store.
#
# Env: HTTP_PORT (80), HEALTH_TIMEOUT (60), HEALTH_INTERVAL (2)
set -euo pipefail

cd "$(dirname "$0")"

IMAGE_REPO=gnomon-dashboard
TARBALL=tmp/image.tar.gz
HTTP_PORT="${HTTP_PORT:-80}"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-60}"
HEALTH_INTERVAL="${HEALTH_INTERVAL:-2}"

die() {
  echo "deploy: $*" >&2
  exit 1
}

preflight() {
  docker version >/dev/null 2>&1 || die \
    "cannot reach the Docker daemon as $(id -un). Install Docker Engine and add this user to the docker group: sudo usermod -aG docker $(id -un) — then log out and back in."
  docker compose version >/dev/null 2>&1 || die \
    "the Docker Compose plugin is missing. Install docker-compose-plugin (v2); the standalone docker-compose script is not used here."
  mkdir -p data tmp
  # Checked before anything starts: a data/ the container cannot write to
  # otherwise surfaces as a confusing SQLite SQLITE_CANTOPEN *after* an
  # apparently green deploy.
  [ -w data ] || die \
    "$(pwd)/data is not writable by $(id -un). The container writes the SQLite DB there. Fix with: sudo chown -R $(id -u):$(id -g) $(pwd)/data"
}

# The tag currently deployed, or empty on a first deploy.
current_tag() {
  [ -f .env ] || return 0
  sed -n 's/^IMAGE_TAG=//p' .env | tail -n1
}

# $1 = IMAGE_TAG, $2 = PREVIOUS_TAG
write_env() {
  cat > .env <<EOF
# GENERATED BY deploy.sh — do not hand-edit; the next deploy overwrites it.
# Compose interpolation only. Application secrets live in app.env.
IMAGE_TAG=$1
PREVIOUS_TAG=$2
DEPLOY_UID=$(id -u)
DEPLOY_GID=$(id -g)
HTTP_PORT=$HTTP_PORT
EOF
}

TAG="${1:-}"
[ -n "$TAG" ] || {
  echo "usage: deploy.sh <image-tag>" >&2
  exit 2
}

preflight

PREVIOUS_TAG="$(current_tag)"
write_env "$TAG" "$PREVIOUS_TAG"
```

Make it executable: `chmod +x dashboard/deploy/deploy.sh`

- [ ] **Step 4: Run test to verify it passes**

Run: `./dashboard/deploy/tests/deploy_test.sh`
Expected: `16 passed, 0 failed`, exit 0. (`14 passed` with one `skip` line if you
run as root — the gate is **0 failed**, which is what CI checks.)

- [ ] **Step 5: Run shellcheck**

Run: `shellcheck dashboard/deploy/deploy.sh dashboard/deploy/tests/deploy_test.sh`
Expected: no output, exit 0. (Install with `sudo apt-get install -y shellcheck` if absent.)

If it flags `SC2086` on the stub's `printf '%s\n' ${FAKE_IMAGE_TAGS:-}`, that word-splitting is deliberate — the stub turns a space-separated list into lines. Add `# shellcheck disable=SC2086` on the line above it inside the heredoc, with a comment saying why.

- [ ] **Step 6: Commit**

```bash
git add dashboard/deploy/deploy.sh dashboard/deploy/tests/deploy_test.sh
git commit -m "feat(deploy): deploy.sh preflight and deploy-metadata bookkeeping"
```

---

### Task 3: deploy.sh — image load, service start, and health gate

**Files:**
- Modify: `dashboard/deploy/deploy.sh`
- Modify: `dashboard/deploy/tests/deploy_test.sh`

**Interfaces:**
- Consumes: `die`, `preflight`, `current_tag`, `write_env`, and the `IMAGE_REPO` / `TARBALL` / `HTTP_PORT` / `HEALTH_TIMEOUT` / `HEALTH_INTERVAL` variables from Task 2.
- Produces: `load_image()` (no args, uses `$TAG`) and `healthy()` (no args, returns 0 when `http://127.0.0.1:$HTTP_PORT/` answers within `HEALTH_TIMEOUT`). Task 4 consumes `healthy` and the `PREVIOUS_TAG` variable.

- [ ] **Step 1: Write the failing test**

In `dashboard/deploy/tests/deploy_test.sh`, insert these cases immediately **before** the final `echo` / `$pass passed` block:

```bash
# --- image load --------------------------------------------------------------
new_box
mkdir -p "$box/tmp"
printf 'not-a-real-image' | gzip > "$box/tmp/image.tar.gz"
run_deploy abc123
assert "$rc" 0 "a healthy deploy exits 0"
assert_contains "$(cat "$DOCKER_LOG")" "load" "the tarball is handed to docker load"
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./dashboard/deploy/tests/deploy_test.sh`
Expected: the new assertions fail — `FAIL - the tarball is handed to docker load (missing 'load')`, `FAIL - the service is started detached`, and so on. The Task 2 assertions still pass.

- [ ] **Step 3: Write the minimal implementation**

In `dashboard/deploy/deploy.sh`, add these two functions after `write_env`:

```bash
load_image() {
  if [ -f "$TARBALL" ]; then
    gunzip -c "$TARBALL" | docker load
    rm -f "$TARBALL"
  fi
  docker image inspect "$IMAGE_REPO:$TAG" >/dev/null 2>&1 || die \
    "image $IMAGE_REPO:$TAG is not in the local store and no $TARBALL was supplied. To roll back, pass a tag that is still loaded: docker image ls $IMAGE_REPO"
}

# Polls the published port from the host — the same endpoint
# .github/workflows/dashboard-image.yml already uses as a readiness probe.
healthy() {
  local deadline=$((SECONDS + HEALTH_TIMEOUT))
  while [ "$SECONDS" -lt "$deadline" ]; do
    if curl -fsS -o /dev/null "http://127.0.0.1:$HTTP_PORT/"; then
      return 0
    fi
    sleep "$HEALTH_INTERVAL"
  done
  return 1
}
```

Then replace the tail of the script (everything from `preflight` onward) with:

```bash
preflight

# Unconditional: a failure anywhere below must not leave hundreds of megabytes
# sitting in the operator's home directory.
trap 'rm -f "$TARBALL"' EXIT

load_image

PREVIOUS_TAG="$(current_tag)"
write_env "$TAG" "$PREVIOUS_TAG"

echo "deploy: starting $IMAGE_REPO:$TAG on port $HTTP_PORT"
docker compose up -d --remove-orphans

if healthy; then
  echo "deploy: healthy — http://127.0.0.1:$HTTP_PORT/ is serving $IMAGE_REPO:$TAG"
  exit 0
fi

echo "deploy: $IMAGE_REPO:$TAG failed the health check after ${HEALTH_TIMEOUT}s" >&2
docker compose logs --tail=100 >&2 || true
die "deploy failed"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./dashboard/deploy/tests/deploy_test.sh`
Expected: `27 passed, 0 failed`, exit 0 (two fewer if running as root).

- [ ] **Step 5: Run shellcheck**

Run: `shellcheck dashboard/deploy/deploy.sh dashboard/deploy/tests/deploy_test.sh`
Expected: no output, exit 0.

- [ ] **Step 6: Commit**

```bash
git add dashboard/deploy/deploy.sh dashboard/deploy/tests/deploy_test.sh
git commit -m "feat(deploy): load the shipped image, start the service, gate on health"
```

---

### Task 4: deploy.sh — rollback and image pruning

**Files:**
- Modify: `dashboard/deploy/deploy.sh`
- Modify: `dashboard/deploy/tests/deploy_test.sh`

**Interfaces:**
- Consumes: `healthy`, `write_env`, `die`, and `PREVIOUS_TAG` from Tasks 2–3.
- Produces: `prune_images <keep_a> <keep_b>`. Nothing later consumes it; this task completes `deploy.sh`.

- [ ] **Step 1: Write the failing test**

In `dashboard/deploy/tests/deploy_test.sh`, insert these cases immediately **before** the final `echo` / `$pass passed` block:

```bash
# --- rollback ----------------------------------------------------------------
new_box
run_deploy good111                      # establishes a known-good tag
: > "$DOCKER_LOG"                       # count only the failing deploy's calls
export FAKE_CURL_RC=1
run_deploy bad222
assert "$rc" 1 "a failing new image fails the workflow run"
env_file="$(cat "$box/.env")"
assert_contains "$env_file" "IMAGE_TAG=good111" "a failing health gate restores the previous tag"
assert_contains "$out" "rolling back" "the rollback is announced"
# Two `compose up` calls: the bad image, then the restored one.
assert "$(grep -c 'compose up' "$DOCKER_LOG")" 2 "rollback brings the previous image back up"

new_box
export FAKE_CURL_RC=1
run_deploy first333
assert "$rc" 1 "a failing FIRST deploy fails"
refute_contains "$out" "rolling back" "a first deploy has nothing to roll back to"
assert_contains "$out" "first deploy" "the first-deploy case says so explicitly"

new_box
run_deploy same444
export FAKE_CURL_RC=1
run_deploy same444
assert "$rc" 1 "redeploying the same failing tag fails"
refute_contains "$out" "rolling back" "rolling back to the identical failing tag is not attempted"

# --- prune -------------------------------------------------------------------
new_box
run_deploy keepA
export FAKE_IMAGE_TAGS="old1 old2 keepA keepB"
run_deploy keepB
log="$(cat "$DOCKER_LOG")"
assert_contains "$log" "image rm gnomon-dashboard:old1" "a stale tag is pruned"
assert_contains "$log" "image rm gnomon-dashboard:old2" "every stale tag is pruned"
refute_contains "$log" "image rm gnomon-dashboard:keepA" "the previous tag is kept for rollback"
refute_contains "$log" "image rm gnomon-dashboard:keepB" "the current tag is kept"

new_box
export FAKE_IMAGE_TAGS="<none> onlytag"
run_deploy onlytag
refute_contains "$(cat "$DOCKER_LOG")" "image rm gnomon-dashboard:<none>" "dangling entries are left to docker"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./dashboard/deploy/tests/deploy_test.sh`
Expected: the new assertions fail — `FAIL - a failing health gate restores the previous tag`, `FAIL - a stale tag is pruned`, and so on.

- [ ] **Step 3: Write the minimal implementation**

In `dashboard/deploy/deploy.sh`, add this function after `healthy`:

```bash
# Removes gnomon-dashboard images other than the two kept tags. Scoped to this
# repository name only — it must never touch anything else running on the box.
prune_images() {
  local keep_a="$1" keep_b="$2" tag
  while read -r tag; do
    case "$tag" in
      "" | "<none>" | "$keep_a" | "$keep_b") continue ;;
    esac
    docker image rm "$IMAGE_REPO:$tag" >/dev/null 2>&1 || true
  done < <(docker image ls "$IMAGE_REPO" --format '{{.Tag}}')
}
```

Then replace everything from `if healthy; then` to the end of the file with:

```bash
if healthy; then
  echo "deploy: healthy — http://127.0.0.1:$HTTP_PORT/ is serving $IMAGE_REPO:$TAG"
  prune_images "$TAG" "$PREVIOUS_TAG"
  exit 0
fi

echo "deploy: $IMAGE_REPO:$TAG failed the health check after ${HEALTH_TIMEOUT}s" >&2
docker compose logs --tail=100 >&2 || true

if [ -z "$PREVIOUS_TAG" ]; then
  die "no previous image to roll back to (first deploy). The box is NOT serving — fix the image and deploy again."
fi
if [ "$PREVIOUS_TAG" = "$TAG" ]; then
  die "the previous tag is the same failing image ($TAG), so there is nothing to roll back to. The box is NOT serving."
fi

echo "deploy: rolling back to $IMAGE_REPO:$PREVIOUS_TAG" >&2
# PREVIOUS_TAG stays pointing at itself, so the next deploy's rollback target is
# this known-good image rather than the one that just failed.
write_env "$PREVIOUS_TAG" "$PREVIOUS_TAG"
docker compose up -d --remove-orphans

if healthy; then
  die "rolled back to $PREVIOUS_TAG, which is serving. $TAG was NOT deployed."
fi
die "the rollback to $PREVIOUS_TAG ALSO failed its health check. The box is NOT serving — investigate now."
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./dashboard/deploy/tests/deploy_test.sh`
Expected: `41 passed, 0 failed`, exit 0 (two fewer if running as root).

- [ ] **Step 5: Run shellcheck**

Run: `shellcheck dashboard/deploy/deploy.sh dashboard/deploy/tests/deploy_test.sh`
Expected: no output, exit 0.

- [ ] **Step 6: Commit**

```bash
git add dashboard/deploy/deploy.sh dashboard/deploy/tests/deploy_test.sh
git commit -m "feat(deploy): roll back on a failed health gate and prune stale images"
```

---

### Task 5: The GitHub Actions deploy workflow

**Files:**
- Create: `.github/workflows/dashboard-deploy.yml`
- Create: `dashboard/deploy/tests/workflow_test.sh`

**Interfaces:**
- Consumes: `dashboard/deploy/deploy.sh` and `dashboard/deploy/docker-compose.yml` from Tasks 1–4; invokes `deploy.sh <tag>` with `HTTP_PORT` in the environment.
- Produces: nothing later tasks consume, except that Task 6 runs `workflow_test.sh` and Task 7 documents the secret names defined here.

Note on scope: the workflow is not unit-testable in any honest sense. `workflow_test.sh` does not prove it deploys — it locks the handful of invariants whose quiet regression would be a security problem, so a future edit that reintroduces one fails CI instead of shipping.

- [ ] **Step 1: Write the failing test**

Create `dashboard/deploy/tests/workflow_test.sh`:

```bash
#!/usr/bin/env bash
# Locks the security-relevant invariants of the deploy workflow. This does not
# prove the workflow deploys — it proves a future edit has not quietly removed
# host-key pinning, leaked a secret onto a command line, or made the deploy
# automatic.
set -uo pipefail

repo_root="$(cd "$(dirname "$0")/../../.." && pwd)"
wf="$repo_root/.github/workflows/dashboard-deploy.yml"

fail=0
check()  { if grep -Eq "$2" "$wf"; then echo "ok   - $1"; else echo "FAIL - $1"; fail=1; fi; }
refute() { if grep -Eq "$2" "$wf"; then echo "FAIL - $1"; fail=1; else echo "ok   - $1"; fi; }

if [ ! -f "$wf" ]; then
  echo "FAIL - $wf does not exist"
  exit 1
fi

check  "the deploy is manual"                     '^[[:space:]]+workflow_dispatch:'
refute "nothing deploys automatically"            '^[[:space:]]+(push|pull_request|schedule):'
check  "concurrent deploys are serialised"        '^[[:space:]]+group: dashboard-deploy'
check  "an in-flight deploy is never cancelled"   'cancel-in-progress: false'
refute "host-key checking is never disabled"      'StrictHostKeyChecking=no'
check  "host keys are pinned from a secret"       'DEPLOY_SSH_KNOWN_HOSTS'
check  "the image is built, never pulled"         'gnomon-dashboard:'
check  "the image travels as a saved tarball"     'docker save'
check  "deploy.sh drives the host"                'deploy\.sh'
check  "key material is removed afterwards"       'rm -f ~/\.ssh/deploy_key'
refute "TRUST_PROXY is not enabled here"          'TRUST_PROXY'
# Secrets reach the box as a copied file. On an ssh command line they would be
# visible in `ps` to every other user on the VM and land in shell history.
refute "no secret is interpolated into an ssh line" 'ssh .*secrets\.'

exit "$fail"
```

Make it executable: `chmod +x dashboard/deploy/tests/workflow_test.sh`

- [ ] **Step 2: Run test to verify it fails**

Run: `./dashboard/deploy/tests/workflow_test.sh`
Expected: FAIL — `FAIL - .../dashboard-deploy.yml does not exist`, exit 1.

- [ ] **Step 3: Write the workflow**

Create `.github/workflows/dashboard-deploy.yml`:

```yaml
name: dashboard-deploy

# Manual only. ci.yml already runs the dashboard unit and e2e suites on every
# PR and every push to main, so this workflow is the SECOND place the code is
# tested, not the first — it builds and ships without re-running them. What it
# keeps is deploy.sh's health gate, which catches what CI cannot see: an image
# that builds green but will not boot against this box's env and volume.
# Design: docs/specs/2026-09-01-dashboard-vm-deploy-design.md
on:
  workflow_dispatch:

# Two deploys must never interleave over the same tag flip — and cancelling one
# mid-flight is worse still, since it can leave the box between images.
concurrency:
  group: dashboard-deploy
  cancel-in-progress: false

jobs:
  deploy:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    permissions:
      contents: read
    env:
      SSH_PORT: ${{ vars.DEPLOY_SSH_PORT || '22' }}
      HTTP_PORT: ${{ vars.HTTP_PORT || '80' }}
      DEPLOY_HOST: ${{ secrets.DEPLOY_HOST }}
      DEPLOY_USER: ${{ secrets.DEPLOY_USER }}
    steps:
      - uses: actions/checkout@v4

      - name: Resolve the image tag
        id: tag
        run: echo "tag=${GITHUB_SHA::12}" >> "$GITHUB_OUTPUT"

      - uses: docker/setup-buildx-action@v3

      # With no test gate ahead of it, the build is the whole critical path, and
      # its slowest step is compiling the better-sqlite3 native addon — hence
      # the layer cache.
      - name: Build the image
        uses: docker/build-push-action@v6
        with:
          context: ./dashboard
          load: true
          tags: gnomon-dashboard:${{ steps.tag.outputs.tag }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

      - name: Save the image
        run: docker save "gnomon-dashboard:${{ steps.tag.outputs.tag }}" | gzip > image.tar.gz

      # Rendered to a file and copied, never echoed through ssh: a secret on a
      # remote command line is visible in `ps` to every other user on the box
      # and lands in the remote shell history.
      - name: Render app.env
        env:
          TEAM_TOKEN: ${{ secrets.TEAM_TOKEN }}
          JWT_SECRET: ${{ secrets.JWT_SECRET }}
          LLM_API_KEY: ${{ secrets.LLM_API_KEY }}
          LLM_MODEL: ${{ secrets.LLM_MODEL }}
          MAX_INGEST_BYTES: ${{ secrets.MAX_INGEST_BYTES }}
        run: |
          if [ -z "$TEAM_TOKEN" ]; then
            echo "::error::TEAM_TOKEN secret is unset — the container refuses to boot without it."
            exit 1
          fi
          umask 077
          : > app.env
          # Only non-empty values are written: an unset optional key must read
          # as unset, not as an empty string the app has to defend against.
          for key in TEAM_TOKEN JWT_SECRET LLM_API_KEY LLM_MODEL MAX_INGEST_BYTES; do
            value="${!key}"
            [ -n "$value" ] || continue
            printf '%s=%s\n' "$key" "$value" >> app.env
          done

      - name: Install the SSH key and pinned host key
        env:
          DEPLOY_SSH_KEY: ${{ secrets.DEPLOY_SSH_KEY }}
          DEPLOY_SSH_KNOWN_HOSTS: ${{ secrets.DEPLOY_SSH_KNOWN_HOSTS }}
        run: |
          if [ -z "$DEPLOY_SSH_KNOWN_HOSTS" ]; then
            echo "::error::DEPLOY_SSH_KNOWN_HOSTS is unset. This job hands TEAM_TOKEN to whatever answers at DEPLOY_HOST, so an unpinned host key is not acceptable. Generate it with: ssh-keyscan -p <port> <host>"
            exit 1
          fi
          mkdir -p ~/.ssh
          chmod 700 ~/.ssh
          umask 077
          printf '%s\n' "$DEPLOY_SSH_KEY" > ~/.ssh/deploy_key
          printf '%s\n' "$DEPLOY_SSH_KNOWN_HOSTS" > ~/.ssh/known_hosts

      - name: Create the remote directories
        run: |
          ssh -i ~/.ssh/deploy_key -p "$SSH_PORT" -o StrictHostKeyChecking=yes \
            "$DEPLOY_USER@$DEPLOY_HOST" 'mkdir -p ~/gnomon/data ~/gnomon/tmp'

      - name: Copy the release
        run: |
          scp -i ~/.ssh/deploy_key -P "$SSH_PORT" -o StrictHostKeyChecking=yes \
            dashboard/deploy/docker-compose.yml dashboard/deploy/deploy.sh app.env \
            "$DEPLOY_USER@$DEPLOY_HOST:gnomon/"
          scp -i ~/.ssh/deploy_key -P "$SSH_PORT" -o StrictHostKeyChecking=yes \
            image.tar.gz "$DEPLOY_USER@$DEPLOY_HOST:gnomon/tmp/"

      # deploy.sh owns everything from here: load, tag bookkeeping, compose up,
      # health gate, rollback, prune.
      - name: Deploy
        run: |
          ssh -i ~/.ssh/deploy_key -p "$SSH_PORT" -o StrictHostKeyChecking=yes \
            "$DEPLOY_USER@$DEPLOY_HOST" \
            "cd ~/gnomon && chmod +x deploy.sh && HTTP_PORT=$HTTP_PORT ./deploy.sh ${{ steps.tag.outputs.tag }}"

      - name: Remove key material
        if: always()
        run: rm -f ~/.ssh/deploy_key ~/.ssh/known_hosts app.env
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./dashboard/deploy/tests/workflow_test.sh`
Expected: twelve `ok   -` lines, exit 0.

- [ ] **Step 5: Confirm GitHub accepts the YAML**

Run: `python3 -c "import sys,yaml; yaml.safe_load(open('.github/workflows/dashboard-deploy.yml')); print('parses')"`
Expected: `parses`. If PyYAML is unavailable, skip — GitHub surfaces a parse error on the Actions tab as soon as the branch is pushed, which Task 8 will catch.

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/dashboard-deploy.yml dashboard/deploy/tests/workflow_test.sh
git commit -m "feat(deploy): manual GitHub Actions workflow that ships the image over SSH"
```

---

### Task 6: Wire the deploy checks into CI

**Files:**
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: the three test scripts from Tasks 1, 2–4, and 5.
- Produces: a `deploy-checks` job that gates PRs.

Deliberately **not** added: `actionlint`. It would mean a third-party action or a downloaded binary for a check the invariant greps in `workflow_test.sh` already cover, and GitHub itself rejects malformed workflow YAML visibly. Revisit only if the workflow grows conditionals.

- [ ] **Step 1: Write the failing test**

There is no test framework for CI config; the check is that the job runs and passes. Verify the current state first —

Run: `grep -c 'deploy-checks' .github/workflows/ci.yml || true`
Expected: `0`

- [ ] **Step 2: Add the job**

Append to `.github/workflows/ci.yml`, after the existing `dashboard` job:

```yaml
  # The VM deploy path is unattended shell that runs `rm` and `docker image rm`
  # against a live box, so it gets the same PR gate the app code does.
  deploy-checks:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@v4

      - name: Install shellcheck
        run: sudo apt-get update && sudo apt-get install -y shellcheck

      # An unquoted variable in one of those rm/docker calls is exactly the bug
      # shellcheck catches.
      - name: Lint the deploy shell
        run: shellcheck dashboard/deploy/deploy.sh dashboard/deploy/tests/*.sh

      - name: Compose config renders
        run: ./dashboard/deploy/tests/compose_test.sh

      - name: deploy.sh behaves
        run: ./dashboard/deploy/tests/deploy_test.sh

      - name: Deploy workflow invariants hold
        run: ./dashboard/deploy/tests/workflow_test.sh
```

- [ ] **Step 3: Run every check locally, exactly as CI will**

Run:
```bash
shellcheck dashboard/deploy/deploy.sh dashboard/deploy/tests/*.sh \
  && ./dashboard/deploy/tests/compose_test.sh \
  && ./dashboard/deploy/tests/deploy_test.sh \
  && ./dashboard/deploy/tests/workflow_test.sh \
  && echo "ALL DEPLOY CHECKS PASS"
```
Expected: `ALL DEPLOY CHECKS PASS`

- [ ] **Step 4: Confirm the scripts are executable in git's index**

Run: `git ls-files -s dashboard/deploy/tests/ dashboard/deploy/deploy.sh`
Expected: every line starts with `100755`. If any shows `100644`, fix it:
```bash
git update-index --chmod=+x <path>
```
This matters: CI invokes them as `./script.sh`, which fails with "Permission denied" on a non-executable file.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: gate the VM deploy scripts on shellcheck and their own tests"
```

---

### Task 7: Operator documentation

**Files:**
- Create: `dashboard/deploy/README.md`
- Modify: `README.md` (the "Self-hosted team dashboard" section, around line 127)

**Interfaces:**
- Consumes: the secret and variable names from Task 5, the `deploy.sh` usage from Tasks 2–4.
- Produces: nothing consumed by code.

- [ ] **Step 1: Write the operator README**

Create `dashboard/deploy/README.md`:

````markdown
# Deploying the dashboard to a Linux VM

Manual deploy over SSH. GitHub Actions builds the image, ships it to the VM as a
tarball, and `deploy.sh` switches the running container with a health gate and
automatic rollback. No registry credentials live on the box.

Design rationale: `docs/specs/2026-09-01-dashboard-vm-deploy-design.md`.

## One-time VM preparation

1. Install Docker Engine and the Compose **plugin** (v2), then enable the
   service so the container comes back after a reboot:

   ```bash
   sudo systemctl enable --now docker
   ```

2. Add the deploy user to the `docker` group, then log out and back in:

   ```bash
   sudo usermod -aG docker "$USER"
   ```

3. Open port 80 in the host firewall and in any cloud security group.

4. Create a **dedicated** deploy keypair — not your personal key — and install
   the public half:

   ```bash
   ssh-keygen -t ed25519 -f ./gnomon-deploy -C "gnomon dashboard deploy" -N ""
   ssh-copy-id -i ./gnomon-deploy.pub <user>@<host>
   ```

   The private half becomes the `DEPLOY_SSH_KEY` secret; delete your local copy
   afterwards.

5. Capture the host key for pinning:

   ```bash
   ssh-keyscan -p 22 <host>
   ```

   The full output becomes the `DEPLOY_SSH_KNOWN_HOSTS` secret. The workflow
   refuses to run without it — it hands `TEAM_TOKEN` to whatever answers at that
   address, so an unpinned host key is not acceptable.

`~/gnomon` needs no manual creation; the workflow makes it.

## Repository secrets

| Secret | Required | Purpose |
| --- | --- | --- |
| `DEPLOY_HOST` | yes | VM hostname or IP |
| `DEPLOY_USER` | yes | SSH user; its home holds `~/gnomon` |
| `DEPLOY_SSH_KEY` | yes | private half of the dedicated deploy key |
| `DEPLOY_SSH_KNOWN_HOSTS` | yes | pinned host key from `ssh-keyscan` |
| `TEAM_TOKEN` | yes | shared team secret; the container refuses to boot without it. Generate with `openssl rand -hex 24` |
| `JWT_SECRET` | no | leave unset — see below |
| `LLM_API_KEY` | no | Anthropic key; enables the AI coach card |
| `LLM_MODEL` | no | coach model override (default `claude-haiku-4-5`) |
| `MAX_INGEST_BYTES` | no | upload cap override (default 900 KiB) |

Repository **variables**: `DEPLOY_SSH_PORT` (default `22`), `HTTP_PORT`
(default `80`).

Leave `JWT_SECRET` unset. This is a single replica, and the app generates a
secret on first boot and persists it to `~/gnomon/data/jwt-secret`, so tokens
issued before a restart still verify after it.

## Deploying

Actions → **dashboard-deploy** → Run workflow → pick the ref. The image is
tagged with the first 12 characters of the commit sha, so what is running is
always traceable to a commit.

## What lives on the VM

```
~/gnomon/
├── docker-compose.yml   # copied from the repo each deploy
├── deploy.sh            # copied from the repo each deploy
├── .env                 # deploy metadata, generated on the box — do not hand-edit
├── app.env              # application secrets, mode 0600
├── data/                # ALL dashboard state
└── tmp/                 # image tarball in transit, deleted after loading
```

`data/` holds the SQLite database and its WAL sidecars, the persisted JWT
secret, and the coach cache — the app routes all of them through one directory.

Docker's own image store stays in `/var/lib/docker`. Everything this deployment
creates is under `~/gnomon`.

## Rolling back

A failed health check rolls back automatically. To roll back by hand, pass a tag
that is still in the local store — `deploy.sh` skips the load step when there is
no tarball:

```bash
ssh <user>@<host>
cd ~/gnomon
docker image ls gnomon-dashboard        # see what is available
HTTP_PORT=80 ./deploy.sh <old-sha>
```

Each deploy keeps the current and previous images and prunes the rest, so the
last-known-good tag is always there.

## Backups

```bash
ssh <user>@<host> 'tar czf - -C ~/gnomon data' > gnomon-data-$(date +%F).tgz
```

Stop the container first if you want a guaranteed-consistent SQLite snapshot:
`cd ~/gnomon && docker compose stop`, back up, then `docker compose start`.

## Pointing the CLI at this instance

`gnomon/upload/mirdash.py` defaults to `https://mirdash.xmartlabs.com`. Point it
at your VM with any of, in precedence order:

```bash
xl-ai-insights --mirdash-base=http://<host>
GNOMON_MIRDASH_BASE=http://<host> xl-ai-insights
# or "mirdash_base": "http://<host>" in ~/.config/gnomon/config.json
```

## TLS and reverse proxies

This deployment serves plain HTTP on port 80. Terminating TLS — Cloudflare or
otherwise — is wired separately.

**Do not set `TRUST_PROXY=1` until port 80 is unreachable except through your
proxy.** While the port is open to the internet, trusting `x-forwarded-for` lets
any client mint a fresh sign-in throttle bucket per request and brute-force the
shared `TEAM_TOKEN` unthrottled. See the comment block in
`dashboard/src/lib/rate-limit.ts`.

## Troubleshooting

| Symptom | Cause |
| --- | --- |
| `cannot reach the Docker daemon` | deploy user not in the `docker` group, or no re-login since |
| `the Docker Compose plugin is missing` | only the standalone `docker-compose` script is installed |
| `data is not writable` | `~/gnomon/data` owned by another user — the message carries the `chown` fix |
| `image ... is not in the local store` | rolling back to a tag that has already been pruned |
| Health check fails on a first deploy | there is nothing to roll back to; the box is down. Read the container logs the job printed |
````

- [ ] **Step 2: Verify every referenced path and command exists**

Run:
```bash
ls dashboard/deploy/deploy.sh dashboard/deploy/docker-compose.yml \
   docs/specs/2026-09-01-dashboard-vm-deploy-design.md dashboard/src/lib/rate-limit.ts \
   gnomon/upload/mirdash.py
grep -n "mirdash-base\|GNOMON_MIRDASH_BASE\|mirdash_base" gnomon/upload/mirdash.py | head -5
```
Expected: every path listed with no error; the grep shows all three override forms.

- [ ] **Step 3: Add the pointer to the root README**

In `README.md`, in the "Self-hosted team dashboard" section (around line 127, near the `docker compose up -d` line), add:

```markdown
> Deploying to your own Linux VM? See [`dashboard/deploy/README.md`](dashboard/deploy/README.md)
> — a manual GitHub Actions workflow that builds the image, ships it over SSH,
> and keeps all state in `~/gnomon` on the box.
```

- [ ] **Step 4: Commit**

```bash
git add dashboard/deploy/README.md README.md
git commit -m "docs(deploy): operator guide for the VM deployment"
```

---

### Task 8: End-to-end rehearsal against a real image

**Files:** none — this is verification.

**Interfaces:**
- Consumes: everything from Tasks 1–7.
- Produces: confidence that the happy path and the rollback path both work against real Docker, before any of it touches the VM.

The stubbed tests prove the decision logic. This proves the script drives real Docker correctly. It needs no VM.

- [ ] **Step 1: Build a real image and set up a scratch box**

```bash
docker build -t gnomon-dashboard:rehearsal ./dashboard
work=$(mktemp -d) && echo "$work"
cp dashboard/deploy/deploy.sh dashboard/deploy/docker-compose.yml "$work/"
printf 'TEAM_TOKEN=rehearsal-token\n' > "$work/app.env"
chmod 600 "$work/app.env"
```

- [ ] **Step 2: Deploy the good image**

```bash
cd "$work" && HTTP_PORT=8080 ./deploy.sh rehearsal
```
Expected: `deploy: healthy — http://127.0.0.1:8080/ is serving gnomon-dashboard:rehearsal`, exit 0.

- [ ] **Step 3: Confirm the state landed where the spec says**

```bash
curl -fsS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8080/
ls -l "$work/data"
stat -c '%U %n' "$work"/data/*
cat "$work/.env"
```
Expected: `200`; `data/` contains `gnomon.db` and `jwt-secret`; both owned by **your** user, not `node` or root; `.env` shows `IMAGE_TAG=rehearsal`, an empty `PREVIOUS_TAG`, your uid/gid, and `HTTP_PORT=8080`.

- [ ] **Step 4: Confirm nothing was written outside the scratch directory**

```bash
docker inspect gnomon-dashboard-1 --format '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{"\n"}}{{end}}'
```
Expected: exactly one mount, `<scratch>/data -> /data`. Anything else means state is escaping the deployment directory.

- [ ] **Step 5: Deploy a deliberately broken image and confirm the rollback**

```bash
printf 'FROM alpine\nENTRYPOINT ["false"]\n' | docker build -t gnomon-dashboard:broken -
cd "$work" && HTTP_PORT=8080 HEALTH_TIMEOUT=20 ./deploy.sh broken
echo "exit: $?"
```
Expected: the health check fails, container logs are printed, `deploy: rolling back to gnomon-dashboard:rehearsal`, then `rolled back to rehearsal, which is serving. broken was NOT deployed.` and a non-zero exit.

- [ ] **Step 6: Confirm the box is actually serving again**

```bash
curl -fsS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8080/
grep IMAGE_TAG "$work/.env"
```
Expected: `200`, and `IMAGE_TAG=rehearsal`.

- [ ] **Step 7: Confirm pruning kept the rollback target**

```bash
docker image ls gnomon-dashboard --format '{{.Tag}}'
```
Expected: `rehearsal` is still present. (`broken` may or may not remain — it was the previous tag at prune time only if the rollback deploy succeeded, and the rollback path does not prune. Either is fine; what matters is that `rehearsal` survived.)

- [ ] **Step 8: Tear down**

```bash
cd "$work" && docker compose down
cd - && rm -rf "$work"
docker image rm gnomon-dashboard:broken gnomon-dashboard:rehearsal gnomon-dashboard:ctxcheck 2>/dev/null || true
```

- [ ] **Step 9: Record the result**

No commit — this task produces no files. Report to the reviewer: whether steps 2, 5, and 6 behaved as expected, and paste the output of steps 3 and 4. If anything diverged, that is a defect in Tasks 2–4, not in this task.

---

## After the plan

Once Task 8 passes, the remaining work is configuration the plan cannot do for you: set the nine secrets and two variables in the GitHub repository, then run **dashboard-deploy** against this branch. The first run is the real acceptance test — and per Task 4, a first deploy has no rollback target, so read the job output rather than assuming.
