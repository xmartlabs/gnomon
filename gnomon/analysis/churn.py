import os
import subprocess


def _git(cwd, args, timeout=30):
    """Run a git command locally; return stdout or '' on any failure. Never raises."""
    try:
        p = subprocess.run(["git", "-C", cwd] + args, capture_output=True,
                           text=True, timeout=timeout)
        return p.stdout if p.returncode == 0 else ""
    except Exception:
        return ""


def git_churn(cwds, since_iso, until_iso):
    """Gold-standard churn: real insertions/deletions from `git log --numstat`,
    capturing EVERY committed change regardless of how it was made (Edit, Bash,
    vim, etc.). 100% local — git reads .git on disk, nothing is uploaded.
    Repos that are missing/non-git are reported as unavailable, not silently dropped.
    """
    # Dedupe by repo IDENTITY (root-commit SHA), not path — otherwise multiple
    # clones/worktrees of the same project (e.g. a fork + a worktree + a copy)
    # each contribute the same commits and inflate the total.
    tops = {}                       # identity -> toplevel path (first seen)
    for cwd in cwds:
        if not cwd or not os.path.isdir(cwd):
            continue
        top = _git(cwd, ["rev-parse", "--show-toplevel"]).strip()
        if not top:
            continue
        root = _git(top, ["rev-list", "--max-parents=0", "HEAD"]).split()
        if root:
            ident = "root:" + ",".join(sorted(root))
        else:
            remote = _git(top, ["config", "remote.origin.url"]).strip()
            ident = "remote:" + remote if remote else "path:" + top
        tops.setdefault(ident, top)
    per_repo, ins_tot, del_tot, commits_tot = [], 0, 0, 0
    for top in sorted(tops.values()):
        email = _git(top, ["config", "user.email"]).strip()
        args = ["log", "--numstat", "--no-merges",
                f"--since={since_iso}", f"--until={until_iso}",
                "--pretty=tformat:__C__"]
        if email:
            args.append(f"--author={email}")
        out = _git(top, args)
        ins = dels = commits = 0
        for ln in out.splitlines():
            if ln == "__C__":
                commits += 1
                continue
            parts = ln.split("\t")
            if len(parts) == 3:
                a, d, _ = parts
                if a.isdigit():
                    ins += int(a)
                if d.isdigit():
                    dels += int(d)
        if ins or dels or commits:
            per_repo.append((os.path.basename(top), ins, dels, commits))
            ins_tot += ins
            del_tot += dels
            commits_tot += commits
    per_repo.sort(key=lambda x: -(x[1] + x[2]))
    return {
        "repos_seen": len(tops),
        "repos_with_commits": len(per_repo),
        "insertions": ins_tot,
        "deletions": del_tot,
        "churn": ins_tot + del_tot,
        "commits": commits_tot,
        "per_repo": per_repo[:12],
    }
