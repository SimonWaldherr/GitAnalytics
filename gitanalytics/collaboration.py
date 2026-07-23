"""Evidence-aware author distances through shared repository membership.

The module deliberately uses an author–repository bipartite graph.  It avoids
materialising an expensive all-to-all author graph for large projects and keeps
the repository that explains each link available for reporting.
"""

from __future__ import annotations

import datetime as dt
import re
from collections import defaultdict, deque
from typing import Any

from .database import GitAnalyticsDatabase


def build_collaboration(
    database: GitAnalyticsDatabase, config: dict, names_by_key: dict[str, str]
) -> dict[str, Any]:
    """Build configurable shortest paths without treating service accounts as people."""
    network = config["network"]
    if not network.get("enabled", False):
        return {
            "enabled": False,
            "reference_names": network.get("reference_names", []),
            "references_found": [],
            "authors": 0,
            "connected_authors": 0,
            "max_distance": None,
            "rows": [],
            "truncated": False,
            "excluded_memberships": 0,
            "method": "Optionale Autoren-/Repository-Distanz ist deaktiviert; normale Repository-Kennzahlen bleiben unverändert.",
            "model": {
                "enabled": False,
                "exclude_service_accounts": network["exclude_service_accounts"],
                "min_commits_per_author_repository": network["min_commits_per_author_repository"],
                "max_contribution_gap_days": network["max_contribution_gap_days"],
                "require_remote_reference": network["require_remote_reference"],
            },
        }
    trusted_condition = "WHERE c.is_trusted = 1" if network["require_remote_reference"] else ""
    memberships = database.rows(
        f"""
        SELECT c.author_key, MAX(c.author_name) AS author_name, MAX(c.author_email) AS author_email,
               MAX(c.author_is_bot) AS is_bot, c.repo_id, r.display_name AS repository, COUNT(*) AS commits,
               MIN(c.activity_date) AS first_date, MAX(c.activity_date) AS last_date
        FROM effective_commits c JOIN repositories r ON r.id = c.repo_id
        {trusted_condition}
        GROUP BY c.author_key, c.repo_id ORDER BY c.author_key, r.display_name
        """
    )
    ignored = [re.compile(str(pattern)) for pattern in network["ignored_account_patterns"]]
    minimum, gap = int(network["min_commits_per_author_repository"]), int(network["max_contribution_gap_days"])
    by_author: dict[str, list[tuple[int, str, str, str]]] = defaultdict(list)
    by_repo: dict[int, list[tuple[str, str, str]]] = defaultdict(list)
    repository_names: dict[int, str] = {}
    commits: dict[str, int] = defaultdict(int)
    excluded = 0
    for row in memberships:
        identity = f"{row['author_name'] or ''} <{row['author_email'] or ''}>"
        service_account = bool(row["is_bot"]) or any(pattern.search(identity) for pattern in ignored)
        if int(row["commits"] or 0) < minimum or (network["exclude_service_accounts"] and service_account):
            excluded += 1
            continue
        author, repo_id = str(row["author_key"]), int(row["repo_id"])
        first, last = str(row["first_date"]), str(row["last_date"])
        by_author[author].append((repo_id, str(row["repository"]), first, last))
        by_repo[repo_id].append((author, first, last))
        repository_names[repo_id] = str(row["repository"])
        commits[author] += int(row["commits"] or 0)

    targets = {name.casefold() for name in network["reference_names"]}
    references = sorted(key for key, name in names_by_key.items() if name.casefold() in targets)
    distance = {key: 0 for key in references}
    parent: dict[str, tuple[str, str]] = {}
    queue: deque[str] = deque(references)
    visited_repositories: set[int] = set()
    while queue:
        author = queue.popleft()
        for repo_id, repository, first, last in by_author.get(author, []):
            if repo_id in visited_repositories:
                continue
            visited_repositories.add(repo_id)
            for neighbour, other_first, other_last in by_repo[repo_id]:
                if dt.date.fromisoformat(other_first) > dt.date.fromisoformat(last) + dt.timedelta(days=gap):
                    continue
                if dt.date.fromisoformat(first) > dt.date.fromisoformat(other_last) + dt.timedelta(days=gap):
                    continue
                if neighbour not in distance:
                    distance[neighbour] = distance[author] + 1
                    parent[neighbour] = (author, repository)
                    queue.append(neighbour)

    def route(author: str) -> list[dict[str, str]]:
        steps = [{"author": names_by_key.get(author, "Unbekannt"), "via_repository": ""}]
        while author in parent:
            author, repository = parent[author]
            steps.append({"author": names_by_key.get(author, "Unbekannt"), "via_repository": repository})
        return list(reversed(steps))

    rows = []
    for author in by_author:
        path = route(author) if author in distance else []
        rows.append({
            "author": names_by_key.get(author, "Unbekannt"), "commits": commits[author],
            "repositories": len(by_author[author]), "distance": distance.get(author),
            "path": path,
            "repository_names": sorted({
                str(step["via_repository"]) for step in path if step.get("via_repository")
            }),
        })
    rows.sort(key=lambda row: (row["distance"] is None, row["distance"] if row["distance"] is not None else 10**9, -row["commits"], row["author"].casefold()))
    direct_pairs: list[dict[str, Any]] = []
    for repo_id, members in by_repo.items():
        repository = repository_names.get(repo_id, "Unbekannt")
        for index, (left, left_first, left_last) in enumerate(members):
            for right, right_first, right_last in members[index + 1:]:
                if dt.date.fromisoformat(right_first) > dt.date.fromisoformat(left_last) + dt.timedelta(days=gap):
                    continue
                if dt.date.fromisoformat(left_first) > dt.date.fromisoformat(right_last) + dt.timedelta(days=gap):
                    continue
                direct_pairs.append({
                    "author": names_by_key.get(left, "Unbekannt"), "co_author": names_by_key.get(right, "Unbekannt"),
                    "repository": repository, "commits": commits[left] + commits[right],
                    "repository_names": [repository],
                })
    direct_pairs.sort(key=lambda row: (-row["commits"], row["author"].casefold(), row["co_author"].casefold()))
    maximum = int(network["max_display_nodes"])
    return {
        "reference_names": network["reference_names"],
        "references_found": [names_by_key[key] for key in references],
        "authors": len(by_author), "connected_authors": len(distance),
        "max_distance": max(distance.values(), default=None), "rows": rows[:maximum],
        "direct_pairs": direct_pairs[:maximum],
        "truncated": len(rows) > maximum, "excluded_memberships": excluded,
        "method": "Autoren sind über gemeinsam bearbeitete Repositories verbunden; die Distanz ist kein Nachweis persönlicher Bekanntschaft.",
        "enabled": True,
        "model": {"enabled": True, "exclude_service_accounts": network["exclude_service_accounts"],
                  "min_commits_per_author_repository": minimum, "max_contribution_gap_days": gap,
                  "require_remote_reference": network["require_remote_reference"]},
    }
