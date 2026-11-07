from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from skyrim_forge.quality import audit, plan, self_test


class QualityTests(unittest.TestCase):
    def test_self_test(self):
        self.assertEqual(self_test()["result"], "PASS")

    def test_plan_is_task_specific(self):
        papyrus = plan(["papyrus"])
        texture = plan(["texture"])
        self.assertIn("performance", papyrus["dimensions"])
        self.assertNotIn("assets", papyrus["dimensions"])
        self.assertIn("assets", texture["dimensions"])
        self.assertNotIn("native" if False else "save_safety", texture["dimensions"])

    def test_pass_without_evidence_is_downgraded(self):
        dimensions = plan(["framework"])["dimensions"]
        report = audit({"mod_types": ["framework"], "checks": {
            item: {"status": "PASS", "evidence": []} for item in dimensions}})
        self.assertEqual(report["verdict"], "FAIL")
        self.assertTrue(all(row["status"] == "FAIL" for row in report["dimensions"].values()))

    def test_complete_report_passes(self):
        dimensions = plan(["texture"])["dimensions"]
        report = audit({"mod_types": ["texture"], "checks": {
            "functional": {"status": "PASS", "evidence": ["load order"]},
            "assets": {"status": "PASS", "evidence": ["DDS inspection"]},
            "performance": {"status": "NOT_APPLICABLE", "notes": "No performance claim."},
            "installation": {"status": "PASS", "evidence": ["branch extraction"]},
            "reproducibility": {"status": "PASS", "evidence": ["two ZIP hashes"]},
            "publication": {"status": "PASS", "evidence": ["rights inventory"]},
        }})
        self.assertEqual(report["verdict"], "PASS")
        self.assertEqual(set(report["dimensions"]), set(dimensions))
        self.assertNotIn("score", report)

    def test_missing_dimension_is_unverified(self):
        report = audit({"mod_types": ["package"], "checks": {
            "installation": {"status": "PASS", "evidence": ["install receipt"]},
            "reproducibility": {"status": "PASS", "evidence": ["hash"]},
        }})
        self.assertEqual(report["verdict"], "UNVERIFIED")
        self.assertEqual(report["result"], "PARTIAL")
        self.assertEqual(report["dimensions"]["publication"]["status"], "NOT_RUN")

    def test_not_applicable_needs_reason(self):
        report = audit({"mod_types": ["framework"], "checks": {
            "functional": {"status": "NOT_APPLICABLE"},
        }})
        self.assertEqual(report["dimensions"]["functional"]["status"], "FAIL")

    def test_unknown_mod_type_rejected(self):
        with self.assertRaises(Exception):
            plan(["not-a-mod-type"])

    def test_schema_file_is_valid_json(self):
        schema = json.loads((ROOT / "skyrim_forge" / "schemas" / "quality-report.schema.json").read_text(encoding="utf-8"))
        self.assertIn("mod_types", schema["required"])


if __name__ == "__main__":
    unittest.main()
