import os, sys, json, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import paxel
from dataclasses import asdict

class TestStatsShape(unittest.TestCase):
    def test_empty_stats_has_all_blocks(self):
        s = asdict(paxel.Stats())
        for key in ("corpus","volume","tools","velocity","behavior","rhythm",
                    "progression","stack","autonomy","token_usage","agentic"):
            self.assertIn(key, s)
    def test_asdict_is_json_serializable(self):
        json.dumps(asdict(paxel.Stats()), default=str)

if __name__ == "__main__":
    unittest.main()
