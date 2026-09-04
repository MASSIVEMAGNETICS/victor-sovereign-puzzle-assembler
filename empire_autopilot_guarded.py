#!/usr/bin/env python3
"""Guarded entrypoint for the Daily Empire Autopilot.

Preserves the existing inventory/assembly algorithm while enriching the PRs that
can enter the P0 queue with authoritative pull-request metadata and routing
those candidates through the fail-closed disposition policy.

This module does not grant merge authority and does not modify other repos.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

import empire_autopilot as base
from pr_action_policy import PRDisposition, classify_pr_disposition


_ORIGINAL_SEARCH_OPEN_PRS = base.search_open_prs
_ORIGINAL_BUILD_NEXT_ACTIONS = base.build_next_actions
_PR_NUMBER_RE = re.compile(r"PR #(\d+):")


def _repo_from_issue(pr: Dict[str, Any]) -> str:
    repo_url = str(pr.get("repository_url") or "")
    return repo_url.split("/repos/", 1)[1] if "/repos/" in repo_url else "unknown"


def _pull_path(pr: Dict[str, Any]) -> str | None:
    repo = _repo_from_issue(pr)
    number = pr.get("number")
    if repo == "unknown" or not isinstance(number, int):
        return None
    return f"/repos/{repo}/pulls/{number}"


def search_open_prs_enriched(api: base.GitHubAPI, owner: str, enrich_limit: int = 5) -> List[Dict[str, Any]]:
    """Return open PR search results with authoritative metadata for P0 candidates.

    The base search is already ordered by recent update and the P0 queue consumes
    at most five PRs. Enriching exactly that prefix keeps API cost bounded while
    making GitHub's real ``draft`` flag available to the disposition policy.

    If enrichment fails, the search item is retained. The classifier can still
    fail closed on explicit donor/gate markers; it never receives synthetic
    merge authority from this wrapper.
    """

    items = _ORIGINAL_SEARCH_OPEN_PRS(api, owner)
    for index, item in enumerate(items[: max(0, enrich_limit)]):
        path = _pull_path(item)
        if path is None:
            continue
        try:
            detail = api.get_json(path)
        except base.GitHubAPIError:
            continue
        if not isinstance(detail, dict):
            continue

        merged = dict(item)
        for key in ("draft", "title", "body", "html_url", "state"):
            if key in detail:
                merged[key] = detail[key]
        items[index] = merged
    return items


def _action_for_disposition(pr: Dict[str, Any], disposition: PRDisposition) -> Dict[str, str]:
    number = pr.get("number")
    title = str(pr.get("title") or "")

    if disposition.action == "review_donor":
        label = "Integrate donor material"
        kind = "review_pr_donor"
    elif disposition.action == "review_draft":
        label = "Review draft"
        kind = "review_pr_draft"
    elif disposition.action == "review_gated":
        label = "Review approval gate"
        kind = "review_pr_gated"
    else:
        label = "Review merge candidate"
        kind = "review_pr_merge_candidate"

    return {
        "kind": kind,
        "title": f"{label} PR #{number}: {title}",
        "reason": disposition.reason,
    }


def build_next_actions_guarded(
    snapshots: List[base.RepoSnapshot],
    prs: List[Dict[str, Any]],
    manifest: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Preserve base queue construction while correcting PR dispositions only."""

    actions = _ORIGINAL_BUILD_NEXT_ACTIONS(snapshots, prs, manifest)
    pr_index = {(_repo_from_issue(pr), pr.get("number")): pr for pr in prs}

    guarded: List[Dict[str, Any]] = []
    for action in actions:
        if action.get("kind") != "review_pr":
            guarded.append(action)
            continue

        match = _PR_NUMBER_RE.search(str(action.get("title") or ""))
        number = int(match.group(1)) if match else None
        repo = str(action.get("repo") or "unknown")
        pr = pr_index.get((repo, number))

        if pr is None:
            # Fail closed if queue metadata cannot be reconciled to its source PR.
            replacement = dict(action)
            replacement["kind"] = "review_pr_unknown"
            replacement["title"] = str(action.get("title") or "").replace("Review/merge", "Review unresolved")
            replacement["reason"] = "PR disposition could not be reconciled to source metadata; merge recommendation suppressed."
            guarded.append(replacement)
            continue

        disposition = classify_pr_disposition(pr)
        replacement = dict(action)
        replacement.update(_action_for_disposition(pr, disposition))
        guarded.append(replacement)

    return guarded


def install_guardrails() -> None:
    base.search_open_prs = search_open_prs_enriched
    base.build_next_actions = build_next_actions_guarded


def main() -> int:
    install_guardrails()
    return base.main()


if __name__ == "__main__":
    raise SystemExit(main())
