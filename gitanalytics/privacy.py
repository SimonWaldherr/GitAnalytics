"""Repository privacy classification with fail-closed defaults.

Classification is intentionally kept separate from discovery and reporting: the
scanner decides which repositories may enter the local database, while exports
can make an even narrower selection.  No rule ever changes a repository.
"""

from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Any

from .models import RepositoryLocation


CLASSIFICATIONS = frozenset({"exclude", "private", "public"})


def classification_candidates(location: RepositoryLocation) -> tuple[str, ...]:
    """Return useful, local-only names against which a configured glob may match."""
    path = location.path.expanduser().resolve()
    root = location.root.expanduser().resolve()
    try:
        relative = path.relative_to(root).as_posix()
    except ValueError:
        relative = path.name
    return (str(path), path.as_posix(), relative, location.display_name, path.name)


def classify_repository(location: RepositoryLocation, privacy: dict[str, Any]) -> str:
    """Classify a repository using the first matching rule, otherwise the default.

    The default is deliberately ``private``.  A repository therefore has to be
    explicitly opted into a public-profile export.
    """
    default = str(privacy.get("default_repository_classification", "private")).lower()
    candidates = classification_candidates(location)
    for rule in privacy.get("repository_rules", []):
        pattern = str(rule.get("match", ""))
        if pattern and any(fnmatch.fnmatchcase(candidate, pattern) for candidate in candidates):
            return str(rule["classification"]).lower()
    return default


def path_is_inside_repository(path: Path) -> bool:
    """Detect whether a target is within a normal worktree or a bare repository."""
    resolved = path.expanduser().resolve()
    for ancestor in (resolved, *resolved.parents):
        if (ancestor / ".git").exists():
            return True
        if (ancestor / "HEAD").is_file() and (ancestor / "objects").is_dir():
            return True
    return False
