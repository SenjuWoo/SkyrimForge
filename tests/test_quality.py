from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from skyrim_forge.quality import audit, plan, self_test


class QualityTests(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.artifacts = Path(self._temp.name)

    def tearDown(self):
        self._temp.cleanup()

    def _receipt(self, name: str, dimension: str = "functional", result: str = "PASS") -> dict[str, str]:
        path = self.artifacts / f"{name}.json"
        path.write_text(json.dumps({"result": result}), encoding="utf-8")
        return {"type": "forge-tool", "tool": "forge", "dimension": dimension, "result": result,
                "artifact": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

    def test_self_test(self):
        self.assertEqual(self_test()["result"], "PASS")

    def test_plan_is_task_specific(self):
        papyrus = plan(["papyrus"])
        texture = plan(["texture"])
        self.assertIn("performance", papyrus["dimensions"])
        self.assertNotIn("assets", papyrus["dimensions"])
        self.assertIn("assets", texture["dimensions"])
        self.assertNotIn("save_safety", texture["dimensions"])

    def test_pass_without_evidence_is_downgraded(self):
        dimensions = plan(["framework"])["dimensions"]
        report = audit({"mod_types": ["framework"], "checks": {
            item: {"status": "PASS", "evidence": []} for item in dimensions}})
        self.assertEqual(report["verdict"], "FAIL")
        self.assertTrue(all(row["status"] == "FAIL" for row in report["dimensions"].values()))

    def test_complete_verified_report_passes(self):
        dimensions = plan(["texture"])["dimensions"]
        report = audit({"mod_types": ["texture"], "checks": {
            "functional": {"status": "PASS", "evidence": [self._receipt("functional", "functional")]},
            "assets": {"status": "PASS", "evidence": [self._receipt("assets", "assets")]},
            "performance": {"status": "NOT_APPLICABLE", "notes": "No performance-sensitive claim."},
            "installation": {"status": "PASS", "evidence": [self._receipt("installation", "installation")]},
            "reproducibility": {"status": "PASS", "evidence": [self._receipt("reproducibility", "reproducibility")]},
            "publication": {"status": "PASS", "evidence": [self._receipt("publication", "publication")]},
        }})
        self.assertEqual(report["verdict"], "PASS")
        self.assertEqual(set(report["dimensions"]), set(dimensions))
        self.assertNotIn("score", report)

    def test_arbitrary_text_never_proves_pass(self):
        dimensions = plan(["papyrus"])["dimensions"]
        report = audit({"mod_types": ["papyrus"], "checks": {
            item: {"status": "PASS", "evidence": ["trust me"]} for item in dimensions}})
        self.assertEqual(report["verdict"], "REVIEW_REQUIRED")
        self.assertEqual(report["result"], "PARTIAL")
        self.assertTrue(all(row["evidence_kind"] == "self_reported" for row in report["dimensions"].values()))

    def test_all_not_applicable_cannot_pass(self):
        dimensions = plan(["papyrus"])["dimensions"]
        report = audit({"mod_types": ["papyrus"], "checks": {
            item: {"status": "NOT_APPLICABLE", "notes": "No applicable evidence for this build."} for item in dimensions}})
        self.assertNotEqual(report["verdict"], "PASS")
        self.assertNotEqual(report["result"], "PASS")
        self.assertIn(report["verdict"], {"FAIL", "INCOMPLETE", "REVIEW_REQUIRED", "UNVERIFIED"})

    def test_tool_receipt_must_match_artifact_hash(self):
        dimensions = plan(["framework"])["dimensions"]
        receipt = self._receipt("tampered", "functional")
        receipt["sha256"] = "0" * 64
        report = audit({"mod_types": ["framework"], "checks": {
            item: {"status": "PASS", "evidence": [dict(receipt)]} for item in dimensions}})
        self.assertNotEqual(report["verdict"], "PASS")

    def test_fabricated_readme_receipt_does_not_pass(self):
        artifact = (ROOT / "README.md").resolve()
        receipt = {"type": "forge-tool", "tool": "totally-invented-verifier", "dimension": "functional",
                   "result": "PASS", "artifact": str(artifact),
                   "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest()}
        report = audit({"mod_types": ["papyrus"], "checks": {
            item: {"status": "PASS", "evidence": [dict(receipt)]}
            for item in plan(["papyrus"])["dimensions"]}})
        self.assertNotEqual(report["verdict"], "PASS")

    def test_artifact_result_must_agree_with_receipt(self):
        dimensions = plan(["framework"])["dimensions"]
        receipt = self._receipt("failed-artifact", "functional", result="FAIL")
        receipt["result"] = "PASS"
        report = audit({"mod_types": ["framework"], "checks": {
            item: {"status": "PASS", "evidence": [dict(receipt)]} for item in dimensions}})
        self.assertNotEqual(report["verdict"], "PASS")

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

    def test_non_waivable_dimension_cannot_be_not_applicable(self):
        report = audit({"mod_types": ["framework"], "checks": {
            "functional": {"status": "NOT_APPLICABLE", "notes": "No functional testing was done."},
        }})
        self.assertEqual(report["dimensions"]["functional"]["status"], "FAIL")

    def test_unknown_mod_type_rejected(self):
        with self.assertRaises(Exception):
            plan(["not-a-mod-type"])

    def test_schema_file_accepts_tool_receipts(self):
        schema = json.loads((ROOT / "skyrim_forge" / "schemas" / "quality-report.schema.json").read_text(encoding="utf-8"))
        self.assertIn("mod_types", schema["required"])
        evidence = schema["properties"]["checks"]["additionalProperties"]["properties"]["evidence"]
        self.assertEqual(evidence["items"]["oneOf"][1]["properties"]["type"]["const"], "forge-tool")


if __name__ == "__main__":
    unittest.main()
