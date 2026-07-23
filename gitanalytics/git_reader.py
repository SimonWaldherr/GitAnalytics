from __future__ import annotations

import datetime as dt
import hashlib
import os
import re
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Iterator, Sequence
from urllib.parse import urlparse

from .config import IdentityResolver, effective_timezone
from .languages import classify_path, file_type, top_directory
from .models import (
    CommitRecord,
    FileChange,
    ReleaseRecord,
    RepositoryLocation,
    RepositoryProbe,
    CommentStats,
    TreeLanguage,
    TreeFileType,
    RepositorySignals,
)
from .util import hash_file, parse_iso_datetime, sanitize_text


RECORD_SEPARATOR = b"\x1e"
FIELD_SEPARATOR = "\x1f"
CONVENTIONAL_RE = re.compile(
    r"^(?P<type>[A-Za-z][A-Za-z0-9_-]*)(?:\((?P<scope>[^)]+)\))?(?P<breaking>!)?:\s+"
)
ISSUE_RE = re.compile(r"(?:#\d+\b|\b[A-Z][A-Z0-9]+-\d+\b)")
KNOWN_TYPES = {
    "feat", "fix", "docs", "style", "refactor", "perf", "test", "build",
    "ci", "chore", "revert", "merge", "release", "security", "deps", "init",
}

LINE_COMMENT_PREFIXES = {
    "Python": ("#",), "Cython": ("#",), "Shell": ("#",), "Ruby": ("#",),
    "Perl": ("#",), "R": ("#",), "YAML": ("#",), "TOML": ("#",),
    "Config": ("#", ";"), "INI": ("#", ";"), "PowerShell": ("#",),
    "SQL": ("--",), "Lua": ("--",), "Haskell": ("--",),
    "JavaScript": ("//",), "JavaScript/React": ("//",), "TypeScript": ("//",),
    "TypeScript/React": ("//",), "Java": ("//",), "Kotlin": ("//",),
    "Go": ("//",), "Rust": ("//",), "C": ("//",), "C++": ("//",),
    "C#": ("//",), "PHP": ("//",), "Swift": ("//",), "Scala": ("//",),
    "Dart": ("//",), "CSS": (), "SCSS": ("//",), "Sass": ("//",),
}
BLOCK_COMMENT_LANGUAGES = {
    "JavaScript", "JavaScript/React", "TypeScript", "TypeScript/React", "Java", "Kotlin",
    "Go", "Rust", "C", "C++", "C#", "PHP", "Swift", "Scala", "Dart", "CSS", "SCSS",
    "Sass", "SQL", "HTML", "XML", "Vue", "Svelte", "Markdown",
}
CI_PATHS = {
    ".gitlab-ci.yml": "GitLab CI", "Jenkinsfile": "Jenkins", ".circleci/config.yml": "CircleCI",
    "azure-pipelines.yml": "Azure Pipelines", ".travis.yml": "Travis CI", "bitbucket-pipelines.yml": "Bitbucket Pipelines",
}

def _license_name(text: str, path: str) -> str:
    upper = text.upper()
    if "MIT LICENSE" in upper:
        return "MIT"
    if "APACHE LICENSE" in upper or "APACHE SOFTWARE FOUNDATION" in upper:
        return "Apache-2.0"
    if "GNU GENERAL PUBLIC LICENSE" in upper:
        return "GPL"
    if "BSD 3-CLAUSE" in upper or "BSD 2-CLAUSE" in upper:
        return "BSD"
    if "MOZILLA PUBLIC LICENSE" in upper:
        return "MPL"
    if "CREATIVE COMMONS" in upper:
        return "Creative Commons"
    return Path(path).name


class GitCommandError(RuntimeError):
    def __init__(self, repository: Path, command: Sequence[str], message: str, returncode: int | None = None):
        self.repository = repository
        self.command = tuple(command)
        self.returncode = returncode
        super().__init__(message.strip() or "Unbekannter Git-Fehler")


class GitReader:
    def __init__(self, git_executable: str | None = None, timeout: int = 900) -> None:
        self.git = git_executable or shutil.which("git") or "git"
        self.timeout = timeout

    @staticmethod
    def environment() -> dict[str, str]:
        env = os.environ.copy()
        env.update(
            {
                "GIT_OPTIONAL_LOCKS": "0",
                "GIT_TERMINAL_PROMPT": "0",
                "GIT_PAGER": "cat",
                "GIT_NO_REPLACE_OBJECTS": "1",
                "GIT_NO_LAZY_FETCH": "1",
                "LC_ALL": "C",
            }
        )
        return env

    def command(self, repository: Path, args: Sequence[str]) -> list[str]:
        return [
            self.git,
            "--no-pager",
            "-c", "core.quotepath=false",
            "-c", "color.ui=false",
            "-c", "i18n.logOutputEncoding=UTF-8",
            "-c", "protocol.allow=never",
            "-c", "maintenance.auto=false",
            "-c", "gc.auto=0",
            "-c", "core.fsmonitor=false",
            "-c", "fetch.writeCommitGraph=false",
            "-C", str(repository),
            *args,
        ]

    def run_bytes(
        self,
        repository: Path,
        args: Sequence[str],
        *,
        check: bool = True,
        timeout: int | None = None,
    ) -> bytes:
        command = self.command(repository, args)
        try:
            completed = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=self.environment(),
                timeout=timeout or self.timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise GitCommandError(repository, command, "Zeitüberschreitung bei Git.") from exc
        except OSError as exc:
            raise GitCommandError(repository, command, f"Git konnte nicht gestartet werden: {exc}") from exc
        if check and completed.returncode != 0:
            message = completed.stderr.decode("utf-8", errors="replace")
            raise GitCommandError(repository, command, message, completed.returncode)
        return completed.stdout

    def run_text(
        self,
        repository: Path,
        args: Sequence[str],
        *,
        check: bool = True,
        timeout: int | None = None,
    ) -> str:
        return self.run_bytes(repository, args, check=check, timeout=timeout).decode(
            "utf-8", errors="replace"
        )

    def optional_text(self, repository: Path, args: Sequence[str], timeout: int | None = None) -> str | None:
        output = self.run_text(repository, args, check=False, timeout=timeout).strip()
        return output or None

    def iter_delimited(
        self,
        repository: Path,
        args: Sequence[str],
        delimiter: bytes,
        *,
        timeout: int | None = None,
        chunk_size: int = 1024 * 1024,
    ) -> Iterator[bytes]:
        command = self.command(repository, args)
        killed = threading.Event()
        with tempfile.TemporaryFile() as stderr_file:
            try:
                process = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=stderr_file,
                    env=self.environment(),
                )
            except OSError as exc:
                raise GitCommandError(repository, command, f"Git konnte nicht gestartet werden: {exc}") from exc

            def kill_process() -> None:
                killed.set()
                try:
                    process.kill()
                except OSError:
                    pass

            timer = threading.Timer(timeout or self.timeout, kill_process)
            timer.daemon = True
            timer.start()
            buffer = b""
            try:
                assert process.stdout is not None
                while True:
                    block = process.stdout.read(chunk_size)
                    if not block:
                        break
                    buffer += block
                    while True:
                        index = buffer.find(delimiter)
                        if index < 0:
                            break
                        yield buffer[:index]
                        buffer = buffer[index + len(delimiter):]
                if buffer:
                    yield buffer
                returncode = process.wait()
            finally:
                timer.cancel()
                if process.poll() is None:
                    process.kill()
                    process.wait()

            stderr_file.seek(0)
            message = stderr_file.read().decode("utf-8", errors="replace")
            if killed.is_set():
                raise GitCommandError(repository, command, "Zeitüberschreitung bei Git.")
            if returncode != 0:
                raise GitCommandError(repository, command, message, returncode)

    @staticmethod
    def _resolve_git_path(repository: Path, raw: str, git_dir: Path | None = None) -> Path:
        candidate = Path(raw)
        if candidate.is_absolute():
            return candidate.resolve()
        from_repo = repository / candidate
        if from_repo.exists():
            return from_repo.resolve()
        if git_dir is not None:
            from_git = git_dir / candidate
            if from_git.exists():
                return from_git.resolve()
        return from_repo.resolve()

    def _count_refs(self, repository: Path, prefix: str) -> int:
        output = self.optional_text(repository, ["for-each-ref", "--format=%(refname)", prefix])
        return sum(1 for line in (output or "").splitlines() if line.strip())

    @staticmethod
    def _remote_host(url: str) -> str:
        value = url.strip()
        if not value:
            return ""
        if re.match(r"^[^/@\s]+@[^:/\s]+:.+$", value):
            return value.split("@", 1)[1].split(":", 1)[0].lower()
        parsed = urlparse(value)
        if parsed.hostname:
            return parsed.hostname.lower()
        return "local"

    def _remote_hosts(self, repository: Path) -> tuple[str, ...]:
        output = self.optional_text(repository, ["remote", "-v"])
        hosts: set[str] = set()
        for line in (output or "").splitlines():
            fields = line.split()
            if len(fields) >= 2:
                host = self._remote_host(fields[1])
                if host:
                    hosts.add(host)
        return tuple(sorted(hosts))

    def _fingerprint(
        self,
        repository: Path,
        config: dict,
        head_hash: str | None,
        git_dir: Path,
    ) -> str:
        history = config["history"]
        refs = self._configured_refs(repository, history)
        if refs:
            ref_data = b""
            for ref in refs:
                ref_data += ref.encode("utf-8", errors="replace") + b"\x00"
                ref_data += self.run_bytes(repository, ["rev-parse", "--verify", ref], check=False) + b"\x00"
        elif history["scope"] == "current":
            ref_data = (head_hash or "").encode()
        elif history["scope"] == "local":
            ref_data = self.run_bytes(
                repository,
                ["for-each-ref", "--format=%(refname)%00%(objectname)", "refs/heads", "refs/tags"],
                check=False,
            )
            ref_data += f"HEAD:{head_hash or ''}".encode()
        else:
            ref_data = self.run_bytes(
                repository,
                ["for-each-ref", "--format=%(refname)%00%(objectname)"],
                check=False,
            )
            ref_data += f"HEAD:{head_hash or ''}".encode()

        digest = hashlib.sha256()
        digest.update(ref_data)
        mailmap_hash = hash_file(repository / ".mailmap")
        digest.update(f"mailmap:{mailmap_hash or ''}".encode())
        shallow_raw = self.optional_text(repository, ["rev-parse", "--git-path", "shallow"])
        if shallow_raw:
            shallow = self._resolve_git_path(repository, shallow_raw, git_dir)
            digest.update(f"shallow:{hash_file(shallow) or ''}".encode())
        return digest.hexdigest()

    def probe(self, location: RepositoryLocation, config: dict) -> RepositoryProbe:
        repository = location.path
        git_dir_raw = self.run_text(repository, ["rev-parse", "--absolute-git-dir"], timeout=30).strip()
        git_dir = Path(git_dir_raw).resolve()
        common_raw = self.run_text(repository, ["rev-parse", "--git-common-dir"], timeout=30).strip()
        common_dir = self._resolve_git_path(repository, common_raw, git_dir)
        is_bare = self.run_text(repository, ["rev-parse", "--is-bare-repository"], timeout=30).strip() == "true"
        is_shallow = self.run_text(repository, ["rev-parse", "--is-shallow-repository"], timeout=30).strip() == "true"
        is_partial = bool(self.optional_text(repository, ["config", "--get", "extensions.partialClone"], timeout=30))
        object_format = self.optional_text(repository, ["rev-parse", "--show-object-format"], timeout=30) or "sha1"
        head_hash_raw = self.optional_text(repository, ["rev-parse", "--verify", "HEAD"], timeout=30)
        head_hash = head_hash_raw if head_hash_raw and re.fullmatch(r"[0-9a-fA-F]{40,64}", head_hash_raw) else None
        head_branch = self.optional_text(repository, ["symbolic-ref", "--quiet", "--short", "HEAD"], timeout=30)
        remote_default = self.optional_text(
            repository, ["symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"], timeout=30
        )
        default_branch = remote_default.split("/", 1)[1] if remote_default and "/" in remote_default else head_branch
        local_branches = self._count_refs(repository, "refs/heads")
        remote_branches = self._count_refs(repository, "refs/remotes")
        tags = self._count_refs(repository, "refs/tags")
        remote_hosts = self._remote_hosts(repository) if config["history"]["collect_remote_hosts"] else ()
        fingerprint = self._fingerprint(repository, config, head_hash, git_dir)
        return RepositoryProbe(
            path=repository.resolve(),
            root=location.root.resolve(),
            display_name=location.display_name,
            repo_key=str(common_dir.resolve()),
            git_dir=git_dir,
            common_dir=common_dir,
            is_bare=is_bare,
            is_shallow=is_shallow,
            is_partial=is_partial,
            object_format=object_format,
            head_branch=head_branch,
            default_branch=default_branch,
            head_hash=head_hash,
            local_branches=local_branches,
            remote_branches=remote_branches,
            tags=tags,
            remote_hosts=remote_hosts,
            fingerprint=fingerprint,
        )

    @staticmethod
    def _classify_subject(subject: str, parent_count: int) -> tuple[str, str | None, bool]:
        if parent_count > 1 or subject.lower().startswith("merge "):
            return "merge", None, False
        lowered = subject.strip().lower()
        if lowered.startswith("revert"):
            return "revert", None, False
        if lowered in {"initial commit", "initial", "first commit"}:
            return "init", None, False
        match = CONVENTIONAL_RE.match(subject.strip())
        if match:
            kind = match.group("type").lower()
            return (kind if kind in KNOWN_TYPES else kind, match.group("scope"), bool(match.group("breaking")))
        return "other", None, False

    @staticmethod
    def _parse_numstat(payload: bytes) -> tuple[FileChange, ...]:
        tokens = payload.lstrip(b"\r\n").split(b"\x00")
        changes: list[FileChange] = []
        index = 0
        while index < len(tokens):
            token = tokens[index]
            index += 1
            if not token:
                continue
            token = token.lstrip(b"\r\n")
            if not token:
                continue
            pieces = token.split(b"\t", 2)
            if len(pieces) != 3:
                continue
            additions_raw, deletions_raw, path_raw = pieces
            old_path: str | None = None
            if path_raw == b"":
                if index + 1 >= len(tokens):
                    continue
                old_path = sanitize_text(tokens[index].decode("utf-8", errors="replace"))
                path = sanitize_text(tokens[index + 1].decode("utf-8", errors="replace"))
                index += 2
            else:
                path = sanitize_text(path_raw.decode("utf-8", errors="replace"))
            binary = additions_raw == b"-" or deletions_raw == b"-"
            try:
                insertions = None if binary else int(additions_raw or b"0")
                deletions = None if binary else int(deletions_raw or b"0")
            except ValueError:
                continue
            changes.append(
                FileChange(
                    path=path,
                    old_path=old_path,
                    language=classify_path(path),
                    top_directory=top_directory(path),
                    insertions=insertions,
                    deletions=deletions,
                    is_binary=binary,
                )
            )
        return tuple(changes)

    def _revision_arguments(self, probe: RepositoryProbe, config: dict) -> list[str]:
        history = config["history"]
        refs = self._configured_refs(probe.path, history)
        if refs:
            return refs
        if history["scope"] == "current":
            return ["HEAD"] if probe.head_hash else []
        if history["scope"] == "local":
            args = ["--branches", "--tags"]
            if probe.head_hash:
                args.append("HEAD")
            return args
        return ["--all"]

    def _configured_refs(self, repository: Path, history: dict) -> list[str]:
        """Return explicit revisions, resolving the main/master shortcut per repository."""
        refs = [str(ref) for ref in history.get("refs", [])]
        if refs or not history.get("main_branches", False):
            return refs
        output = self.run_text(
            repository,
            ["for-each-ref", "--format=%(refname)", "refs/heads/main", "refs/heads/master"],
            check=False,
        )
        return [line.strip() for line in output.splitlines() if line.strip()]

    def untrusted_commit_hashes(self, probe: RepositoryProbe, config: dict) -> set[str]:
        """Return selected commits not reachable from a trusted remote reference.

        Ordinary worktrees contribute remote-tracking refs (`refs/remotes/*`).
        Repositories created by ``gitanalytics fetch`` additionally carry a
        separate immutable-at-analysis-time `refs/gitanalytics/trusted/*`
        namespace.  Comparing selected revisions against those refs is much
        cheaper than retaining every trusted hash, and excludes local-only or
        unmerged commits from optional network paths.
        """
        revisions = self._revision_arguments(probe, config)
        if not revisions:
            return set()
        raw_refs = self.run_text(
            probe.path,
            ["for-each-ref", "--format=%(refname)", "refs/remotes", "refs/gitanalytics/trusted"],
            check=False,
        )
        trusted_refs = [line.strip() for line in raw_refs.splitlines() if line.strip()]
        args = ["rev-list", *revisions]
        if trusted_refs:
            args.extend(["--not", *trusted_refs])
        output = self.run_text(probe.path, args, check=False)
        return {line.strip() for line in output.splitlines() if line.strip()}

    def iter_commits(
        self,
        probe: RepositoryProbe,
        config: dict,
        untrusted_hashes: set[str] | None = None,
    ) -> Iterator[CommitRecord]:
        history = config["history"]
        revisions = self._revision_arguments(probe, config)
        if not revisions:
            return
        collect_churn = bool(history["collect_churn"])
        pretty = (
            "%x1e%H%x1f%P%x1f%an%x1f%ae%x1f%aN%x1f%aE"
            "%x1f%cn%x1f%ce%x1f%cN%x1f%cE%x1f%aI%x1f%cI%x1f%s%x00"
        )
        args: list[str] = [
            "log", "--no-color", "--no-show-signature", "--no-ext-diff", "--no-textconv",
            "--ignore-submodules=all", "--date-order", f"--pretty=format:{pretty}",
        ]
        if collect_churn:
            args.extend(["--numstat", "-z"])
            args.append("--find-renames=50%" if history["detect_renames"] else "--no-renames")
        if history["respect_mailmap"]:
            args.append("--use-mailmap")
        if history["first_parent"]:
            args.append("--first-parent")
        if not history["include_merges"]:
            args.append("--no-merges")
        if history.get("since"):
            args.append(f"--since={history['since']}")
        if history.get("until"):
            args.append(f"--until={history['until']}")
        if history.get("max_commits_per_repository"):
            args.append(f"--max-count={int(history['max_commits_per_repository'])}")
        args.extend(revisions)
        args.append("--")

        resolver = IdentityResolver(config)
        timezone = effective_timezone(config)
        use_mailmap = bool(history["respect_mailmap"])
        store_details = bool(history["store_file_details"] and collect_churn)
        store_subjects = bool(history["store_subjects"])

        for block in self.iter_delimited(probe.path, args, RECORD_SEPARATOR):
            block = block.lstrip(b"\r\n\x00")
            if not block:
                continue
            metadata_raw, separator, stats_raw = block.partition(b"\x00")
            if not separator:
                continue
            metadata = metadata_raw.decode("utf-8", errors="replace")
            fields = metadata.split(FIELD_SEPARATOR, 12)
            if len(fields) != 13:
                continue
            (
                commit_hash, parents, author_name_raw, author_email_raw,
                author_name_mailmap, author_email_mailmap,
                committer_name_raw, committer_email_raw,
                committer_name_mailmap, committer_email_mailmap,
                authored_at, committed_at, subject,
            ) = fields
            parent_count = len([parent for parent in parents.split() if parent])
            base_author_name = author_name_mailmap if use_mailmap else author_name_raw
            base_author_email = author_email_mailmap if use_mailmap else author_email_raw
            base_committer_name = committer_name_mailmap if use_mailmap else committer_name_raw
            base_committer_email = committer_email_mailmap if use_mailmap else committer_email_raw
            author = resolver.resolve(base_author_name, base_author_email)
            committer = resolver.resolve(base_committer_name, base_committer_email)
            message_type, message_scope, is_breaking = self._classify_subject(subject, parent_count)
            activity_source = authored_at if history["activity_timestamp"] == "author" else committed_at
            activity = parse_iso_datetime(activity_source)
            if timezone is not None:
                activity = activity.astimezone(timezone)
            offset = activity.utcoffset() or dt.timedelta(0)
            changes = self._parse_numstat(stats_raw) if collect_churn else ()
            insertions = sum(change.insertions or 0 for change in changes)
            deletions = sum(change.deletions or 0 for change in changes)
            binary_files = sum(1 for change in changes if change.is_binary)
            yield CommitRecord(
                commit_hash=sanitize_text(commit_hash),
                parent_count=parent_count,
                author_name_raw=sanitize_text(author_name_raw),
                author_email_raw=sanitize_text(author_email_raw),
                author_name_mailmap=sanitize_text(author_name_mailmap),
                author_email_mailmap=sanitize_text(author_email_mailmap),
                committer_name_raw=sanitize_text(committer_name_raw),
                committer_email_raw=sanitize_text(committer_email_raw),
                committer_name_mailmap=sanitize_text(committer_name_mailmap),
                committer_email_mailmap=sanitize_text(committer_email_mailmap),
                author_name=author.name,
                author_email=author.email,
                author_key=author.key,
                author_is_bot=author.is_bot,
                committer_name=committer.name,
                committer_email=committer.email,
                committer_key=committer.key,
                committer_is_bot=committer.is_bot,
                authored_at=authored_at,
                committed_at=committed_at,
                activity_at=activity.isoformat(),
                activity_date=activity.date().isoformat(),
                activity_year=activity.year,
                activity_month=activity.month,
                activity_weekday=activity.weekday(),
                activity_hour=activity.hour,
                timezone_offset_minutes=int(offset.total_seconds() // 60),
                subject=sanitize_text(subject) if store_subjects else None,
                message_type=message_type,
                message_scope=sanitize_text(message_scope) if message_scope else None,
                is_breaking=is_breaking,
                has_issue_reference=bool(ISSUE_RE.search(subject)),
                is_merge=parent_count > 1,
                is_trusted=untrusted_hashes is None or commit_hash not in untrusted_hashes,
                insertions=insertions,
                deletions=deletions,
                files_changed=len(changes),
                binary_files=binary_files,
                stats_collected=collect_churn,
                file_changes=changes if store_details else (),
            )

    @staticmethod
    def _comment_lines(text: str, language: str) -> tuple[int, int, int, dict[str, int]]:
        """Return code, comment, blank and kind counts using conservative line heuristics."""
        code = comments = blank = 0
        kinds: dict[str, int] = {"line": 0, "block": 0, "documentation": 0}
        in_block = False
        in_docstring: str | None = None
        line_prefixes = LINE_COMMENT_PREFIXES.get(language, ())
        for raw in text.splitlines():
            line = raw.strip()
            if not line:
                blank += 1
                continue
            if language == "Python" and (line.startswith('"""') or line.startswith("'''")):
                marker = line[:3]
                if in_docstring == marker or line.count(marker) >= 2:
                    in_docstring = None
                else:
                    in_docstring = marker
                comments += 1
                kinds["documentation"] += 1
                continue
            if in_docstring:
                comments += 1
                kinds["documentation"] += 1
                if in_docstring in line:
                    in_docstring = None
                continue
            if language in {"HTML", "XML", "Vue", "Svelte", "Markdown"}:
                if in_block or line.startswith("<!--"):
                    comments += 1
                    kinds["block"] += 1
                    in_block = "-->" not in line
                    continue
            if language in BLOCK_COMMENT_LANGUAGES and (in_block or line.startswith("/*")):
                comments += 1
                kinds["block"] += 1
                in_block = "*/" not in line
                continue
            if any(line.startswith(prefix) for prefix in line_prefixes):
                comments += 1
                kinds["line"] += 1
                continue
            code += 1
        return code, comments, blank, {key: value for key, value in kinds.items() if value}

    def _blob_contents(self, repository: Path, object_ids: Sequence[str]) -> Iterator[bytes]:
        """Read committed blobs in a single plumbing call without touching the worktree."""
        if not object_ids:
            return
        command = self.command(repository, ["cat-file", "--batch"])
        try:
            completed = subprocess.run(
                command, input=("\n".join(object_ids) + "\n").encode(), stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, env=self.environment(), timeout=self.timeout, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise GitCommandError(repository, command, "Kommentare konnten nicht aus Git-Blobs gelesen werden.") from exc
        if completed.returncode:
            raise GitCommandError(repository, command, completed.stderr.decode("utf-8", errors="replace"), completed.returncode)
        data, offset = completed.stdout, 0
        for _ in object_ids:
            end = data.find(b"\n", offset)
            if end < 0:
                return
            header = data[offset:end].split()
            offset = end + 1
            if len(header) < 3 or header[1] != b"blob":
                yield b""
                continue
            try:
                size = int(header[2])
            except ValueError:
                yield b""
                continue
            yield data[offset:offset + size]
            offset += size + 1

    def collect_tree(self, probe: RepositoryProbe, config: dict) -> tuple[list[TreeLanguage], list[TreeFileType], list[CommentStats], RepositorySignals, int, int]:
        if not config["history"]["collect_tree"] or not probe.head_hash:
            return [], [], [], RepositorySignals((), ()), 0, 0
        counts: dict[str, list[int]] = {}
        type_counts: dict[str, list[int]] = {}
        blobs: list[tuple[str, str]] = []
        signal_blobs: list[tuple[str, str]] = []
        ci_systems: set[str] = set()
        files = total_bytes = 0
        for record in self.iter_delimited(probe.path, ["ls-tree", "-r", "-l", "-z", "HEAD"], b"\x00"):
            if not record or b"\t" not in record:
                continue
            header, path_raw = record.split(b"\t", 1)
            parts = header.split()
            if len(parts) < 4 or parts[1] != b"blob":
                continue
            try:
                size = 0 if parts[3] == b"-" else int(parts[3])
            except ValueError:
                size = 0
            path = sanitize_text(path_raw.decode("utf-8", errors="replace"))
            if path.startswith(".github/workflows/") and path.endswith((".yml", ".yaml")):
                ci_systems.add("GitHub Actions")
            if path in CI_PATHS:
                ci_systems.add(CI_PATHS[path])
            if Path(path).name.upper().startswith(("LICENSE", "COPYING")):
                signal_blobs.append((parts[2].decode("ascii", errors="ignore"), path))
            language = classify_path(path)
            extension = file_type(path)
            values = counts.setdefault(language, [0, 0])
            values[0] += 1
            values[1] += size
            type_values = type_counts.setdefault(extension, [0, 0])
            type_values[0] += 1
            type_values[1] += size
            files += 1
            total_bytes += size
            if config["history"].get("collect_comments", True) and 0 < size <= 2_000_000:
                blobs.append((parts[2].decode("ascii", errors="ignore"), language))
        rows = [TreeLanguage(language=language, files=values[0], bytes=values[1]) for language, values in counts.items()]
        rows.sort(key=lambda row: (-row.bytes, -row.files, row.language))
        file_types = [TreeFileType(file_type=extension, files=values[0], bytes=values[1]) for extension, values in type_counts.items()]
        file_types.sort(key=lambda row: (-row.bytes, -row.files, row.file_type))
        totals: dict[str, list[int]] = {}
        kinds: dict[tuple[str, str], int] = {}
        for start in range(0, len(blobs), 500):
            batch = blobs[start:start + 500]
            for (object_id, language), content in zip(batch, self._blob_contents(probe.path, [item[0] for item in batch])):
                if not content or b"\x00" in content:
                    continue
                code, comments, blank, found_kinds = self._comment_lines(content.decode("utf-8", errors="replace"), language)
                values = totals.setdefault(language, [0, 0, 0, 0])
                values[0] += 1
                values[1] += code
                values[2] += comments
                values[3] += blank
                for kind, count in found_kinds.items():
                    kinds[(language, kind)] = kinds.get((language, kind), 0) + count
        stats = [CommentStats(language, "all", values[0], values[1], values[2], values[3]) for language, values in totals.items()]
        stats.extend(CommentStats(language, kind, 0, 0, count, 0) for (language, kind), count in kinds.items())
        stats.sort(key=lambda row: (row.language, row.kind))
        licenses: set[str] = set()
        for object_id, path in signal_blobs:
            for content in self._blob_contents(probe.path, [object_id]):
                licenses.add(_license_name(content[:32768].decode("utf-8", errors="replace"), path))
        return rows, file_types, stats, RepositorySignals(tuple(sorted(ci_systems)), tuple(sorted(licenses))), files, total_bytes

    def collect_releases(self, probe: RepositoryProbe, config: dict) -> list[ReleaseRecord]:
        if not config["history"]["collect_releases"]:
            return []
        output = self.optional_text(
            probe.path,
            [
                "for-each-ref", "--sort=creatordate",
                "--format=%(refname:short)%1f%(creatordate:iso-strict)%1f%(objectname)",
                "refs/tags",
            ],
        )
        releases: list[ReleaseRecord] = []
        for line in (output or "").splitlines():
            fields = line.split("\x1f", 2)
            if len(fields) != 3:
                continue
            name, date_raw, object_hash = fields
            created_at = None
            if date_raw.strip():
                try:
                    created_at = parse_iso_datetime(date_raw.strip()).isoformat()
                except ValueError:
                    created_at = None
            releases.append(
                ReleaseRecord(
                    name=sanitize_text(name),
                    created_at=created_at,
                    object_hash=object_hash,
                )
            )
        return releases
