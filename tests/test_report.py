from __future__ import annotations

import json
import unittest

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


if __name__ == "__main__":
    unittest.main()
