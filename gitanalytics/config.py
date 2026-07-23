from __future__ import annotations

import fnmatch
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .util import canonical_json, deep_merge, stable_hash


DEFAULT_CONFIG: dict[str, Any] = {
    "discovery": {
        "max_depth": None,
        "include_hidden": False,
        "follow_symlinks": False,
        "nested_repositories": False,
        "ignore": [
            ".git", "node_modules", "vendor", ".venv", "venv", "__pycache__",
            ".tox", ".mypy_cache", ".pytest_cache", ".idea", ".vscode",
            "target", "dist", "build",
        ],
    },
    "history": {
        "scope": "local",
        "refs": [],
        "main_branches": False,
        "since": None,
        "until": None,
        "first_parent": False,
        "include_merges": True,
        "include_bots": True,
        "deduplicate_global": False,
        "activity_timestamp": "author",
        "timezone": "commit",
        "respect_mailmap": True,
        "collect_churn": True,
        "detect_renames": True,
        "store_file_details": True,
        "store_subjects": False,
        "collect_tree": True,
        "collect_comments": True,
        "collect_releases": True,
        "collect_remote_hosts": True,
        "max_commits_per_repository": None,
    },
    "identity": {
        "aliases": [],
        "bot_patterns": [
            r"(?i)\[bot\]",
            r"(?i)(^|[\s._-])bot($|[\s@._-])",
            r"(?i)dependabot",
            r"(?i)renovate",
            r"(?i)github-actions",
        ],
    },
    "work_time": {
        "working_days": [0, 1, 2, 3, 4],
        "start_hour": 8,
        "end_hour": 18,
    },
    "privacy": {
        "include_absolute_paths": False,
        "show_emails": True,
        "anonymize_authors": False,
        # Private is deliberately the default.  Only an explicit public rule
        # permits a repository to appear in a generated profile package.
        "default_repository_classification": "private",
        "repository_rules": [],
    },
    "report": {
        "title": "GitAnalytics",
        "top_n": 15,
        "timeline_months": 60,
        "quiet_after_days": 90,
        "dormant_after_days": 365,
    },
    "profile": {
        # Public-profile packages are intentionally less detailed than the
        # local report.  Exact engineering telemetry is opt-in.
        "include_repository_names": True,
        "include_languages": True,
        "include_exact_metrics": False,
        "include_last_activity_date": False,
    },
    "network": {
        "enabled": False,
        "reference_names": [],
        "max_display_nodes": 500,
        "exclude_service_accounts": True,
        "ignored_account_patterns": [
            r"(?i)dependabot", r"(?i)renovate", r"(?i)github-actions", r"(?i)gitlab-ci",
            r"(?i)codex", r"(?i)claude", r"(?i)copilot", r"(?i)\[bot\]",
        ],
        "min_commits_per_author_repository": 2,
        "max_contribution_gap_days": 365,
        # A commit must be reachable from a remote-tracking ref before it is
        # used as graph evidence.  This excludes local-only test commits.
        "require_remote_reference": True,
    },
    "performance": {
        "git_timeout_seconds": 900,
        "sqlite_batch_size": 500,
    },
}


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class ResolvedIdentity:
    name: str
    email: str
    key: str
    is_bot: bool


class IdentityResolver:
    def __init__(self, config: dict[str, Any]) -> None:
        identity = config.get("identity", {})
        self.aliases = identity.get("aliases", [])
        self.bot_regexes: list[re.Pattern[str]] = []
        for pattern in identity.get("bot_patterns", []):
            try:
                self.bot_regexes.append(re.compile(str(pattern)))
            except re.error as exc:
                raise ConfigError(f"Ungültiges Bot-Muster {pattern!r}: {exc}") from exc

    def resolve(self, name: str, email: str) -> ResolvedIdentity:
        clean_name = (name or "Unbekannt").strip() or "Unbekannt"
        clean_email = (email or "").strip().lower()
        for alias in self.aliases:
            if not isinstance(alias, dict):
                continue
            email_patterns = [str(item).lower() for item in alias.get("match_emails", [])]
            name_patterns = [str(item).lower() for item in alias.get("match_names", [])]
            if any(fnmatch.fnmatch(clean_email, pattern) for pattern in email_patterns) or any(
                fnmatch.fnmatch(clean_name.casefold(), pattern.casefold()) for pattern in name_patterns
            ):
                clean_name = str(alias.get("name") or clean_name).strip() or clean_name
                clean_email = str(alias.get("email") or clean_email).strip().lower()
                break
        combined = f"{clean_name} <{clean_email}>"
        is_bot = any(regex.search(combined) for regex in self.bot_regexes)
        key_source = clean_email if clean_email else f"name:{clean_name.casefold()}"
        return ResolvedIdentity(
            name=clean_name,
            email=clean_email,
            key=stable_hash(key_source, length=24),
            is_bot=is_bot,
        )


def load_config(path: Path | None) -> dict[str, Any]:
    if path is None:
        config = deep_merge(DEFAULT_CONFIG, {})
    else:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ConfigError(f"Konfigurationsdatei nicht gefunden: {path}") from exc
        except json.JSONDecodeError as exc:
            raise ConfigError(
                f"Ungültiges JSON in {path}, Zeile {exc.lineno}, Spalte {exc.colno}: {exc.msg}"
            ) from exc
        if not isinstance(raw, dict):
            raise ConfigError("Die Konfiguration muss ein JSON-Objekt sein.")
        config = deep_merge(DEFAULT_CONFIG, raw)
    validate_config(config)
    return config


def validate_config(config: dict[str, Any]) -> None:
    discovery = config["discovery"]
    max_depth = discovery.get("max_depth")
    if max_depth is not None and (not isinstance(max_depth, int) or max_depth < 0):
        raise ConfigError("discovery.max_depth muss null oder eine nichtnegative Ganzzahl sein.")
    if not isinstance(discovery.get("ignore"), list):
        raise ConfigError("discovery.ignore muss eine Liste sein.")

    history = config["history"]
    if history.get("scope") not in {"current", "local", "all"}:
        raise ConfigError("history.scope muss current, local oder all sein.")
    if not isinstance(history.get("refs"), list):
        raise ConfigError("history.refs muss eine Liste sein.")
    if not isinstance(history.get("main_branches"), bool):
        raise ConfigError("history.main_branches muss true oder false sein.")
    if history.get("activity_timestamp") not in {"author", "committer"}:
        raise ConfigError("history.activity_timestamp muss author oder committer sein.")
    maximum = history.get("max_commits_per_repository")
    if maximum is not None and (not isinstance(maximum, int) or maximum < 1):
        raise ConfigError("history.max_commits_per_repository muss null oder mindestens 1 sein.")
    for key in (
        "first_parent", "include_merges", "include_bots", "deduplicate_global",
        "respect_mailmap", "collect_churn", "detect_renames", "store_file_details", "collect_comments",
        "store_subjects", "collect_tree", "collect_releases", "collect_remote_hosts",
    ):
        if not isinstance(history.get(key), bool):
            raise ConfigError(f"history.{key} muss true oder false sein.")

    timezone_name = str(history.get("timezone", "commit"))
    if timezone_name not in {"commit", "UTC", "utc"}:
        try:
            ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise ConfigError(f"Unbekannte Zeitzone: {timezone_name}") from exc

    work_time = config["work_time"]
    days = work_time.get("working_days")
    if not isinstance(days, list) or any(not isinstance(day, int) or day not in range(7) for day in days):
        raise ConfigError("work_time.working_days muss eine Liste mit Werten 0 bis 6 sein.")
    start, end = work_time.get("start_hour"), work_time.get("end_hour")
    if not isinstance(start, int) or not isinstance(end, int) or not 0 <= start < end <= 24:
        raise ConfigError("Arbeitszeit muss als gültiges Intervall innerhalb 0 bis 24 angegeben werden.")

    report = config["report"]
    for key in ("top_n", "timeline_months", "quiet_after_days", "dormant_after_days"):
        if not isinstance(report.get(key), int) or report[key] < 1:
            raise ConfigError(f"report.{key} muss mindestens 1 sein.")
    if report["quiet_after_days"] >= report["dormant_after_days"]:
        raise ConfigError("report.quiet_after_days muss kleiner als dormant_after_days sein.")

    profile = config.setdefault("profile", {})
    for key, value in DEFAULT_CONFIG["profile"].items():
        profile.setdefault(key, value)
    for key in DEFAULT_CONFIG["profile"]:
        if not isinstance(profile.get(key), bool):
            raise ConfigError(f"profile.{key} muss true oder false sein.")

    privacy = config["privacy"]
    privacy.setdefault("default_repository_classification", "private")
    privacy.setdefault("repository_rules", [])
    for key in (
        "include_absolute_paths", "show_emails", "anonymize_authors",
    ):
        if not isinstance(privacy.get(key), bool):
            raise ConfigError(f"privacy.{key} muss true oder false sein.")
    classifications = {"exclude", "private", "public"}
    default_classification = privacy.get("default_repository_classification")
    if default_classification not in classifications:
        raise ConfigError("privacy.default_repository_classification muss exclude, private oder public sein.")
    rules = privacy.get("repository_rules")
    if not isinstance(rules, list):
        raise ConfigError("privacy.repository_rules muss eine Liste sein.")
    for index, rule in enumerate(rules, start=1):
        if not isinstance(rule, dict):
            raise ConfigError(f"privacy.repository_rules[{index}] muss ein Objekt sein.")
        pattern = rule.get("match")
        classification = rule.get("classification")
        if not isinstance(pattern, str) or not pattern.strip():
            raise ConfigError(f"privacy.repository_rules[{index}].match muss ein nichtleeres Glob-Muster sein.")
        if classification not in classifications:
            raise ConfigError(
                f"privacy.repository_rules[{index}].classification muss exclude, private oder public sein."
            )

    performance = config["performance"]
    if not isinstance(performance.get("git_timeout_seconds"), int) or performance["git_timeout_seconds"] < 1:
        raise ConfigError("performance.git_timeout_seconds muss mindestens 1 sein.")
    if not isinstance(performance.get("sqlite_batch_size"), int) or performance["sqlite_batch_size"] < 1:
        raise ConfigError("performance.sqlite_batch_size muss mindestens 1 sein.")
    network = config.setdefault("network", {"enabled": False, "reference_names": [], "max_display_nodes": 500})
    network.setdefault("enabled", False)
    network.setdefault("reference_names", [])
    network.setdefault("exclude_service_accounts", True)
    network.setdefault("ignored_account_patterns", DEFAULT_CONFIG["network"]["ignored_account_patterns"])
    network.setdefault("min_commits_per_author_repository", 2)
    network.setdefault("max_contribution_gap_days", 365)
    network.setdefault("require_remote_reference", True)
    if not isinstance(network.get("enabled"), bool):
        raise ConfigError("network.enabled muss true oder false sein.")
    if not isinstance(network.get("reference_names"), list) or not all(isinstance(item, str) and item.strip() for item in network["reference_names"]):
        raise ConfigError("network.reference_names muss eine Liste von Namen sein.")
    if network["enabled"] and not network["reference_names"]:
        raise ConfigError("network.reference_names muss mindestens einen Namen enthalten, wenn network.enabled true ist.")
    if not isinstance(network.get("max_display_nodes"), int) or network["max_display_nodes"] < 1:
        raise ConfigError("network.max_display_nodes muss mindestens 1 sein.")
    if not isinstance(network.get("exclude_service_accounts"), bool):
        raise ConfigError("network.exclude_service_accounts muss true oder false sein.")
    if not isinstance(network.get("ignored_account_patterns"), list):
        raise ConfigError("network.ignored_account_patterns muss eine Liste sein.")
    for pattern in network["ignored_account_patterns"]:
        try:
            re.compile(str(pattern))
        except re.error as exc:
            raise ConfigError(f"Ungültiges Netzwerk-Account-Muster {pattern!r}: {exc}") from exc
    if not isinstance(network.get("min_commits_per_author_repository"), int) or network["min_commits_per_author_repository"] < 1:
        raise ConfigError("network.min_commits_per_author_repository muss mindestens 1 sein.")
    if not isinstance(network.get("max_contribution_gap_days"), int) or network["max_contribution_gap_days"] < 0:
        raise ConfigError("network.max_contribution_gap_days muss nichtnegativ sein.")
    if not isinstance(network.get("require_remote_reference"), bool):
        raise ConfigError("network.require_remote_reference muss true oder false sein.")
    IdentityResolver(config)


def effective_timezone(config: dict[str, Any]):
    value = str(config["history"].get("timezone", "commit"))
    if value == "commit":
        return None
    if value.lower() == "utc":
        return ZoneInfo("UTC")
    return ZoneInfo(value)


def scan_signature(config: dict[str, Any], tool_version: str) -> str:
    relevant = {
        "tool_version": tool_version,
        "history": config["history"],
        "identity": config["identity"],
        "network": {
            "enabled": config["network"]["enabled"],
            "require_remote_reference": config["network"]["require_remote_reference"],
        },
    }
    return stable_hash(canonical_json(relevant), length=32)


def write_example_config(path: Path) -> None:
    example = deep_merge(DEFAULT_CONFIG, {})
    example["identity"]["aliases"] = [
        {
            "name": "Max Mustermann",
            "email": "max@example.com",
            "match_emails": ["max@old-company.example", "*+max@users.noreply.github.com"],
            "match_names": ["M. Mustermann", "maxm"],
        }
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(example, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
