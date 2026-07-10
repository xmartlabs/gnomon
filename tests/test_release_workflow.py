import os
import pathlib
import subprocess
import tempfile
import textwrap
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = pathlib.Path(os.environ.get(
    "RELEASE_WORKFLOW_UNDER_TEST",
    ROOT / ".github" / "workflows" / "release.yml",
))


def _workflow_run_block(workflow_text, step_name):
    lines = workflow_text.splitlines()
    step_index = next(
        index for index, line in enumerate(lines)
        if line.strip() == f"- name: {step_name}"
    )
    run_index = next(
        index for index in range(step_index + 1, len(lines))
        if lines[index].strip() == "run: |"
    )
    run_indent = len(lines[run_index]) - len(lines[run_index].lstrip())
    block = []
    for line in lines[run_index + 1:]:
        indent = len(line) - len(line.lstrip())
        if line.strip() and indent <= run_indent:
            break
        block.append(line)
    return textwrap.dedent("\n".join(block))


class TestReleaseWorkflowContract(unittest.TestCase):
    def setUp(self):
        self.text = WORKFLOW.read_text(encoding="utf-8")

    def test_is_manual_and_main_only(self):
        self.assertIn("workflow_dispatch:", self.text)
        self.assertIn("version:", self.text)
        self.assertIn("required: true", self.text)
        self.assertIn("github.ref == 'refs/heads/main'", self.text)

    def test_validates_version_and_runs_repository_ci(self):
        self.assertIn("pyproject.toml", self.text)
        self.assertIn("requested version", self.text.lower())
        self.assertIn("python3 -m py_compile paxel.py", self.text)
        self.assertIn("python3 -m unittest discover -s tests -v", self.text)

    def test_checkout_and_tagging_are_pinned_to_event_sha(self):
        self.assertIn("ref: ${{ github.sha }}", self.text)
        self.assertIn('test "$(git rev-parse HEAD)" = "$GITHUB_SHA"', self.text)

    def test_creates_or_accepts_matching_immutable_version_tag(self):
        self.assertIn('git tag -a "$TAG"', self.text)
        self.assertIn('git push origin "refs/tags/$TAG"', self.text)
        self.assertIn('REMOTE_VERSION_SHA', self.text)
        self.assertIn('"$REMOTE_VERSION_SHA" != "$GITHUB_SHA"', self.text)
        self.assertIn("already exists at expected SHA", self.text)

    def test_release_retry_is_accepted_and_latest_moves_after_release_exists(self):
        version_push = self.text.index('git push origin "refs/tags/$TAG"')
        release_guard = self.text.index('gh release view "$TAG"')
        release_create = self.text.index('gh release create "$TAG"')
        release_verify = self.text.index('releases/tags/$TAG')
        latest_tag = self.text.index('git tag -fa latest')
        latest_push = self.text.index('git push origin "+refs/tags/latest"')

        self.assertLess(version_push, release_guard)
        self.assertLess(release_guard, release_create)
        self.assertLess(release_create, release_verify)
        self.assertLess(release_verify, latest_tag)
        self.assertLess(latest_tag, latest_push)
        self.assertIn("Release $TAG already exists at expected tag", self.text)
        self.assertNotIn('git push --atomic origin "refs/tags/$TAG" "+refs/tags/latest"', self.text)

    def test_workflow_input_is_passed_through_env_not_shell_interpolation(self):
        self.assertIn("REQUESTED_VERSION: ${{ inputs.version }}", self.text)
        self.assertIn('REQUESTED="$REQUESTED_VERSION"', self.text)
        self.assertNotIn("REQUESTED='${{ inputs.version }}'", self.text)

        lines = self.text.splitlines()
        in_run = False
        run_indent = None
        run_lines = []
        for line in lines:
            indent = len(line) - len(line.lstrip())
            if line.strip() == "run: |":
                in_run = True
                run_indent = indent
                continue
            if in_run and line.strip() and indent <= run_indent:
                in_run = False
            if in_run:
                run_lines.append(line)
        self.assertNotIn("${{ inputs.version }}", "\n".join(run_lines))

    def test_creates_and_verifies_github_release_refs(self):
        self.assertIn('gh release create "$TAG"', self.text)
        self.assertIn('releases/tags/$TAG', self.text)
        self.assertIn('git/ref/tags/$TAG', self.text)
        self.assertIn('git/ref/tags/latest', self.text)
        self.assertIn('GITHUB_SHA', self.text)


class TestReleaseWorkflowFinalVerification(unittest.TestCase):
    def setUp(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.script = _workflow_run_block(text, "Verify release API and tag SHAs")

    def _run_verification(self, *, local_version_tag="lightweight",
                          version_ref_type=None, version_ref_sha=None,
                          latest_ref_sha=None):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = pathlib.Path(temp_dir) / "repo"
            fake_bin = pathlib.Path(temp_dir) / "bin"
            repo.mkdir()
            fake_bin.mkdir()

            def git(*args, capture=False):
                command = ["git", *args]
                if capture:
                    return subprocess.check_output(
                        command, cwd=repo, text=True).strip()
                subprocess.run(command, cwd=repo, check=True,
                               stdout=subprocess.DEVNULL)
                return None

            git("init", "-q", "-b", "main")
            git("config", "user.name", "Release Test")
            git("config", "user.email", "release-test@example.com")
            (repo / "artifact.txt").write_text("release\n", encoding="utf-8")
            git("add", "artifact.txt")
            git("commit", "-qm", "release fixture")
            commit_sha = git("rev-parse", "HEAD", capture=True)
            if local_version_tag == "annotated":
                git("tag", "-a", "v1.2.3", "-m", "Release v1.2.3")
            else:
                git("tag", "v1.2.3")
            git("tag", "-a", "latest", "-m", "Latest stable release")

            version_ref_type = version_ref_type or (
                "tag" if local_version_tag == "annotated" else "commit")
            if version_ref_sha is None:
                version_ref_sha = (git("rev-parse", "v1.2.3^{tag}", capture=True)
                                   if version_ref_type == "tag" else commit_sha)
            if latest_ref_sha is None:
                latest_ref_sha = git("rev-parse", "latest^{tag}", capture=True)

            fake_gh = fake_bin / "gh"
            fake_gh.write_text(textwrap.dedent("""\
                #!/usr/bin/env bash
                set -euo pipefail
                case "$*" in
                  *"releases/tags/$TAG"*)
                    printf '%s\n' "$TAG"
                    ;;
                  *"git/ref/tags/$TAG"*)
                    if [[ "$*" == *"@tsv"* ]]; then
                      printf '%s\t%s\n' "$FAKE_VERSION_REF_TYPE" "$FAKE_VERSION_REF_SHA"
                    else
                      printf '%s\n' "$FAKE_VERSION_REF_SHA"
                    fi
                    ;;
                  *"git/ref/tags/latest"*)
                    printf '%s\n' "$FAKE_LATEST_REF_SHA"
                    ;;
                  *)
                    echo "Unexpected fake gh request: $*" >&2
                    exit 2
                    ;;
                esac
                """), encoding="utf-8")
            fake_gh.chmod(0o755)

            env = dict(os.environ)
            env.update({
                "PATH": f"{fake_bin}{os.pathsep}{env['PATH']}",
                "GITHUB_REPOSITORY": "example/gnomon",
                "GITHUB_SHA": commit_sha,
                "TAG": "v1.2.3",
                "FAKE_VERSION_REF_TYPE": version_ref_type,
                "FAKE_VERSION_REF_SHA": version_ref_sha,
                "FAKE_LATEST_REF_SHA": latest_ref_sha,
            })
            return subprocess.run(
                ["bash", "-c", self.script], cwd=repo, env=env,
                text=True, capture_output=True,
            )

    def test_matching_lightweight_version_tag_passes(self):
        result = self._run_verification(local_version_tag="lightweight")

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_matching_annotated_version_tag_passes(self):
        result = self._run_verification(local_version_tag="annotated")

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_unexpected_version_ref_type_fails(self):
        result = self._run_verification(version_ref_type="tree")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Unexpected version ref type", result.stderr)

    def test_version_ref_sha_mismatch_fails(self):
        result = self._run_verification(version_ref_sha="deadbeef")

        self.assertNotEqual(result.returncode, 0)

    def test_latest_ref_sha_mismatch_fails(self):
        result = self._run_verification(latest_ref_sha="deadbeef")

        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
