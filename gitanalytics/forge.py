"""Explicit, bounded repository discovery through forge HTTP APIs.

Discovery only lists repositories of one account chosen on the command line.
It never follows contributors, followers, forks, or other transitive links.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urljoin
from urllib.request import Request, urlopen


class ForgeError(ValueError):
    pass


JsonOpener = Callable[..., Any]


def _api_base(forge: str, base_url: str | None) -> str:
    defaults = {"github": "https://api.github.com/", "gitlab": "https://gitlab.com/api/v4/"}
    if base_url:
        if not base_url.startswith(("https://", "http://")):
            raise ForgeError("--base-url muss mit https:// oder http:// beginnen.")
        return base_url.rstrip("/") + "/"
    if forge in defaults:
        return defaults[forge]
    raise ForgeError(f"Für {forge} ist --base-url erforderlich, z. B. https://git.example.org.")


def _headers(forge: str, token: str | None) -> dict[str, str]:
    headers = {"Accept": "application/json", "User-Agent": "GitAnalytics/forge-import"}
    if not token:
        return headers
    if forge == "gitlab":
        headers["PRIVATE-TOKEN"] = token
    elif forge in {"gitea", "forgejo", "gogs"}:
        headers["Authorization"] = f"token {token}"
    else:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _get_json(url: str, *, forge: str, token: str | None, timeout: int, opener: JsonOpener) -> tuple[Any, dict[str, str]]:
    request = Request(url, headers=_headers(forge, token), method="GET")
    try:
        with opener(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            headers = {str(key).lower(): str(value) for key, value in response.headers.items()}
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise ForgeError(f"Forge-API antwortete mit HTTP {exc.code}: {detail}") from exc
    except (URLError, OSError, TimeoutError) as exc:
        raise ForgeError(f"Forge-API nicht erreichbar: {exc}") from exc
    try:
        return json.loads(raw), headers
    except json.JSONDecodeError as exc:
        raise ForgeError("Forge-API lieferte kein gültiges JSON.") from exc


def _pages(path: str, *, forge: str, base: str, token: str | None, timeout: int, opener: JsonOpener, pagination: str) -> list[dict[str, Any]]:
    page, rows = 1, []
    while True:
        separator = "&" if "?" in path else "?"
        parameters = {"page": page, "per_page": 100} if pagination != "simple" else {"page": page, "limit": 100}
        payload, headers = _get_json(urljoin(base, f"{path}{separator}{urlencode(parameters)}"), forge=forge, token=token, timeout=timeout, opener=opener)
        if not isinstance(payload, list):
            raise ForgeError(f"{forge}-API lieferte keine Repository-Liste.")
        batch = [item for item in payload if isinstance(item, dict)]
        rows.extend(batch)
        if pagination == "github":
            if 'rel="next"' not in headers.get("link", ""):
                return rows
            page += 1
        elif pagination == "gitlab":
            next_page = headers.get("x-next-page", "")
            if not next_page:
                return rows
            try:
                page = int(next_page)
            except ValueError as exc:
                raise ForgeError("GitLab-API lieferte eine ungültige Seitennummer.") from exc
        else:
            if len(batch) < 100:
                return rows
            page += 1


def _normalise(rows: list[dict[str, Any]], *, forge: str, protocol: str, visibility: str, include_forks: bool) -> list[dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for row in rows:
        is_private = bool(row.get("private") or row.get("visibility") == "private")
        if visibility == "public" and is_private or visibility == "private" and not is_private:
            continue
        if not include_forks and bool(row.get("fork")):
            continue
        source = str(row.get("ssh_url" if protocol == "ssh" else "clone_url") or row.get("http_url_to_repo") or "").strip()
        if not source:
            continue
        name = str(row.get("full_name") or row.get("path_with_namespace") or row.get("name") or source)
        result[source] = {"source": source, "name": name, "visibility": "private" if is_private else "public", "fork": "yes" if bool(row.get("fork")) else "no", "forge": forge}
    return sorted(result.values(), key=lambda item: (item["name"].casefold(), item["source"]))


def discover_account_repositories(
    forge: str, account: str, *, base_url: str | None = None, token: str | None = None,
    visibility: str = "public", include_forks: bool = False, protocol: str = "https",
    timeout: int = 30, opener: JsonOpener = urlopen,
) -> list[dict[str, str]]:
    """List the bounded set of repositories directly owned by one forge account."""
    forge, account = forge.casefold(), account.strip()
    if forge not in {"github", "gitlab", "gitea", "forgejo", "gogs"}:
        raise ForgeError(f"Nicht unterstützte Forge: {forge}")
    if not account:
        raise ForgeError("--account darf nicht leer sein.")
    if visibility not in {"public", "private", "all"}:
        raise ForgeError("--visibility muss public, private oder all sein.")
    if protocol not in {"https", "ssh"}:
        raise ForgeError("--clone-protocol muss https oder ssh sein.")
    if timeout < 1:
        raise ForgeError("--api-timeout muss mindestens 1 sein.")
    if visibility in {"private", "all"} and not token:
        raise ForgeError("Für --visibility private oder all ist ein Token über --token-env erforderlich.")
    base, quoted = _api_base(forge, base_url), quote(account, safe="")
    if forge == "github":
        try:
            rows = _pages(f"users/{quoted}/repos?type=owner", forge=forge, base=base, token=token, timeout=timeout, opener=opener, pagination="github")
        except ForgeError as exc:
            if "HTTP 404" not in str(exc):
                raise
            rows = _pages(f"orgs/{quoted}/repos?type=all", forge=forge, base=base, token=token, timeout=timeout, opener=opener, pagination="github")
        if visibility != "public":
            own = _pages("user/repos?affiliation=owner&visibility=all", forge=forge, base=base, token=token, timeout=timeout, opener=opener, pagination="github")
            rows.extend(row for row in own if str((row.get("owner") or {}).get("login", "")).casefold() == account.casefold())
    elif forge == "gitlab":
        users, _ = _get_json(urljoin(base, f"users?{urlencode({'username': account})}"), forge=forge, token=token, timeout=timeout, opener=opener)
        if not isinstance(users, list) or not users or not isinstance(users[0], dict) or not isinstance(users[0].get("id"), int):
            raise ForgeError(f"GitLab-Account nicht gefunden: {account}")
        rows = _pages(f"users/{users[0]['id']}/projects?simple=true&owned=true", forge=forge, base=base, token=token, timeout=timeout, opener=opener, pagination="gitlab")
    else:
        rows = _pages(f"api/v1/users/{quoted}/repos", forge=forge, base=base, token=token, timeout=timeout, opener=opener, pagination="simple")
        if visibility != "public":
            own = _pages("api/v1/user/repos", forge=forge, base=base, token=token, timeout=timeout, opener=opener, pagination="simple")
            rows.extend(row for row in own if str((row.get("owner") or {}).get("login", "")).casefold() == account.casefold())
    return _normalise(rows, forge=forge, protocol=protocol, visibility=visibility, include_forks=include_forks)


def discover_starred_repositories(
    forge: str, account: str, *, base_url: str | None = None, token: str | None = None,
    visibility: str = "public", include_forks: bool = False, protocol: str = "https",
    timeout: int = 30, opener: JsonOpener = urlopen,
) -> list[dict[str, str]]:
    """List repositories visibly starred by one explicitly chosen account.

    Stars are a user's bookmarks, not evidence of contribution, endorsement, or
    collaboration.  GitHub and GitLab expose a documented endpoint for this.
    """
    forge, account = forge.casefold(), account.strip()
    if forge not in {"github", "gitlab"}:
        raise ForgeError("Favorisierte Repositories werden derzeit nur für GitHub und GitLab unterstützt.")
    if not account:
        raise ForgeError("--account darf nicht leer sein.")
    if visibility not in {"public", "private", "all"}:
        raise ForgeError("--visibility muss public, private oder all sein.")
    if protocol not in {"https", "ssh"}:
        raise ForgeError("--clone-protocol muss https oder ssh sein.")
    if timeout < 1:
        raise ForgeError("--api-timeout muss mindestens 1 sein.")
    if visibility in {"private", "all"} and not token:
        raise ForgeError("Für --visibility private oder all ist ein Token über --token-env erforderlich.")
    base, quoted = _api_base(forge, base_url), quote(account, safe="")
    if forge == "github":
        rows = _pages(
            f"users/{quoted}/starred?sort=created&direction=desc",
            forge=forge, base=base, token=token, timeout=timeout, opener=opener,
            pagination="github",
        )
    else:
        rows = _pages(
            f"users/{quoted}/starred_projects?simple=true",
            forge=forge, base=base, token=token, timeout=timeout, opener=opener,
            pagination="gitlab",
        )
    return _normalise(rows, forge=forge, protocol=protocol, visibility=visibility, include_forks=include_forks)
