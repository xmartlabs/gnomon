# Deploying the dashboard to a Linux VM

Manual deploy over SSH. GitHub Actions builds the image, ships it to the VM as a
tarball, and `deploy.sh` switches the running container with a health gate and
automatic rollback. No registry credentials live on the box.

Design rationale: `docs/specs/2026-09-01-dashboard-vm-deploy-design.md`.

## One-time VM preparation

1. Install Docker Engine, the Compose **plugin** (v2), and `curl` — `deploy.sh`
   polls the health check with it — then enable the Docker service so the
   container comes back after a reboot:

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
| `curl is not installed` | the health gate has nothing to poll with; install `curl` |
| `data is not writable` | `~/gnomon/data` owned by another user — the message carries the `chown` fix |
| `image ... is not in the local store` | rolling back to a tag that has already been pruned |
| Health check fails on a first deploy | there is nothing to roll back to; the box is down. Read the container logs the job printed |
