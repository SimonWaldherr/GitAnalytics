from __future__ import annotations

import collections
import fnmatch
import os
from pathlib import Path
from typing import Iterable

from .models import DiscoveryIssue, DiscoveryResult, RepositoryLocation
from .util import is_within, relative_display


class DiscoveryError(RuntimeError):
    pass


def _looks_like_repository(path: Path) -> bool:
    marker = path / ".git"
    try:
        if marker.is_dir() or marker.is_file():
            return True
        return (
            (path / "HEAD").is_file()
            and (path / "objects").is_dir()
            and ((path / "refs").is_dir() or (path / "packed-refs").is_file())
        )
    except OSError:
        return False


def _ignored(path: Path, root: Path, patterns: list[str]) -> bool:
    try:
        relative = path.relative_to(root).as_posix()
    except ValueError:
        relative = path.name
    for pattern in patterns:
        normalized = str(pattern).replace("\\", "/")
        if "/" not in normalized and fnmatch.fnmatch(path.name, normalized):
            return True
        if fnmatch.fnmatch(relative, normalized) or fnmatch.fnmatch(f"/{relative}", normalized):
            return True
    return False


def discover_repositories(
    roots: Iterable[Path],
    config: dict,
    *,
    skip_paths: Iterable[Path] = (),
) -> DiscoveryResult:
    settings = config["discovery"]
    max_depth = settings.get("max_depth")
    include_hidden = bool(settings.get("include_hidden", False))
    follow_symlinks = bool(settings.get("follow_symlinks", False))
    nested = bool(settings.get("nested_repositories", False))
    ignore = [str(item) for item in settings.get("ignore", [])]
    skip = [item.expanduser().resolve() for item in skip_paths]

    resolved_roots: list[Path] = []
    for root in roots:
        candidate = root.expanduser().resolve()
        if not candidate.exists():
            raise DiscoveryError(f"Ordner existiert nicht: {candidate}")
        if not candidate.is_dir():
            raise DiscoveryError(f"Pfad ist kein Ordner: {candidate}")
        resolved_roots.append(candidate)

    result = DiscoveryResult()
    multiple_roots = len(resolved_roots) > 1
    seen_paths: set[str] = set()

    for root in resolved_roots:
        queue: collections.deque[tuple[Path, int]] = collections.deque([(root, 0)])
        seen_directories: set[tuple[int, int] | str] = set()

        while queue:
            current, depth = queue.popleft()
            if any(current == blocked or is_within(current, blocked) for blocked in skip):
                continue
            try:
                stat = current.stat(follow_symlinks=follow_symlinks)
                identity: tuple[int, int] | str = (
                    (stat.st_dev, stat.st_ino) if stat.st_ino else str(current.resolve())
                )
            except (OSError, PermissionError) as exc:
                result.issues.append(DiscoveryIssue(current, f"Ordner nicht lesbar: {exc}"))
                continue
            if identity in seen_directories:
                continue
            seen_directories.add(identity)

            found_repository = _looks_like_repository(current)
            if found_repository:
                key = str(current.resolve())
                if key not in seen_paths:
                    relative = relative_display(current, root)
                    display = f"{root.name}/{relative}" if multiple_roots else relative
                    result.repositories.append(
                        RepositoryLocation(path=current.resolve(), root=root, display_name=display)
                    )
                    seen_paths.add(key)
                if not nested:
                    continue

            if max_depth is not None and depth >= int(max_depth):
                continue
            try:
                entries = sorted(os.scandir(current), key=lambda entry: entry.name.casefold())
            except (OSError, PermissionError) as exc:
                result.issues.append(DiscoveryIssue(current, f"Ordner nicht lesbar: {exc}"))
                continue

            for entry in entries:
                if entry.name == ".git":
                    continue
                if not include_hidden and entry.name.startswith("."):
                    continue
                path = Path(entry.path)
                if _ignored(path, root, ignore):
                    continue
                try:
                    is_directory = entry.is_dir(follow_symlinks=follow_symlinks)
                    is_link = entry.is_symlink()
                except OSError as exc:
                    result.issues.append(DiscoveryIssue(path, str(exc)))
                    continue
                if not is_directory or (is_link and not follow_symlinks):
                    continue
                queue.append((path, depth + 1))

    result.repositories.sort(key=lambda item: item.display_name.casefold())
    return result


def assert_outputs_outside_repositories(
    repository_paths: Iterable[Path],
    output_paths: Iterable[Path],
) -> None:
    offending: list[str] = []
    repos = [path.resolve() for path in repository_paths]
    for output in output_paths:
        resolved = output.expanduser().resolve()
        for repo in repos:
            if is_within(resolved, repo):
                offending.append(f"{resolved} liegt in {repo}")
    if offending:
        raise DiscoveryError(
            "Ausgabe oder Cache läge innerhalb eines analysierten Repositories. "
            "Das widerspricht dem strikten Read-only-Modus. " + "; ".join(offending)
        )
