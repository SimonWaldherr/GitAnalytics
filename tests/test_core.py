from __future__ import annotations

import datetime as dt
import tempfile
import unittest
from pathlib import Path

from gitanalytics.config import ConfigError, IdentityResolver, load_config, validate_config
from gitanalytics.discovery import DiscoveryError, assert_outputs_outside_repositories
from gitanalytics.languages import classify_path, top_directory
from gitanalytics.models import RepositoryLocation
from gitanalytics.privacy import classify_repository
from gitanalytics.util import longest_gap, longest_streak


class UtilityTests(unittest.TestCase):
    def test_streak_and_gap(self) -> None:
        days = [
            dt.date(2024, 1, 1),
            dt.date(2024, 1, 2),
            dt.date(2024, 1, 3),
            dt.date(2024, 1, 7),
        ]
        self.assertEqual(longest_streak(days), (3, days[0], days[2]))
        self.assertEqual(longest_gap(days), (3, days[2], days[3]))

    def test_languages(self) -> None:
        self.assertEqual(classify_path("src/app.py"), "Python")
        self.assertEqual(classify_path("types/index.d.ts"), "TypeScript")
        self.assertEqual(classify_path("Dockerfile"), "Dockerfile")
        self.assertEqual(top_directory("src/app.py"), "src")
        self.assertEqual(top_directory("README.md"), "[root]")

    def test_identity_alias_and_bot(self) -> None:
        config = load_config(None)
        config["identity"]["aliases"] = [
            {
                "name": "Alice",
                "email": "alice@example.com",
                "match_emails": ["alice@old.example", "*+alice@users.noreply.github.com"],
                "match_names": [],
            }
        ]
        resolver = IdentityResolver(config)
        identity = resolver.resolve("Alice Old", "alice@old.example")
        self.assertEqual(identity.name, "Alice")
        self.assertEqual(identity.email, "alice@example.com")
        self.assertFalse(identity.is_bot)
        self.assertTrue(resolver.resolve("dependabot[bot]", "bot@example.com").is_bot)

    def test_config_validation(self) -> None:
        config = load_config(None)
        config["history"]["scope"] = "unknown"
        with self.assertRaises(ConfigError):
            validate_config(config)

    def test_output_guard(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            with self.assertRaises(DiscoveryError):
                assert_outputs_outside_repositories([repo], [repo / "report"])
            assert_outputs_outside_repositories([repo], [Path(temporary) / "report"])

    def test_repository_privacy_rules_are_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "projects"
            location = RepositoryLocation(path=root / "open-source", root=root, display_name="open-source")
            config = load_config(None)
            self.assertEqual(classify_repository(location, config["privacy"]), "private")
            config["privacy"]["repository_rules"] = [
                {"match": "open-source", "classification": "public"},
                {"match": "*", "classification": "exclude"},
            ]
            self.assertEqual(classify_repository(location, config["privacy"]), "public")
            config["privacy"]["repository_rules"][0]["classification"] = "exclude"
            self.assertEqual(classify_repository(location, config["privacy"]), "exclude")


if __name__ == "__main__":
    unittest.main()
