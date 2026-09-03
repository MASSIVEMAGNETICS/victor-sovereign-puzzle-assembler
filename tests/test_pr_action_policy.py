import unittest

from pr_action_policy import classify_pr_disposition


class PRActionPolicyTests(unittest.TestCase):
    def test_github_draft_never_becomes_merge_candidate(self):
        result = classify_pr_disposition({"title": "Feature", "body": "", "draft": True})
        self.assertEqual(result.action, "review_draft")
        self.assertFalse(result.merge_candidate)

    def test_draft_donor_title_is_not_merge_candidate(self):
        result = classify_pr_disposition(
            {
                "title": "DRAFT DONOR: Victor GEV mobile Empire control plane v0.2",
                "body": "Useful source material for v0.3.",
                "draft": False,
            }
        )
        self.assertEqual(result.action, "review_donor")
        self.assertFalse(result.merge_candidate)

    def test_do_not_merge_body_fails_closed(self):
        result = classify_pr_disposition(
            {
                "title": "Experimental continuity adapter",
                "body": "DO NOT MERGE AS-IS; physical-device acceptance remains pending.",
                "draft": False,
            }
        )
        self.assertEqual(result.action, "review_donor")
        self.assertFalse(result.merge_candidate)

    def test_human_gate_is_review_only(self):
        result = classify_pr_disposition(
            {
                "title": "Security boundary update",
                "body": "Requires human review before promotion.",
                "draft": False,
            }
        )
        self.assertEqual(result.action, "review_gated")
        self.assertFalse(result.merge_candidate)

    def test_normal_open_pr_is_only_a_review_candidate(self):
        result = classify_pr_disposition(
            {
                "title": "Fix deterministic parser defect",
                "body": "Regression tests included.",
                "draft": False,
            }
        )
        self.assertEqual(result.action, "review_merge_candidate")
        self.assertTrue(result.merge_candidate)
        self.assertIn("review candidate only", result.reason.lower())


if __name__ == "__main__":
    unittest.main()
