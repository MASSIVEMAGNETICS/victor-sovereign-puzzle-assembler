#!/usr/bin/env python3
"""Daily Empire Autopilot.

Scans the MASSIVEMAGNETICS repository lattice, classifies repositories into
empire pillars, identifies open pull requests, scores attention pressure, and
writes deterministic machine-readable + human-readable receipts.

The default mode is intentionally bounded: it observes, plans, and assembles
inside this repository. It does NOT modify other repositories.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent
DEFAULT_MANIFEST = ROOT / "empire_manifest.json"
DEFAULT_STATE = ROOT / "state" / "empire.json"
DEFAULT_REPORT = ROOT / "EMPIRE_STATUS.md"
API_BASE = "https://api.github.com"


class GitHubAPIError(RuntimeError):
    pass


class GitHubAPI:
    def __init__(self, token: Optional[str] = None, timeout: int = 20):
        self.token = token
        self.timeout = timeout
        self.request_count = 0
        self.errors: List[str] = []

    def _request(self, url: str) -> Tuple[Any, Dict[str, str]]:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "victor-empire-autopilot/1.0",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        req = urllib.request.Request(url, headers=headers)
        self.request_count += 1
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw), dict(response.headers.items())
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            message = f"GitHub API {exc.code} for {url}: {body[:500]}"
            self.errors.append(message)
            raise GitHubAPIError(message) from exc
        except urllib.error.URLError as exc:
            message = f"GitHub API network error for {url}: {exc}"
            self.errors.append(message)
            raise GitHubAPIError(message) from exc

    def get_json(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        query = ""
        if params:
            query = "?" + urllib.parse.urlencode(params)
        payload, _ = self._request(f"{API_BASE}{path}{query}")
        return payload

    def paginated(self, path: str, params: Optional[Dict[str, Any]] = None, max_pages: int = 20) -> List[Any]:
        params = dict(params or {})
        params.setdefault("per_page", 100)
        results: List[Any] = []
        for page in range(1, max_pages + 1):
            params["page"] = page
            payload = self.get_json(path, params)
            if not isinstance(payload, list):
                raise GitHubAPIError(f"Expected list from {path}, received {type(payload).__name__}")
            results.extend(payload)
            if len(payload) < int(params["per_page"]):
                break
            time.sleep(0.05)
        return results


@dataclass
class RepoSnapshot:
    full_name: str
    name: str
    html_url: str
    description: str
    private: bool
    archived: bool
    fork: bool
    size_kb: int
    stars: int
    forks: int
    open_items: int
    open_prs: int
    open_issues_estimate: int
    default_branch: str
    pushed_at: Optional[str]
    updated_at: Optional[str]
    age_days: int
    pillar_id: str
    pillar_name: str
    pillar_priority: int
    canonical: bool
    attention_score: int


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def load_manifest(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if "pillars" not in data or not isinstance(data["pillars"], list):
        raise ValueError("Manifest must contain a pillars list")
    return data


def canonical_index(manifest: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    index: Dict[str, Dict[str, Any]] = {}
    for pillar in manifest["pillars"]:
        for full_name in pillar.get("canonical_repos", []):
            index[full_name.lower()] = pillar
    return index


def classify_repo(repo: Dict[str, Any], manifest: Dict[str, Any]) -> Dict[str, Any]:
    full_name = str(repo.get("full_name") or "")
    canon = canonical_index(manifest)
    exact = canon.get(full_name.lower())
    if exact:
        return exact

    haystack = " ".join(
        [
            str(repo.get("name") or ""),
            str(repo.get("description") or ""),
            str(repo.get("topics") or ""),
        ]
    ).lower()

    best: Optional[Tuple[int, int, Dict[str, Any]]] = None
    for pillar in manifest["pillars"]:
        patterns = [str(p).lower() for p in pillar.get("patterns", []) if str(p).strip()]
        if not patterns:
            continue
        matches = sum(1 for pattern in patterns if pattern in haystack)
        if matches <= 0:
            continue
        priority = int(pillar.get("priority", 0))
        candidate = (matches, priority, pillar)
        if best is None or candidate[:2] > best[:2]:
            best = candidate

    if best:
        return best[2]
    return manifest["pillars"][-1]


def age_in_days(repo: Dict[str, Any], now: datetime) -> int:
    stamp = parse_dt(repo.get("pushed_at")) or parse_dt(repo.get("updated_at"))
    if stamp is None:
        return 9999
    return max(0, (now - stamp).days)


def compute_attention_score(
    *,
    age_days: int,
    open_prs: int,
    open_issues: int,
    pillar_priority: int,
    canonical: bool,
    archived: bool,
) -> int:
    if archived:
        return 0

    if age_days <= 3:
        freshness = 25
    elif age_days <= 14:
        freshness = 20
    elif age_days <= 30:
        freshness = 14
    elif age_days <= 90:
        freshness = 7
    else:
        freshness = 2

    pr_pressure = min(25, open_prs * 7)
    issue_pressure = min(15, open_issues * 2)
    strategy = min(25, max(0, pillar_priority) * 2)
    canon_bonus = 10 if canonical else 0
    return min(100, freshness + pr_pressure + issue_pressure + strategy + canon_bonus)


def list_owner_repos(api: GitHubAPI, owner: str, include_private: bool) -> List[Dict[str, Any]]:
    public = api.paginated(
        f"/users/{urllib.parse.quote(owner)}/repos",
        {"type": "owner", "sort": "updated", "direction": "desc"},
    )
    merged = {str(r.get("full_name")): r for r in public if r.get("full_name")}

    if include_private and api.token:
        try:
            private_visible = api.paginated(
                "/user/repos",
                {"affiliation": "owner", "visibility": "all", "sort": "updated", "direction": "desc"},
            )
            for repo in private_visible:
                full_name = str(repo.get("full_name") or "")
                repo_owner = str((repo.get("owner") or {}).get("login") or "")
                if full_name and repo_owner.lower() == owner.lower():
                    merged[full_name] = repo
        except GitHubAPIError:
            # Public inventory remains valid; the report will expose API errors.
            pass

    return list(merged.values())


def search_open_prs(api: GitHubAPI, owner: str) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    query = f"user:{owner} is:pr is:open"
    for page in range(1, 11):
        try:
            payload = api.get_json(
                "/search/issues",
                {"q": query, "sort": "updated", "order": "desc", "per_page": 100, "page": page},
            )
        except GitHubAPIError:
            return items
        batch = payload.get("items", []) if isinstance(payload, dict) else []
        items.extend(batch)
        if len(batch) < 100:
            break
        time.sleep(0.15)
    return items


def pr_counts_by_repo(prs: Iterable[Dict[str, Any]]) -> Counter:
    counts: Counter = Counter()
    for pr in prs:
        repo_url = str(pr.get("repository_url") or "")
        marker = "/repos/"
        if marker in repo_url:
            full_name = repo_url.split(marker, 1)[1]
            counts[full_name] += 1
    return counts


def make_snapshots(
    repos: List[Dict[str, Any]],
    prs: List[Dict[str, Any]],
    manifest: Dict[str, Any],
    now: datetime,
) -> List[RepoSnapshot]:
    pr_counts = pr_counts_by_repo(prs)
    canon = canonical_index(manifest)
    snapshots: List[RepoSnapshot] = []

    for repo in repos:
        full_name = str(repo.get("full_name") or "")
        if not full_name:
            continue
        pillar = classify_repo(repo, manifest)
        age_days = age_in_days(repo, now)
        open_prs = int(pr_counts.get(full_name, 0))
        open_items = int(repo.get("open_issues_count") or 0)
        open_issues = max(0, open_items - open_prs)
        canonical = full_name.lower() in canon
        archived = bool(repo.get("archived"))
        score = compute_attention_score(
            age_days=age_days,
            open_prs=open_prs,
            open_issues=open_issues,
            pillar_priority=int(pillar.get("priority", 0)),
            canonical=canonical,
            archived=archived,
        )

        snapshots.append(
            RepoSnapshot(
                full_name=full_name,
                name=str(repo.get("name") or ""),
                html_url=str(repo.get("html_url") or ""),
                description=str(repo.get("description") or ""),
                private=bool(repo.get("private")),
                archived=archived,
                fork=bool(repo.get("fork")),
                size_kb=int(repo.get("size") or 0),
                stars=int(repo.get("stargazers_count") or 0),
                forks=int(repo.get("forks_count") or 0),
                open_items=open_items,
                open_prs=open_prs,
                open_issues_estimate=open_issues,
                default_branch=str(repo.get("default_branch") or ""),
                pushed_at=repo.get("pushed_at"),
                updated_at=repo.get("updated_at"),
                age_days=age_days,
                pillar_id=str(pillar.get("id") or "supporting_lattice"),
                pillar_name=str(pillar.get("name") or "Supporting Lattice"),
                pillar_priority=int(pillar.get("priority", 0)),
                canonical=canonical,
                attention_score=score,
            )
        )

    return snapshots


def build_next_actions(
    snapshots: List[RepoSnapshot],
    prs: List[Dict[str, Any]],
    manifest: Dict[str, Any],
) -> List[Dict[str, Any]]:
    cfg = manifest.get("autopilot", {})
    max_actions = int(cfg.get("max_next_actions", 12))
    stale_days = int(cfg.get("stale_days", 30))
    actions: List[Dict[str, Any]] = []
    seen: set[str] = set()

    for pr in prs:
        repo_url = str(pr.get("repository_url") or "")
        repo = repo_url.split("/repos/", 1)[1] if "/repos/" in repo_url else "unknown"
        key = f"pr:{repo}:{pr.get('number')}"
        if key in seen:
            continue
        seen.add(key)
        actions.append(
            {
                "kind": "review_pr",
                "priority": "P0",
                "repo": repo,
                "title": f"Review/merge PR #{pr.get('number')}: {pr.get('title', '')}",
                "url": pr.get("html_url"),
                "reason": "Open pull requests are the shortest path from work-in-progress to MERGED/SHIPPED.",
            }
        )
        if len(actions) >= min(5, max_actions):
            break

    repo_map = {s.full_name.lower(): s for s in snapshots}
    for pillar in manifest["pillars"]:
        for canonical in pillar.get("canonical_repos", []):
            snapshot = repo_map.get(str(canonical).lower())
            if snapshot is None:
                key = f"missing:{canonical}"
                if key not in seen:
                    seen.add(key)
                    actions.append(
                        {
                            "kind": "recover_canonical_repo",
                            "priority": "P1",
                            "repo": canonical,
                            "title": f"Resolve missing canonical repo: {canonical}",
                            "url": None,
                            "reason": f"Manifest expects this repo inside {pillar.get('name')} but the current scan could not see it.",
                        }
                    )
            elif snapshot.age_days > stale_days and not snapshot.archived:
                key = f"stale:{snapshot.full_name}"
                if key not in seen:
                    seen.add(key)
                    actions.append(
                        {
                            "kind": "triage_stale_canonical",
                            "priority": "P1",
                            "repo": snapshot.full_name,
                            "title": f"Triage stale canonical repo: {snapshot.name}",
                            "url": snapshot.html_url,
                            "reason": f"Canonical repo has not been pushed in {snapshot.age_days} days.",
                        }
                    )
            if len(actions) >= max_actions:
                return actions[:max_actions]

    for snapshot in sorted(snapshots, key=lambda s: (-s.attention_score, s.age_days, s.full_name.lower())):
        if snapshot.archived:
            continue
        key = f"attention:{snapshot.full_name}"
        if key in seen:
            continue
        seen.add(key)
        reason_bits = [f"attention score {snapshot.attention_score}/100"]
        if snapshot.open_prs:
            reason_bits.append(f"{snapshot.open_prs} open PR(s)")
        if snapshot.open_issues_estimate:
            reason_bits.append(f"~{snapshot.open_issues_estimate} open issue(s)")
        if snapshot.age_days <= 14:
            reason_bits.append("recently active")
        actions.append(
            {
                "kind": "inspect_high_attention_repo",
                "priority": "P2",
                "repo": snapshot.full_name,
                "title": f"Inspect and terminal-state {snapshot.name}",
                "url": snapshot.html_url,
                "reason": "; ".join(reason_bits) + ".",
            }
        )
        if len(actions) >= max_actions:
            break

    return actions[:max_actions]


def pillar_summary(snapshots: List[RepoSnapshot], manifest: Dict[str, Any]) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[RepoSnapshot]] = defaultdict(list)
    for snapshot in snapshots:
        grouped[snapshot.pillar_id].append(snapshot)

    rows: List[Dict[str, Any]] = []
    for pillar in manifest["pillars"]:
        repos = grouped.get(str(pillar.get("id")), [])
        rows.append(
            {
                "id": pillar.get("id"),
                "name": pillar.get("name"),
                "priority": pillar.get("priority", 0),
                "repo_count": len(repos),
                "canonical_count": sum(1 for r in repos if r.canonical),
                "active_14d": sum(1 for r in repos if r.age_days <= 14 and not r.archived),
                "open_prs": sum(r.open_prs for r in repos),
                "open_issues_estimate": sum(r.open_issues_estimate for r in repos),
                "attention_sum": sum(r.attention_score for r in repos),
            }
        )
    return rows


def render_markdown(state: Dict[str, Any]) -> str:
    summary = state["summary"]
    lines = [
        "# Empire Status",
        "",
        f"**Generated:** {state['generated_at']}  ",
        f"**Owner:** `{state['owner']}`  ",
        f"**Mode:** `{state['mode']}`",
        "",
        "## Bippity Boppity Boop Loop",
        "",
        "`SCAN → CLASSIFY → ASSEMBLE → VERIFY → RECEIPT → PRIORITIZE → NEXT RUN`",
        "",
        "The daily run observes the lattice, runs Victor's local assembler, writes state, and ranks the shortest path to MERGED / SHIPPED / MONETIZED. Cross-repository writes stay disabled unless explicitly authorized.",
        "",
        "## Scoreboard",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Visible repositories | {summary['visible_repositories']} |",
        f"| Canonical repositories visible | {summary['canonical_visible']} |",
        f"| Active in last 14 days | {summary['active_14d']} |",
        f"| Archived | {summary['archived']} |",
        f"| Private visible | {summary['private_visible']} |",
        f"| Open PRs discovered | {summary['open_prs']} |",
        f"| Estimated open issues | {summary['open_issues_estimate']} |",
        "",
        "## Empire Skin / Pillars",
        "",
        "| Pillar | Repos | Canonical | Active ≤14d | Open PRs | ~Issues |",
        "|---|---:|---:|---:|---:|---:|",
    ]

    for row in state["pillars"]:
        lines.append(
            f"| {row['name']} | {row['repo_count']} | {row['canonical_count']} | {row['active_14d']} | {row['open_prs']} | {row['open_issues_estimate']} |"
        )

    lines.extend([
        "",
        "## Highest-Attention Repositories",
        "",
        "The attention score is a routing heuristic, not a quality score. It combines strategic pillar weight, recency, canonical status, and unresolved work pressure.",
        "",
        "| Score | Repository | Pillar | Age | PRs | ~Issues |",
        "|---:|---|---|---:|---:|---:|",
    ])

    for repo in state["top_attention"]:
        link = f"[{repo['full_name']}]({repo['html_url']})" if repo.get("html_url") else repo["full_name"]
        lines.append(
            f"| {repo['attention_score']} | {link} | {repo['pillar_name']} | {repo['age_days']}d | {repo['open_prs']} | {repo['open_issues_estimate']} |"
        )

    lines.extend([
        "",
        "## Next Assembly Queue",
        "",
    ])
    for i, action in enumerate(state["next_actions"], start=1):
        title = action["title"]
        if action.get("url"):
            title = f"[{title}]({action['url']})"
        lines.append(f"{i}. **{action['priority']} — {title}** — {action['reason']}")

    if state.get("api_errors"):
        lines.extend([
            "",
            "## Coverage Warnings",
            "",
            "The run completed with API limitations. Public data and any successfully visible private data were still processed.",
            "",
        ])
        for error in state["api_errors"][:10]:
            lines.append(f"- `{error[:300]}`")

    lines.extend([
        "",
        "## Architecture",
        "",
        "```mermaid",
        "flowchart TD",
        "    FAN[Fans / Creators / Customers] --> SITE[iambandobandz Empire Router]",
        "    SITE --> BHEARD[B Heard Network]",
        "    SITE --> MUSIC[Music + Catalog Engine]",
        "    SITE --> TRUTH[Truth Compiler + Revenue]",
        "    VICTOR[Victor Authority + Continuity] --> DEV[Dev-Ville Execution]",
        "    DEV --> SITE",
        "    DEV --> BHEARD",
        "    DEV --> MUSIC",
        "    DEV --> TRUTH",
        "    RND[Massive Magnetics Frontier R&D] --> VICTOR",
        "    RND --> MUSIC",
        "    MUSIC --> REVENUE[Revenue / Proof / Telemetry]",
        "    BHEARD --> REVENUE",
        "    TRUTH --> REVENUE",
        "    REVENUE --> VICTOR",
        "    VICTOR --> RECEIPT[Chronos-style Receipts / State]",
        "    RECEIPT --> NEXT[Next Daily Assembly Run]",
        "    NEXT --> VICTOR",
        "```",
        "",
        "---",
        "Generated by `empire_autopilot.py`. The machine-readable receipt is `state/empire.json`.",
    ])
    return "\n".join(lines) + "\n"


def write_outputs(state: Dict[str, Any], state_path: Path, report_path: Path) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report_path.write_text(render_markdown(state), encoding="utf-8")


def build_state(
    owner: str,
    manifest: Dict[str, Any],
    snapshots: List[RepoSnapshot],
    prs: List[Dict[str, Any]],
    api: GitHubAPI,
    generated_at: datetime,
) -> Dict[str, Any]:
    cfg = manifest.get("autopilot", {})
    max_attention = int(cfg.get("max_attention_repos", 15))
    top = sorted(snapshots, key=lambda s: (-s.attention_score, s.age_days, s.full_name.lower()))[:max_attention]

    summary = {
        "visible_repositories": len(snapshots),
        "canonical_visible": sum(1 for s in snapshots if s.canonical),
        "active_14d": sum(1 for s in snapshots if s.age_days <= 14 and not s.archived),
        "archived": sum(1 for s in snapshots if s.archived),
        "private_visible": sum(1 for s in snapshots if s.private),
        "open_prs": len(prs),
        "open_issues_estimate": sum(s.open_issues_estimate for s in snapshots),
    }

    return {
        "schema_version": 1,
        "generated_at": generated_at.isoformat(),
        "owner": owner,
        "mission": manifest.get("mission"),
        "mode": cfg.get("default_mode", "observe-plan-assemble-local"),
        "cross_repo_write_policy": cfg.get("cross_repo_write_policy", "disabled-unless-explicitly-authorized"),
        "terminal_states": manifest.get("terminal_states", []),
        "summary": summary,
        "pillars": pillar_summary(snapshots, manifest),
        "top_attention": [asdict(s) for s in top],
        "next_actions": build_next_actions(snapshots, prs, manifest),
        "repositories": [asdict(s) for s in sorted(snapshots, key=lambda x: x.full_name.lower())],
        "api_request_count": api.request_count,
        "api_errors": api.errors,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Scan and map the MASSIVEMAGNETICS empire lattice")
    parser.add_argument("--owner", default=os.getenv("GITHUB_OWNER", "MASSIVEMAGNETICS"))
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--public-only", action="store_true", help="Skip authenticated private-repository discovery")
    args = parser.parse_args(argv)

    try:
        manifest = load_manifest(args.manifest)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot load manifest: {exc}", file=sys.stderr)
        return 2

    token = os.getenv("EMPIRE_GH_PAT") or os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN")
    api = GitHubAPI(token=token)
    now = utcnow()

    try:
        repos = list_owner_repos(api, args.owner, include_private=not args.public_only)
    except GitHubAPIError as exc:
        print(f"ERROR: repository inventory failed: {exc}", file=sys.stderr)
        return 3

    prs = search_open_prs(api, args.owner)
    snapshots = make_snapshots(repos, prs, manifest, now)
    state = build_state(args.owner, manifest, snapshots, prs, api, now)
    write_outputs(state, args.state, args.report)

    print(
        f"Empire scan complete: {state['summary']['visible_repositories']} repos, "
        f"{state['summary']['open_prs']} open PRs, "
        f"{len(state['next_actions'])} queued actions."
    )
    print(f"Report: {args.report}")
    print(f"State:  {args.state}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
