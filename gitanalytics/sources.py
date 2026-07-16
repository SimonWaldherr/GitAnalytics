"""Managed, explicit source-clone lifecycle for graph expansion.

Only clones recorded in the registry are ever synchronized.  Existing user
repositories are neither adopted nor fetched, and no command performs a pull
or checkout.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Sequence

from .privacy import path_is_inside_repository
from .util import atomic_write_json, iso_now, is_within, slugify, stable_hash


REGISTRY_NAME = ".gitanalytics-sources.json"
REGISTRY_VERSION = 1


class SourceError(ValueError):
    pass


def registry_path(destination: Path) -> Path:
    return destination.expanduser().resolve() / REGISTRY_NAME


def _environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment.update({"GIT_TERMINAL_PROMPT": "0", "GIT_PAGER": "cat", "LC_ALL": "C"})
    return environment


def _load_registry(destination: Path) -> dict[str, Any]:
    path = registry_path(destination)
    if not path.is_file():
        return {"version": REGISTRY_VERSION, "sources": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SourceError(f"Ungültiges Quellenregister: {path}") from exc
    if not isinstance(data, dict) or data.get("version") != REGISTRY_VERSION or not isinstance(data.get("sources"), list):
        raise SourceError(f"Nicht unterstütztes Quellenregister: {path}")
    return data


def _write_registry(destination: Path, registry: dict[str, Any]) -> None:
    registry["version"] = REGISTRY_VERSION
    registry["updated_at"] = iso_now()
    atomic_write_json(registry_path(destination), registry)


def _run(command: Sequence[str], timeout: int) -> tuple[bool, str]:
    try:
        completed = subprocess.run(
            command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            encoding="utf-8", errors="replace", check=False, timeout=timeout, env=_environment(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    return completed.returncode == 0, completed.stdout.strip()


def _bare_repository(path: Path) -> bool:
    return path.is_dir() and (path / "HEAD").is_file() and (path / "objects").is_dir() and (path / "config").is_file()


def _managed_target(destination: Path, relative_target: str) -> Path:
    candidate = (destination / relative_target).resolve()
    if not is_within(candidate, destination) or not _bare_repository(candidate):
        raise SourceError(f"Registriertes Clone-Ziel ist ungültig oder nicht mehr tool-eigen: {relative_target}")
    return candidate


def _trusted_refspec_fetch(
    git: str, target: Path, timeout: int, depth: int | None = None
) -> tuple[bool, str]:
    """Fetch source refs into a separate trusted namespace in the managed clone."""
    command = [git, "-C", str(target), "fetch", "--prune"]
    if depth is not None:
        command.extend(["--depth", str(depth)])
    command.extend([
        "origin", "+refs/heads/*:refs/gitanalytics/trusted/heads/*",
        "+refs/tags/*:refs/gitanalytics/trusted/tags/*",
    ])
    return _run(command, timeout)


def fetch_sources(
    destination: Path, sources: Sequence[str], *, git: str | None = None,
    depth: int | None = None, timeout: int = 900,
) -> list[dict[str, str]]:
    """Clone user-supplied URLs into a dedicated registry-managed folder."""
    destination = destination.expanduser().resolve()
    if path_is_inside_repository(destination):
        raise SourceError("Das Clone-Ziel darf nicht innerhalb eines bestehenden Git-Repositories liegen.")
    if depth is not None and depth < 1:
        raise SourceError("--depth muss mindestens 1 sein.")
    if timeout < 1:
        raise SourceError("--timeout muss mindestens 1 sein.")
    destination.mkdir(parents=True, exist_ok=True)
    executable = git or shutil.which("git") or "git"
    registry = _load_registry(destination)
    entries: list[dict[str, Any]] = registry["sources"]
    known_sources = {str(entry.get("source", "")): entry for entry in entries if isinstance(entry, dict)}
    results: list[dict[str, str]] = []
    for source in sources:
        source = str(source).strip()
        if not source:
            results.append({"source": source, "status": "error", "detail": "Leere Git-URL."})
            continue
        existing = known_sources.get(source)
        if existing is not None:
            results.append({"source": source, "status": "registered", "detail": str(existing.get("target", ""))})
            continue
        name = source.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git").replace(":", "-")
        relative_target = f"{slugify(name, 'repository')}-{stable_hash(source, 8)}.git"
        target = destination / relative_target
        if target.exists():
            results.append({"source": source, "status": "unmanaged", "detail": str(target)})
            continue
        command = [executable, "clone", "--bare"]
        if depth is not None:
            command.extend(["--depth", str(depth)])
        command.extend([source, str(target)])
        ok, detail = _run(command, timeout)
        if not ok:
            results.append({"source": source, "status": "error", "detail": detail})
            continue
        trusted, trusted_detail = _trusted_refspec_fetch(executable, target, timeout, depth)
        entry = {
            "source": source,
            "target": relative_target,
            "added_at": iso_now(),
            "depth": depth,
            "trusted_refs": trusted,
        }
        entries.append(entry)
        known_sources[source] = entry
        results.append({
            "source": source, "status": "cloned", "detail": str(target),
            "trusted": "yes" if trusted else "no",
            "trusted_detail": trusted_detail,
        })
        _write_registry(destination, registry)
    _write_registry(destination, registry)
    return results


def sync_sources(destination: Path, *, git: str | None = None, timeout: int = 900) -> list[dict[str, str]]:
    """Fetch only clones already registered as GitAnalytics-managed sources."""
    destination = destination.expanduser().resolve()
    if not registry_path(destination).is_file():
        raise SourceError(f"Kein GitAnalytics-Quellenregister in {destination}.")
    if timeout < 1:
        raise SourceError("--timeout muss mindestens 1 sein.")
    registry = _load_registry(destination)
    executable = git or shutil.which("git") or "git"
    results: list[dict[str, str]] = []
    for entry in registry["sources"]:
        if not isinstance(entry, dict):
            continue
        source = str(entry.get("source", ""))
        target_name = str(entry.get("target", ""))
        try:
            target = _managed_target(destination, target_name)
        except SourceError as exc:
            results.append({"source": source, "status": "refused", "detail": str(exc)})
            continue
        depth = entry.get("depth")
        depth = int(depth) if isinstance(depth, int) and depth > 0 else None
        fetch_command = [executable, "-C", str(target), "fetch", "--prune", "--tags"]
        if depth is not None:
            fetch_command.extend(["--depth", str(depth)])
        fetch_command.append("origin")
        fetched, fetch_detail = _run(fetch_command, timeout)
        if not fetched:
            results.append({"source": source, "status": "error", "detail": fetch_detail})
            continue
        trusted, trusted_detail = _trusted_refspec_fetch(executable, target, timeout, depth)
        entry["last_synced_at"] = iso_now()
        entry["trusted_refs"] = trusted
        results.append({
            "source": source, "status": "synced", "detail": str(target),
            "trusted": "yes" if trusted else "no", "trusted_detail": trusted_detail,
        })
    _write_registry(destination, registry)
    return results
