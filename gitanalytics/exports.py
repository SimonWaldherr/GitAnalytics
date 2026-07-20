from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .util import atomic_write_json, atomic_write_text, human_int, human_percent, iso_now


def _csv_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return value


def write_rows_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                fieldnames.append(str(key))
    if not fieldnames:
        fieldnames = ["no_data"]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _csv_value(row.get(key)) for key in fieldnames})


def export_csv_bundle(directory: Path, report: dict[str, Any]) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    datasets: dict[str, Sequence[Mapping[str, Any]]] = {
        "repositories.csv": report.get("repositories", []),
        "contributors.csv": report.get("contributors", {}).get("rows", []),
        "collaboration_distances.csv": report.get("collaboration", {}).get("rows", []),
        "identity_hints.csv": report.get("contributors", {}).get("identity_hints", []),
        "activity_daily.csv": report.get("activity", {}).get("daily", []),
        "activity_monthly.csv": report.get("activity", {}).get("monthly", []),
        "activity_yearly.csv": report.get("activity", {}).get("yearly", []),
        "activity_weekdays.csv": report.get("activity", {}).get("weekdays", []),
        "activity_hours.csv": report.get("activity", {}).get("hours", []),
        "activity_dayparts.csv": report.get("activity", {}).get("dayparts", []),
        "activity_busiest_days.csv": report.get("activity", {}).get("busiest_days", []),
        "commit_types.csv": report.get("code", {}).get("commit_types", []),
        "commit_sizes.csv": report.get("code", {}).get("commit_sizes", []),
        "commit_scopes.csv": report.get("code", {}).get("top_scopes", []),
        "tree_languages.csv": report.get("code", {}).get("tree_languages", []),
        "churn_languages.csv": report.get("code", {}).get("churn_languages", []),
        "hot_files.csv": report.get("code", {}).get("hot_files", []),
        "top_directories.csv": report.get("code", {}).get("top_directories", []),
        "releases.csv": report.get("releases", {}).get("rows", []),
        "scan_errors.csv": report.get("quality", {}).get("errors", []),
        "timezone_offsets.csv": report.get("quality", {}).get("timezone_offsets", []),
    }
    output: list[Path] = []
    for filename, rows in datasets.items():
        target = directory / filename
        write_rows_csv(target, list(rows))
        output.append(target)
    write_rows_csv(directory / "summary.csv", [report.get("summary", {})])
    output.append(directory / "summary.csv")
    return output


def write_json_report(path: Path, report: dict[str, Any]) -> None:
    atomic_write_json(path, report)


def _markdown_cell(value: Any) -> str:
    """Render an untrusted report value safely inside a Markdown table cell."""
    return str(value if value is not None else "–").replace("|", "\\|").replace("\n", " ")


def write_markdown_report(path: Path, report: Mapping[str, Any]) -> None:
    """Write a compact, portable report suitable for a README, wiki, or ticket.

    This contains only existing report data; the HTML report remains the place for
    interactive filtering and full detail.
    """
    meta = report.get("meta", {})
    summary = report.get("summary", {})
    quality = report.get("quality", {})
    lines = [
        f"# {_markdown_cell(meta.get('title') or 'GitAnalytics-Bericht')}", "",
        f"Erzeugt: {_markdown_cell(meta.get('generated_at'))}", "", "## Überblick", "",
        "| Kennzahl | Wert |", "| --- | ---: |",
    ]
    metrics = (
        ("Repositories", human_int(summary.get("repositories"))),
        ("Repositories mit Commits", human_int(summary.get("repositories_with_commits"))),
        ("Commits", human_int(summary.get("commits"))),
        ("Autor:innen", human_int(summary.get("authors"))),
        ("Churn", human_int(summary.get("churn"))),
        ("Codezeilen (HEAD)", human_int(summary.get("code_lines"))),
        ("Kommentar-Dichte", human_percent(summary.get("comment_density"))),
        ("Letzter Commit", summary.get("last_commit") or "–"),
        ("Inaktive Repositories", human_int(summary.get("dormant_repositories"))),
    )
    lines.extend(f"| {label} | {_markdown_cell(value)} |" for label, value in metrics)
    repositories = list(report.get("repositories", []))
    if repositories:
        lines.extend(["", "## Repositories", "", "| Repository | Commits | Autor:innen | Letzter Commit | Status |", "| --- | ---: | ---: | --- | --- |"])
        for repository in repositories:
            lines.append("| {name} | {commits} | {authors} | {last} | {status} |".format(
                name=_markdown_cell(repository.get("name")), commits=human_int(repository.get("commits")),
                authors=human_int(repository.get("authors")), last=_markdown_cell(repository.get("last_commit") or "–"),
                status=_markdown_cell(repository.get("activity_status") or repository.get("status")),
            ))
    contributors = list(report.get("contributors", {}).get("rows", []))
    if contributors:
        lines.extend(["", "## Beitragende", "", "| Name | Commits | Repositories |", "| --- | ---: | ---: |"])
        for contributor in contributors[:10]:
            lines.append(f"| {_markdown_cell(contributor.get('name'))} | {human_int(contributor.get('commits'))} | {human_int(contributor.get('repositories'))} |")
    warnings = list(quality.get("warnings", []))
    if warnings:
        lines.extend(["", "## Hinweise", ""])
        lines.extend(f"- {_markdown_cell(warning)}" for warning in warnings)
    lines.extend(["", "_Git-Telemetrie ist kein Maß für individuelle Leistung oder Qualität._", ""])
    atomic_write_text(path, "\n".join(lines))


DATA_DICTIONARY = """# GitAnalytics data dictionary

GitAnalytics writes a self-contained HTML report, a JSON snapshot, normalized CSV files,
and a SQLite database. The repository data is read-only; only the selected output
folder is written.

## SQLite tables

- `runs`: one row per analysis run, including effective configuration and counters.
- `repositories`: repository metadata, cache fingerprint, scan state, aggregate counts.
- `commits`: normalized commit metadata and aggregate numstat values.
- `file_changes`: optional file-level numstat history.
- `tree_languages`: language/file/byte inventory for the current `HEAD` tree.
- `tree_file_types`: extension/file/byte inventory for the current `HEAD` tree.
- `tree_comment_stats`: language-level code, comment and blank line metrics.
- `repository_signals`: detected CI systems and license identifiers from versioned `HEAD` files.
- `repository_privacy`: explicit `exclude`, `private` or `public` classification used for profile exports.
- `releases`: Git tags and creator dates.
- `scan_errors`: discovery and scan diagnostics.

## SQLite views

- `v_commits`: commits of currently active, usable repository snapshots.
- `v_file_changes`: file changes of active snapshots.
- `v_repository_summary`: compact repository aggregates.
- `v_author_summary`: compact author aggregates.

The temporary views used by the report additionally apply bot exclusion and global
commit de-duplication. They exist only while GitAnalytics is running; the persistent views
show the stored active data without those run-time filters.

## Important fields

- `activity_at`: author or committer time, transformed according to configuration.
- `author_key`: stable hash after `.mailmap` and configured alias resolution.
- `message_type`: heuristic Conventional-Commit-like subject classification.
- `insertions` / `deletions`: Git numstat totals; binary files do not contribute lines.
- `tree_languages.bytes`: current Git blob size, not installed or build artifact size.
- `fingerprint`: hash of relevant refs and history-affecting repository metadata.
- `scan_signature`: hash of GitAnalytics version plus history/identity configuration.
- `is_trusted`: whether the commit is reachable from a remote-tracking or managed-source trusted ref; optional network analysis uses this by default.
- `repository_privacy.classification`: `private` is the fail-closed default; only `public` repositories can enter a profile package.

## Interpretation

Commit and churn counts are engineering telemetry, not individual performance
metrics. Squashing, merges, mirrored histories, generated code, bots, pair work,
time zones and repository topology materially affect the results.
"""


def write_data_dictionary(path: Path) -> None:
    atomic_write_text(path, DATA_DICTIONARY)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def write_manifest(path: Path, root: Path, files: Iterable[Path]) -> None:
    lines = [
        "GitAnalytics export manifest",
        f"generated_at={iso_now()}",
        "algorithm=sha256",
        "",
    ]
    for file in sorted({item.resolve() for item in files if item.exists()}):
        try:
            relative = file.relative_to(root.resolve()).as_posix()
        except ValueError:
            relative = file.name
        lines.append(f"{_sha256(file)}  {relative}")
    atomic_write_text(path, "\n".join(lines) + "\n")
