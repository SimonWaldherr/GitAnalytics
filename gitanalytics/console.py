from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, TextIO

from .util import format_console_table, human_int, human_percent


class Console:
    def __init__(self, *, quiet: bool = False, stream: TextIO | None = None) -> None:
        self.quiet = quiet
        self.stream = stream or sys.stderr

    def info(self, message: str) -> None:
        if not self.quiet:
            print(message, file=self.stream)

    def warning(self, message: str) -> None:
        print(f"Warnung: {message}", file=self.stream)

    def error(self, message: str) -> None:
        print(f"Fehler: {message}", file=self.stream)


def print_summary(report: dict[str, Any], output: Path | None = None, *, stream: TextIO | None = None) -> None:
    stream = stream or sys.stdout
    summary = report["summary"]
    insights = report["insights"]
    print("GitAnalytics", file=stream)
    print("=====", file=stream)
    print(
        f"{human_int(summary['repositories'])} Repositories · "
        f"{human_int(summary['commits'])} Commits · "
        f"{human_int(summary['authors'])} Autoren · "
        f"{human_int(summary['active_days'])} aktive Tage",
        file=stream,
    )
    print(
        f"Zeitraum: {summary.get('first_commit') or '–'} bis {summary.get('last_commit') or '–'}",
        file=stream,
    )
    print(
        f"Churn: {human_int(summary['churn'])} "
        f"(+{human_int(summary['additions'])} / −{human_int(summary['deletions'])})",
        file=stream,
    )

    rows = []
    for row in report["repositories"][:10]:
        rows.append(
            (
                row["name"], human_int(row["commits"]), human_int(row["authors"]),
                row.get("top_language") or "–", row.get("activity_status") or "–",
            )
        )
    if rows:
        print("\nTop-Repositories", file=stream)
        print(format_console_table(("Repository", "Commits", "Autoren", "Sprache", "Status"), rows), file=stream)

    author_rows = []
    for row in report["contributors"]["rows"][:10]:
        author_rows.append(
            (
                row["name"], human_int(row["commits"]), human_percent(row.get("share")),
                human_int(row["repositories"]), human_int(row["active_days"]),
            )
        )
    if author_rows:
        print("\nTop-Autoren", file=stream)
        print(format_console_table(("Autor", "Commits", "Anteil", "Repos", "Aktive Tage"), author_rows), file=stream)

    top_weekday = insights.get("top_weekday")
    top_hour = insights.get("top_hour")
    if top_weekday or top_hour:
        parts = []
        if top_weekday:
            parts.append(f"stärkster Wochentag: {top_weekday['weekday']} ({human_int(top_weekday['commits'])})")
        if top_hour:
            parts.append(f"stärkste Stunde: {int(top_hour['hour']):02d}:00 ({human_int(top_hour['commits'])})")
        print("\n" + " · ".join(parts), file=stream)

    warnings = report.get("quality", {}).get("warnings", [])
    if warnings:
        print(f"\nDatenhinweise: {len(warnings)}; Details im Bericht.", file=stream)
    if output is not None:
        print(f"\nBericht: {output / 'index.html'}", file=stream)
        print(f"SQLite:  {output / 'data' / 'gitanalytics.sqlite3'}", file=stream)
