from __future__ import annotations

import json
import unittest
from email.message import Message
from urllib.error import HTTPError

from gitanalytics.forge import ForgeError, discover_account_repositories, discover_starred_repositories


class _Response:
    def __init__(self, payload: object, headers: dict[str, str] | None = None) -> None:
        self._payload = json.dumps(payload).encode("utf-8")
        self.headers = Message()
        for key, value in (headers or {}).items():
            self.headers[key] = value

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *args: object) -> None:
        return None


class ForgeDiscoveryTests(unittest.TestCase):
    def test_github_public_repositories_exclude_private_and_forks(self) -> None:
        def opener(request: object, *, timeout: int) -> _Response:
            url = request.full_url  # type: ignore[attr-defined]
            self.assertIn("users/alice/repos", url)
            self.assertEqual(timeout, 30)
            return _Response([
                {"full_name": "alice/public", "clone_url": "https://github.com/alice/public.git"},
                {"full_name": "alice/private", "private": True, "clone_url": "https://github.com/alice/private.git"},
                {"full_name": "alice/fork", "fork": True, "clone_url": "https://github.com/alice/fork.git"},
            ])

        rows = discover_account_repositories("github", "alice", opener=opener)
        self.assertEqual(rows, [{
            "source": "https://github.com/alice/public.git", "name": "alice/public",
            "visibility": "public", "fork": "no", "forge": "github",
        }])

    def test_private_discovery_requires_token(self) -> None:
        with self.assertRaises(ForgeError):
            discover_account_repositories("github", "alice", visibility="all")

    def test_gitea_needs_explicit_base_url(self) -> None:
        with self.assertRaises(ForgeError):
            discover_account_repositories("gitea", "alice")

    def test_github_organisation_is_used_after_user_not_found(self) -> None:
        def opener(request: object, *, timeout: int) -> _Response:
            url = request.full_url  # type: ignore[attr-defined]
            if "users/acme/repos" in url:
                raise HTTPError(url, 404, "not found", Message(), None)
            self.assertIn("orgs/acme/repos", url)
            return _Response([{"full_name": "acme/tool", "clone_url": "https://github.com/acme/tool.git"}])

        rows = discover_account_repositories("github", "acme", opener=opener)
        self.assertEqual([row["name"] for row in rows], ["acme/tool"])

    def test_github_starred_repositories_are_listed_without_forks(self) -> None:
        def opener(request: object, *, timeout: int) -> _Response:
            url = request.full_url  # type: ignore[attr-defined]
            self.assertIn("users/alice/starred", url)
            return _Response([
                {"full_name": "org/tool", "clone_url": "https://github.com/org/tool.git"},
                {"full_name": "alice/fork", "fork": True, "clone_url": "https://github.com/alice/fork.git"},
            ])

        rows = discover_starred_repositories("github", "alice", opener=opener)
        self.assertEqual(rows, [{
            "source": "https://github.com/org/tool.git", "name": "org/tool",
            "visibility": "public", "fork": "no", "forge": "github",
        }])

    def test_gitlab_starred_repositories_use_account_endpoint(self) -> None:
        def opener(request: object, *, timeout: int) -> _Response:
            url = request.full_url  # type: ignore[attr-defined]
            self.assertIn("users/alice/starred_projects", url)
            return _Response([{
                "path_with_namespace": "group/tool",
                "http_url_to_repo": "https://gitlab.com/group/tool.git",
                "visibility": "public",
            }])

        rows = discover_starred_repositories("gitlab", "alice", opener=opener)
        self.assertEqual([row["source"] for row in rows], ["https://gitlab.com/group/tool.git"])

    def test_starred_repositories_reject_unsupported_forge(self) -> None:
        with self.assertRaises(ForgeError):
            discover_starred_repositories("gitea", "alice", base_url="https://git.example.org")


if __name__ == "__main__":
    unittest.main()
