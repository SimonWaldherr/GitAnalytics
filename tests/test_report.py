from __future__ import annotations

import json
import unittest

from gitanalytics.exports import write_markdown_report
from gitanalytics.report import render_html


class ReportTests(unittest.TestCase):
    def test_json_embedding_escapes_script_breakout(self) -> None:
        report = {
            "meta": {"title": "</script><script>alert(1)</script>"},
            "summary": {}, "insights": {}, "activity": {}, "contributors": {},
            "repositories": [], "code": {}, "releases": {}, "quality": {},
        }
        html = render_html(report)
        payload = html.split('<script id="gitanalytics-data" type="application/json">', 1)[1].split("</script>", 1)[0]
        self.assertNotIn("</script>", payload.lower())
        decoded = json.loads(payload)
        self.assertEqual(decoded["meta"]["title"], "</script><script>alert(1)</script>")

    def test_sortable_tables_expose_sort_state(self) -> None:
        html = render_html({
            "meta": {}, "summary": {}, "insights": {}, "activity": {}, "contributors": {},
            "repositories": [], "code": {}, "releases": {}, "quality": {},
        })
        self.assertIn('class="sort-ind">↕</span>', html)
        self.assertIn("th.setAttribute('aria-sort',asc?'ascending':'descending')", html)

    def test_dashboard_offers_main_and_master_branch_filter(self) -> None:
        html = render_html({
            "meta": {}, "summary": {}, "insights": {}, "activity": {}, "contributors": {},
            "repositories": [], "code": {}, "releases": {}, "quality": {},
        })
        self.assertIn('id="branch-filter"', html)
        self.assertIn('option value="main"', html)
        self.assertIn('option value="master"', html)
        self.assertIn("function branchMatch(repository)", html)

    def test_calendar_offers_multiple_activity_metrics(self) -> None:
        html = render_html({
            "meta": {}, "summary": {}, "insights": {}, "activity": {}, "contributors": {},
            "repositories": [], "code": {}, "releases": {}, "quality": {},
        })
        self.assertIn('id="calendar-metric"', html)
        self.assertIn('option value="churn"', html)
        self.assertIn('option value="repositories"', html)
        self.assertIn("function calendarValue(row,metric)", html)

    def test_markdown_report_escapes_table_values(self) -> None:
        from pathlib import Path
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            target = Path(directory) / "REPORT.md"
            write_markdown_report(target, {
                "meta": {"title": "A | B", "generated_at": "2026-07-20T10:00:00+00:00"},
                "summary": {"repositories": 1, "commits": 2, "authors": 1, "comment_density": 0.5},
                "repositories": [{"name": "api|core", "commits": 2, "authors": 1, "activity_status": "active"}],
                "contributors": {"rows": [{"name": "Alice", "commits": 2, "repositories": 1}]},
                "quality": {"warnings": ["Keine externen Daten"]},
            })
            content = target.read_text(encoding="utf-8")
        self.assertIn("# A \\| B", content)
        self.assertIn("api\\|core", content)
        self.assertIn("## Beitragende", content)


if __name__ == "__main__":
    unittest.main()
