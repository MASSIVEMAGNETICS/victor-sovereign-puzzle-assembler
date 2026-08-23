import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import empire_autopilot as ea


class EmpireAutopilotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = ea.load_manifest(Path("empire_manifest.json"))

    def test_canonical_repo_classification_wins(self):
        repo = {
            "full_name": "MASSIVEMAGNETICS/victorOS",
            "name": "victorOS",
            "description": "could contain unrelated music words",
        }
        pillar = ea.classify_repo(repo, self.manifest)
        self.assertEqual(pillar["id"], "victor_core")

    def test_pattern_classification(self):
        repo = {
            "full_name": "MASSIVEMAGNETICS/example-audio-engine",
            "name": "example-audio-engine",
            "description": "voice mastering and music tooling",
        }
        pillar = ea.classify_repo(repo, self.manifest)
        self.assertEqual(pillar["id"], "music_engine")

    def test_unmatched_repo_falls_to_supporting_lattice(self):
        repo = {
            "full_name": "MASSIVEMAGNETICS/plain-utility",
            "name": "plain-utility",
            "description": "generic helper",
        }
        pillar = ea.classify_repo(repo, self.manifest)
        self.assertEqual(pillar["id"], "supporting_lattice")

    def test_attention_score_is_bounded_and_rewards_terminal_pressure(self):
        low = ea.compute_attention_score(
            age_days=400,
            open_prs=0,
            open_issues=0,
            pillar_priority=4,
            canonical=False,
            archived=False,
        )
        high = ea.compute_attention_score(
            age_days=1,
            open_prs=3,
            open_issues=4,
            pillar_priority=10,
            canonical=True,
            archived=False,
        )
        self.assertGreater(high, low)
        self.assertGreaterEqual(low, 0)
        self.assertLessEqual(high, 100)
        self.assertEqual(
            ea.compute_attention_score(
                age_days=1,
                open_prs=10,
                open_issues=10,
                pillar_priority=10,
                canonical=True,
                archived=True,
            ),
            0,
        )

    def test_age_in_days_uses_push_time(self):
        now = datetime(2026, 8, 23, tzinfo=timezone.utc)
        repo = {"pushed_at": "2026-08-20T00:00:00Z", "updated_at": "2026-08-21T00:00:00Z"}
        self.assertEqual(ea.age_in_days(repo, now), 3)

    def test_render_outputs_are_valid(self):
        state = {
            "generated_at": "2026-08-23T12:00:00+00:00",
            "owner": "MASSIVEMAGNETICS",
            "mode": "observe-plan-assemble-local",
            "summary": {
                "visible_repositories": 1,
                "canonical_visible": 1,
                "active_14d": 1,
                "archived": 0,
                "private_visible": 0,
                "open_prs": 0,
                "open_issues_estimate": 0,
            },
            "pillars": [
                {
                    "name": "Victor Authority + Continuity",
                    "repo_count": 1,
                    "canonical_count": 1,
                    "active_14d": 1,
                    "open_prs": 0,
                    "open_issues_estimate": 0,
                }
            ],
            "top_attention": [
                {
                    "full_name": "MASSIVEMAGNETICS/victorOS",
                    "html_url": "https://github.com/MASSIVEMAGNETICS/victorOS",
                    "pillar_name": "Victor Authority + Continuity",
                    "attention_score": 55,
                    "age_days": 1,
                    "open_prs": 0,
                    "open_issues_estimate": 0,
                }
            ],
            "next_actions": [],
            "api_errors": [],
        }
        markdown = ea.render_markdown(state)
        self.assertIn("Bippity Boppity Boop Loop", markdown)
        self.assertIn("```mermaid", markdown)

        with tempfile.TemporaryDirectory() as td:
            state_path = Path(td) / "state" / "empire.json"
            report_path = Path(td) / "EMPIRE_STATUS.md"
            ea.write_outputs(state, state_path, report_path)
            self.assertTrue(state_path.exists())
            self.assertTrue(report_path.exists())
            loaded = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(loaded["owner"], "MASSIVEMAGNETICS")


if __name__ == "__main__":
    unittest.main()
