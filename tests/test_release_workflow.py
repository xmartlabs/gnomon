import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"


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


if __name__ == "__main__":
    unittest.main()
