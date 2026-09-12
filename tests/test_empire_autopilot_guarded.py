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

    def test_victoros_donor_is_routed_to_donor_integration(self):
        pr = self._pr(
            "MASSIVEMAGNETICS/victorOS",
            4,
            "DRAFT DONOR: Victor GEV mobile Empire control plane v0.2",
            draft=True,
            body="DO NOT MERGE THIS BRANCH AS-IS. Preserve it as donor/source material.",
        )
        actions = guarded.build_next_actions_guarded([], [pr], self.manifest)
        self.assertEqual(actions[0]["kind"], "review_pr_donor")
        self.assertIn("Integrate donor material PR #4", actions[0]["title"])
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

    def test_non_draft_approval_gate_is_not_a_merge_candidate(self):
        pr = self._pr(
            "MASSIVEMAGNETICS/dev-ville",
            19,
            "Add secure browser admin sessions for iambandobandz.com",
            draft=False,
            body="Approval gate: do not merge automatically until production probes pass.",
        )
        actions = guarded.build_next_actions_guarded([], [pr], self.manifest)
        self.assertEqual(actions[0]["kind"], "review_pr_gated")
        self.assertIn("Review approval gate PR #19", actions[0]["title"])
        self.assertNotIn("Review merge candidate", actions[0]["title"])

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

    def test_guarded_state_stamps_actual_receipt_generator(self):
        original = guarded._ORIGINAL_BUILD_STATE
        try:
            guarded._ORIGINAL_BUILD_STATE = lambda *args, **kwargs: {"schema_version": 1}
            state = guarded.build_state_guarded()
        finally:
            guarded._ORIGINAL_BUILD_STATE = original

        self.assertEqual(state["receipt_generator"], "empire_autopilot_guarded.py")
        self.assertTrue(state["private_inventory_complete"])

    def test_private_inventory_failure_qualifies_unseen_canonical_repo(self):
        original = guarded._ORIGINAL_BUILD_STATE
        raw_error = (
            'GitHub API 403 for https://api.github.com/user/repos?affiliation=owner&visibility=all: '
            '{"message":"Resource not accessible by integration"}'
        )
        base_state = {
            "api_errors": [raw_error],
            "next_actions": [
                {
                    "kind": "recover_canonical_repo",
                    "priority": "P1",
                    "repo": "MASSIVEMAGNETICS/suno-killer",
                    "title": "Resolve missing canonical repo: MASSIVEMAGNETICS/suno-killer",
                    "reason": "Manifest expects this repo but the current scan could not see it.",
                    "url": None,
                }
            ],
        }
        try:
            guarded._ORIGINAL_BUILD_STATE = lambda *args, **kwargs: base_state
            state = guarded.build_state_guarded()
        finally:
            guarded._ORIGINAL_BUILD_STATE = original

        self.assertFalse(state["private_inventory_complete"])
        self.assertEqual(state["next_actions"][0]["kind"], "recover_canonical_repo")
        self.assertEqual(
            state["next_actions"][0]["title"],
            "Resolve unseen canonical repo: MASSIVEMAGNETICS/suno-killer",
        )
        self.assertIn("private inventory coverage is incomplete", state["next_actions"][0]["reason"])
        self.assertNotIn("missing canonical repo", state["next_actions"][0]["title"].lower())

    def test_complete_private_inventory_preserves_missing_canonical_wording(self):
        original = guarded._ORIGINAL_BUILD_STATE
        base_state = {
            "api_errors": [],
            "next_actions": [
                {
                    "kind": "recover_canonical_repo",
                    "repo": "MASSIVEMAGNETICS/actually-missing",
                    "title": "Resolve missing canonical repo: MASSIVEMAGNETICS/actually-missing",
                    "reason": "Manifest expects this repo but the current scan could not see it.",
                }
            ],
        }
        try:
            guarded._ORIGINAL_BUILD_STATE = lambda *args, **kwargs: base_state
            state = guarded.build_state_guarded()
        finally:
            guarded._ORIGINAL_BUILD_STATE = original

        self.assertTrue(state["private_inventory_complete"])
        self.assertIn("Resolve missing canonical repo", state["next_actions"][0]["title"])

    def test_private_inventory_qualification_preserves_non_recovery_actions(self):
        state = {
            "api_errors": ["GitHub API 403 for https://api.github.com/user/repos: denied"],
            "next_actions": [
                {"kind": "review_pr_draft", "title": "Review draft PR #1"},
                {"kind": "triage_stale_canonical", "title": "Triage stale canonical repo"},
            ],
        }
        original_actions = [dict(action) for action in state["next_actions"]]
        guarded._qualify_unseen_canonical_actions(state)
        self.assertEqual(state["next_actions"], original_actions)

    def test_compact_api_error_preserves_http_status_endpoint_and_message(self):
        raw = (
            'GitHub API 403 for https://api.github.com/user/repos?affiliation=owner&visibility=all&sort=updated&direction=desc&per_page=100&page=1: '
            '{"message":"Resource not accessible by integration","documentation_url":"https://docs.github.com/rest/repos/repos#list-repositories-for-the-authenticated-user","status":"403"}'
        )
        compact = guarded._compact_api_error(raw)
        self.assertEqual(
            compact,
            "GitHub API 403 for /user/repos: Resource not accessible by integration",
        )
        self.assertLessEqual(len(compact), guarded._MAX_RENDERED_API_ERROR)

    def test_compact_api_error_marks_non_json_truncation_explicitly(self):
        raw = "network failure " + ("x" * 500)
        compact = guarded._compact_api_error(raw)
        self.assertTrue(compact.endswith("... [truncated]"))
        self.assertEqual(len(compact), guarded._MAX_RENDERED_API_ERROR)

    def test_guarded_markdown_renders_compact_coverage_warning_without_mutating_state(self):
        original = guarded._ORIGINAL_RENDER_MARKDOWN
        raw = (
            'GitHub API 403 for https://api.github.com/user/repos?affiliation=owner&visibility=all: '
            '{"message":"Resource not accessible by integration","documentation_url":"https://docs.github.com/rest/repos/repos"}'
        )
        state = {
            "receipt_generator": "empire_autopilot_guarded.py",
            "api_errors": [raw],
        }
        try:
            guarded._ORIGINAL_RENDER_MARKDOWN = lambda render_state: (
                f"# Empire Status\n\n- `{render_state['api_errors'][0][:300]}`\n\n"
                "Generated by `empire_autopilot.py`. The machine-readable receipt is `state/empire.json`.\n"
            )
            rendered = guarded.render_markdown_guarded(state)
        finally:
            guarded._ORIGINAL_RENDER_MARKDOWN = original

        self.assertIn("GitHub API 403 for /user/repos: Resource not accessible by integration", rendered)
        self.assertNotIn("documentation_url", rendered)
        self.assertEqual(state["api_errors"], [raw])

    def test_guarded_markdown_replaces_base_generator_footer(self):
        original = guarded._ORIGINAL_RENDER_MARKDOWN
        try:
            guarded._ORIGINAL_RENDER_MARKDOWN = lambda state: (
                "# Empire Status\n\n"
                "Generated by `empire_autopilot.py`. The machine-readable receipt is `state/empire.json`.\n"
            )
            rendered = guarded.render_markdown_guarded(
                {"receipt_generator": "empire_autopilot_guarded.py"}
            )
        finally:
            guarded._ORIGINAL_RENDER_MARKDOWN = original

        self.assertIn("Generated by `empire_autopilot_guarded.py`", rendered)
        self.assertNotIn("Generated by `empire_autopilot.py`", rendered)

    def test_guarded_markdown_fails_closed_if_footer_contract_changes(self):
        original = guarded._ORIGINAL_RENDER_MARKDOWN
        try:
            guarded._ORIGINAL_RENDER_MARKDOWN = lambda state: "# Empire Status\n"
            with self.assertRaisesRegex(RuntimeError, "ambiguous generator provenance"):
                guarded.render_markdown_guarded({})
        finally:
            guarded._ORIGINAL_RENDER_MARKDOWN = original


if __name__ == "__main__":
    unittest.main()
