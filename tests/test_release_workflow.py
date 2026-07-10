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

    def test_creates_immutable_version_and_movable_latest_atomically(self):
        self.assertIn('git tag -a "$TAG"', self.text)
        self.assertIn('git tag -fa latest', self.text)
        self.assertIn('git push --atomic origin "refs/tags/$TAG" "+refs/tags/latest"', self.text)
        self.assertIn('refs/tags/$TAG', self.text)
        self.assertIn("already exists", self.text)

    def test_creates_and_verifies_github_release_refs(self):
        self.assertIn('gh release create "$TAG"', self.text)
        self.assertIn('releases/tags/$TAG', self.text)
        self.assertIn('git/ref/tags/$TAG', self.text)
        self.assertIn('git/ref/tags/latest', self.text)
        self.assertIn('GITHUB_SHA', self.text)


if __name__ == "__main__":
    unittest.main()
