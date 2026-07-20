from __future__ import annotations

import argparse
import csv
import http.server
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import Any, Sequence

from . import __version__
from .analytics import Analytics
from .config import ConfigError, load_config, scan_signature, validate_config, write_example_config
from .console import Console, print_summary
from .database import DatabaseError, GitAnalyticsDatabase
from .discovery import DiscoveryError, assert_outputs_outside_repositories, discover_repositories
from .exports import (
    export_csv_bundle,
    write_data_dictionary,
    write_json_report,
    write_markdown_report,
    write_manifest,
)
from .forge import ForgeError, discover_account_repositories, discover_starred_repositories
from .git_reader import GitCommandError, GitReader
from .privacy import classify_repository, path_is_inside_repository
from .profile import ProfileError, public_profile_data, write_profile_package
from .report import write_html
from .sources import SourceError, fetch_sources, sync_sources
from .util import atomic_write_json, format_console_table, slugify, stable_hash


class UserError(RuntimeError):
    pass


def _stat_token(path: Path) -> str:
    """Cheap local change marker for Git metadata; does not invoke or modify Git."""
    marker = path / ".git"
    git_dir = marker
    try:
        if marker.is_file():
            raw = marker.read_text(encoding="utf-8", errors="replace").strip()
            if raw.startswith("gitdir:"):
                git_dir = (path / raw.split(":", 1)[1].strip()).resolve()
        elif not marker.is_dir():
            git_dir = path
        parts = [marker, git_dir / "HEAD", git_dir / "packed-refs", git_dir / "logs" / "HEAD"]
        refs = git_dir / "refs"
        if refs.is_dir():
            for current, _, files in os.walk(refs):
                parts.extend(Path(current) / name for name in files)
        return "|".join(f"{item}:{item.stat().st_mtime_ns}:{item.stat().st_size}" for item in sorted(parts) if item.exists())
    except OSError:
        return "unreadable"


def _load_local_index(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _default_data_home() -> Path:
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        return Path(base) if base else Path.home() / "AppData" / "Local"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))


def _default_output(roots: Sequence[Path]) -> Path:
    resolved = [root.expanduser().resolve() for root in roots]
    label = resolved[0].name if len(resolved) == 1 else f"{resolved[0].name}-plus-{len(resolved)-1}"
    identity = "\x00".join(str(root) for root in resolved)
    return _default_data_home() / "gitanalytics" / "reports" / f"{slugify(label, 'portfolio')}-{stable_hash(identity, 8)}"


def _set(config: dict[str, Any], section: str, key: str, value: Any) -> None:
    if value is not None:
        config[section][key] = value


def _apply_overrides(config: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    for key in ("max_depth", "include_hidden", "follow_symlinks", "nested_repositories"):
        _set(config, "discovery", key, getattr(args, key, None))
    if getattr(args, "ignore", None):
        config["discovery"]["ignore"] = list(config["discovery"]["ignore"]) + list(args.ignore)

    for key in (
        "scope", "since", "until", "first_parent", "include_merges", "include_bots",
        "deduplicate_global", "activity_timestamp", "timezone", "respect_mailmap",
        "collect_churn", "detect_renames", "store_file_details", "store_subjects",
        "collect_tree", "collect_releases", "collect_remote_hosts", "max_commits_per_repository",
    ):
        _set(config, "history", key, getattr(args, key, None))
    if getattr(args, "refs", None):
        config["history"]["refs"] = list(args.refs)

    for key in ("include_absolute_paths", "show_emails", "anonymize_authors"):
        _set(config, "privacy", key, getattr(args, key, None))
    for key in ("title", "top_n", "timeline_months", "quiet_after_days", "dormant_after_days"):
        _set(config, "report", key, getattr(args, key, None))
    for key in ("git_timeout_seconds", "sqlite_batch_size"):
        _set(config, "performance", key, getattr(args, key, None))
    validate_config(config)
    return config


def _write_outputs(
    output: Path,
    report: dict[str, Any],
    config: dict[str, Any],
    *,
    html: bool,
    json_output: bool,
    csv_output: bool,
    markdown: bool,
) -> list[Path]:
    files: list[Path] = []
    html_path = output / "index.html"
    json_path = output / "data" / "report.json"
    csv_path = output / "data" / "csv"
    markdown_path = output / "REPORT.md"
    if html:
        write_html(html_path, report)
        files.append(html_path)
    elif html_path.exists():
        html_path.unlink()
    if json_output:
        write_json_report(json_path, report)
        files.append(json_path)
    elif json_path.exists():
        json_path.unlink()
    if csv_output:
        files.extend(export_csv_bundle(csv_path, report))
    elif csv_path.exists():
        shutil.rmtree(csv_path)
    if markdown:
        write_markdown_report(markdown_path, report)
        files.append(markdown_path)
    elif markdown_path.exists():
        markdown_path.unlink()
    atomic_write_json(output / "data" / "effective-config.json", config)
    files.append(output / "data" / "effective-config.json")
    write_data_dictionary(output / "DATA_DICTIONARY.md")
    files.append(output / "DATA_DICTIONARY.md")
    return files


def _probe_unique(reader: GitReader, locations, config: dict, console: Console, classifications: dict[str, str]):
    probes = []
    failures: list[tuple[Path, str]] = []
    seen: dict[str, int] = {}
    probe_classifications: dict[str, str] = {}
    privacy_rank = {"exclude": 0, "private": 1, "public": 2}
    for index, location in enumerate(locations, start=1):
        console.info(f"[Probe {index}/{len(locations)}] {location.display_name}")
        try:
            probe = reader.probe(location, config)
        except GitCommandError as exc:
            failures.append((location.path, str(exc)))
            console.warning(f"{location.display_name}: {exc}")
            continue
        classification = classifications.get(str(location.path.resolve()), "private")
        if probe.repo_key in seen:
            current = probe_classifications[probe.repo_key]
            # If two worktrees share an object store, retaining the more
            # restrictive class prevents an alias from exposing it publicly.
            if privacy_rank[classification] < privacy_rank[current]:
                probe_classifications[probe.repo_key] = classification
            console.info("  Gemeinsamer Git-Objektspeicher bereits erfasst; Worktree übersprungen.")
            continue
        seen[probe.repo_key] = len(probes)
        probe_classifications[probe.repo_key] = classification
        probes.append(probe)
    return [(probe, probe_classifications[probe.repo_key]) for probe in probes], failures


def command_analyze(args: argparse.Namespace) -> int:
    roots = [Path(item).expanduser().resolve() for item in args.roots]
    config = _apply_overrides(load_config(args.config), args)
    output = (args.output or _default_output(roots)).expanduser().resolve()
    signature = scan_signature(config, __version__)
    index_path = output / "data" / "repository-index.json"
    local_index = _load_local_index(index_path)
    console = Console(quiet=args.quiet)

    console.info("GitAnalytics · strikte read-only Repository-Analyse")
    console.info("Suche Repositories …")
    discovery = discover_repositories(roots, config, skip_paths=[output])
    if not discovery.repositories:
        raise UserError("Keine Git-Repositories gefunden.")

    # No output is created before this guard has verified that it is outside every
    # discovered repository. This includes the SQLite cache itself.
    assert_outputs_outside_repositories(
        [location.path for location in discovery.repositories],
        [output],
    )

    classifications = {
        str(location.path.resolve()): classify_repository(location, config["privacy"])
        for location in discovery.repositories
    }
    locations = [
        location for location in discovery.repositories
        if classifications[str(location.path.resolve())] != "exclude"
    ]
    excluded_locations = [
        location for location in discovery.repositories
        if classifications[str(location.path.resolve())] == "exclude"
    ]
    excluded_count = len(discovery.repositories) - len(locations)
    if excluded_count:
        console.info(f"{excluded_count} Repository(s) durch Datenschutzregel ausgeschlossen.")
    if not locations:
        console.info("Alle gefundenen Repositories sind ausgeschlossen; der Bericht wird leer aktualisiert.")

    indexed = local_index.get("repositories", {}) if local_index.get("scan_signature") == signature else {}
    fast_locations: list[tuple[Any, str]] = []
    locations_to_probe = []
    for location in locations:
        classification = classifications[str(location.path.resolve())]
        if not args.force and indexed.get(str(location.path)) == _stat_token(location.path):
            fast_locations.append((location, classification))
        else:
            locations_to_probe.append(location)
    reader = GitReader(args.git, timeout=int(config["performance"]["git_timeout_seconds"]))
    probes, probe_failures = _probe_unique(reader, locations_to_probe, config, console, classifications)
    if locations and not probes and not probe_failures and not fast_locations:
        raise UserError("Keine gültigen Git-Repositories gefunden.")
    assert_outputs_outside_repositories(
        [path for probe, _ in probes for path in (probe.path, probe.git_dir, probe.common_dir)],
        [output],
    )

    output.mkdir(parents=True, exist_ok=True)
    data_dir = output / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    database_path = data_dir / "gitanalytics.sqlite3"
    scanned = cached = failed = 0
    report: dict[str, Any]

    with GitAnalyticsDatabase(database_path) as database:
        run_id = database.begin_run(roots, __version__, config)
        purged = database.purge_repository_paths([location.path for location in excluded_locations])
        if purged:
            console.info(f"{purged} zuvor gespeicherte(s) ausgeschlossene(s) Repository aus dem lokalen Cache entfernt.")
        for location, classification in fast_locations:
            if database.touch_cached_path(location.path, signature, run_id, classification):
                cached += 1
                console.info(f"[Index {cached}/{len(fast_locations)}] {location.display_name}")
        for issue in discovery.issues:
            database.record_error(run_id, issue.path, "discovery", issue.message)
        for path, message in probe_failures:
            database.mark_path_error(
                run_id, path, message, classifications.get(str(path.resolve()), "private")
            )
            database.record_error(run_id, path, "probe", message)
            failed += 1

        try:
            for index, (probe, privacy_classification) in enumerate(probes, start=1):
                if not args.force and database.repository_cache_hit(probe, signature):
                    console.info(f"[Cache {index}/{len(probes)}] {probe.display_name}")
                    database.touch_cached_repository(probe, signature, run_id, privacy_classification)
                    cached += 1
                    continue

                console.info(f"[Scan  {index}/{len(probes)}] {probe.display_name}")
                try:
                    tree_languages, tree_file_types, comment_stats, signals, tree_files, tree_bytes = reader.collect_tree(probe, config)
                    releases = reader.collect_releases(probe, config)
                    untrusted_hashes = (
                        reader.untrusted_commit_hashes(probe, config)
                        if config["network"]["enabled"] and config["network"]["require_remote_reference"] else None
                    )
                    result = database.import_repository(
                        probe=probe,
                        signature=signature,
                        run_id=run_id,
                        commits=reader.iter_commits(probe, config, untrusted_hashes),
                        tree_languages=tree_languages,
                        tree_file_types=tree_file_types,
                        comment_stats=comment_stats,
                        signals=signals,
                        tree_files=tree_files,
                        tree_bytes=tree_bytes,
                        releases=releases,
                        batch_size=int(config["performance"]["sqlite_batch_size"]),
                        privacy_classification=privacy_classification,
                    )
                    scanned += 1
                    console.info(
                        f"  {result.commits} Commits · {result.file_changes} Dateiänderungen · "
                        f"{result.insertions + result.deletions} Churn"
                    )
                except (GitCommandError, sqlite3.Error, OSError, ValueError) as exc:
                    failed += 1
                    message = str(exc)
                    console.warning(f"{probe.display_name}: {message}")
                    database.mark_repository_error(
                        probe, signature, run_id, message, privacy_classification
                    )
                    database.record_error(run_id, probe.path, "scan", message)
        except KeyboardInterrupt:
            database.finish_run(
                run_id, found=len(locations), scanned=scanned, cached=cached,
                failed=failed, status="aborted",
            )
            raise

        status = "complete" if failed == 0 else ("partial" if scanned + cached else "failed")
        database.finish_run(
            run_id,
            found=len(locations),
            scanned=scanned,
            cached=cached,
            failed=failed,
            status=status,
        )
        database.optimize()
        report = Analytics(database, config).build()
        generated = _write_outputs(
            output,
            report,
            config,
            html=not args.no_html,
            json_output=not args.no_json,
            csv_output=not args.no_csv,
            markdown=not args.no_markdown,
        )
    atomic_write_json(index_path, {
        "scan_signature": signature,
        "repositories": {str(location.path): _stat_token(location.path) for location in locations},
    })

    generated.append(database_path)
    write_manifest(output / "MANIFEST.txt", output, generated)
    print_summary(report, output)
    if args.open and not args.no_html:
        webbrowser.open((output / "index.html").as_uri())
    return 0 if failed == 0 else 2


def _load_latest_config(database: GitAnalyticsDatabase) -> dict[str, Any]:
    row = database.row("SELECT config_json FROM runs ORDER BY id DESC LIMIT 1")
    if not row:
        raise UserError("Die Datenbank enthält keinen Analyse-Lauf.")
    try:
        config = json.loads(row["config_json"])
    except (json.JSONDecodeError, TypeError) as exc:
        raise UserError("Die gespeicherte Konfiguration ist ungültig.") from exc
    validate_config(config)
    return config


def command_report(args: argparse.Namespace) -> int:
    database_path = args.database.expanduser().resolve()
    if not database_path.is_file():
        raise UserError(f"SQLite-Datenbank nicht gefunden: {database_path}")
    output = (args.output or database_path.parent.parent).expanduser().resolve()
    with GitAnalyticsDatabase(database_path, readonly=True) as database:
        config = _apply_overrides(_load_latest_config(database), args)
        report = Analytics(database, config).build()
        generated = _write_outputs(
            output, report, config,
            html=not args.no_html, json_output=not args.no_json, csv_output=not args.no_csv,
            markdown=not args.no_markdown,
        )
    bundled_database = output / "data" / "gitanalytics.sqlite3"
    if bundled_database.resolve() != database_path:
        bundled_database.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(database_path, bundled_database)
    generated.append(bundled_database)
    write_manifest(output / "MANIFEST.txt", output, generated)
    print_summary(report, output)
    if args.open and not args.no_html:
        webbrowser.open((output / "index.html").as_uri())
    return 0


def command_init_config(args: argparse.Namespace) -> int:
    target = args.path.expanduser().resolve()
    if target.exists() and not args.force:
        raise UserError(f"Datei existiert bereits: {target}. Mit --force überschreiben.")
    write_example_config(target)
    print(target)
    return 0


def command_doctor(args: argparse.Namespace) -> int:
    rows: list[tuple[str, str, str]] = []
    python_ok = sys.version_info >= (3, 10)
    rows.append(("Python", sys.version.split()[0], "ok" if python_ok else "mindestens 3.10 erforderlich"))
    rows.append(("SQLite", sqlite3.sqlite_version, "ok"))
    git = args.git or shutil.which("git")
    if git:
        try:
            completed = subprocess.run(
                [git, "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", errors="replace", timeout=15, check=False,
            )
            version = completed.stdout.strip() or completed.stderr.strip()
            status = "ok" if completed.returncode == 0 else f"Exit {completed.returncode}"
        except (OSError, subprocess.TimeoutExpired) as exc:
            version, status = str(git), str(exc)
    else:
        version, status = "nicht gefunden", "Fehler"
    rows.append(("Git", version, status))
    rows.append(("GitAnalytics", __version__, "ok"))
    print(format_console_table(("Komponente", "Version/Pfad", "Status"), rows))
    return 0 if python_ok and git and rows[2][2] == "ok" else 1


def _query_connection(path: Path) -> sqlite3.Connection:
    uri = path.expanduser().resolve().as_uri() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")

    denied_actions = {
        sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE,
        sqlite3.SQLITE_CREATE_INDEX, sqlite3.SQLITE_CREATE_TABLE,
        sqlite3.SQLITE_CREATE_TEMP_INDEX, sqlite3.SQLITE_CREATE_TEMP_TABLE,
        sqlite3.SQLITE_CREATE_TEMP_TRIGGER, sqlite3.SQLITE_CREATE_TEMP_VIEW,
        sqlite3.SQLITE_CREATE_TRIGGER, sqlite3.SQLITE_CREATE_VIEW,
        sqlite3.SQLITE_DROP_INDEX, sqlite3.SQLITE_DROP_TABLE,
        sqlite3.SQLITE_DROP_TEMP_INDEX, sqlite3.SQLITE_DROP_TEMP_TABLE,
        sqlite3.SQLITE_DROP_TEMP_TRIGGER, sqlite3.SQLITE_DROP_TEMP_VIEW,
        sqlite3.SQLITE_DROP_TRIGGER, sqlite3.SQLITE_DROP_VIEW,
        sqlite3.SQLITE_ALTER_TABLE, sqlite3.SQLITE_REINDEX,
        sqlite3.SQLITE_ANALYZE, sqlite3.SQLITE_ATTACH, sqlite3.SQLITE_DETACH,
        sqlite3.SQLITE_TRANSACTION, sqlite3.SQLITE_SAVEPOINT,
    }

    def authorize(action: int, argument1: str | None, argument2: str | None,
                  database_name: str | None, trigger_name: str | None) -> int:
        del argument1, database_name, trigger_name
        if action in denied_actions:
            return sqlite3.SQLITE_DENY
        # A PRAGMA with a second argument is generally an assignment. Reading
        # metadata PRAGMAs remains possible, but changing connection state is not.
        if action == sqlite3.SQLITE_PRAGMA and argument2 is not None:
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    connection.set_authorizer(authorize)
    return connection


def command_query(args: argparse.Namespace) -> int:
    database = args.database.expanduser().resolve()
    if not database.is_file():
        raise UserError(f"SQLite-Datenbank nicht gefunden: {database}")
    sql = args.sql
    if args.file:
        sql = args.file.expanduser().read_text(encoding="utf-8")
    if not sql or not sql.strip():
        raise UserError("Keine SQL-Abfrage angegeben.")
    with _query_connection(database) as connection:
        try:
            cursor = connection.execute(sql)
            columns = [item[0] for item in cursor.description or []]
            rows = [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as exc:
            raise UserError(f"SQLite: {exc}") from exc
    if args.format == "json":
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    elif args.format == "csv":
        writer = csv.DictWriter(sys.stdout, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    else:
        table_rows = [[row.get(column, "") for column in columns] for row in rows]
        print(format_console_table(columns, table_rows) if columns else "Keine Ergebnisspalten.")
    return 0


def command_serve(args: argparse.Namespace) -> int:
    directory = args.directory.expanduser().resolve()
    if not directory.is_dir():
        raise UserError(f"Berichtsordner nicht gefunden: {directory}")
    handler = lambda *handler_args, **handler_kwargs: http.server.SimpleHTTPRequestHandler(  # noqa: E731
        *handler_args, directory=str(directory), **handler_kwargs
    )
    server = http.server.ThreadingHTTPServer((args.bind, args.port), handler)
    address, port = server.server_address[:2]
    print(f"GitAnalytics-Bericht: http://{address}:{port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def _print_source_results(results: Sequence[dict[str, str]]) -> int:
    partial = False
    for row in results:
        source, status, detail = row.get("source", ""), row.get("status", ""), row.get("detail", "")
        if status == "cloned":
            print(f"Geklont: {source} → {detail}")
        elif status == "synced":
            print(f"Synchronisiert: {source} → {detail}")
        elif status == "registered":
            print(f"Bereits registriert: {source} → {detail}")
        else:
            partial = True
            print(f"{status.title()}: {source} — {detail}", file=sys.stderr)
        if row.get("trusted") == "no":
            partial = True
            print(
                f"Warnung: Vertrauens-Referenzen für {source} konnten nicht aktualisiert werden; "
                "diese Historie steht optionalen Netzwerkpfaden nicht als Remote-Evidenz zur Verfügung.",
                file=sys.stderr,
            )
    return 2 if partial else 0


def command_fetch(args: argparse.Namespace) -> int:
    """Clone explicit Git URLs into a registry-managed, tool-owned folder."""
    results = fetch_sources(
        args.destination, args.sources, git=args.git, depth=args.depth, timeout=args.timeout,
    )
    return _print_source_results(results)


def command_sync(args: argparse.Namespace) -> int:
    """Fetch only clones previously created by the `fetch` command."""
    return _print_source_results(sync_sources(args.destination, git=args.git, timeout=args.timeout))


def command_fetch_account(args: argparse.Namespace) -> int:
    """Discover one account's repositories, then clone the exact discovered URLs."""
    token = os.environ.get(args.token_env) if args.token_env else None
    if args.token_env and not token:
        raise UserError(f"Die Umgebungsvariable {args.token_env} ist nicht gesetzt oder leer.")
    repositories = discover_account_repositories(
        args.forge, args.account, base_url=args.base_url, token=token,
        visibility=args.visibility, include_forks=args.include_forks,
        protocol=args.clone_protocol, timeout=args.api_timeout,
    )
    if args.max_repositories is not None:
        if args.max_repositories < 1:
            raise UserError("--max-repositories muss mindestens 1 sein.")
        repositories = repositories[:args.max_repositories]
    if not repositories:
        print("Keine passenden Repositories gefunden.")
        return 0
    for repository in repositories:
        print(f"Gefunden: {repository['name']} ({repository['visibility']}, Fork: {repository['fork']}) → {repository['source']}")
    if args.dry_run:
        print(f"Vorschau: {len(repositories)} Repositories würden in {args.destination.expanduser()} geklont.")
        return 0
    print(f"Importiere {len(repositories)} explizit gefundene Repositories nach {args.destination.expanduser()}.")
    return _print_source_results(fetch_sources(
        args.destination, [repository["source"] for repository in repositories],
        git=args.git, depth=args.depth, timeout=args.timeout,
    ))


def command_fetch_starred(args: argparse.Namespace) -> int:
    """Discover repositories starred by one account, then clone the exact visible URLs."""
    token = os.environ.get(args.token_env) if args.token_env else None
    if args.token_env and not token:
        raise UserError(f"Die Umgebungsvariable {args.token_env} ist nicht gesetzt oder leer.")
    repositories = discover_starred_repositories(
        args.forge, args.account, base_url=args.base_url, token=token,
        visibility=args.visibility, include_forks=args.include_forks,
        protocol=args.clone_protocol, timeout=args.api_timeout,
    )
    if args.max_repositories is not None:
        if args.max_repositories < 1:
            raise UserError("--max-repositories muss mindestens 1 sein.")
        repositories = repositories[:args.max_repositories]
    if not repositories:
        print("Keine passenden favorisierten Repositories gefunden.")
        return 0
    for repository in repositories:
        print(f"Favorit: {repository['name']} ({repository['visibility']}, Fork: {repository['fork']}) → {repository['source']}")
    if args.dry_run:
        print(f"Vorschau: {len(repositories)} favorisierte Repositories würden in {args.destination.expanduser()} geklont.")
        return 0
    print(f"Importiere {len(repositories)} favorisierte Repositories nach {args.destination.expanduser()}.")
    return _print_source_results(fetch_sources(
        args.destination, [repository["source"] for repository in repositories],
        git=args.git, depth=args.depth, timeout=args.timeout,
    ))


def command_profile(args: argparse.Namespace) -> int:
    database_path = args.database.expanduser().resolve()
    if not database_path.is_file():
        raise UserError(f"SQLite-Datenbank nicht gefunden: {database_path}")
    output = args.output.expanduser().resolve()
    if path_is_inside_repository(output):
        raise UserError(
            "Der Profil-Entwurf darf nicht innerhalb eines Git-Repositories geschrieben werden. "
            "Er wird bewusst nur als separat prüfbares Paket erzeugt."
        )
    with GitAnalyticsDatabase(database_path, readonly=True) as database:
        config = _load_latest_config(database)
        policy = {key: bool(config["profile"][key]) for key in config["profile"]}
        for key in (
            "include_repository_names", "include_languages", "include_exact_metrics",
            "include_last_activity_date",
        ):
            override = getattr(args, key, None)
            if override is not None:
                policy[key] = bool(override)
        repositories, languages = public_profile_data(database, args.include_repo)
    files = write_profile_package(
        output,
        github_user=args.github_user,
        display_name=args.name,
        repositories=repositories,
        languages=languages,
        policy=policy,
        force=args.force,
    )
    print("Profil-Entwurf erstellt (nicht veröffentlicht):")
    for path in files:
        print(path)
    return 0


def _add_report_overrides(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--title", help="Titel des Berichts.")
    parser.add_argument("--top-n", type=int, help="Standardgröße von Ranglisten.")
    parser.add_argument("--timeline-months", type=int, help="Monate in kompakten Zeitreihen.")
    parser.add_argument("--quiet-after-days", type=int, help="Grenze für ruhige Repositories.")
    parser.add_argument("--dormant-after-days", type=int, help="Grenze für inaktive Repositories.")
    parser.add_argument("--include-absolute-paths", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--show-emails", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--anonymize-authors", action=argparse.BooleanOptionalAction, default=None)


def _add_output_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--output", type=Path, help="Ausgabeordner; muss außerhalb analysierter Repositories liegen.")
    parser.add_argument("--no-html", action="store_true", help="Keinen HTML-Bericht schreiben.")
    parser.add_argument("--no-json", action="store_true", help="Keinen JSON-Snapshot schreiben.")
    parser.add_argument("--no-csv", action="store_true", help="Keine CSV-Dateien schreiben.")
    parser.add_argument("--no-markdown", action="store_true", help="Keinen kompakten Markdown-Bericht schreiben.")
    parser.add_argument("--open", action="store_true", help="HTML-Bericht nach dem Lauf im Browser öffnen.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gitanalytics",
        description="Lokale, read-only Business-Intelligence für Git-Repositories.",
    )
    parser.add_argument("--version", action="version", version=f"GitAnalytics {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    analyze = sub.add_parser("analyze", aliases=["analyse"], help="Repositories suchen, einlesen und Bericht erzeugen.")
    analyze.add_argument("roots", nargs="+", help="Ein oder mehrere Stammverzeichnisse.")
    analyze.add_argument("--config", type=Path, help="JSON-Konfiguration.")
    analyze.add_argument("--git", help="Pfad zur Git-Executable.")
    analyze.add_argument("--force", action="store_true", help="Cache ignorieren und alle Repositories neu einlesen.")
    analyze.add_argument("--quiet", action="store_true", help="Fortschrittsausgabe reduzieren.")
    _add_output_options(analyze)
    _add_report_overrides(analyze)

    analyze.add_argument("--max-depth", type=int)
    analyze.add_argument("--include-hidden", action=argparse.BooleanOptionalAction, default=None)
    analyze.add_argument("--follow-symlinks", action=argparse.BooleanOptionalAction, default=None)
    analyze.add_argument("--nested-repositories", action=argparse.BooleanOptionalAction, default=None)
    analyze.add_argument("--ignore", action="append", help="Zusätzliches Discovery-Glob; mehrfach verwendbar.")

    analyze.add_argument("--scope", choices=["current", "local", "all"])
    analyze.add_argument("--ref", dest="refs", action="append", help="Explizite Revision; mehrfach verwendbar.")
    analyze.add_argument("--since", help="Git-Zeitgrenze, z. B. 2024-01-01 oder '1 year ago'.")
    analyze.add_argument("--until", help="Git-Zeitgrenze.")
    analyze.add_argument("--first-parent", action=argparse.BooleanOptionalAction, default=None)
    analyze.add_argument("--include-merges", action=argparse.BooleanOptionalAction, default=None)
    analyze.add_argument("--exclude-merges", dest="include_merges", action="store_false", default=None, help="Alias für --no-include-merges.")
    analyze.add_argument("--include-bots", action=argparse.BooleanOptionalAction, default=None)
    analyze.add_argument("--exclude-bots", dest="include_bots", action="store_false", default=None, help="Alias für --no-include-bots.")
    analyze.add_argument("--deduplicate-global", action=argparse.BooleanOptionalAction, default=None)
    analyze.add_argument("--activity-timestamp", choices=["author", "committer"])
    analyze.add_argument("--timezone", help="commit, UTC oder IANA-Zeitzone wie Europe/Berlin.")
    analyze.add_argument("--respect-mailmap", action=argparse.BooleanOptionalAction, default=None)
    analyze.add_argument("--collect-churn", action=argparse.BooleanOptionalAction, default=None)
    analyze.add_argument("--detect-renames", action=argparse.BooleanOptionalAction, default=None)
    analyze.add_argument("--store-file-details", action=argparse.BooleanOptionalAction, default=None)
    analyze.add_argument("--store-subjects", action=argparse.BooleanOptionalAction, default=None)
    analyze.add_argument("--collect-tree", action=argparse.BooleanOptionalAction, default=None)
    analyze.add_argument("--collect-releases", action=argparse.BooleanOptionalAction, default=None)
    analyze.add_argument("--collect-remote-hosts", action=argparse.BooleanOptionalAction, default=None)
    analyze.add_argument("--max-commits-per-repository", type=int)
    analyze.add_argument("--git-timeout-seconds", type=int)
    analyze.add_argument("--sqlite-batch-size", type=int)
    analyze.set_defaults(func=command_analyze)

    report = sub.add_parser("report", help="Bericht aus einer bestehenden GitAnalytics-SQLite-Datenbank neu erzeugen.")
    report.add_argument("database", type=Path)
    _add_output_options(report)
    _add_report_overrides(report)
    report.set_defaults(func=command_report)

    fetch = sub.add_parser(
        "fetch", aliases=["graph-fetch"],
        help="Explizit angegebene Git-URLs als registrierte Bare-Repositories klonen.",
    )
    fetch.add_argument("sources", nargs="+", help="Git-URLs, z. B. https://github.com/org/repo.git oder git@gitlab.com:org/repo.git")
    fetch.add_argument("--destination", type=Path, required=True, help="Eigener Zielordner für neue Bare-Repositories.")
    fetch.add_argument("--depth", type=int, help="Optionale flache Klontiefe; begrenzt Historien-Kennzahlen.")
    fetch.add_argument("--git", help="Pfad zur Git-Executable.")
    fetch.add_argument("--timeout", type=int, default=900, help="Zeitlimit pro Git-Netzwerkoperation in Sekunden.")
    fetch.set_defaults(func=command_fetch)

    fetch_account = sub.add_parser(
        "fetch-account", aliases=["import-account"],
        help="Repos eines explizit gewählten Forge-Accounts auflisten und als verwaltete Quellen klonen.",
    )
    fetch_account.add_argument("--forge", required=True, choices=["github", "gitlab", "gitea", "forgejo", "gogs"])
    fetch_account.add_argument("--account", required=True, help="Benutzer- oder Organisationsname auf der Forge.")
    fetch_account.add_argument("--destination", type=Path, required=True, help="Eigener Zielordner für neue Bare-Repositories.")
    fetch_account.add_argument("--base-url", help="Basis der selbst gehosteten Forge, z. B. https://git.example.org.")
    fetch_account.add_argument("--visibility", choices=["public", "private", "all"], default="public")
    fetch_account.add_argument("--token-env", help="Name einer Umgebungsvariable mit API-Token; nie als Kommandoargument übergeben.")
    fetch_account.add_argument("--clone-protocol", choices=["https", "ssh"], default="https")
    fetch_account.add_argument("--include-forks", action="store_true", help="Forks des Accounts ebenfalls importieren.")
    fetch_account.add_argument("--max-repositories", type=int, help="Import nach dieser Anzahl stoppen.")
    fetch_account.add_argument("--dry-run", action="store_true", help="Nur gefundene URLs anzeigen; nichts klonen.")
    fetch_account.add_argument("--depth", type=int, help="Optionale flache Klontiefe; begrenzt Historien-Kennzahlen.")
    fetch_account.add_argument("--git", help="Pfad zur Git-Executable.")
    fetch_account.add_argument("--timeout", type=int, default=900, help="Zeitlimit pro Git-Netzwerkoperation in Sekunden.")
    fetch_account.add_argument("--api-timeout", type=int, default=30, help="Zeitlimit pro Forge-API-Anfrage in Sekunden.")
    fetch_account.set_defaults(func=command_fetch_account)

    fetch_starred = sub.add_parser(
        "fetch-starred", aliases=["import-starred"],
        help="Von einem Account favorisierte Repositories als verwaltete Quellen klonen.",
    )
    fetch_starred.add_argument("--forge", required=True, choices=["github", "gitlab"])
    fetch_starred.add_argument("--account", required=True, help="Benutzername auf der Forge.")
    fetch_starred.add_argument("--destination", type=Path, required=True, help="Eigener Zielordner für neue Bare-Repositories.")
    fetch_starred.add_argument("--base-url", help="Basis einer selbst gehosteten GitLab-Instanz, z. B. https://git.example.org/api/v4.")
    fetch_starred.add_argument("--visibility", choices=["public", "private", "all"], default="public")
    fetch_starred.add_argument("--token-env", help="Name einer Umgebungsvariable mit API-Token; nie als Kommandoargument übergeben.")
    fetch_starred.add_argument("--clone-protocol", choices=["https", "ssh"], default="https")
    fetch_starred.add_argument("--include-forks", action="store_true", help="Favorisierte Forks ebenfalls importieren.")
    fetch_starred.add_argument("--max-repositories", type=int, help="Import nach dieser Anzahl stoppen.")
    fetch_starred.add_argument("--dry-run", action="store_true", help="Nur gefundene URLs anzeigen; nichts klonen.")
    fetch_starred.add_argument("--depth", type=int, help="Optionale flache Klontiefe; begrenzt Historien-Kennzahlen.")
    fetch_starred.add_argument("--git", help="Pfad zur Git-Executable.")
    fetch_starred.add_argument("--timeout", type=int, default=900, help="Zeitlimit pro Git-Netzwerkoperation in Sekunden.")
    fetch_starred.add_argument("--api-timeout", type=int, default=30, help="Zeitlimit pro Forge-API-Anfrage in Sekunden.")
    fetch_starred.set_defaults(func=command_fetch_starred)

    sync = sub.add_parser(
        "sync", aliases=["update-sources"],
        help="Nur zuvor mit fetch registrierte, tool-eigene Bare-Clones aktualisieren.",
    )
    sync.add_argument("--destination", type=Path, required=True, help="Ordner mit .gitanalytics-sources.json.")
    sync.add_argument("--git", help="Pfad zur Git-Executable.")
    sync.add_argument("--timeout", type=int, default=900, help="Zeitlimit pro Git-Netzwerkoperation in Sekunden.")
    sync.set_defaults(func=command_sync)

    profile = sub.add_parser(
        "profile",
        help="Separates, nur aus explizit public freigegebenen Repositories bestehendes GitHub-Profilpaket erzeugen.",
    )
    profile.add_argument("database", type=Path, help="GitAnalytics-SQLite-Datenbank.")
    profile.add_argument("--github-user", required=True, help="GitHub-Benutzername für den Profil-Entwurf.")
    profile.add_argument("--name", help="Anzeigename im README; Standard ist --github-user.")
    profile.add_argument("--output", type=Path, required=True, help="Neuer, separater Ordner für README.md und PROFILE_DATA.md.")
    profile.add_argument("--include-repo", action="append", default=[], help="Nur dieses bereits public freigegebene Repository aufnehmen; mehrfach verwendbar.")
    profile.add_argument("--force", action="store_true", help="Vorhandenes README.md und PROFILE_DATA.md im Entwurfsordner überschreiben.")
    profile.add_argument("--include-repository-names", action=argparse.BooleanOptionalAction, default=None)
    profile.add_argument("--include-languages", action=argparse.BooleanOptionalAction, default=None)
    profile.add_argument("--include-exact-metrics", action=argparse.BooleanOptionalAction, default=None)
    profile.add_argument("--include-last-activity-date", action=argparse.BooleanOptionalAction, default=None)
    profile.set_defaults(func=command_profile)

    init_config = sub.add_parser("init-config", help="Dokumentierte Beispielkonfiguration erzeugen.")
    init_config.add_argument("path", type=Path, nargs="?", default=Path("gitanalytics.json"))
    init_config.add_argument("--force", action="store_true")
    init_config.set_defaults(func=command_init_config)

    doctor = sub.add_parser("doctor", help="Python-, SQLite- und Git-Installation prüfen.")
    doctor.add_argument("--git", help="Pfad zur Git-Executable.")
    doctor.set_defaults(func=command_doctor)

    query = sub.add_parser("query", help="Read-only SQL-Abfrage gegen die GitAnalytics-Datenbank.")
    query.add_argument("database", type=Path)
    query.add_argument("sql", nargs="?", help="SELECT/WITH-Abfrage.")
    query.add_argument("--file", type=Path, help="SQL aus Datei lesen.")
    query.add_argument("--format", choices=["table", "json", "csv"], default="table")
    query.set_defaults(func=command_query)

    serve = sub.add_parser("serve", help="Berichtsordner über einen lokalen HTTP-Server bereitstellen.")
    serve.add_argument("directory", type=Path)
    serve.add_argument("--bind", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    serve.set_defaults(func=command_serve)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        print("Abgebrochen.", file=sys.stderr)
        return 130
    except (
        UserError, ConfigError, DiscoveryError, DatabaseError, GitCommandError,
        ProfileError, SourceError, ForgeError,
        sqlite3.Error, OSError, ValueError,
    ) as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1
    except PermissionError as exc:
        print(f"Fehler: Keine Berechtigung: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
