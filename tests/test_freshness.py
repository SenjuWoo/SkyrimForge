"""The freshness report is read-only and degrades to UNKNOWN without network."""
from __future__ import annotations

import unittest

from scripts import check_freshness


class FreshnessTests(unittest.TestCase):
    def test_offline_report_names_every_pin_without_claiming_a_latest(self) -> None:
        result = check_freshness.report(online=False)
        names = {item["name"] for item in result["items"]}
        self.assertTrue({"forge", "houseCARL", "CommonLibSSE-NG", "vcpkg", "Go", "MCP"} <= names)
        statuses = {item["status"] for item in result["items"]}
        self.assertTrue(statuses <= {"NOT_CHECKED", "PINNED_COMMIT", "UNKNOWN"}, statuses)
        self.assertFalse(any(item["status"] == "CURRENT" for item in result["items"]))
        self.assertIn("never changes a pin", result["note"])

    def test_classification_never_invents_freshness(self) -> None:
        self.assertEqual(check_freshness.classify("houseCARL", "2.1.2", {"latest": "2.1.2"})[0], "CURRENT")
        self.assertEqual(check_freshness.classify("houseCARL", "2.1.2", {"latest": "2.1.3"})[0], "DRIFT")
        self.assertEqual(check_freshness.classify("houseCARL", "2.1.2", {"latest": "unknown"})[0], "UNKNOWN")
        self.assertEqual(check_freshness.classify("houseCARL", "2.1.2", {"error": "HTTPError"})[0], "ERROR")
        self.assertEqual(check_freshness.classify("houseCARL", "2.1.2", {"malformed": "bad url"})[0], "MALFORMED")
        self.assertEqual(check_freshness.classify("vcpkg", "00c5775", {"latest": "2026.10.16"})[0], "PINNED_COMMIT")
        self.assertEqual(check_freshness.classify("MCP", "2026-07-28", None)[0], "NOT_CHECKED")
        self.assertEqual(check_freshness.classify("houseCARL", "2.1.2", None)[0], "NOT_CHECKED")

    def test_report_never_writes_a_pin_file(self) -> None:
        before = (check_freshness.ROOT / "integrations/skyrim-pack/housecarl-pin.json").read_bytes()
        check_freshness.report(online=False)
        self.assertEqual((check_freshness.ROOT / "integrations/skyrim-pack/housecarl-pin.json").read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
