"""Release evidence must be byte-stable across runs; raw logs stay out of assets."""
from __future__ import annotations

import copy
import sys
import unittest
from unittest import mock

from scripts import validate_repository as validator


def raw_report(*, duration: str = "1.234", temp: str = "tmpab12", returncode: int = 0,
               error: str = "") -> dict:
    tests = f"Ran 3 tests in {duration}s\n\n{'FAILED' if returncode else 'OK'}\n{temp}"
    checks = {
        "files": {"file_count": 10, "counts": {"python": 2}},
        "powershell": {"result": "PASS", "findings": []},
        "python": {"compile": {"command": ["python", "-m", "compileall"], "returncode": 0, "stdout": "", "stderr": ""},
                   "tests": {"command": ["python", "-m", "unittest"], "returncode": returncode,
                             "stdout": "", "stderr": tests},
                   "self_test": {"command": ["python", "-m", "skyrim_forge", "self-test"], "returncode": 0,
                                 "stdout": "PASS", "stderr": ""},
                   "test_count": 3, "result": "PASS" if not returncode else "FAIL"},
        "native": {"hashes": {"linux": "a" * 64}, "result": "PASS"},
        "go": {"format": {"returncode": 0, "stdout": "", "stderr": ""},
               "vet": {"returncode": 0, "stdout": "", "stderr": ""},
               "tests": {"returncode": 0, "stdout": "", "stderr": ""},
               "race": {"returncode": 0, "stdout": "", "stderr": ""},
               "builds": {"linux": {"first": "b" * 64, "second": "b" * 64, "bundled": "b" * 64,
                                    "first_metadata": {"stdout": temp}, "result": "PASS"}},
               "result": "PASS"},
        "packaging": {"wheel": {"result": "PASS", "sha256": "c" * 64, "size": 1}},
        "sbom": {"result": "PASS", "files": 1, "relationships": 2, "violations": 0},
        "mcp": {"result": "PASS", "tools": 68, "protocols": ["2026-07-28"], "stderr": temp},
        "version": {"result": "PASS", "version": "1.2.3"},
    }
    return {"product": "Skyrim Forge", "version": "1.2.3", "scope": "full",
            "result": "PASS" if not returncode else "FAIL",
            "errors": [error] if error else [], "warnings": [], "checks": checks}


class ReleaseEvidenceTests(unittest.TestCase):
    def test_timing_and_temp_paths_do_not_change_evidence(self) -> None:
        first = validator.release_evidence(raw_report(duration="1.234", temp="tmpab12"))
        second = validator.release_evidence(raw_report(duration="9.876", temp="tmpzz99"))
        self.assertEqual(first, second)
        text = validator.json.dumps(first, sort_keys=True)
        self.assertNotIn("1.234", text)
        self.assertNotIn("tmpab12", text)

    def test_real_changes_remain_visible(self) -> None:
        passed = validator.release_evidence(raw_report())
        failed = validator.release_evidence(raw_report(returncode=1, error="Python unit tests failed"))
        self.assertNotEqual(passed, failed)
        self.assertEqual(failed["checks"]["python"]["tests"]["failures"], 0)
        self.assertIn("Python unit tests failed", failed["errors"])

    def test_full_scope_requires_every_check_to_have_passed(self) -> None:
        checks = {name: {"result": "PASS"} for name in validator.VALIDATION_SCOPES["full"]}
        checks["go"] = {"result": "NOT-RUN"}
        self.assertIn("go validation did not pass (NOT-RUN)",
                      validator.required_failures("full", checks))
        checks["go"] = {"result": "PASS"}
        checks["sbom"] = {"result": "NOT-RUN"}
        self.assertTrue(any("sbom" in item for item in validator.required_failures("full", checks)))
        self.assertEqual(validator.required_failures("python", checks), [])

    def test_missing_schema_validator_blocks_full_validation(self) -> None:
        errors: list[str] = []
        with mock.patch.dict(sys.modules, {"jsonschema": None}):
            result = validator.validate_sbom(errors)
        self.assertEqual(result["result"], "NOT-RUN")
        self.assertTrue(any("jsonschema" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
