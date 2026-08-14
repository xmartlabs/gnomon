#!/usr/bin/env bash
# A shim. The implementation moved to anchor.py so that no POSIX shell is required: every
# published requirements list said "python3, git and uv" while the whole path needed bash,
# and on Windows `bash` is the WSL launcher, which failed for the first Windows runner.
#
# Kept because this filename is quoted in the README, in commit messages and in reports that
# are already out. It forwards and exits with the same code -- there is one implementation,
# not two.
exec python3 "$(dirname "${BASH_SOURCE[0]}")/anchor.py" "$@"
