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
check  "the image is referenced by the expected repo name"  'gnomon-dashboard:'
refute "the image is never pulled from a registry"          'docker pull|docker/login-action'
check  "app.env is restricted on the host"        'chmod 600 app\.env'
check  "the image travels as a saved tarball"     'docker save'
check  "deploy.sh drives the host"                'deploy\.sh'
check  "key material is removed afterwards"       'rm -f ~/\.ssh/deploy_key'
refute "TRUST_PROXY is not enabled here"          'TRUST_PROXY'
# Secrets reach the box as a copied file. On an ssh command line they would be
# visible in `ps` to every other user on the VM and land in shell history.
# ssh/scp invocations wrap across backslash continuations, so a line-based
# grep would miss a secret spliced into the second or third line of one.
joined="$(sed -e :a -e '/\\$/N; s/\\\n//; ta' "$wf")"
refute_joined() { if grep -Eq "$2" <<<"$joined"; then echo "FAIL - $1"; fail=1; else echo "ok   - $1"; fi; }

refute_joined "no secret is interpolated into an ssh or scp invocation" '(ssh|scp) .*secrets\.'

exit "$fail"
