"""Fail-closed pull-request disposition policy for Empire routing.

This module deliberately separates "open work deserves review" from
"open work is a merge candidate".  It is side-effect free and can be used by
Empire inventory/reporting code without granting merge authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class PRDisposition:
    action: str
    merge_candidate: bool
    reason: str


_DONOR_MARKERS = (
    "draft donor",
    "donor only",
    "source material",
    "do not merge",
    "do-not-merge",
    "do not merge as-is",
    "do not merge as is",
    "obsolete-base",
    "obsolete base",
)

_REVIEW_ONLY_MARKERS = (
    "requires human review",
    "human-gated",
    "human gated",
    "acceptance gate",
)


def _text(pr: Mapping[str, Any]) -> str:
    title = str(pr.get("title") or "")
    body = str(pr.get("body") or "")
    return f"{title}\n{body}".casefold()


def classify_pr_disposition(pr: Mapping[str, Any]) -> PRDisposition:
    """Classify an open PR without ever granting merge authority.

    The returned ``merge_candidate`` flag means only that the inventory layer
    found no explicit draft/donor/review-only blocker.  It is not merge
    authorization and must never bypass CI, review, branch protection, owner
    approval, or repository-specific gates.
    """

    text = _text(pr)

    if bool(pr.get("draft")):
        return PRDisposition(
            action="review_draft",
            merge_candidate=False,
            reason="GitHub marks the pull request as draft.",
        )

    if any(marker in text for marker in _DONOR_MARKERS):
        return PRDisposition(
            action="review_donor",
            merge_candidate=False,
            reason="Pull request is explicitly donor/source material or marked do-not-merge.",
        )

    if any(marker in text for marker in _REVIEW_ONLY_MARKERS):
        return PRDisposition(
            action="review_gated",
            merge_candidate=False,
            reason="Pull request declares a human or acceptance gate.",
        )

    return PRDisposition(
        action="review_merge_candidate",
        merge_candidate=True,
        reason=(
            "No explicit draft/donor/review-only blocker was found. This is a review "
            "candidate only; merge still requires independent verification and approval."
        ),
    )
