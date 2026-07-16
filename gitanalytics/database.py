from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable, Sequence

from .models import CommentStats, CommitRecord, ImportResult, ReleaseRecord, RepositoryProbe, RepositorySignals, TreeFileType, TreeLanguage
from .util import iso_now


SCHEMA_VERSION = 5


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    roots_json TEXT NOT NULL,
    tool_version TEXT NOT NULL,
    config_json TEXT NOT NULL,
    repositories_found INTEGER NOT NULL DEFAULT 0,
    repositories_scanned INTEGER NOT NULL DEFAULT 0,
    repositories_cached INTEGER NOT NULL DEFAULT 0,
    repositories_failed INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'running'
);

CREATE TABLE IF NOT EXISTS repositories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_key TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    path TEXT NOT NULL,
    root_path TEXT NOT NULL,
    git_dir TEXT NOT NULL,
    common_dir TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'ready',
    error TEXT,
    is_bare INTEGER NOT NULL DEFAULT 0,
    is_shallow INTEGER NOT NULL DEFAULT 0,
    is_partial INTEGER NOT NULL DEFAULT 0,
    object_format TEXT NOT NULL DEFAULT 'sha1',
    head_branch TEXT,
    default_branch TEXT,
    head_hash TEXT,
    local_branches INTEGER NOT NULL DEFAULT 0,
    remote_branches INTEGER NOT NULL DEFAULT 0,
    tags INTEGER NOT NULL DEFAULT 0,
    remote_hosts_json TEXT NOT NULL DEFAULT '[]',
    fingerprint TEXT NOT NULL,
    scan_signature TEXT NOT NULL,
    commit_count INTEGER NOT NULL DEFAULT 0,
    file_change_count INTEGER NOT NULL DEFAULT 0,
    insertions INTEGER NOT NULL DEFAULT 0,
    deletions INTEGER NOT NULL DEFAULT 0,
    tree_files INTEGER NOT NULL DEFAULT 0,
    tree_bytes INTEGER NOT NULL DEFAULT 0,
    release_count INTEGER NOT NULL DEFAULT 0,
    first_activity TEXT,
    last_activity TEXT,
    last_scanned_at TEXT NOT NULL,
    last_run_id INTEGER,
    FOREIGN KEY(last_run_id) REFERENCES runs(id)
);

CREATE TABLE IF NOT EXISTS commits (
    repo_id INTEGER NOT NULL,
    hash TEXT NOT NULL,
    parent_count INTEGER NOT NULL,
    author_name_raw TEXT NOT NULL,
    author_email_raw TEXT NOT NULL,
    author_name_mailmap TEXT NOT NULL,
    author_email_mailmap TEXT NOT NULL,
    committer_name_raw TEXT NOT NULL,
    committer_email_raw TEXT NOT NULL,
    committer_name_mailmap TEXT NOT NULL,
    committer_email_mailmap TEXT NOT NULL,
    author_name TEXT NOT NULL,
    author_email TEXT NOT NULL,
    author_key TEXT NOT NULL,
    author_is_bot INTEGER NOT NULL,
    committer_name TEXT NOT NULL,
    committer_email TEXT NOT NULL,
    committer_key TEXT NOT NULL,
    committer_is_bot INTEGER NOT NULL,
    authored_at TEXT NOT NULL,
    committed_at TEXT NOT NULL,
    activity_at TEXT NOT NULL,
    activity_date TEXT NOT NULL,
    activity_year INTEGER NOT NULL,
    activity_month INTEGER NOT NULL,
    activity_weekday INTEGER NOT NULL,
    activity_hour INTEGER NOT NULL,
    timezone_offset_minutes INTEGER NOT NULL,
    subject TEXT,
    message_type TEXT NOT NULL,
    message_scope TEXT,
    is_breaking INTEGER NOT NULL,
    has_issue_reference INTEGER NOT NULL,
    is_merge INTEGER NOT NULL,
    is_trusted INTEGER NOT NULL DEFAULT 0,
    insertions INTEGER NOT NULL,
    deletions INTEGER NOT NULL,
    files_changed INTEGER NOT NULL,
    binary_files INTEGER NOT NULL,
    stats_collected INTEGER NOT NULL,
    PRIMARY KEY(repo_id, hash),
    FOREIGN KEY(repo_id) REFERENCES repositories(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS file_changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_id INTEGER NOT NULL,
    commit_hash TEXT NOT NULL,
    path TEXT NOT NULL,
    old_path TEXT,
    language TEXT NOT NULL,
    top_directory TEXT NOT NULL,
    insertions INTEGER,
    deletions INTEGER,
    is_binary INTEGER NOT NULL,
    FOREIGN KEY(repo_id, commit_hash) REFERENCES commits(repo_id, hash) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tree_languages (
    repo_id INTEGER NOT NULL,
    language TEXT NOT NULL,
    files INTEGER NOT NULL,
    bytes INTEGER NOT NULL,
    PRIMARY KEY(repo_id, language),
    FOREIGN KEY(repo_id) REFERENCES repositories(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tree_file_types (
    repo_id INTEGER NOT NULL,
    file_type TEXT NOT NULL,
    files INTEGER NOT NULL,
    bytes INTEGER NOT NULL,
    PRIMARY KEY(repo_id, file_type),
    FOREIGN KEY(repo_id) REFERENCES repositories(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tree_comment_stats (
    repo_id INTEGER NOT NULL,
    language TEXT NOT NULL,
    kind TEXT NOT NULL,
    files INTEGER NOT NULL DEFAULT 0,
    code_lines INTEGER NOT NULL DEFAULT 0,
    comment_lines INTEGER NOT NULL DEFAULT 0,
    blank_lines INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(repo_id, language, kind),
    FOREIGN KEY(repo_id) REFERENCES repositories(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS repository_signals (
    repo_id INTEGER PRIMARY KEY,
    ci_systems_json TEXT NOT NULL DEFAULT '[]',
    licenses_json TEXT NOT NULL DEFAULT '[]',
    FOREIGN KEY(repo_id) REFERENCES repositories(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS repository_privacy (
    repo_id INTEGER PRIMARY KEY,
    classification TEXT NOT NULL CHECK(classification IN ('exclude', 'private', 'public')),
    updated_at TEXT NOT NULL,
    FOREIGN KEY(repo_id) REFERENCES repositories(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS releases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    created_at TEXT,
    object_hash TEXT NOT NULL,
    FOREIGN KEY(repo_id) REFERENCES repositories(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS scan_errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    path TEXT NOT NULL,
    stage TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES runs(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_repositories_active ON repositories(active, status);
CREATE INDEX IF NOT EXISTS idx_commits_date ON commits(activity_date);
CREATE INDEX IF NOT EXISTS idx_commits_month ON commits(activity_year, activity_month);
CREATE INDEX IF NOT EXISTS idx_commits_author ON commits(author_key);
CREATE INDEX IF NOT EXISTS idx_commits_committer ON commits(committer_key);
CREATE INDEX IF NOT EXISTS idx_commits_repo_author ON commits(repo_id, author_key);
CREATE INDEX IF NOT EXISTS idx_commits_trusted ON commits(repo_id, is_trusted);
CREATE INDEX IF NOT EXISTS idx_file_changes_language ON file_changes(language);
CREATE INDEX IF NOT EXISTS idx_file_changes_path ON file_changes(repo_id, path);
CREATE INDEX IF NOT EXISTS idx_tree_comment_stats_repo ON tree_comment_stats(repo_id, language);
CREATE INDEX IF NOT EXISTS idx_tree_file_types_repo ON tree_file_types(repo_id, file_type);
CREATE INDEX IF NOT EXISTS idx_releases_date ON releases(created_at);

CREATE VIEW IF NOT EXISTS v_commits AS
SELECT r.display_name AS repository, c.*
FROM commits c JOIN repositories r ON r.id = c.repo_id
WHERE r.active = 1 AND r.status IN ('ready', 'stale');

CREATE VIEW IF NOT EXISTS v_file_changes AS
SELECT r.display_name AS repository, f.*
FROM file_changes f JOIN repositories r ON r.id = f.repo_id
WHERE r.active = 1 AND r.status IN ('ready', 'stale');

CREATE VIEW IF NOT EXISTS v_repository_summary AS
SELECT r.display_name AS repository, r.status, r.commit_count AS commits,
       r.file_change_count AS file_changes, r.insertions, r.deletions,
       r.tree_files, r.tree_bytes, r.release_count AS releases,
       r.first_activity, r.last_activity, r.local_branches, r.remote_branches, r.tags
FROM repositories r WHERE r.active = 1;

CREATE VIEW IF NOT EXISTS v_author_summary AS
SELECT c.author_key, MAX(c.author_name) AS author_name, MAX(c.author_email) AS author_email,
       MAX(c.author_is_bot) AS is_bot, COUNT(*) AS commits,
       COUNT(DISTINCT c.repo_id) AS repositories,
       COUNT(DISTINCT c.activity_date) AS active_days,
       SUM(c.insertions) AS insertions, SUM(c.deletions) AS deletions,
       MIN(c.activity_at) AS first_activity, MAX(c.activity_at) AS last_activity
FROM commits c JOIN repositories r ON r.id = c.repo_id
WHERE r.active = 1 AND r.status IN ('ready', 'stale')
GROUP BY c.author_key;
"""


COMMIT_INSERT = """
INSERT INTO commits (
    repo_id, hash, parent_count,
    author_name_raw, author_email_raw, author_name_mailmap, author_email_mailmap,
    committer_name_raw, committer_email_raw, committer_name_mailmap, committer_email_mailmap,
    author_name, author_email, author_key, author_is_bot,
    committer_name, committer_email, committer_key, committer_is_bot,
    authored_at, committed_at, activity_at, activity_date,
    activity_year, activity_month, activity_weekday, activity_hour, timezone_offset_minutes,
    subject, message_type, message_scope, is_breaking, has_issue_reference, is_merge, is_trusted,
    insertions, deletions, files_changed, binary_files, stats_collected
) VALUES (
    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
)
"""

FILE_CHANGE_INSERT = """
INSERT INTO file_changes (
    repo_id, commit_hash, path, old_path, language, top_directory,
    insertions, deletions, is_binary
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


class DatabaseError(RuntimeError):
    pass


class GitAnalyticsDatabase:
    def __init__(self, path: Path, *, readonly: bool = False) -> None:
        if sqlite3.sqlite_version_info < (3, 25, 0):
            raise DatabaseError(
                f"SQLite {sqlite3.sqlite_version} ist zu alt; GitAnalytics benötigt mindestens 3.25."
            )
        self.path = path.expanduser().resolve()
        self.readonly = readonly
        if readonly:
            if not self.path.is_file():
                raise DatabaseError(f"Datenbank nicht gefunden: {self.path}")
            self.connection = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA temp_store = MEMORY")
        if readonly:
            self._verify_readonly()
        else:
            self.connection.execute("PRAGMA journal_mode = DELETE")
            self.connection.execute("PRAGMA synchronous = NORMAL")
            self._initialize()

    def _verify_readonly(self) -> None:
        current = int(self.connection.execute("PRAGMA user_version").fetchone()[0])
        if current != SCHEMA_VERSION:
            raise DatabaseError(
                f"Datenbankversion {current} wird nicht unterstützt; erwartet {SCHEMA_VERSION}."
            )
        required = {
            "runs", "repositories", "commits", "file_changes", "tree_comment_stats",
            "tree_file_types", "repository_signals", "repository_privacy",
        }
        existing = {
            str(row[0])
            for row in self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        missing = sorted(required - existing)
        if missing:
            raise DatabaseError("Unvollständige GitAnalytics-Datenbank; fehlt: " + ", ".join(missing))

    def _initialize(self) -> None:
        current = int(self.connection.execute("PRAGMA user_version").fetchone()[0])
        if current not in {0, 1, 2, 3, 4, SCHEMA_VERSION}:
            raise DatabaseError(f"Datenbankversion {current} wird nicht unterstützt; erwartet {SCHEMA_VERSION}.")
        self.connection.executescript(SCHEMA)
        columns = {
            str(row["name"])
            for row in self.connection.execute("PRAGMA table_info(commits)").fetchall()
        }
        if "is_trusted" not in columns:
            self.connection.execute("ALTER TABLE commits ADD COLUMN is_trusted INTEGER NOT NULL DEFAULT 0")
        self.connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        self.connection.execute(
            "INSERT OR REPLACE INTO metadata(key, value) VALUES('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )
        self.connection.commit()

    def close(self) -> None:
        if not self.readonly:
            self.connection.commit()
        self.connection.close()

    def __enter__(self) -> "GitAnalyticsDatabase":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if not self.readonly:
            if exc_type is None:
                self.connection.commit()
            else:
                self.connection.rollback()
        self.close()

    def begin_run(self, roots: Sequence[Path], tool_version: str, config: dict) -> int:
        # A process killed between begin_run and finish_run leaves an auditable
        # running row. Close such rows before starting the next analysis.
        self.connection.execute(
            "UPDATE runs SET status = 'aborted', finished_at = COALESCE(finished_at, ?) "
            "WHERE status = 'running'",
            (iso_now(),),
        )
        cursor = self.connection.execute(
            """
            INSERT INTO runs(started_at, roots_json, tool_version, config_json)
            VALUES (?, ?, ?, ?)
            """,
            (
                iso_now(),
                json.dumps([str(root) for root in roots], ensure_ascii=False),
                tool_version,
                json.dumps(config, ensure_ascii=False, sort_keys=True),
            ),
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    def finish_run(
        self,
        run_id: int,
        *,
        found: int,
        scanned: int,
        cached: int,
        failed: int,
        status: str,
    ) -> None:
        self.connection.execute(
            """
            UPDATE runs SET finished_at = ?, repositories_found = ?, repositories_scanned = ?,
                repositories_cached = ?, repositories_failed = ?, status = ?
            WHERE id = ?
            """,
            (iso_now(), found, scanned, cached, failed, status, run_id),
        )
        if status != "aborted":
            self.connection.execute(
                "UPDATE repositories SET active = CASE WHEN last_run_id = ? THEN 1 ELSE 0 END",
                (run_id,),
            )
        self.connection.commit()

    def record_error(self, run_id: int, path: Path | str, stage: str, message: str) -> None:
        self.connection.execute(
            """
            INSERT INTO scan_errors(run_id, path, stage, message, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (run_id, str(path), stage, message.strip(), iso_now()),
        )
        self.connection.commit()

    def purge_repository_paths(self, paths: Sequence[Path]) -> int:
        """Remove snapshots explicitly classified as ``exclude``.

        This is intentionally stronger than merely hiding rows in a report:
        foreign-key cascades remove their commits, file details and signals
        from the local cache as well.
        """
        resolved = sorted({str(path.resolve()) for path in paths})
        if not resolved:
            return 0
        placeholders = ", ".join("?" for _ in resolved)
        cursor = self.connection.execute(
            f"DELETE FROM repositories WHERE path IN ({placeholders})", resolved
        )
        self.connection.execute(f"DELETE FROM scan_errors WHERE path IN ({placeholders})", resolved)
        self.connection.commit()
        return int(cursor.rowcount)

    def mark_path_error(
        self, run_id: int, path: Path, message: str, privacy_classification: str = "private"
    ) -> bool:
        """Preserve a previous snapshot when probing the same worktree now fails."""
        cursor = self.connection.execute(
            """
            UPDATE repositories SET active = 1, status = 'stale', error = ?,
                last_scanned_at = ?, last_run_id = ?
            WHERE path = ?
            """,
            (message.strip(), iso_now(), run_id, str(path.resolve())),
        )
        if cursor.rowcount == 1:
            row = self.connection.execute("SELECT id FROM repositories WHERE path = ?", (str(path.resolve()),)).fetchone()
            if row is not None:
                self._set_repository_classification(int(row["id"]), privacy_classification)
        self.connection.commit()
        return cursor.rowcount > 0

    def repository_cache_hit(self, probe: RepositoryProbe, signature: str) -> bool:
        row = self.connection.execute(
            "SELECT fingerprint, scan_signature, status FROM repositories WHERE repo_key = ?",
            (probe.repo_key,),
        ).fetchone()
        return bool(
            row
            and row["fingerprint"] == probe.fingerprint
            and row["scan_signature"] == signature
            and row["status"] == "ready"
        )

    def _upsert_repository(
        self,
        probe: RepositoryProbe,
        signature: str,
        run_id: int,
        status: str,
        error: str | None = None,
    ) -> int:
        self.connection.execute(
            """
            INSERT INTO repositories (
                repo_key, display_name, path, root_path, git_dir, common_dir,
                active, status, error, is_bare, is_shallow, is_partial, object_format,
                head_branch, default_branch, head_hash, local_branches, remote_branches,
                tags, remote_hosts_json, fingerprint, scan_signature, last_scanned_at, last_run_id
            ) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(repo_key) DO UPDATE SET
                display_name = excluded.display_name,
                path = excluded.path,
                root_path = excluded.root_path,
                git_dir = excluded.git_dir,
                common_dir = excluded.common_dir,
                active = 1,
                status = excluded.status,
                error = excluded.error,
                is_bare = excluded.is_bare,
                is_shallow = excluded.is_shallow,
                is_partial = excluded.is_partial,
                object_format = excluded.object_format,
                head_branch = excluded.head_branch,
                default_branch = excluded.default_branch,
                head_hash = excluded.head_hash,
                local_branches = excluded.local_branches,
                remote_branches = excluded.remote_branches,
                tags = excluded.tags,
                remote_hosts_json = excluded.remote_hosts_json,
                fingerprint = excluded.fingerprint,
                scan_signature = excluded.scan_signature,
                last_scanned_at = excluded.last_scanned_at,
                last_run_id = excluded.last_run_id
            """,
            (
                probe.repo_key,
                probe.display_name,
                str(probe.path),
                str(probe.root),
                str(probe.git_dir),
                str(probe.common_dir),
                status,
                error,
                int(probe.is_bare),
                int(probe.is_shallow),
                int(probe.is_partial),
                probe.object_format,
                probe.head_branch,
                probe.default_branch,
                probe.head_hash,
                probe.local_branches,
                probe.remote_branches,
                probe.tags,
                json.dumps(probe.remote_hosts, ensure_ascii=False),
                probe.fingerprint,
                signature,
                iso_now(),
                run_id,
            ),
        )
        row = self.connection.execute("SELECT id FROM repositories WHERE repo_key = ?", (probe.repo_key,)).fetchone()
        assert row is not None
        return int(row["id"])

    def _set_repository_classification(self, repo_id: int, classification: str) -> None:
        self.connection.execute(
            """
            INSERT INTO repository_privacy(repo_id, classification, updated_at) VALUES (?, ?, ?)
            ON CONFLICT(repo_id) DO UPDATE SET
                classification = excluded.classification, updated_at = excluded.updated_at
            """,
            (repo_id, classification, iso_now()),
        )

    def touch_cached_repository(
        self, probe: RepositoryProbe, signature: str, run_id: int, privacy_classification: str = "private"
    ) -> None:
        repo_id = self._upsert_repository(probe, signature, run_id, "ready")
        self._set_repository_classification(repo_id, privacy_classification)
        self.connection.commit()

    def touch_cached_path(
        self, path: Path, signature: str, run_id: int, privacy_classification: str = "private"
    ) -> bool:
        """Advance a locally indexed unchanged repository without starting Git."""
        cursor = self.connection.execute(
            """
            UPDATE repositories SET active = 1, last_scanned_at = ?, last_run_id = ?
            WHERE path = ? AND scan_signature = ? AND status = 'ready'
            """,
            (iso_now(), run_id, str(path.resolve()), signature),
        )
        if cursor.rowcount == 1:
            row = self.connection.execute("SELECT id FROM repositories WHERE path = ?", (str(path.resolve()),)).fetchone()
            if row is not None:
                self._set_repository_classification(int(row["id"]), privacy_classification)
        self.connection.commit()
        return cursor.rowcount == 1

    @staticmethod
    def _commit_values(repo_id: int, commit: CommitRecord) -> tuple:
        return (
            repo_id, commit.commit_hash, commit.parent_count,
            commit.author_name_raw, commit.author_email_raw,
            commit.author_name_mailmap, commit.author_email_mailmap,
            commit.committer_name_raw, commit.committer_email_raw,
            commit.committer_name_mailmap, commit.committer_email_mailmap,
            commit.author_name, commit.author_email, commit.author_key, int(commit.author_is_bot),
            commit.committer_name, commit.committer_email, commit.committer_key, int(commit.committer_is_bot),
            commit.authored_at, commit.committed_at, commit.activity_at, commit.activity_date,
            commit.activity_year, commit.activity_month, commit.activity_weekday, commit.activity_hour,
            commit.timezone_offset_minutes, commit.subject, commit.message_type, commit.message_scope,
            int(commit.is_breaking), int(commit.has_issue_reference), int(commit.is_merge),
            int(commit.is_trusted),
            commit.insertions, commit.deletions, commit.files_changed, commit.binary_files,
            int(commit.stats_collected),
        )

    def import_repository(
        self,
        probe: RepositoryProbe,
        signature: str,
        run_id: int,
        commits: Iterable[CommitRecord],
        tree_languages: Sequence[TreeLanguage],
        tree_file_types: Sequence[TreeFileType],
        comment_stats: Sequence[CommentStats],
        signals: RepositorySignals,
        tree_files: int,
        tree_bytes: int,
        releases: Sequence[ReleaseRecord],
        batch_size: int,
        privacy_classification: str = "private",
    ) -> ImportResult:
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            repo_id = self._upsert_repository(probe, signature, run_id, "scanning")
            self.connection.execute("DELETE FROM commits WHERE repo_id = ?", (repo_id,))
            self.connection.execute("DELETE FROM tree_languages WHERE repo_id = ?", (repo_id,))
            self.connection.execute("DELETE FROM tree_file_types WHERE repo_id = ?", (repo_id,))
            self.connection.execute("DELETE FROM tree_comment_stats WHERE repo_id = ?", (repo_id,))
            self.connection.execute("DELETE FROM repository_signals WHERE repo_id = ?", (repo_id,))
            self.connection.execute("DELETE FROM repository_privacy WHERE repo_id = ?", (repo_id,))
            self.connection.execute("DELETE FROM releases WHERE repo_id = ?", (repo_id,))

            commit_batch: list[tuple] = []
            change_batch: list[tuple] = []
            commit_count = file_change_count = insertions = deletions = 0
            first_activity: str | None = None
            last_activity: str | None = None

            def flush() -> None:
                if commit_batch:
                    self.connection.executemany(COMMIT_INSERT, commit_batch)
                    commit_batch.clear()
                if change_batch:
                    self.connection.executemany(FILE_CHANGE_INSERT, change_batch)
                    change_batch.clear()

            for commit in commits:
                commit_batch.append(self._commit_values(repo_id, commit))
                commit_count += 1
                file_change_count += commit.files_changed
                insertions += commit.insertions
                deletions += commit.deletions
                if first_activity is None or commit.activity_at < first_activity:
                    first_activity = commit.activity_at
                if last_activity is None or commit.activity_at > last_activity:
                    last_activity = commit.activity_at
                for change in commit.file_changes:
                    change_batch.append(
                        (
                            repo_id, commit.commit_hash, change.path, change.old_path,
                            change.language, change.top_directory, change.insertions,
                            change.deletions, int(change.is_binary),
                        )
                    )
                if len(commit_batch) >= batch_size or len(change_batch) >= batch_size * 10:
                    flush()
            flush()

            self.connection.executemany(
                "INSERT INTO tree_languages(repo_id, language, files, bytes) VALUES (?, ?, ?, ?)",
                [(repo_id, row.language, row.files, row.bytes) for row in tree_languages],
            )
            self.connection.execute(
                "INSERT INTO repository_signals(repo_id, ci_systems_json, licenses_json) VALUES (?, ?, ?)",
                (repo_id, json.dumps(signals.ci_systems), json.dumps(signals.licenses)),
            )
            self._set_repository_classification(repo_id, privacy_classification)
            self.connection.executemany(
                "INSERT INTO tree_file_types(repo_id, file_type, files, bytes) VALUES (?, ?, ?, ?)",
                [(repo_id, row.file_type, row.files, row.bytes) for row in tree_file_types],
            )
            self.connection.executemany(
                """
                INSERT INTO tree_comment_stats(
                    repo_id, language, kind, files, code_lines, comment_lines, blank_lines
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (repo_id, row.language, row.kind, row.files, row.code_lines, row.comment_lines, row.blank_lines)
                    for row in comment_stats
                ],
            )
            self.connection.executemany(
                "INSERT INTO releases(repo_id, name, created_at, object_hash) VALUES (?, ?, ?, ?)",
                [(repo_id, row.name, row.created_at, row.object_hash) for row in releases],
            )
            self.connection.execute(
                """
                UPDATE repositories SET status = 'ready', error = NULL,
                    commit_count = ?, file_change_count = ?, insertions = ?, deletions = ?,
                    tree_files = ?, tree_bytes = ?, release_count = ?,
                    first_activity = ?, last_activity = ?, last_scanned_at = ?, last_run_id = ?, active = 1
                WHERE id = ?
                """,
                (
                    commit_count, file_change_count, insertions, deletions,
                    tree_files, tree_bytes, len(releases), first_activity, last_activity,
                    iso_now(), run_id, repo_id,
                ),
            )
            self.connection.commit()
            return ImportResult(
                commits=commit_count,
                file_changes=file_change_count,
                insertions=insertions,
                deletions=deletions,
                tree_files=tree_files,
                tree_bytes=tree_bytes,
                releases=len(releases),
                first_activity=first_activity,
                last_activity=last_activity,
            )
        except Exception:
            self.connection.rollback()
            raise

    def mark_repository_error(
        self,
        probe: RepositoryProbe,
        signature: str,
        run_id: int,
        message: str,
        privacy_classification: str = "private",
    ) -> None:
        existing = self.connection.execute(
            "SELECT commit_count FROM repositories WHERE repo_key = ?",
            (probe.repo_key,),
        ).fetchone()
        status = "stale" if existing and int(existing["commit_count"] or 0) > 0 else "error"
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            repo_id = self._upsert_repository(probe, signature, run_id, status, message)
            self._set_repository_classification(repo_id, privacy_classification)
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def create_effective_views(self, config: dict) -> None:
        self.connection.executescript(
            "DROP VIEW IF EXISTS temp.effective_file_changes; DROP VIEW IF EXISTS temp.effective_commits;"
        )
        conditions = ["r.active = 1", "r.status IN ('ready', 'stale')"]
        if not config["history"]["include_bots"]:
            conditions.append("c.author_is_bot = 0")
        where = " AND ".join(conditions)
        if config["history"]["deduplicate_global"]:
            sql = f"""
            CREATE TEMP VIEW effective_commits AS
            SELECT * FROM (
                SELECT c.*, ROW_NUMBER() OVER (PARTITION BY c.hash ORDER BY c.repo_id) AS _global_rank
                FROM commits c JOIN repositories r ON r.id = c.repo_id
                WHERE {where}
            ) WHERE _global_rank = 1;
            """
        else:
            sql = f"""
            CREATE TEMP VIEW effective_commits AS
            SELECT c.*, 1 AS _global_rank
            FROM commits c JOIN repositories r ON r.id = c.repo_id
            WHERE {where};
            """
        sql += """
        CREATE TEMP VIEW effective_file_changes AS
        SELECT f.* FROM file_changes f
        JOIN effective_commits c ON c.repo_id = f.repo_id AND c.hash = f.commit_hash;
        """
        self.connection.executescript(sql)

    def optimize(self) -> None:
        self.connection.execute("ANALYZE")
        self.connection.commit()

    def rows(self, sql: str, parameters: Sequence[Any] = ()) -> list[dict[str, Any]]:
        return [dict(row) for row in self.connection.execute(sql, parameters).fetchall()]

    def row(self, sql: str, parameters: Sequence[Any] = ()) -> dict[str, Any] | None:
        value = self.connection.execute(sql, parameters).fetchone()
        return dict(value) if value is not None else None

    def scalar(self, sql: str, parameters: Sequence[Any] = ()) -> Any:
        value = self.connection.execute(sql, parameters).fetchone()
        return value[0] if value is not None else None
