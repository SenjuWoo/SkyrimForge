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
        self.assertEqual(check_freshness.classify("vcpkg", "0" * 40, {"latest": "2026.10.16"})[0], "PINNED_COMMIT")
        self.assertEqual(check_freshness.classify("MCP", "2026-07-28", None)[0], "NOT_CHECKED")
        self.assertEqual(check_freshness.classify("houseCARL", "2.1.2", None)[0], "NOT_CHECKED")

    def test_vcpkg_report_carries_both_real_pins(self) -> None:
        item = next(item for item in check_freshness.report(False)["items"] if item["name"] == "vcpkg")
        self.assertRegex(item["pinned"], r"^[0-9a-f]{40}$")
        self.assertEqual(item["sdk_ref"], "2026.10.16")
        self.assertRegex(item["sdk_commit"], r"^[0-9a-f]{40}$")
        self.assertNotIn("unknown", item["pinned"])

    def test_vcpkg_pins_are_read_from_their_own_sources(self) -> None:
        import json, tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "references").mkdir()
            (root / "references/NATIVE-SOURCE-LOCK.json").write_text(
                json.dumps({"commonlibsse_ng": {"vcpkg_baseline": "a" * 40}}), encoding="utf-8")
            (root / "references/SDK-LOCK.json").write_text(
                json.dumps({"sdks": [{"id": "vcpkg", "ref": "2026.10.16", "commit": "b" * 40}]}),
                encoding="utf-8")
            self.assertEqual(check_freshness.vcpkg_pins(root),
                             {"baseline": "a" * 40, "sdk_ref": "2026.10.16", "sdk_commit": "b" * 40})

    def test_malformed_vcpkg_baseline_is_unknown_not_healthy(self) -> None:
        self.assertEqual(check_freshness.classify("vcpkg", "", None)[0], "UNKNOWN")
        self.assertEqual(check_freshness.classify("vcpkg", "not-a-sha", None)[0], "UNKNOWN")

    def test_report_never_writes_a_pin_file(self) -> None:
        before = (check_freshness.ROOT / "integrations/skyrim-pack/housecarl-pin.json").read_bytes()
        check_freshness.report(online=False)
        self.assertEqual((check_freshness.ROOT / "integrations/skyrim-pack/housecarl-pin.json").read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
