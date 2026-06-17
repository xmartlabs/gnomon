import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import paxel


def _user(text, ts="2026-03-01T12:00:00Z", sid="s1", cwd="/tmp/proj"):
    """A genuine Claude-shaped human prompt event (iter_events output shape)."""
    return {
        "type": "user",
        "sessionId": sid,
        "cwd": cwd,
        "timestamp": ts,
        "message": {"role": "user", "content": text},
    }


def _tool(name, inp=None, ts="2026-03-01T12:01:00Z", sid="s1", cwd="/tmp/proj",
          model="claude-opus-4"):
    """A Claude-shaped assistant turn carrying a single tool_use block."""
    return {
        "type": "assistant",
        "sessionId": sid,
        "cwd": cwd,
        "timestamp": ts,
        "message": {
            "role": "assistant",
            "model": model,
            "content": [{"type": "tool_use", "name": name, "input": inp or {}}],
        },
    }


class TestEventAccumulator(unittest.TestCase):
    def test_counts_prompts_and_tools_without_git(self):
        acc = paxel.EventAccumulator()
        acc.consume_file("claude", [
            _user("add a login form to the dashboard"),
            _tool("Read", {"file_path": "/tmp/proj/a.py"}),
            _tool("Bash", {"command": "ls"}),
        ])
        stats = acc.finalize(churn=None)
        self.assertEqual(stats.volume.total_prompts, 1)
        self.assertEqual(stats.volume.tool_calls_total, 2)
        # churn=None => git velocity zeroed, no exception
        self.assertEqual(stats.velocity.git_churn_total, 0)
        self.assertEqual(stats.velocity.git_velocity_lines_per_hour, 0.0)
        self.assertEqual(stats.velocity.git_repos_seen, 0)

    def test_window_drops_out_of_range(self):
        acc = paxel.EventAccumulator(
            window=(paxel.parse_ts("2026-06-01T00:00:00Z"), None))
        acc.consume_file("claude", [
            _user("first prompt way before window", ts="2026-01-01T00:00:00Z"),
            _user("second prompt inside window", ts="2026-06-02T00:00:00Z"),
        ])
        stats = acc.finalize(churn=None)
        self.assertEqual(stats.volume.total_prompts, 1)

    def test_finalize_returns_stats_object_not_dict(self):
        acc = paxel.EventAccumulator()
        acc.consume_file("claude", [_user("hello")])
        stats = acc.finalize(churn=None)
        self.assertIsInstance(stats, paxel.Stats)

    def test_codex_empty_seed_file_skipped(self):
        acc = paxel.EventAccumulator()
        # a codex file with no genuine human prompt (only an injected wrapper) is dropped
        acc.consume_file("codex", [
            {"type": "user", "sessionId": "c1", "timestamp": "2026-03-01T00:00:00Z",
             "message": {"role": "user", "content": ""}},
        ])
        stats = acc.finalize(churn=None)
        self.assertEqual(stats.corpus.files_parsed, 0)

    def test_churn_dict_feeds_velocity(self):
        acc = paxel.EventAccumulator()
        acc.consume_file("claude", [
            _user("p", ts="2026-03-01T12:00:00Z"),
            _tool("Read", ts="2026-03-01T13:00:00Z"),
        ])
        churn = {"repos_seen": 2, "repos_with_commits": 1, "insertions": 80,
                 "deletions": 20, "churn": 100, "commits": 3, "per_repo": []}
        stats = acc.finalize(churn=churn)
        self.assertEqual(stats.velocity.git_churn_total, 100)
        self.assertEqual(stats.velocity.git_insertions, 80)
        self.assertEqual(stats.velocity.git_commits_real, 3)

    def test_voice_samples_local_only(self):
        acc = paxel.EventAccumulator()
        acc.consume_file("claude", [_user("ship it")])
        vs = acc.voice_samples()
        self.assertIn("voice", vs)
        self.assertIn("opening_prompts", vs)
        self.assertIn("longest_prompts", vs)
        self.assertEqual(len(vs["opening_prompts"]), 1)

    def test_cwds_and_window(self):
        acc = paxel.EventAccumulator()
        acc.consume_file("claude", [_user("x", cwd="/tmp/proj", ts="2026-03-01T00:00:00Z")])
        self.assertEqual(acc.cwds(), ["/tmp/proj"])
        since, until = acc.window()
        # no explicit window => derived from observed event timestamps (ISO strings)
        self.assertIsInstance(since, str)
        self.assertIsInstance(until, str)
        self.assertIn("2026-0", since)


if __name__ == "__main__":
    unittest.main()
