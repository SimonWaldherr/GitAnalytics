from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path

from gitanalytics.cli import _query_connection, main


GIT = shutil.which("git")


def run(command: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> None:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=merged,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode:
        raise AssertionError(f"Command failed: {command}\n{completed.stdout}\n{completed.stderr}")


def snapshot(directory: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in sorted(item for item in directory.rglob("*") if item.is_file()):
        try:
            result[path.relative_to(directory).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
        except FileNotFoundError:
            # Git may remove a transient maintenance lock between rglob and
            # read; it is not part of a stable repository snapshot.
            continue
    return result


@unittest.skipUnless(GIT, "Git is required for integration tests")
class IntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.root = self.base / "projects"
        self.output = self.base / "output"
        self.repo = self.root / "alpha"
        self.repo.mkdir(parents=True)
        run([GIT, "init", "-q"], cwd=self.repo)
        run([GIT, "config", "user.name", "Default User"], cwd=self.repo)
        run([GIT, "config", "user.email", "default@example.com"], cwd=self.repo)
        (self.repo / ".mailmap").write_text(
            "Alice Example <alice@example.com> Alice Old <alice@old.example>\n",
            encoding="utf-8",
        )
        (self.repo / "LICENSE").write_text("MIT License\n\nPermission is hereby granted...\n", encoding="utf-8")
        (self.repo / ".github" / "workflows").mkdir(parents=True)
        (self.repo / ".github" / "workflows" / "checks.yml").write_text("name: checks\n", encoding="utf-8")
        (self.repo / "app.py").write_text(
            '# line comment\n"""module documentation"""\nprint(\'one\')\n', encoding="utf-8"
        )
        run([GIT, "add", "."], cwd=self.repo)
        stamp = "2024-01-01T09:00:00+01:00"
        run(
            [GIT, "commit", "-q", "-m", "feat(core): first #12"],
            cwd=self.repo,
            env={
                "GIT_AUTHOR_NAME": "Alice Old",
                "GIT_AUTHOR_EMAIL": "alice@old.example",
                "GIT_AUTHOR_DATE": stamp,
                "GIT_COMMITTER_NAME": "Alice Old",
                "GIT_COMMITTER_EMAIL": "alice@old.example",
                "GIT_COMMITTER_DATE": stamp,
            },
        )
        (self.repo / "app.py").write_text(
            '# line comment\n"""module documentation"""\nprint(\'one\')\nprint(\'two\')\n', encoding="utf-8"
        )
        stamp = "2024-01-06T22:30:00+01:00"
        run(
            [GIT, "commit", "-qam", "fix!: weekend ABC-42"],
            cwd=self.repo,
            env={
                "GIT_AUTHOR_NAME": "Bob Builder",
                "GIT_AUTHOR_EMAIL": "bob@example.com",
                "GIT_AUTHOR_DATE": stamp,
                "GIT_COMMITTER_NAME": "Bob Builder",
                "GIT_COMMITTER_EMAIL": "bob@example.com",
                "GIT_COMMITTER_DATE": stamp,
            },
        )
        run([GIT, "tag", "-a", "v1.0.0", "-m", "release"], cwd=self.repo)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def invoke(self, arguments: list[str]) -> int:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return main(arguments)

    def test_end_to_end_cache_and_read_only(self) -> None:
        before = snapshot(self.repo)
        code = self.invoke(
            [
                "analyze", str(self.root), "--output", str(self.output),
                "--timezone", "Europe/Berlin", "--quiet",
            ]
        )
        self.assertEqual(code, 0)
        self.assertEqual(before, snapshot(self.repo))

        report = json.loads((self.output / "data" / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["summary"]["repositories"], 1)
        self.assertEqual(report["summary"]["commits"], 2)
        self.assertEqual(report["summary"]["authors"], 2)
        self.assertEqual(report["contributors"]["rows"][0]["name"], "Alice Example")
        self.assertEqual(report["summary"]["breaking_changes"], 1)
        self.assertEqual(report["releases"]["summary"]["tags"], 1)
        self.assertEqual(report["repositories"][0]["comment_lines"], 2)
        self.assertGreater(report["repositories"][0]["comment_density"], 0)
        python_language = next(row for row in report["repositories"][0]["languages"] if row["language"] == "Python")
        self.assertEqual(python_language["comment_types"], {"documentation": 1, "line": 1})
        self.assertTrue(any(row["file_type"] == ".py" for row in report["repositories"][0]["file_types"]))
        self.assertEqual(report["repositories"][0]["ci_systems"], ["GitHub Actions"])
        self.assertEqual(report["repositories"][0]["licenses"], ["MIT"])
        self.assertIn("collaboration", report)
        self.assertFalse(report["collaboration"]["enabled"])
        self.assertEqual(report["collaboration"]["references_found"], [])
        self.assertEqual(report["activity"]["daily"][0]["repository_names"], ["alpha"])
        self.assertEqual(report["contributors"]["rows"][0]["repository_names"], ["alpha"])
        self.assertEqual(report["code"]["commit_types"][0]["repository_names"], ["alpha"])
        self.assertTrue((self.output / "index.html").is_file())
        self.assertTrue((self.output / "data" / "csv" / "repositories.csv").is_file())

        html = (self.output / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="gitanalytics-data"', html)
        self.assertNotIn("https://", html)
        self.assertNotIn("http://", html)

        code = self.invoke(
            [
                "analyze", str(self.root), "--output", str(self.output),
                "--timezone", "Europe/Berlin", "--quiet",
            ]
        )
        self.assertEqual(code, 0)
        with contextlib.closing(sqlite3.connect(self.output / "data" / "gitanalytics.sqlite3")) as connection:
            row = connection.execute(
                "SELECT repositories_scanned, repositories_cached FROM runs ORDER BY id DESC LIMIT 1"
            ).fetchone()
        self.assertEqual(row, (0, 1))
        self.assertEqual(before, snapshot(self.repo))

    def test_report_can_be_anonymized_without_rescan(self) -> None:
        self.assertEqual(
            self.invoke(["analyze", str(self.root), "--output", str(self.output), "--quiet"]),
            0,
        )
        anonymous = self.base / "anonymous"
        database = self.output / "data" / "gitanalytics.sqlite3"
        database_hash = hashlib.sha256(database.read_bytes()).hexdigest()
        self.assertEqual(
            self.invoke(
                [
                    "report", str(database), "--output", str(anonymous),
                    "--anonymize-authors", "--no-show-emails",
                ]
            ),
            0,
        )
        self.assertEqual(database_hash, hashlib.sha256(database.read_bytes()).hexdigest())
        self.assertTrue((anonymous / "data" / "gitanalytics.sqlite3").is_file())
        report = json.loads((anonymous / "data" / "report.json").read_text(encoding="utf-8"))
        self.assertTrue(all(row["name"].startswith("Autor ") for row in report["contributors"]["rows"]))
        self.assertTrue(all(not row["email"] for row in report["contributors"]["rows"]))

    def test_public_profile_is_allowlisted_and_omits_exact_metrics_by_default(self) -> None:
        private_repo = self.root / "customer-secret"
        private_repo.mkdir()
        run([GIT, "init", "-q"], cwd=private_repo)
        run([GIT, "config", "user.name", "Private User"], cwd=private_repo)
        run([GIT, "config", "user.email", "private@example.com"], cwd=private_repo)
        (private_repo / "secret.txt").write_text("not for export\n", encoding="utf-8")
        run([GIT, "add", "."], cwd=private_repo)
        run([GIT, "commit", "-q", "-m", "private work"], cwd=private_repo)

        self.assertEqual(self.invoke(["analyze", str(self.root), "--output", str(self.output), "--quiet"]), 0)
        database = self.output / "data" / "gitanalytics.sqlite3"
        draft = self.base / "profile-draft"
        self.assertEqual(
            self.invoke([
                "profile", str(database), "--github-user", "example-user", "--output", str(draft),
            ]),
            1,
        )
        self.assertFalse(draft.exists())

        config = self.base / "public-config.json"
        config.write_text(json.dumps({
            "privacy": {"repository_rules": [{"match": "alpha", "classification": "public"}]}
        }), encoding="utf-8")
        self.assertEqual(
            self.invoke([
                "analyze", str(self.root), "--output", str(self.output), "--config", str(config), "--quiet",
            ]),
            0,
        )
        report = json.loads((self.output / "data" / "report.json").read_text(encoding="utf-8"))
        classifications = {row["name"]: row["classification"] for row in report["repositories"]}
        self.assertEqual(classifications["alpha"], "public")
        self.assertEqual(classifications["customer-secret"], "private")

        self.assertEqual(
            self.invoke([
                "profile", str(database), "--github-user", "example-user", "--output", str(draft),
            ]),
            0,
        )
        profile = (draft / "README.md").read_text(encoding="utf-8")
        review = (draft / "PROFILE_DATA.md").read_text(encoding="utf-8")
        self.assertIn("alpha", profile)
        self.assertNotIn("customer-secret", profile)
        self.assertNotIn("Commits", profile)
        self.assertNotIn("private@example.com", review)
        self.assertNotIn("customer-secret", review)
        self.assertEqual(
            self.invoke([
                "profile", str(database), "--github-user", "example-user", "--output", str(draft),
                "--force", "--include-exact-metrics",
            ]),
            0,
        )
        self.assertIn("Commits", (draft / "README.md").read_text(encoding="utf-8"))

    def test_unpushed_commits_are_not_trusted_for_collaboration(self) -> None:
        upstream = self.base / "upstream.git"
        run([GIT, "init", "--bare", "-q", str(upstream)], cwd=self.base)
        seed = self.base / "seed"
        seed.mkdir()
        run([GIT, "init", "-q"], cwd=seed)
        run([GIT, "config", "user.name", "Remote Author"], cwd=seed)
        run([GIT, "config", "user.email", "remote@example.com"], cwd=seed)
        (seed / "remote.py").write_text("print('remote')\n", encoding="utf-8")
        run([GIT, "add", "."], cwd=seed)
        run([GIT, "commit", "-q", "-m", "remote commit"], cwd=seed)
        run([GIT, "remote", "add", "origin", str(upstream)], cwd=seed)
        run([GIT, "push", "-q", "-u", "origin", "HEAD"], cwd=seed)

        clones = self.base / "clones"
        run([GIT, "clone", "-q", str(upstream), str(clones / "working-copy")], cwd=self.base)
        worktree = clones / "working-copy"
        run([GIT, "config", "user.name", "Local Author"], cwd=worktree)
        run([GIT, "config", "user.email", "local@example.com"], cwd=worktree)
        (worktree / "local.py").write_text("print('local only')\n", encoding="utf-8")
        run([GIT, "add", "."], cwd=worktree)
        run([GIT, "commit", "-q", "-m", "local-only commit"], cwd=worktree)

        output = self.base / "trusted-output"
        config = self.base / "network-enabled.json"
        config.write_text(json.dumps({
            "network": {"enabled": True, "reference_names": ["Remote Author"]}
        }), encoding="utf-8")
        self.assertEqual(
            self.invoke(["analyze", str(clones), "--output", str(output), "--config", str(config), "--quiet"]),
            0,
        )
        with contextlib.closing(sqlite3.connect(output / "data" / "gitanalytics.sqlite3")) as connection:
            trusted, untrusted = connection.execute(
                "SELECT SUM(is_trusted), SUM(CASE WHEN is_trusted = 0 THEN 1 ELSE 0 END) FROM commits"
            ).fetchone()
        self.assertEqual((trusted, untrusted), (1, 1))

    def test_excluded_repository_is_purged_from_local_cache(self) -> None:
        self.assertEqual(self.invoke(["analyze", str(self.root), "--output", str(self.output), "--quiet"]), 0)
        config = self.base / "exclude-config.json"
        config.write_text(json.dumps({
            "privacy": {"repository_rules": [{"match": "alpha", "classification": "exclude"}]}
        }), encoding="utf-8")
        self.assertEqual(
            self.invoke([
                "analyze", str(self.root), "--output", str(self.output), "--config", str(config), "--quiet",
            ]),
            0,
        )
        report = json.loads((self.output / "data" / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["summary"]["repositories"], 0)
        with contextlib.closing(sqlite3.connect(self.output / "data" / "gitanalytics.sqlite3")) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM repositories").fetchone()[0], 0)

    def test_fetch_and_sync_only_touch_registered_bare_clones(self) -> None:
        source_before = snapshot(self.repo)
        sources = self.base / "sources"
        self.assertEqual(
            self.invoke(["fetch", str(self.repo), "--destination", str(sources), "--timeout", "30"]),
            0,
        )
        self.assertEqual(source_before, snapshot(self.repo))
        registry = json.loads((sources / ".gitanalytics-sources.json").read_text(encoding="utf-8"))
        self.assertEqual(len(registry["sources"]), 1)
        target = sources / registry["sources"][0]["target"]
        self.assertTrue((target / "HEAD").is_file())
        trusted_refs = subprocess.run(
            [GIT, "-C", str(target), "for-each-ref", "--format=%(refname)", "refs/gitanalytics/trusted"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", check=False,
        ).stdout
        self.assertIn("refs/gitanalytics/trusted/heads/", trusted_refs)

        (self.repo / "after-sync.py").write_text("print('new source commit')\n", encoding="utf-8")
        run([GIT, "add", "."], cwd=self.repo)
        run([GIT, "commit", "-q", "-m", "source update"], cwd=self.repo)
        source_after_commit = snapshot(self.repo)
        self.assertEqual(self.invoke(["sync", "--destination", str(sources), "--timeout", "30"]), 0)
        self.assertEqual(source_after_commit, snapshot(self.repo))


    def test_failed_rescan_preserves_previous_snapshot(self) -> None:
        self.assertEqual(
            self.invoke(["analyze", str(self.root), "--output", str(self.output), "--quiet"]),
            0,
        )
        git_directory = self.repo / ".git"
        saved = self.repo / ".git-saved-for-test"
        git_directory.rename(saved)
        git_directory.write_text("gitdir: definitely-missing\n", encoding="utf-8")
        try:
            self.assertEqual(
                self.invoke(["analyze", str(self.root), "--output", str(self.output), "--quiet"]),
                2,
            )
            report = json.loads((self.output / "data" / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["summary"]["commits"], 2)
            self.assertEqual(report["repositories"][0]["status"], "stale")
            self.assertTrue(report["quality"]["errors"])
            serialized = json.dumps(report["quality"]["errors"], ensure_ascii=False)
            self.assertNotIn(str(self.base), serialized)
        finally:
            git_directory.unlink()
            saved.rename(git_directory)

    def test_read_only_query_connection_rejects_update(self) -> None:
        self.assertEqual(
            self.invoke(["analyze", str(self.root), "--output", str(self.output), "--quiet"]),
            0,
        )
        database = self.output / "data" / "gitanalytics.sqlite3"
        with contextlib.closing(_query_connection(database)) as connection:
            count = connection.execute("SELECT COUNT(*) FROM v_commits").fetchone()[0]
            self.assertEqual(count, 2)
            with self.assertRaises(sqlite3.DatabaseError):
                connection.execute("UPDATE repositories SET display_name = 'changed'")

        attached = self.base / "must-not-exist.sqlite3"
        with contextlib.closing(_query_connection(database)) as connection:
            with self.assertRaises(sqlite3.DatabaseError):
                connection.execute(f"ATTACH DATABASE '{attached.as_posix()}' AS external")
        self.assertFalse(attached.exists())


if __name__ == "__main__":
    unittest.main()
