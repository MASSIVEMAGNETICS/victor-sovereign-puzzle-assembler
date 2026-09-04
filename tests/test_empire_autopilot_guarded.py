import unittest

import empire_autopilot_guarded as guarded


class GuardedEmpireRoutingTests(unittest.TestCase):
    def setUp(self):
        self.manifest = {
            "autopilot": {"max_next_actions": 5, "stale_days": 30},
            "pillars": [],
        }

    @staticmethod
    def _pr(repo, number, title, *, draft=False, body=""):
        return {
            "repository_url": f"https://api.github.com/repos/{repo}",
            "number": number,
            "title": title,
            "body": body,
            "draft": draft,
            "html_url": f"https://github.com/{repo}/pull/{number}",
        }

    def test_victoros_donor_is_never_review_merge(self):
        pr = self._pr(
            "MASSIVEMAGNETICS/victorOS",
            4,
            "DRAFT DONOR: Victor GEV mobile Empire control plane v0.2",
            draft=True,
            body="DO NOT MERGE THIS BRANCH AS-IS. Preserve it as donor/source material.",
        )
        actions = guarded.build_next_actions_guarded([], [pr], self.manifest)
        self.assertEqual(actions[0]["kind"], "review_pr_draft")
        self.assertNotIn("Review/merge", actions[0]["title"])
        self.assertNotIn("Review merge candidate", actions[0]["title"])

    def test_victor_empire_draft_stays_review_only(self):
        pr = self._pr(
            "MASSIVEMAGNETICS/victor_empire",
            7,
            "Add bounded Victor interoception body-state contract",
            draft=True,
            body="DRAFT. Do not merge automatically. Human review should confirm the observability cost.",
        )
        actions = guarded.build_next_actions_guarded([], [pr], self.manifest)
        self.assertEqual(actions[0]["kind"], "review_pr_draft")
        self.assertIn("Review draft PR #7", actions[0]["title"])

    def test_non_draft_unblocked_pr_is_only_merge_review_candidate(self):
        pr = self._pr(
            "MASSIVEMAGNETICS/suno-clone-mycelial",
            1,
            "Add persistent-effort reference adaptation engine",
            draft=False,
            body="CI verifies the control plane. Real generation requires a local ACE-Step server.",
        )
        actions = guarded.build_next_actions_guarded([], [pr], self.manifest)
        self.assertEqual(actions[0]["kind"], "review_pr_merge_candidate")
        self.assertIn("Review merge candidate PR #1", actions[0]["title"])
        self.assertIn("merge still requires independent verification and approval", actions[0]["reason"])

    def test_unreconciled_pr_metadata_fails_closed(self):
        original = guarded._ORIGINAL_BUILD_NEXT_ACTIONS
        try:
            guarded._ORIGINAL_BUILD_NEXT_ACTIONS = lambda snapshots, prs, manifest: [
                {
                    "kind": "review_pr",
                    "priority": "P0",
                    "repo": "MASSIVEMAGNETICS/unknown",
                    "title": "Review/merge PR #99: unknown",
                    "url": None,
                    "reason": "legacy",
                }
            ]
            actions = guarded.build_next_actions_guarded([], [], self.manifest)
        finally:
            guarded._ORIGINAL_BUILD_NEXT_ACTIONS = original
        self.assertEqual(actions[0]["kind"], "review_pr_unknown")
        self.assertIn("merge recommendation suppressed", actions[0]["reason"])
        self.assertNotIn("Review/merge", actions[0]["title"])

    def test_enrichment_uses_authoritative_pull_metadata_for_top_candidates(self):
        original_search = guarded._ORIGINAL_SEARCH_OPEN_PRS

        class FakeAPI:
            def __init__(self):
                self.paths = []

            def get_json(self, path):
                self.paths.append(path)
                return {
                    "draft": True,
                    "title": "DRAFT DONOR: authoritative title",
                    "body": "DO NOT MERGE AS-IS",
                    "html_url": "https://github.com/MASSIVEMAGNETICS/victorOS/pull/4",
                    "state": "open",
                }

        search_item = self._pr(
            "MASSIVEMAGNETICS/victorOS",
            4,
            "stale search title",
            draft=False,
        )
        try:
            guarded._ORIGINAL_SEARCH_OPEN_PRS = lambda api, owner: [search_item]
            api = FakeAPI()
            enriched = guarded.search_open_prs_enriched(api, "MASSIVEMAGNETICS")
        finally:
            guarded._ORIGINAL_SEARCH_OPEN_PRS = original_search

        self.assertTrue(enriched[0]["draft"])
        self.assertEqual(enriched[0]["title"], "DRAFT DONOR: authoritative title")
        self.assertEqual(api.paths, ["/repos/MASSIVEMAGNETICS/victorOS/pulls/4"])


if __name__ == "__main__":
    unittest.main()
