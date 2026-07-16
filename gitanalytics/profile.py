"""Fail-closed, reviewable public-profile package generation."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Sequence

from .database import GitAnalyticsDatabase
from .util import atomic_write_text, iso_now


class ProfileError(ValueError):
    pass


GITHUB_USER_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")


def validate_github_user(value: str) -> str:
    user = value.strip()
    if not GITHUB_USER_RE.fullmatch(user):
        raise ProfileError("--github-user muss ein gültiger GitHub-Benutzername sein.")
    return user


def _markdown(value: str) -> str:
    return " ".join(value.replace("|", "\\|").splitlines()).strip()


def public_profile_data(
    database: GitAnalyticsDatabase, include_repositories: Sequence[str] = ()
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Read only repositories explicitly approved for public use.

    This intentionally queries the normalized database rather than filtering a
    whole-report aggregate, so private repositories cannot affect a public
    profile's totals or language mix.
    """
    repositories = database.rows(
        """
        SELECT r.id, r.display_name AS name, r.commit_count AS commits,
               r.tree_files AS files, r.release_count AS releases, r.last_activity,
               COALESCE((
                   SELECT language FROM tree_languages t
                   WHERE t.repo_id = r.id
                   ORDER BY t.bytes DESC, t.files DESC, t.language LIMIT 1
               ), 'Unbekannt') AS top_language
        FROM repositories r
        JOIN repository_privacy p ON p.repo_id = r.id
        WHERE r.active = 1 AND r.status IN ('ready', 'stale') AND p.classification = 'public'
        ORDER BY r.display_name COLLATE NOCASE
        """
    )
    requested = {_markdown(name).casefold() for name in include_repositories if _markdown(name)}
    available = {str(row["name"]).casefold() for row in repositories}
    unavailable = sorted(requested - available)
    if unavailable:
        raise ProfileError(
            "Diese Repositories sind nicht als public freigegeben oder nicht verfügbar: "
            + ", ".join(unavailable)
        )
    if requested:
        repositories = [row for row in repositories if str(row["name"]).casefold() in requested]
    if not repositories:
        raise ProfileError(
            "Kein Repository ist für den Profil-Export freigegeben. "
            "Setze eine passende privacy.repository_rules-Regel auf classification: public."
        )

    placeholders = ", ".join("?" for _ in repositories)
    languages = database.rows(
        f"""
        SELECT language, SUM(files) AS files, SUM(bytes) AS bytes
        FROM tree_languages WHERE repo_id IN ({placeholders})
        GROUP BY language ORDER BY bytes DESC, files DESC, language LIMIT 12
        """,
        tuple(int(row["id"]) for row in repositories),
    )
    return repositories, languages


def render_profile_markdown(
    *, github_user: str, display_name: str | None, repositories: Sequence[dict[str, Any]],
    languages: Sequence[dict[str, Any]], policy: dict[str, bool],
) -> tuple[str, str]:
    user = _markdown(github_user)
    name = _markdown(display_name or github_user)
    language_text = ", ".join(_markdown(str(row["language"])) for row in languages) or "Noch keine Sprachen erkannt"

    readme = [
        f"# Hallo, ich bin {name}",
        "",
        f"Öffentliche Projekte und Technologien von [@{user}](https://github.com/{user}).",
        "",
    ]
    if policy["include_repository_names"]:
        columns = ["Repository"]
        if policy["include_languages"]:
            columns.append("Hauptsprache")
        if policy["include_exact_metrics"]:
            columns.extend(["Commits", "Dateien", "Releases"])
        if policy["include_last_activity_date"]:
            columns.append("Letzte Aktivität")
        readme.extend(["## Öffentliche Projekte", "", "| " + " | ".join(columns) + " |"])
        alignment = ["---"] * len(columns)
        if policy["include_exact_metrics"]:
            alignment[-3:] = ["---:", "---:", "---:"]
        readme.append("| " + " | ".join(alignment) + " |")
        for row in repositories:
            values = [_markdown(str(row["name"]))]
            if policy["include_languages"]:
                values.append(_markdown(str(row["top_language"])))
            if policy["include_exact_metrics"]:
                values.extend(str(int(row[key] or 0)) for key in ("commits", "files", "releases"))
            if policy["include_last_activity_date"]:
                values.append(_markdown(str(row["last_activity"] or "–")[:10]))
            readme.append("| " + " | ".join(values) + " |")
        readme.append("")
    if policy["include_languages"]:
        readme.extend(["## Technologie-Überblick", "", language_text, ""])
    readme.extend([
        "_Dieser Entwurf wurde lokal mit GitAnalytics erzeugt. Er enthält nur explizit freigegebene Repositories und wird nicht automatisch veröffentlicht._",
        "",
    ])
    data = [
        "# Profile package review data",
        "",
        f"Generated locally: {iso_now()}",
        f"GitHub handle supplied by user: @{user}",
        "",
        "## Included public data only",
        "",
        f"- Included public repositories: {len(repositories)}" if policy["include_repository_names"] else "- Repository names withheld by policy.",
        f"- Languages: {language_text}" if policy["include_languages"] else "- Languages withheld by policy.",
        "",
        "No private repository, local path, remote URL, contributor identity, email address, exact activity timestamp, or collaboration graph is included in this package.",
        "Review `README.md` and copy it manually into a GitHub profile repository if desired; GitAnalytics never pushes it.",
        "",
    ]
    return "\n".join(readme), "\n".join(data)


def write_profile_package(
    output: Path, *, github_user: str, display_name: str | None,
    repositories: Sequence[dict[str, Any]], languages: Sequence[dict[str, Any]], policy: dict[str, bool], force: bool = False,
) -> list[Path]:
    output = output.expanduser().resolve()
    github_user = validate_github_user(github_user)
    targets = [output / "README.md", output / "PROFILE_DATA.md"]
    existing = [path for path in targets if path.exists()]
    if existing and not force:
        raise ProfileError(
            "Profil-Dateien existieren bereits: " + ", ".join(str(path) for path in existing)
            + ". Mit --force nur diese Dateien überschreiben."
        )
    readme, review_data = render_profile_markdown(
        github_user=github_user, display_name=display_name,
        repositories=repositories, languages=languages, policy=policy,
    )
    atomic_write_text(targets[0], readme)
    atomic_write_text(targets[1], review_data)
    return targets
