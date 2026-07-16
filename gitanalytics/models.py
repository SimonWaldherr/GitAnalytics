from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class RepositoryLocation:
    path: Path
    root: Path
    display_name: str


@dataclass(frozen=True)
class RepositoryProbe:
    path: Path
    root: Path
    display_name: str
    repo_key: str
    git_dir: Path
    common_dir: Path
    is_bare: bool
    is_shallow: bool
    is_partial: bool
    object_format: str
    head_branch: str | None
    default_branch: str | None
    head_hash: str | None
    local_branches: int
    remote_branches: int
    tags: int
    remote_hosts: tuple[str, ...]
    fingerprint: str


@dataclass(frozen=True)
class FileChange:
    path: str
    old_path: str | None
    language: str
    top_directory: str
    insertions: int | None
    deletions: int | None
    is_binary: bool


@dataclass(frozen=True)
class CommitRecord:
    commit_hash: str
    parent_count: int
    author_name_raw: str
    author_email_raw: str
    author_name_mailmap: str
    author_email_mailmap: str
    committer_name_raw: str
    committer_email_raw: str
    committer_name_mailmap: str
    committer_email_mailmap: str
    author_name: str
    author_email: str
    author_key: str
    author_is_bot: bool
    committer_name: str
    committer_email: str
    committer_key: str
    committer_is_bot: bool
    authored_at: str
    committed_at: str
    activity_at: str
    activity_date: str
    activity_year: int
    activity_month: int
    activity_weekday: int
    activity_hour: int
    timezone_offset_minutes: int
    subject: str | None
    message_type: str
    message_scope: str | None
    is_breaking: bool
    has_issue_reference: bool
    is_merge: bool
    is_trusted: bool
    insertions: int
    deletions: int
    files_changed: int
    binary_files: int
    stats_collected: bool
    file_changes: tuple[FileChange, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class TreeLanguage:
    language: str
    files: int
    bytes: int


@dataclass(frozen=True)
class TreeFileType:
    file_type: str
    files: int
    bytes: int


@dataclass(frozen=True)
class RepositorySignals:
    ci_systems: tuple[str, ...]
    licenses: tuple[str, ...]


@dataclass(frozen=True)
class CommentStats:
    """Comment-line metrics for the current HEAD, grouped by language and kind."""
    language: str
    kind: str
    files: int
    code_lines: int
    comment_lines: int
    blank_lines: int


@dataclass(frozen=True)
class ReleaseRecord:
    name: str
    created_at: str | None
    object_hash: str


@dataclass(frozen=True)
class ImportResult:
    commits: int
    file_changes: int
    insertions: int
    deletions: int
    tree_files: int
    tree_bytes: int
    releases: int
    first_activity: str | None
    last_activity: str | None


@dataclass(frozen=True)
class DiscoveryIssue:
    path: Path
    message: str


@dataclass
class DiscoveryResult:
    repositories: list[RepositoryLocation] = field(default_factory=list)
    issues: list[DiscoveryIssue] = field(default_factory=list)
