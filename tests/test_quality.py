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

SUBJECT = "fixture-mod"
VERIFIER = {
    "functional": ("lint", "framework-source"),
    "compatibility": ("lint", "framework-source"),
    "conflicts": ("framework-plan-validate", "framework-plan"),
    "installation": ("framework-build", "framework-build"),
    "reproducibility": ("framework-build", "framework-build"),
    "publication": ("release-validate", "release-package"),
    "assets": ("texture-inspect", "texture-file"),
}


class QualityTests(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.artifacts = Path(self._temp.name)

    def tearDown(self):
        self._temp.cleanup()

    def _receipt(self, name: str, dimension: str, *, subject: str = SUBJECT,
                 tool: str | None = None, scope: str | None = None) -> dict[str, str]:
        default_tool, default_scope = VERIFIER[dimension]
        tool = tool or default_tool
        scope = scope or default_scope
        path = self.artifacts / f"{name}.json"
        path.write_text(json.dumps({"schema": "skyrim-forge-quality-evidence/1", "tool": tool,
                                    "dimension": dimension, "subject": subject, "scope": scope,
                                    "result": "PASS"}), encoding="utf-8")
        return {"type": "forge-tool", "tool": tool, "dimension": dimension, "subject": subject,
                "scope": scope, "result": "PASS", "artifact": str(path),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

    def _report(self, checks: dict[str, dict]) -> dict:
        return audit({"mod_types": ["texture"], "subject": SUBJECT, "checks": checks})

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
        checks = {
            "functional": {"status": "PASS", "evidence": [self._receipt("functional", "functional")]},
            "assets": {"status": "PASS", "evidence": [self._receipt("assets", "assets")]},
            "performance": {"status": "NOT_APPLICABLE", "notes": "No performance-sensitive claim."},
            "installation": {"status": "PASS", "evidence": [self._receipt("installation", "installation")]},
            "reproducibility": {"status": "PASS", "evidence": [self._receipt("reproducibility", "reproducibility")]},
            "publication": {"status": "PASS", "evidence": [self._receipt("publication", "publication")]},
        }
        report = self._report(checks)
        self.assertEqual(report["verdict"], "PASS")
        self.assertFalse(report["runtime_verified"])
        self.assertEqual(set(report["dimensions"]), set(plan(["texture"])["dimensions"]))
        self.assertNotIn("score", report)

    def test_arbitrary_text_never_proves_pass(self):
        dimensions = plan(["papyrus"])["dimensions"]
        report = audit({"mod_types": ["papyrus"], "checks": {
            item: {"status": "PASS", "evidence": ["trust me"]} for item in dimensions}})
        self.assertEqual(report["verdict"], "REVIEW_REQUIRED")
        self.assertEqual(report["result"], "PARTIAL")

    def test_all_not_applicable_cannot_pass(self):
        dimensions = plan(["papyrus"])["dimensions"]
        report = audit({"mod_types": ["papyrus"], "checks": {
            item: {"status": "NOT_APPLICABLE", "notes": "No applicable evidence for this build."} for item in dimensions}})
        self.assertNotEqual(report["verdict"], "PASS")

    def test_tool_receipt_must_match_artifact_hash(self):
        receipt = self._receipt("tampered", "functional")
        receipt["sha256"] = "0" * 64
        report = self._report({"functional": {"status": "PASS", "evidence": [receipt]}})
        self.assertNotEqual(report["verdict"], "PASS")

    def test_fabricated_readme_receipt_does_not_pass(self):
        artifact = (ROOT / "README.md").resolve()
        receipt = {"type": "forge-tool", "tool": "totally-invented-verifier", "dimension": "functional",
                   "subject": SUBJECT, "scope": "framework-source", "result": "PASS", "artifact": str(artifact),
                   "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest()}
        report = audit({"mod_types": ["papyrus"], "subject": SUBJECT, "checks": {
            item: {"status": "PASS", "evidence": [dict(receipt)]}
            for item in plan(["papyrus"])["dimensions"]}})
        self.assertNotEqual(report["verdict"], "PASS")

    def test_repository_validation_is_not_universal_proof(self):
        artifact = (ROOT / "VALIDATION.json").resolve()
        receipt = {"type": "forge-tool", "tool": "lint", "dimension": "functional", "subject": SUBJECT,
                   "scope": "framework-source", "result": "PASS", "artifact": str(artifact),
                   "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest()}
        report = audit({"mod_types": ["papyrus"], "subject": SUBJECT, "checks": {
            item: {"status": "PASS", "evidence": [dict(receipt)]}
            for item in plan(["papyrus"])["dimensions"]}})
        self.assertNotEqual(report["verdict"], "PASS")

    def test_bare_result_json_does_not_establish_verification(self):
        artifact = self.artifacts / "bare.json"
        artifact.write_text(json.dumps({"result": "PASS"}), encoding="utf-8")
        receipt = {"type": "forge-tool", "tool": "lint", "dimension": "functional", "subject": SUBJECT,
                   "scope": "framework-source", "result": "PASS", "artifact": str(artifact),
                   "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest()}
        report = self._report({"functional": {"status": "PASS", "evidence": [receipt]}})
        self.assertNotEqual(report["verdict"], "PASS")

    def test_artifact_result_must_agree_with_receipt(self):
        receipt = self._receipt("failed-artifact", "functional")
        artifact = Path(receipt["artifact"])
        artifact.write_text(json.dumps({"schema": "skyrim-forge-quality-evidence/1", "tool": "lint",
                                        "dimension": "functional", "subject": SUBJECT,
                                        "scope": "framework-source", "result": "FAIL"}), encoding="utf-8")
        receipt["sha256"] = hashlib.sha256(artifact.read_bytes()).hexdigest()
        report = self._report({"functional": {"status": "PASS", "evidence": [receipt]}})
        self.assertNotEqual(report["verdict"], "PASS")

    def test_result_cannot_be_reused_for_unrelated_dimension(self):
        receipt = self._receipt("functional-reuse", "functional")
        receipt["dimension"] = "assets"
        receipt["tool"] = "texture-inspect"
        receipt["scope"] = "texture-file"
        report = self._report({"assets": {"status": "PASS", "evidence": [receipt]}})
        self.assertNotEqual(report["verdict"], "PASS")

    def test_subject_must_match_report(self):
        receipt = self._receipt("other-subject", "functional", subject="a-different-mod")
        report = self._report({"functional": {"status": "PASS", "evidence": [receipt]}})
        self.assertNotEqual(report["verdict"], "PASS")

    def test_scope_must_be_supported_by_verifier(self):
        receipt = self._receipt("bad-scope", "functional", scope="release-package")
        report = self._report({"functional": {"status": "PASS", "evidence": [receipt]}})
        self.assertNotEqual(report["verdict"], "PASS")

    def test_missing_dimension_is_unverified(self):
        report = audit({"mod_types": ["package"], "checks": {
            "installation": {"status": "PASS", "evidence": ["install receipt"]},
            "reproducibility": {"status": "PASS", "evidence": ["hash"]},
        }})
        self.assertEqual(report["verdict"], "UNVERIFIED")
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
