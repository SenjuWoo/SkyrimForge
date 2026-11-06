"""The freshness report is read-only and degrades to UNKNOWN without network."""
from __future__ import annotations

import unittest

from scripts import check_freshness


class FreshnessTests(unittest.TestCase):
    def test_offline_report_names_every_pin_without_claiming_a_latest(self) -> None:
        result = check_freshness.report(online=False)
        names = {item["name"] for item in result["items"]}
        self.assertTrue({"forge", "houseCARL", "CommonLibSSE-NG", "vcpkg", "Go", "MCP"} <= names)
        self.assertTrue(all(item["status"] == "UNKNOWN" for item in result["items"]))
        self.assertIn("never changes a pin", result["note"])

    def test_report_never_writes_a_pin_file(self) -> None:
        before = (check_freshness.ROOT / "integrations/skyrim-pack/housecarl-pin.json").read_bytes()
        check_freshness.report(online=False)
        self.assertEqual((check_freshness.ROOT / "integrations/skyrim-pack/housecarl-pin.json").read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
