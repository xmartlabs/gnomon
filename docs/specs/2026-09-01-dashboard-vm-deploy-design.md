# Dashboard deploy to a self-managed Linux VM (2026-09-01)

Manual, SSH-based deployment of the self-hosted dashboard to a Linux VM. GitHub Actions
builds the image, ships it over SSH as a tarball, and a host-side script switches the
running container over with a health gate and automatic rollback.

Complements — does not replace — `.github/workflows/dashboard-image.yml`, which keeps
publishing tagged images to GHCR for anyone self-hosting from the registry.

## Why

The dashboard has a working Dockerfile and a root `docker-compose.yml` for local use, but
no path from a merged commit to a running instance on a real box. This spec defines that
path for one specific target: a Linux VM the operator reaches over SSH, with all dashboard
state confined to `~/gnomon` on that VM.

## Decisions

Each of these was chosen deliberately; alternatives are recorded so a later reader does not
relitigate them by accident.

| Decision | Choice | Rejected |
|---|---|---|
| Image delivery | `docker save` → gzip → `scp` → `docker load` | GHCR pull (needs a registry PAT on the box); build on the VM (burns host CPU compiling `better-sqlite3`) |
| Trigger | `workflow_dispatch` only | push-to-main; `v*` tags |
| Exposure | host port 80 → container 3000, plain HTTP | bare 3000; bundled Caddy with auto-TLS. Cloudflare will terminate TLS in front, wired separately by the operator |
| Secrets | GitHub Secrets, rendered into `~/gnomon/app.env` each deploy | hand-managed on the VM; seed-once |
| Pre-deploy test gate | none — build and ship | full unit+e2e+contract; container smoke |
| Host orchestration | committed compose file + committed `deploy.sh`, both copied each run | inline heredocs in the workflow YAML; bare `docker run` |

Skipping the test gate is defensible because `ci.yml` already runs the dashboard unit and
e2e suites on every PR and every push to `main`. The deploy workflow is the second place
the code is tested, not the first. The health gate in `deploy.sh` remains, and covers what
CI cannot see: an image that builds and tests green but will not boot against this box's
environment and volume.

## Host layout

Everything this deployment creates lives under `~/gnomon` on the VM:

```
~/gnomon/
├── docker-compose.yml   # copied from the repo each deploy
├── deploy.sh            # copied from the repo each deploy
├── .env                 # deploy metadata, GENERATED ON THE HOST by deploy.sh
├── app.env              # application secrets, mode 0600, rendered by the workflow
├── data/                # bind-mounted to /data
└── tmp/                 # image tarball in transit; deleted immediately after load
```

`data/` holds every piece of dashboard state. `dashboard/src/lib/paths.ts` routes the SQLite
database (`gnomon.db` plus its `-wal`/`-shm` sidecars), the persisted JWT secret
(`dashboard/src/lib/auth.ts`), and the coach cache through a single `dataDir()`. One bind
mount therefore covers all of it, and a backup is `tar czf gnomon-backup.tgz ~/gnomon/data`.

### Two env files, on purpose

Compose reads `.env` from the project directory for **variable interpolation**; `env_file:`
is what hands variables to the **container**. Keeping them separate means deploy metadata
(`IMAGE_TAG`, `PREVIOUS_TAG`) never enters the application's process environment, and the
only file needing mode 0600 is the one holding `TEAM_TOKEN`.

`.env` is generated on the host rather than shipped by the workflow, for two reasons. The
runner cannot know the deploy user's uid/gid. More importantly, `deploy.sh` must read the
*previous* `IMAGE_TAG` before writing the new one; a pre-rendered `.env` would destroy the
rollback target before rollback could need it.

### Ownership

The image runs as `node` (uid 1000), but with a bind mount the host directory's ownership
wins — the Dockerfile's `chown node:node /data` only affected the image layer. Compose
therefore sets `user: "${DEPLOY_UID}:${DEPLOY_GID}"`, filled in from `id -u` / `id -g` on
the box. Files land owned by the deploy user, readable and backup-able without `sudo`,
whatever uid that user happens to have.

### Scope boundary

Docker's own image and layer store stays in `/var/lib/docker`. Everything *this deployment
creates* lives in `~/gnomon`, but the engine's storage is not ours to relocate, and moving
it would be a system-wide change affecting anything else running on the box.

## Workflow — `.github/workflows/dashboard-deploy.yml`

Trigger: `workflow_dispatch` only. The ref is chosen in the GitHub UI.

Concurrency: `group: dashboard-deploy`, `cancel-in-progress: false`. Two simultaneous
deploys would race over the same tag flip, and cancelling one mid-flight is worse still —
it can leave the box between images.

Single job, `runs-on: ubuntu-latest`, `timeout-minutes: 20`, `permissions: { contents: read }`:

1. `actions/checkout@v4`
2. `docker/setup-buildx-action@v3`
3. Build `gnomon-dashboard:$TAG` from `./dashboard` with `load: true`,
   `cache-from: type=gha`, `cache-to: type=gha,mode=max`.
   `TAG="${GITHUB_SHA::12}"` — the image on the box is always traceable to a commit, and
   redeploying a sha is idempotent.
4. `docker save gnomon-dashboard:$TAG | gzip > image.tar.gz`
5. Render `app.env` into the runner workspace (see below).
6. Install the SSH key and a pinned `known_hosts` into a temp dir, mode 0600.
7. `ssh` a `mkdir -p ~/gnomon/data ~/gnomon/tmp` so the first deploy needs no manual prep.
8. `scp` `docker-compose.yml`, `deploy.sh`, `app.env` → `~/gnomon/`, and `image.tar.gz` →
   `~/gnomon/tmp/`.
9. `ssh` → `cd ~/gnomon && HTTP_PORT=$HTTP_PORT bash deploy.sh $TAG`.
10. `if: always()` — remove the key material from the runner.

The GHA layer cache matters more than usual here: with no test gate, the build is the whole
critical path, and its slowest step is compiling the `better-sqlite3` native addon.

### Secrets are written to a file, never echoed over SSH

`ssh host "echo TEAM_TOKEN=... > app.env"` places the token in the remote command line,
where it is visible in `ps` to every other user on the box and lands in shell history.
Rendering the file on the runner and `scp`-ing it keeps the secret inside the SSH tunnel.

Optional keys are emitted only when the corresponding secret is non-empty, so an unset key
means unset rather than an empty string the application must defend against.

### known_hosts is pinned, with no fallback

No `StrictHostKeyChecking=no`. The job hands `TEAM_TOKEN` to whatever answers at that
address; accepting an unknown host key would hand it to whoever arrives first. If
`DEPLOY_SSH_KNOWN_HOSTS` is empty, the job fails with a message pointing at the
`ssh-keyscan` line in the deploy README.

### Secrets and variables

Repository **secrets**:

| Name | Required | Purpose |
|---|---|---|
| `DEPLOY_HOST` | yes | VM hostname or IP |
| `DEPLOY_USER` | yes | SSH user; its home holds `~/gnomon` |
| `DEPLOY_SSH_KEY` | yes | private key, dedicated to deploys |
| `DEPLOY_SSH_KNOWN_HOSTS` | yes | pinned host key |
| `TEAM_TOKEN` | yes | shared token; the container refuses to boot without it |
| `JWT_SECRET` | no | leave unset — see below |
| `LLM_API_KEY` | no | enables the AI coach card |
| `LLM_MODEL` | no | coach model override |
| `MAX_INGEST_BYTES` | no | upload cap override |

Repository **variables**: `DEPLOY_SSH_PORT` (default `22`), `HTTP_PORT` (default `80`).

Leaving `JWT_SECRET` unset is the correct default for this deployment: a single replica, and
`auth.ts` already persists a generated secret to `~/gnomon/data/jwt-secret`, so tokens issued
before a restart still verify after it.

`TRUST_PROXY` is **not** set. It is only safe once port 80 is unreachable except through
Cloudflare; while the port is open to the internet, trusting `x-forwarded-for` lets any
client mint a fresh sign-in throttle bucket per request and brute-force the shared
`TEAM_TOKEN` unthrottled (see the comment block in `dashboard/src/lib/rate-limit.ts`).

## `dashboard/deploy/docker-compose.yml`

```yaml
name: gnomon
services:
  dashboard:
    image: gnomon-dashboard:${IMAGE_TAG}
    user: "${DEPLOY_UID}:${DEPLOY_GID}"
    ports: ["${HTTP_PORT}:3000"]
    env_file: app.env
    volumes: ["./data:/data"]
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "node", "-e", "fetch('http://127.0.0.1:3000/').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 20s
```

`name: gnomon` pins the compose project name so container naming is stable regardless of
directory. There is no `build:` key — the host never compiles anything. The healthcheck
uses `node`, which is the only HTTP-capable binary in `node:22-bookworm-slim` (no curl, no
wget), so `docker compose ps` reports the truth months later.

Binding host port 80 needs no elevated privileges for the deploy user: the Docker daemon
performs the bind as root and forwards to container port 3000.

## `dashboard/deploy/deploy.sh`

`bash`, `set -euo pipefail`, `cd "$(dirname "$0")"` as the first action so it operates on
its own directory and can be rehearsed anywhere. Usage: `deploy.sh <tag>`, with `HTTP_PORT`
read from the environment and defaulting to `80`.

1. **Preflight.** `docker` reachable without sudo; `docker compose` plugin present; `data/`
   writable by the current user. Each failure exits with the remedy, not a stack trace. The
   `data/` check matters most: a directory owned by another user otherwise surfaces as a
   confusing SQLite `SQLITE_CANTOPEN` *after* an apparently green deploy.
2. **Load.** `gunzip -c tmp/image.tar.gz | docker load`, then delete the tarball. A `trap`
   removes it on any exit path, so a failure does not leave hundreds of megabytes in the
   home directory. If the tarball is absent, this step is skipped and the tag must already
   exist locally (`docker image inspect`) — this is what makes the script double as the
   rollback tool.
3. **Record and flip.** Read the existing `IMAGE_TAG` out of `.env`, then rewrite `.env`
   with the new `IMAGE_TAG`, the old value as `PREVIOUS_TAG`, and `DEPLOY_UID`,
   `DEPLOY_GID`, `HTTP_PORT`.
4. **Start.** `docker compose up -d --remove-orphans`.
5. **Health gate.** Poll `http://127.0.0.1:$HTTP_PORT/` from the host, up to 60 seconds.
   `/` is the same endpoint `dashboard-image.yml` already uses as a readiness probe.
6. **Roll back on failure.** Print `docker compose logs --tail=100`, restore
   `IMAGE_TAG=$PREVIOUS_TAG` in `.env`, `docker compose up -d` again, and exit non-zero. A
   bad image costs a red workflow run, not a dark dashboard. On a first deploy there is no
   `PREVIOUS_TAG`, so the script fails loudly with the logs instead.
7. **Prune.** Remove `gnomon-dashboard` images whose tags are neither the current nor the
   previous one. Scoped to that repository name; it never touches other images on the box.

Manual rollback is therefore:

```
ssh <user>@<host> 'cd ~/gnomon && HTTP_PORT=80 ./deploy.sh <old-sha>'
```

using the previous image still present in the local Docker store — no GitHub, no rebuild.

## Verification

Automated, added to `.github/workflows/ci.yml`:

- `shellcheck dashboard/deploy/deploy.sh`. This is unattended shell that runs `rm` and
  `docker image rm` against a live box; an unquoted variable is exactly the bug shellcheck
  catches.
- `docker compose -f dashboard/deploy/docker-compose.yml config` with dummy values for
  `IMAGE_TAG`, `DEPLOY_UID`, `DEPLOY_GID`, `HTTP_PORT`, and a stub `app.env` — catches
  interpolation typos before they reach the VM.

Manual, and the final step of the implementation plan — a local rehearsal, no VM required:

1. `docker build -t gnomon-dashboard:rehearsal ./dashboard`
2. Copy `docker-compose.yml`, `deploy.sh` and a minimal `app.env` (`TEAM_TOKEN=dev`) into a
   scratch directory.
3. `HTTP_PORT=8080 ./deploy.sh rehearsal` → confirm the container starts, `curl localhost:8080`
   answers, and `data/gnomon.db` plus `data/jwt-secret` appear owned by the current user.
4. Build a deliberately broken image (for example, one whose entrypoint exits immediately),
   deploy it, and confirm the health gate fails, the logs print, and `.env` is restored to
   the `rehearsal` tag with the container serving again.

## One-time VM preparation

Not automated; documented in `dashboard/deploy/README.md`:

- Docker Engine and the Compose plugin installed.
- The deploy user added to the `docker` group.
- `systemctl enable --now docker`, so `restart: unless-stopped` survives a reboot.
- Port 80 reachable (host firewall and any cloud security group).
- A dedicated deploy keypair — not the operator's personal key — with the public half in
  the deploy user's `authorized_keys`.

`~/gnomon` itself needs no manual creation; step 7 of the workflow makes it.

## Files

| Path | Change |
|---|---|
| `.github/workflows/dashboard-deploy.yml` | new |
| `dashboard/deploy/docker-compose.yml` | new |
| `dashboard/deploy/deploy.sh` | new |
| `dashboard/deploy/README.md` | new — VM prep, secret list, `ssh-keyscan` line, rollback, backup |
| `dashboard/.dockerignore` | add `deploy/` — otherwise these files sit in the build context and needlessly bust the layer cache |
| `.github/workflows/ci.yml` | add the shellcheck and compose-config checks |
| `README.md` | pointer to the deploy doc from the "Self-hosted team dashboard" section |

## CLI note

`gnomon/upload/mirdash.py` defaults to `https://mirdash.xmartlabs.com`. Teams uploading to
this VM point at it with `--mirdash-base=http://<host>`, the `GNOMON_MIRDASH_BASE`
environment variable, or `mirdash_base` in `~/.config/gnomon/config.json`. No code change —
documentation only, in the deploy README.

## Out of scope

Named explicitly so the implementation plan does not grow into them:

- TLS and the Cloudflare wiring — the operator's, later.
- `TRUST_PROXY=1` — stays off until port 80 is firewalled to Cloudflare's ranges.
- Automated backups of `~/gnomon/data` — the README documents the `tar` command; no cron.
- Monitoring and alerting.
- `dashboard/terraform/` — generic xmartlabs boilerplate (VPC/RDS/ECS/EFS/VPN), unrelated to
  this VM and untouched by this work.
- Changes to `.github/workflows/dashboard-image.yml`, which keeps publishing to GHCR on tags.
