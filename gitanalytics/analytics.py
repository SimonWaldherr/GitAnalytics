from __future__ import annotations

import datetime as dt
import json
import math
import statistics
from collections import defaultdict
from typing import Any, Iterable

from .database import GitAnalyticsDatabase
from .collaboration import build_collaboration
from .util import iso_now, longest_gap, longest_streak, month_range, parse_iso_datetime


WEEKDAYS_DE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
DAYPARTS = [
    ("Nacht", 0, 6),
    ("Vormittag", 6, 12),
    ("Nachmittag", 12, 18),
    ("Abend", 18, 24),
]
TYPE_LABELS = {
    "feat": "Features", "fix": "Fixes", "docs": "Dokumentation", "style": "Style",
    "refactor": "Refactoring", "perf": "Performance", "test": "Tests", "build": "Build",
    "ci": "CI", "chore": "Chores", "revert": "Reverts", "merge": "Merges",
    "release": "Releases", "security": "Security", "deps": "Dependencies",
    "init": "Initialisierung", "other": "Sonstige",
}


def _attach_repository_names(
    rows: list[dict[str, Any]], memberships: Iterable[dict[str, Any]], keys: tuple[str, ...]
) -> None:
    """Attach stable repository-membership sets for client-side crossfilters."""
    grouped: dict[tuple[Any, ...], set[str]] = defaultdict(set)
    for membership in memberships:
        repository = membership.get("repository")
        if repository is not None:
            grouped[tuple(membership.get(key) for key in keys)].add(str(repository))
    for row in rows:
        row["repository_names"] = sorted(grouped.get(tuple(row.get(key) for key in keys), set()))


def _percentile(values: list[int], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(ordered[lower])
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def _gini(values: Iterable[int]) -> float | None:
    ordered = sorted(value for value in values if value >= 0)
    if not ordered or sum(ordered) == 0:
        return None
    n = len(ordered)
    weighted = sum((index + 1) * value for index, value in enumerate(ordered))
    return (2 * weighted) / (n * sum(ordered)) - (n + 1) / n


def _bus_factor(values: Iterable[int], threshold: float) -> int:
    ordered = sorted((value for value in values if value > 0), reverse=True)
    total = sum(ordered)
    if not total:
        return 0
    cumulative = 0
    for index, value in enumerate(ordered, start=1):
        cumulative += value
        if cumulative / total >= threshold:
            return index
    return len(ordered)


def _repo_status(last_date: str | None, today: dt.date, quiet: int, dormant: int, commits: int) -> tuple[str, int | None]:
    if not commits or not last_date:
        return "empty", None
    date = dt.date.fromisoformat(last_date[:10])
    days = (today - date).days
    if days >= dormant:
        return "dormant", days
    if days >= quiet:
        return "quiet", days
    return "active", days


class Analytics:
    def __init__(self, database: GitAnalyticsDatabase, config: dict) -> None:
        self.db = database
        self.config = config
        self.today = dt.datetime.now(dt.timezone.utc).date()
        self.top_n = int(config["report"]["top_n"])
        self.include_paths = bool(config["privacy"]["include_absolute_paths"])
        self.db.create_effective_views(config)
        self._path_replacements: list[tuple[str, str]] = []
        for row in self.db.rows(
            "SELECT display_name, path, root_path, git_dir, common_dir FROM repositories"
        ):
            name = str(row.get("display_name") or "Repository")
            for key, label in (
                ("path", f"<repo:{name}>"),
                ("git_dir", f"<git:{name}>"),
                ("common_dir", f"<git-common:{name}>"),
                ("root_path", "<root>"),
            ):
                value = str(row.get(key) or "")
                if value:
                    self._path_replacements.append((value, label))
        self._path_replacements.sort(key=lambda item: len(item[0]), reverse=True)

    def _redact(self, value: Any) -> Any:
        if self.include_paths or not isinstance(value, str):
            return value
        result = value
        for raw, replacement in self._path_replacements:
            result = result.replace(raw, replacement)
            result = result.replace(raw.replace("\\", "/"), replacement)
            result = result.replace(raw.replace("/", "\\"), replacement)
        return result

    def _meta(self) -> dict[str, Any]:
        run = self.db.row("SELECT * FROM runs ORDER BY id DESC LIMIT 1") or {}
        try:
            roots = json.loads(run.get("roots_json") or "[]")
        except json.JSONDecodeError:
            roots = []
        include_paths = bool(self.config["privacy"]["include_absolute_paths"])
        displayed_roots = roots if include_paths else [f"Root {index + 1}" for index in range(len(roots))]
        return {
            "title": self.config["report"]["title"],
            "generated_at": iso_now(),
            "roots": displayed_roots,
            "tool_version": run.get("tool_version"),
            "run": {
                key: run.get(key)
                for key in (
                    "id", "started_at", "finished_at", "repositories_found", "repositories_scanned",
                    "repositories_cached", "repositories_failed", "status",
                )
            },
            "history": {
                key: self.config["history"].get(key)
                for key in (
                    "scope", "refs", "since", "until", "first_parent", "include_merges",
                    "include_bots", "deduplicate_global", "activity_timestamp", "timezone",
                    "respect_mailmap", "collect_churn", "detect_renames", "store_file_details",
                    "store_subjects", "collect_tree", "collect_releases", "max_commits_per_repository",
                )
            },
            "work_time": self.config["work_time"],
            "privacy": self.config["privacy"],
            "profile": self.config["profile"],
            "report": self.config["report"],
        }

    def _activity(self) -> dict[str, Any]:
        daily_rows = self.db.rows(
            """
            SELECT activity_date AS date, COUNT(*) AS commits,
                   COUNT(DISTINCT author_key) AS authors,
                   COUNT(DISTINCT repo_id) AS repositories,
                   SUM(insertions) AS insertions, SUM(deletions) AS deletions
            FROM effective_commits GROUP BY activity_date ORDER BY activity_date
            """
        )
        _attach_repository_names(
            daily_rows,
            self.db.rows(
                """
                SELECT DISTINCT c.activity_date AS date, r.display_name AS repository
                FROM effective_commits c JOIN repositories r ON r.id = c.repo_id
                """
            ),
            ("date",),
        )
        monthly_raw = self.db.rows(
            """
            SELECT activity_year AS year, activity_month AS month, COUNT(*) AS commits,
                   COUNT(DISTINCT author_key) AS authors,
                   COUNT(DISTINCT repo_id) AS repositories,
                   SUM(insertions) AS insertions, SUM(deletions) AS deletions
            FROM effective_commits GROUP BY activity_year, activity_month
            ORDER BY activity_year, activity_month
            """
        )
        monthly: list[dict[str, Any]] = []
        if monthly_raw:
            values = {(int(row["year"]), int(row["month"])): row for row in monthly_raw}
            start = dt.date(int(monthly_raw[0]["year"]), int(monthly_raw[0]["month"]), 1)
            end = dt.date(int(monthly_raw[-1]["year"]), int(monthly_raw[-1]["month"]), 1)
            for year, month in month_range(start, end):
                row = values.get((year, month), {})
                monthly.append(
                    {
                        "key": f"{year:04d}-{month:02d}", "year": year, "month": month,
                        "commits": int(row.get("commits") or 0),
                        "authors": int(row.get("authors") or 0),
                        "repositories": int(row.get("repositories") or 0),
                        "insertions": int(row.get("insertions") or 0),
                        "deletions": int(row.get("deletions") or 0),
                    }
                )
        _attach_repository_names(
            monthly,
            self.db.rows(
                """
                SELECT DISTINCT c.activity_year AS year, c.activity_month AS month,
                       r.display_name AS repository
                FROM effective_commits c JOIN repositories r ON r.id = c.repo_id
                """
            ),
            ("year", "month"),
        )
        yearly = self.db.rows(
            """
            SELECT activity_year AS year, COUNT(*) AS commits,
                   COUNT(DISTINCT author_key) AS authors,
                   COUNT(DISTINCT repo_id) AS repositories,
                   SUM(insertions) AS insertions, SUM(deletions) AS deletions
            FROM effective_commits GROUP BY activity_year ORDER BY activity_year
            """
        )
        _attach_repository_names(
            yearly,
            self.db.rows(
                """
                SELECT DISTINCT c.activity_year AS year, r.display_name AS repository
                FROM effective_commits c JOIN repositories r ON r.id = c.repo_id
                """
            ),
            ("year",),
        )
        heat_raw = self.db.rows(
            """
            SELECT activity_weekday AS weekday, activity_hour AS hour, COUNT(*) AS commits
            FROM effective_commits GROUP BY activity_weekday, activity_hour
            """
        )
        heat_counts = {(int(row["weekday"]), int(row["hour"])): int(row["commits"]) for row in heat_raw}
        heatmap = [
            {
                "weekday": weekday, "weekday_label": WEEKDAYS_DE[weekday], "hour": hour,
                "commits": heat_counts.get((weekday, hour), 0),
            }
            for weekday in range(7) for hour in range(24)
        ]
        _attach_repository_names(
            heatmap,
            self.db.rows(
                """
                SELECT DISTINCT c.activity_weekday AS weekday, c.activity_hour AS hour,
                       r.display_name AS repository
                FROM effective_commits c JOIN repositories r ON r.id = c.repo_id
                """
            ),
            ("weekday", "hour"),
        )
        weekday_repositories: dict[int, set[str]] = defaultdict(set)
        hour_repositories: dict[int, set[str]] = defaultdict(set)
        for cell in heatmap:
            weekday_repositories[int(cell["weekday"])].update(cell["repository_names"])
            hour_repositories[int(cell["hour"])].update(cell["repository_names"])
        weekdays = [
            {
                "weekday_number": weekday, "weekday": WEEKDAYS_DE[weekday],
                "commits": sum(heat_counts.get((weekday, hour), 0) for hour in range(24)),
                "repository_names": sorted(weekday_repositories[weekday]),
            }
            for weekday in range(7)
        ]
        hours = [
            {
                "hour": hour, "commits": sum(heat_counts.get((weekday, hour), 0) for weekday in range(7)),
                "repository_names": sorted(hour_repositories[hour]),
            }
            for hour in range(24)
        ]
        dayparts = [
            {
                "daypart": name,
                "commits": sum(row["commits"] for row in hours if start <= int(row["hour"]) < end),
                "repository_names": sorted({
                    repository for row in hours if start <= int(row["hour"]) < end
                    for repository in row["repository_names"]
                }),
            }
            for name, start, end in DAYPARTS
        ]
        dates = [dt.date.fromisoformat(row["date"]) for row in daily_rows]
        streak_length, streak_start, streak_end = longest_streak(dates)
        gap_length, gap_left, gap_right = longest_gap(dates)
        daily_counts = [int(row["commits"]) for row in daily_rows]

        working_days = set(int(day) for day in self.config["work_time"]["working_days"])
        start_hour = int(self.config["work_time"]["start_hour"])
        end_hour = int(self.config["work_time"]["end_hour"])
        total = sum(daily_counts)
        weekend = sum(
            cell["commits"] for cell in heatmap if int(cell["weekday"]) not in working_days
        )
        outside = sum(
            cell["commits"]
            for cell in heatmap
            if int(cell["weekday"]) not in working_days or not start_hour <= int(cell["hour"]) < end_hour
        )

        recent: dict[str, Any] = {}
        for days in (30, 90, 365):
            current_start = self.today - dt.timedelta(days=days - 1)
            previous_end = current_start - dt.timedelta(days=1)
            previous_start = previous_end - dt.timedelta(days=days - 1)
            row = self.db.row(
                """
                SELECT
                    SUM(CASE WHEN activity_date BETWEEN ? AND ? THEN 1 ELSE 0 END) AS current_count,
                    SUM(CASE WHEN activity_date BETWEEN ? AND ? THEN 1 ELSE 0 END) AS previous_count
                FROM effective_commits
                """,
                (current_start.isoformat(), self.today.isoformat(), previous_start.isoformat(), previous_end.isoformat()),
            ) or {}
            current = int(row.get("current_count") or 0)
            previous = int(row.get("previous_count") or 0)
            delta = (current - previous) / previous if previous else (None if current else 0.0)
            recent[str(days)] = {
                "days": days, "current": current, "previous": previous, "delta": delta,
                "start": current_start.isoformat(), "end": self.today.isoformat(),
            }

        calendar_start = self.today - dt.timedelta(days=364)
        daily_map = {str(row["date"]): row for row in daily_rows}
        calendar = [
            {
                "date": (calendar_start + dt.timedelta(days=offset)).isoformat(),
                "commits": int(daily_map.get((calendar_start + dt.timedelta(days=offset)).isoformat(), {}).get("commits") or 0),
                "repository_names": daily_map.get(
                    (calendar_start + dt.timedelta(days=offset)).isoformat(), {}
                ).get("repository_names", []),
            }
            for offset in range(365)
        ]
        busiest = sorted(daily_rows, key=lambda row: (-int(row["commits"]), row["date"]))[:50]
        return {
            "daily": daily_rows,
            "monthly": monthly,
            "yearly": yearly,
            "weekdays": weekdays,
            "hours": hours,
            "dayparts": dayparts,
            "weekday_hour_heatmap": heatmap,
            "calendar_365": calendar,
            "busiest_days": busiest,
            "longest_streak": {
                "days": streak_length,
                "start": streak_start.isoformat() if streak_start else None,
                "end": streak_end.isoformat() if streak_end else None,
            },
            "longest_gap": {
                "days_without_commits": gap_length,
                "after": gap_left.isoformat() if gap_left else None,
                "before": gap_right.isoformat() if gap_right else None,
            },
            "average_commits_per_active_day": total / len(daily_rows) if daily_rows else None,
            "median_commits_per_active_day": statistics.median(daily_counts) if daily_counts else None,
            "weekend_share": weekend / total if total else None,
            "outside_work_time_share": outside / total if total else None,
            "recent": recent,
        }

    def _contributors(self) -> tuple[dict[str, Any], dict[str, str]]:
        rows = self.db.rows(
            """
            SELECT author_key, MAX(author_name) AS name, MAX(author_email) AS email,
                   MAX(author_is_bot) AS is_bot, COUNT(*) AS commits,
                   COUNT(DISTINCT repo_id) AS repositories,
                   COUNT(DISTINCT activity_date) AS active_days,
                   SUM(is_merge) AS merges, SUM(insertions) AS insertions,
                   SUM(deletions) AS deletions, SUM(files_changed) AS files_changed,
                   MIN(activity_at) AS first_commit, MAX(activity_at) AS last_commit
            FROM effective_commits GROUP BY author_key
            ORDER BY commits DESC, name COLLATE NOCASE
            """
        )
        total = sum(int(row["commits"]) for row in rows)
        anonymize = bool(self.config["privacy"]["anonymize_authors"])
        show_emails = bool(self.config["privacy"]["show_emails"]) and not anonymize
        sorted_keys = sorted((str(row["author_key"]) for row in rows))
        anon = {key: f"Autor {index:03d}" for index, key in enumerate(sorted_keys, start=1)}
        for row in rows:
            row["commits"] = int(row["commits"] or 0)
            row["share"] = row["commits"] / total if total else 0.0
            row["churn"] = int(row["insertions"] or 0) + int(row["deletions"] or 0)
            if anonymize:
                row["name"] = anon[str(row["author_key"])]
                row["email"] = ""
            elif not show_emails:
                row["email"] = ""

        _attach_repository_names(
            rows,
            self.db.rows(
                """
                SELECT DISTINCT c.author_key, r.display_name AS repository
                FROM effective_commits c JOIN repositories r ON r.id = c.repo_id
                """
            ),
            ("author_key",),
        )

        counts = [int(row["commits"]) for row in rows]
        hhi = sum((count / total) ** 2 for count in counts) if total else None
        hints: list[dict[str, Any]] = []
        if not anonymize:
            same_name = self.db.rows(
                """
                SELECT LOWER(author_name_raw) AS normalized_name, MAX(author_name_raw) AS name,
                       COUNT(DISTINCT LOWER(author_email_raw)) AS variants,
                       GROUP_CONCAT(DISTINCT LOWER(author_email_raw)) AS variant_values,
                       COUNT(*) AS commits
                FROM commits c JOIN repositories r ON r.id = c.repo_id
                WHERE r.active = 1 AND r.status IN ('ready','stale') AND TRIM(author_name_raw) <> ''
                GROUP BY LOWER(author_name_raw) HAVING COUNT(DISTINCT LOWER(author_email_raw)) > 1
                ORDER BY commits DESC LIMIT 100
                """
            )
            for row in same_name:
                hints.append(
                    {
                        "kind": "name_multiple_emails", "name": row["name"],
                        "values": row["variant_values"].split(",") if row.get("variant_values") and show_emails else [],
                        "commits": row["commits"],
                    }
                )
            same_email = self.db.rows(
                """
                SELECT LOWER(author_email_raw) AS email,
                       COUNT(DISTINCT author_name_raw) AS variants,
                       GROUP_CONCAT(DISTINCT author_name_raw) AS variant_values,
                       COUNT(*) AS commits
                FROM commits c JOIN repositories r ON r.id = c.repo_id
                WHERE r.active = 1 AND r.status IN ('ready','stale') AND TRIM(author_email_raw) <> ''
                GROUP BY LOWER(author_email_raw) HAVING COUNT(DISTINCT author_name_raw) > 1
                ORDER BY commits DESC LIMIT 100
                """
            )
            for row in same_email:
                hints.append(
                    {
                        "kind": "email_multiple_names", "email": row["email"] if show_emails else "",
                        "values": row["variant_values"].split(",") if row.get("variant_values") else [],
                        "commits": row["commits"],
                    }
                )
        names_by_key = {str(row["author_key"]): str(row["name"]) for row in rows}
        for row in rows:
            row.pop("author_key", None)
        return ({
            "rows": rows,
            "concentration": {
                "top_author_share": max(counts, default=0) / total if total else None,
                "bus_factor_50": _bus_factor(counts, 0.50),
                "bus_factor_80": _bus_factor(counts, 0.80),
                "gini": _gini(counts),
                "hhi": hhi,
                "note": "Heuristiken auf Basis der Commit-Anteile; keine organisatorische Risikobewertung.",
            },
            "identity_hints": hints,
        }, names_by_key)

    def _repositories(self, author_names: dict[str, str]) -> list[dict[str, Any]]:
        rows = self.db.rows(
            """
            SELECT r.id, r.display_name AS name, r.path, r.status, r.error,
                   COALESCE(p.classification, 'private') AS classification,
                   r.is_bare, r.is_shallow, r.is_partial, r.object_format,
                   r.head_branch, r.default_branch, r.local_branches, r.remote_branches,
                   r.tags, r.remote_hosts_json, r.tree_files, r.tree_bytes, r.release_count,
                   COUNT(c.hash) AS commits, COUNT(DISTINCT c.author_key) AS authors,
                   COUNT(DISTINCT c.activity_date) AS active_days,
                   SUM(c.is_merge) AS merges, SUM(c.insertions) AS insertions,
                   SUM(c.deletions) AS deletions, SUM(c.files_changed) AS files_changed,
                   MIN(c.activity_at) AS first_commit, MAX(c.activity_at) AS last_commit
            FROM repositories r
            LEFT JOIN repository_privacy p ON p.repo_id = r.id
            LEFT JOIN effective_commits c ON c.repo_id = r.id
            WHERE r.active = 1
            GROUP BY r.id ORDER BY commits DESC, r.display_name COLLATE NOCASE
            """
        )
        author_counts = self.db.rows(
            """
            SELECT repo_id, author_key, COUNT(*) AS commits
            FROM effective_commits GROUP BY repo_id, author_key
            ORDER BY repo_id, commits DESC
            """
        )
        counts_by_repo: dict[int, list[tuple[str, int]]] = defaultdict(list)
        for item in author_counts:
            counts_by_repo[int(item["repo_id"])].append((str(item["author_key"]), int(item["commits"])))
        top_languages = {
            int(row["repo_id"]): str(row["language"])
            for row in self.db.rows(
                """
                SELECT repo_id, language FROM (
                    SELECT repo_id, language, bytes,
                           ROW_NUMBER() OVER(PARTITION BY repo_id ORDER BY bytes DESC, files DESC, language) AS rank
                    FROM tree_languages
                ) WHERE rank = 1
                """
            )
        }
        language_rows = self.db.rows(
            """
            SELECT t.repo_id, t.language, t.files, t.bytes,
                   COALESCE(s.code_lines, 0) AS code_lines,
                   COALESCE(s.comment_lines, 0) AS comment_lines,
                   COALESCE(s.blank_lines, 0) AS blank_lines
            FROM tree_languages t
            LEFT JOIN tree_comment_stats s
              ON s.repo_id = t.repo_id AND s.language = t.language AND s.kind = 'all'
            ORDER BY t.repo_id, t.bytes DESC, t.language
            """
        )
        kind_rows = self.db.rows(
            """
            SELECT repo_id, language, kind, comment_lines
            FROM tree_comment_stats WHERE kind <> 'all'
            ORDER BY repo_id, language, kind
            """
        )
        kinds_by_language: dict[tuple[int, str], dict[str, int]] = defaultdict(dict)
        for item in kind_rows:
            kinds_by_language[(int(item["repo_id"]), str(item["language"]))][str(item["kind"])] = int(item["comment_lines"] or 0)
        languages_by_repo: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for item in language_rows:
            code_lines, comment_lines = int(item["code_lines"] or 0), int(item["comment_lines"] or 0)
            denominator = code_lines + comment_lines
            languages_by_repo[int(item["repo_id"])].append({
                "language": str(item["language"]), "files": int(item["files"] or 0), "bytes": int(item["bytes"] or 0),
                "code_lines": code_lines, "comment_lines": comment_lines, "blank_lines": int(item["blank_lines"] or 0),
                "comment_density": comment_lines / denominator if denominator else None,
                "comment_types": kinds_by_language.get((int(item["repo_id"]), str(item["language"])), {}),
            })
        file_types_by_repo: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for item in self.db.rows(
            "SELECT repo_id, file_type, files, bytes FROM tree_file_types ORDER BY repo_id, bytes DESC, file_type"
        ):
            file_types_by_repo[int(item["repo_id"])].append({
                "file_type": str(item["file_type"]), "files": int(item["files"] or 0), "bytes": int(item["bytes"] or 0),
            })
        signals_by_repo = {
            int(item["repo_id"]): {
                "ci_systems": json.loads(item["ci_systems_json"] or "[]"),
                "licenses": json.loads(item["licenses_json"] or "[]"),
            }
            for item in self.db.rows("SELECT repo_id, ci_systems_json, licenses_json FROM repository_signals")
        }
        include_paths = bool(self.config["privacy"]["include_absolute_paths"])
        quiet = int(self.config["report"]["quiet_after_days"])
        dormant = int(self.config["report"]["dormant_after_days"])
        maximum = self.config["history"].get("max_commits_per_repository")
        for row in rows:
            repo_id = int(row.pop("id"))
            row["remote_hosts"] = json.loads(row.pop("remote_hosts_json") or "[]")
            row["error"] = self._redact(row.get("error"))
            row["commits"] = int(row["commits"] or 0)
            row["authors"] = int(row["authors"] or 0)
            row["insertions"] = int(row["insertions"] or 0)
            row["deletions"] = int(row["deletions"] or 0)
            row["churn"] = row["insertions"] + row["deletions"]
            repo_counts = counts_by_repo.get(repo_id, [])
            row["top_author"] = author_names.get(repo_counts[0][0]) if repo_counts else None
            row["top_author_share"] = repo_counts[0][1] / row["commits"] if repo_counts and row["commits"] else None
            row["bus_factor_50"] = _bus_factor((value for _, value in repo_counts), 0.50)
            row["top_language"] = top_languages.get(repo_id)
            row["languages"] = languages_by_repo.get(repo_id, [])
            row["file_types"] = file_types_by_repo.get(repo_id, [])
            row.update(signals_by_repo.get(repo_id, {"ci_systems": [], "licenses": []}))
            row["code_lines"] = sum(item["code_lines"] for item in row["languages"])
            row["comment_lines"] = sum(item["comment_lines"] for item in row["languages"])
            denominator = row["code_lines"] + row["comment_lines"]
            row["comment_density"] = row["comment_lines"] / denominator if denominator else None
            status, days = _repo_status(row.get("last_commit"), self.today, quiet, dormant, row["commits"])
            row["activity_status"] = status
            row["days_since_last_commit"] = days
            warnings: list[str] = []
            if row["is_shallow"]:
                warnings.append("Shallow Clone: Historie wahrscheinlich unvollständig.")
            if row["is_partial"]:
                warnings.append("Partial Clone: fehlende Objekte werden nicht nachgeladen.")
            if row["is_bare"]:
                warnings.append("Bare Repository.")
            if row["status"] == "stale":
                warnings.append("Letzter Neu-Scan fehlgeschlagen; vorheriger Snapshot wird verwendet.")
            if row["status"] == "error":
                warnings.append("Repository konnte nicht eingelesen werden.")
            if maximum is not None and row["commits"] >= int(maximum):
                warnings.append(f"Analyse auf höchstens {maximum} Commits begrenzt.")
            row["warnings"] = warnings
            if not include_paths:
                row.pop("path", None)
            elif row.get("path"):
                row["path"] = str(row["path"])
        return rows

    def _code(self) -> dict[str, Any]:
        commit_types = self.db.rows(
            """
            SELECT message_type AS type, COUNT(*) AS commits,
                   SUM(insertions) AS insertions, SUM(deletions) AS deletions,
                   COUNT(DISTINCT author_key) AS authors
            FROM effective_commits GROUP BY message_type
            ORDER BY commits DESC, type
            """
        )
        total = sum(int(row["commits"]) for row in commit_types)
        for row in commit_types:
            row["label"] = TYPE_LABELS.get(str(row["type"]), str(row["type"]))
            row["share"] = int(row["commits"]) / total if total else 0.0
        _attach_repository_names(
            commit_types,
            self.db.rows(
                """
                SELECT DISTINCT c.message_type AS type, r.display_name AS repository
                FROM effective_commits c JOIN repositories r ON r.id = c.repo_id
                """
            ),
            ("type",),
        )

        size_rows = self.db.rows(
            """
            SELECT CASE
                WHEN stats_collected = 0 THEN 'Unbekannt'
                WHEN insertions + deletions = 0 THEN '0'
                WHEN insertions + deletions <= 10 THEN '1–10'
                WHEN insertions + deletions <= 50 THEN '11–50'
                WHEN insertions + deletions <= 200 THEN '51–200'
                WHEN insertions + deletions <= 1000 THEN '201–1.000'
                ELSE '>1.000' END AS bucket,
                COUNT(*) AS commits
            FROM effective_commits WHERE is_merge = 0 GROUP BY bucket
            """
        )
        bucket_order = ["0", "1–10", "11–50", "51–200", "201–1.000", ">1.000", "Unbekannt"]
        size_map = {row["bucket"]: int(row["commits"]) for row in size_rows}
        commit_sizes = [{"bucket": bucket, "commits": size_map.get(bucket, 0)} for bucket in bucket_order]
        size_case = """
            CASE
                WHEN c.stats_collected = 0 THEN 'Unbekannt'
                WHEN c.insertions + c.deletions = 0 THEN '0'
                WHEN c.insertions + c.deletions <= 10 THEN '1–10'
                WHEN c.insertions + c.deletions <= 50 THEN '11–50'
                WHEN c.insertions + c.deletions <= 200 THEN '51–200'
                WHEN c.insertions + c.deletions <= 1000 THEN '201–1.000'
                ELSE '>1.000' END
        """
        _attach_repository_names(
            commit_sizes,
            self.db.rows(
                f"""
                SELECT DISTINCT {size_case} AS bucket, r.display_name AS repository
                FROM effective_commits c JOIN repositories r ON r.id = c.repo_id
                WHERE c.is_merge = 0
                """
            ),
            ("bucket",),
        )
        churn_values = [
            int(row["churn"])
            for row in self.db.rows(
                """
                SELECT insertions + deletions AS churn FROM effective_commits
                WHERE is_merge = 0 AND stats_collected = 1
                """
            )
        ]
        tree_languages = self.db.rows(
            """
            SELECT t.language, SUM(t.files) AS files, SUM(t.bytes) AS bytes,
                   COUNT(DISTINCT t.repo_id) AS repositories
            FROM tree_languages t JOIN repositories r ON r.id = t.repo_id
            WHERE r.active = 1 AND r.status IN ('ready','stale')
            GROUP BY t.language ORDER BY bytes DESC, files DESC, t.language
            """
        )
        _attach_repository_names(
            tree_languages,
            self.db.rows(
                """
                SELECT DISTINCT t.language, r.display_name AS repository
                FROM tree_languages t JOIN repositories r ON r.id = t.repo_id
                WHERE r.active = 1 AND r.status IN ('ready','stale')
                """
            ),
            ("language",),
        )
        churn_languages = self.db.rows(
            """
            SELECT f.language, COUNT(*) AS touches,
                   COUNT(DISTINCT f.repo_id) AS repositories,
                   SUM(COALESCE(f.insertions, 0)) AS insertions,
                   SUM(COALESCE(f.deletions, 0)) AS deletions,
                   SUM(f.is_binary) AS binary_touches
            FROM effective_file_changes f GROUP BY f.language
            ORDER BY touches DESC, (SUM(COALESCE(f.insertions, 0)) + SUM(COALESCE(f.deletions, 0))) DESC
            """
        )
        _attach_repository_names(
            churn_languages,
            self.db.rows(
                """
                SELECT DISTINCT f.language, r.display_name AS repository
                FROM effective_file_changes f JOIN repositories r ON r.id = f.repo_id
                """
            ),
            ("language",),
        )
        for row in churn_languages:
            row["churn"] = int(row["insertions"] or 0) + int(row["deletions"] or 0)
        comment_languages = self.db.rows(
            """
            SELECT s.language, SUM(s.files) AS files, SUM(s.code_lines) AS code_lines,
                   SUM(s.comment_lines) AS comment_lines, SUM(s.blank_lines) AS blank_lines,
                   COUNT(DISTINCT s.repo_id) AS repositories
            FROM tree_comment_stats s JOIN repositories r ON r.id = s.repo_id
            WHERE s.kind = 'all' AND r.active = 1 AND r.status IN ('ready','stale')
            GROUP BY s.language ORDER BY comment_lines DESC, s.language
            """
        )
        _attach_repository_names(
            comment_languages,
            self.db.rows(
                """
                SELECT DISTINCT s.language, r.display_name AS repository
                FROM tree_comment_stats s JOIN repositories r ON r.id = s.repo_id
                WHERE s.kind = 'all' AND r.active = 1 AND r.status IN ('ready','stale')
                """
            ),
            ("language",),
        )
        comment_types = self.db.rows(
            """
            SELECT kind, SUM(comment_lines) AS comment_lines
            FROM tree_comment_stats s JOIN repositories r ON r.id = s.repo_id
            WHERE s.kind <> 'all' AND r.active = 1 AND r.status IN ('ready','stale')
            GROUP BY kind ORDER BY comment_lines DESC, kind
            """
        )
        _attach_repository_names(
            comment_types,
            self.db.rows(
                """
                SELECT DISTINCT s.kind, r.display_name AS repository
                FROM tree_comment_stats s JOIN repositories r ON r.id = s.repo_id
                WHERE s.kind <> 'all' AND r.active = 1 AND r.status IN ('ready','stale')
                """
            ),
            ("kind",),
        )
        for row in comment_languages:
            row["code_lines"] = int(row["code_lines"] or 0)
            row["comment_lines"] = int(row["comment_lines"] or 0)
            total_lines = row["code_lines"] + row["comment_lines"]
            row["comment_density"] = row["comment_lines"] / total_lines if total_lines else None
        hot_files = self.db.rows(
            """
            SELECT r.display_name AS repository, f.path, f.language,
                   COUNT(*) AS touches, COUNT(DISTINCT c.author_key) AS authors,
                   SUM(COALESCE(f.insertions, 0)) AS insertions,
                   SUM(COALESCE(f.deletions, 0)) AS deletions,
                   MAX(c.activity_at) AS last_activity
            FROM effective_file_changes f
            JOIN effective_commits c ON c.repo_id = f.repo_id AND c.hash = f.commit_hash
            JOIN repositories r ON r.id = f.repo_id
            GROUP BY f.repo_id, f.path
            ORDER BY touches DESC, (SUM(COALESCE(f.insertions, 0)) + SUM(COALESCE(f.deletions, 0))) DESC
            LIMIT 500
            """
        )
        for row in hot_files:
            row["churn"] = int(row["insertions"] or 0) + int(row["deletions"] or 0)
        directories = self.db.rows(
            """
            SELECT top_directory AS directory, COUNT(*) AS touches,
                   COUNT(DISTINCT repo_id) AS repositories,
                   SUM(COALESCE(insertions, 0)) AS insertions,
                   SUM(COALESCE(deletions, 0)) AS deletions
            FROM effective_file_changes GROUP BY top_directory
            ORDER BY touches DESC, (SUM(COALESCE(insertions, 0)) + SUM(COALESCE(deletions, 0))) DESC
            LIMIT 500
            """
        )
        _attach_repository_names(
            directories,
            self.db.rows(
                """
                SELECT DISTINCT f.top_directory AS directory, r.display_name AS repository
                FROM effective_file_changes f JOIN repositories r ON r.id = f.repo_id
                """
            ),
            ("directory",),
        )
        for row in directories:
            row["churn"] = int(row["insertions"] or 0) + int(row["deletions"] or 0)
        scopes = self.db.rows(
            """
            SELECT message_scope AS scope, COUNT(*) AS commits
            FROM effective_commits WHERE message_scope IS NOT NULL AND TRIM(message_scope) <> ''
            GROUP BY message_scope ORDER BY commits DESC, scope LIMIT 100
            """
        )
        _attach_repository_names(
            scopes,
            self.db.rows(
                """
                SELECT DISTINCT c.message_scope AS scope, r.display_name AS repository
                FROM effective_commits c JOIN repositories r ON r.id = c.repo_id
                WHERE c.message_scope IS NOT NULL AND TRIM(c.message_scope) <> ''
                """
            ),
            ("scope",),
        )
        aggregate = self.db.row(
            """
            SELECT COUNT(*) AS commits, SUM(CASE WHEN message_type <> 'other' THEN 1 ELSE 0 END) AS typed,
                   SUM(has_issue_reference) AS issue_refs, SUM(is_breaking) AS breaking,
                   SUM(stats_collected) AS stats_known
            FROM effective_commits
            """
        ) or {}
        commits = int(aggregate.get("commits") or 0)
        return {
            "commit_types": commit_types,
            "commit_sizes": commit_sizes,
            "top_scopes": scopes,
            "typed_commit_share": int(aggregate.get("typed") or 0) / commits if commits else None,
            "issue_reference_share": int(aggregate.get("issue_refs") or 0) / commits if commits else None,
            "breaking_changes": int(aggregate.get("breaking") or 0),
            "stats_known_share": int(aggregate.get("stats_known") or 0) / commits if commits else None,
            "churn_per_non_merge_commit": {
                "mean": statistics.mean(churn_values) if churn_values else None,
                "median": statistics.median(churn_values) if churn_values else None,
                "p90": _percentile(churn_values, 0.90),
                "p95": _percentile(churn_values, 0.95),
                "max": max(churn_values) if churn_values else None,
            },
            "tree_languages": tree_languages,
            "churn_languages": churn_languages,
            "comment_languages": comment_languages,
            "comment_types": comment_types,
            "hot_files": hot_files,
            "top_directories": directories,
        }

    def _releases(self) -> dict[str, Any]:
        rows = self.db.rows(
            """
            SELECT r.display_name AS repository, rel.name, rel.created_at, rel.object_hash
            FROM releases rel JOIN repositories r ON r.id = rel.repo_id
            WHERE r.active = 1 AND r.status IN ('ready','stale')
            ORDER BY CASE WHEN rel.created_at IS NULL THEN 1 ELSE 0 END, rel.created_at DESC, r.display_name
            LIMIT 500
            """
        )
        summary = self.db.row(
            """
            SELECT COUNT(*) AS tags,
                   SUM(CASE WHEN rel.created_at IS NOT NULL THEN 1 ELSE 0 END) AS dated_tags,
                   COUNT(DISTINCT rel.repo_id) AS repositories,
                   MIN(rel.created_at) AS first, MAX(rel.created_at) AS last
            FROM releases rel JOIN repositories r ON r.id = rel.repo_id
            WHERE r.active = 1 AND r.status IN ('ready','stale')
            """
        ) or {}
        return {"summary": summary, "rows": rows}

    def _summary(self, activity: dict[str, Any], contributors: dict[str, Any], repositories: list[dict[str, Any]], code: dict[str, Any], releases: dict[str, Any]) -> dict[str, Any]:
        commit = self.db.row(
            """
            SELECT COUNT(*) AS commits, COUNT(DISTINCT author_key) AS authors,
                   COUNT(DISTINCT committer_key) AS committers,
                   COUNT(DISTINCT activity_date) AS active_days,
                   MIN(activity_at) AS first_commit, MAX(activity_at) AS last_commit,
                   SUM(is_merge) AS merge_commits, SUM(author_is_bot) AS bot_commits,
                   SUM(insertions) AS additions, SUM(deletions) AS deletions,
                   SUM(files_changed) AS files_changed, SUM(binary_files) AS binary_files
            FROM effective_commits
            """
        ) or {}
        raw_bot = int(
            self.db.scalar(
                """
                SELECT COALESCE(SUM(c.author_is_bot), 0)
                FROM commits c JOIN repositories r ON r.id = c.repo_id
                WHERE r.active = 1 AND r.status IN ('ready','stale')
                """
            ) or 0
        )
        commits = int(commit.get("commits") or 0)
        merge_commits = int(commit.get("merge_commits") or 0)
        additions = int(commit.get("additions") or 0)
        deletions = int(commit.get("deletions") or 0)
        status_counts = defaultdict(int)
        for repo in repositories:
            status_counts[str(repo["activity_status"])] += 1
        last_date = commit.get("last_commit")
        days_since = None
        if last_date:
            days_since = (self.today - parse_iso_datetime(last_date).date()).days
        return {
            "repositories": len(repositories),
            "repositories_with_commits": sum(1 for repo in repositories if repo["commits"]),
            "active_repositories": status_counts["active"],
            "quiet_repositories": status_counts["quiet"],
            "dormant_repositories": status_counts["dormant"],
            "empty_repositories": status_counts["empty"],
            "commits": commits,
            "merge_commits": merge_commits,
            "non_merge_commits": commits - merge_commits,
            "merge_share": merge_commits / commits if commits else None,
            "authors": int(commit.get("authors") or 0),
            "committers": int(commit.get("committers") or 0),
            "bot_commits_in_effective_set": int(commit.get("bot_commits") or 0),
            "bot_commits_raw": raw_bot,
            "active_days": int(commit.get("active_days") or 0),
            "first_commit": commit.get("first_commit"),
            "last_commit": last_date,
            "days_since_last_commit": days_since,
            "additions": additions,
            "deletions": deletions,
            "churn": additions + deletions,
            "files_changed": int(commit.get("files_changed") or 0),
            "binary_files": int(commit.get("binary_files") or 0),
            "tree_files": sum(int(repo.get("tree_files") or 0) for repo in repositories),
            "tree_bytes": sum(int(repo.get("tree_bytes") or 0) for repo in repositories),
            "code_lines": sum(int(repo.get("code_lines") or 0) for repo in repositories),
            "comment_lines": sum(int(repo.get("comment_lines") or 0) for repo in repositories),
            "comment_density": (
                sum(int(repo.get("comment_lines") or 0) for repo in repositories)
                / (sum(int(repo.get("code_lines") or 0) for repo in repositories) + sum(int(repo.get("comment_lines") or 0) for repo in repositories))
                if sum(int(repo.get("code_lines") or 0) + int(repo.get("comment_lines") or 0) for repo in repositories) else None
            ),
            "local_branches": sum(int(repo.get("local_branches") or 0) for repo in repositories),
            "remote_branches": sum(int(repo.get("remote_branches") or 0) for repo in repositories),
            "tags": int(releases["summary"].get("tags") or 0),
            "failed_repositories": sum(1 for repo in repositories if repo["status"] == "stale") + int(
                self.db.scalar("SELECT COUNT(*) FROM repositories WHERE active = 1 AND status = 'error'") or 0
            ),
            "shallow_repositories": sum(int(repo["is_shallow"]) for repo in repositories),
            "partial_repositories": sum(int(repo["is_partial"]) for repo in repositories),
            "longest_streak_days": activity["longest_streak"]["days"],
            "longest_streak_start": activity["longest_streak"]["start"],
            "longest_streak_end": activity["longest_streak"]["end"],
            "longest_gap_days": activity["longest_gap"]["days_without_commits"],
            "average_commits_per_active_day": activity["average_commits_per_active_day"],
            "weekend_share": activity["weekend_share"],
            "outside_work_time_share": activity["outside_work_time_share"],
            "top_author_share": contributors["concentration"]["top_author_share"],
            "bus_factor_50": contributors["concentration"]["bus_factor_50"],
            "bus_factor_80": contributors["concentration"]["bus_factor_80"],
            "author_gini": contributors["concentration"]["gini"],
            "author_hhi": contributors["concentration"]["hhi"],
            "typed_commit_share": code["typed_commit_share"],
            "issue_reference_share": code["issue_reference_share"],
            "breaking_changes": code["breaking_changes"],
        }

    def _quality(self, repositories: list[dict[str, Any]], contributors: dict[str, Any]) -> dict[str, Any]:
        latest = self.db.row("SELECT * FROM runs ORDER BY id DESC LIMIT 1") or {}
        errors = self.db.rows(
            "SELECT path, stage, message, created_at FROM scan_errors WHERE run_id = ? ORDER BY id",
            (latest.get("id"),),
        ) if latest.get("id") else []
        if not self.include_paths:
            for error in errors:
                error["path"] = self._redact(error.get("path"))
                error["message"] = self._redact(error.get("message"))
        warnings: list[str] = []
        shallow = sum(int(repo["is_shallow"]) for repo in repositories)
        partial = sum(int(repo["is_partial"]) for repo in repositories)
        stale = sum(repo["status"] == "stale" for repo in repositories)
        if shallow:
            warnings.append(f"{shallow} Repository/Repositories sind shallow; die Historie kann unvollständig sein.")
        if partial:
            warnings.append(f"{partial} Partial Clone(s); GitAnalytics lädt keine fehlenden Objekte nach.")
        if stale:
            warnings.append(f"{stale} Repository/Repositories verwenden nach einem Scanfehler einen älteren Snapshot.")
        if errors:
            warnings.append(f"Im letzten Lauf wurden {len(errors)} Fehler oder Discovery-Hinweise protokolliert.")
        if not self.config["history"]["collect_churn"]:
            warnings.append("Churn- und Dateiverlaufsanalyse ist deaktiviert.")
        if not self.config["history"].get("collect_comments", True):
            warnings.append("Kommentar-Analyse ist deaktiviert.")
        elif not self.config["history"]["store_file_details"]:
            warnings.append("Dateidetails sind deaktiviert; Hotspots und Verzeichnisstatistiken fehlen.")
        if self.config["history"]["max_commits_per_repository"]:
            warnings.append("Die Commit-Historie ist pro Repository begrenzt; Langzeitkennzahlen sind abgeschnitten.")
        if self.config["history"]["deduplicate_global"]:
            warnings.append(
                "Globale SHA-Deduplizierung ist aktiv. Bei Spiegeln oder Forks werden gemeinsame Commits "
                "nur einem Repository zugeordnet; repositorybezogene Commit-Zahlen können dadurch null sein."
            )
        timezone_offsets = self.db.rows(
            """
            SELECT timezone_offset_minutes AS offset_minutes, COUNT(*) AS commits
            FROM effective_commits GROUP BY timezone_offset_minutes
            ORDER BY commits DESC, offset_minutes
            """
        )
        if self.config["history"].get("timezone") == "commit" and len(timezone_offsets) > 1:
            warnings.append(
                "Die ursprünglichen Commit-Zeitzonen werden beibehalten. Wochentag- und Stundenwerte "
                "beziehen sich dadurch auf verschiedene lokale Zeitzonen."
            )
        return {
            "warnings": warnings,
            "errors": errors,
            "repository_warnings": [
                {"repository": repo["name"], "warnings": repo["warnings"]}
                for repo in repositories if repo["warnings"]
            ],
            "identity_hints": contributors["identity_hints"],
            "timezone_offsets": timezone_offsets,
            "latest_run": {
                key: latest.get(key)
                for key in (
                    "id", "started_at", "finished_at", "repositories_found", "repositories_scanned",
                    "repositories_cached", "repositories_failed", "status",
                )
            },
        }

    @staticmethod
    def _insights(activity: dict[str, Any], contributors: dict[str, Any], repositories: list[dict[str, Any]], code: dict[str, Any]) -> dict[str, Any]:
        weekday = max(activity["weekdays"], key=lambda row: row["commits"], default=None)
        hour = max(activity["hours"], key=lambda row: row["commits"], default=None)
        author = contributors["rows"][0] if contributors["rows"] else None
        repository = repositories[0] if repositories else None
        language = code["tree_languages"][0] if code["tree_languages"] else None
        month = max(activity["monthly"], key=lambda row: row["commits"], default=None)
        day = activity["busiest_days"][0] if activity["busiest_days"] else None
        return {
            "top_weekday": weekday,
            "top_hour": hour,
            "top_author": author,
            "top_repository": repository,
            "top_tree_language": language,
            "peak_month": month,
            "busiest_day": day,
        }

    def build(self) -> dict[str, Any]:
        meta = self._meta()
        activity = self._activity()
        contributors, author_names = self._contributors()
        repositories = self._repositories(author_names)
        code = self._code()
        releases = self._releases()
        summary = self._summary(activity, contributors, repositories, code, releases)
        quality = self._quality(repositories, contributors)
        collaboration = build_collaboration(self.db, self.config, author_names)
        return {
            "meta": meta,
            "summary": summary,
            "insights": self._insights(activity, contributors, repositories, code),
            "activity": activity,
            "contributors": contributors,
            "repositories": repositories,
            "code": code,
            "releases": releases,
            "quality": quality,
            "collaboration": collaboration,
        }
