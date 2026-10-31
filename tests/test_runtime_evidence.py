from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from skyrim_forge import telemetry, vfs_sandbox
from skyrim_forge.util import json_dump


class TelemetryTests(unittest.TestCase):
    def test_self_test(self):
        self.assertEqual(telemetry.self_test()["result"], "PASS")

    def test_warning_is_promoted_only_by_matching_row(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            mod = root / "mod"
            mod.mkdir()
            (mod / "test_DISTR.ini").write_text("Perk = 0x1~A.esp|||12(20)|||100\n", encoding="utf-8")
            logs = root / "logs"
            logs.mkdir()
            (logs / "po3_SpellPerkItemDistributor.log").write_text(
                "[info] loaded test_DISTR.ini: 1 entries\n[info] test_DISTR.ini:1 distributed 3 records\n", encoding="utf-8")
            report = telemetry.correlate(mod, logs)
            row = report["findings"][0]
            self.assertEqual(row["runtime_status"], "RUNTIME_VERIFIED_PASS")
            self.assertTrue(row["promoted"])
            self.assertEqual(row["log_evidence"][0]["log"], "po3_SpellPerkItemDistributor.log")
            self.assertEqual(report["status_counts"]["RUNTIME_VERIFIED_PASS"], 1)

    def test_unmatched_rows_stay_unverified(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            mod = root / "mod"
            mod.mkdir()
            (mod / "test_DISTR.ini").write_text("Perk = 0x1~A.esp|||12(20)|||100\n", encoding="utf-8")
            logs = root / "logs"
            logs.mkdir()
            (logs / "po3_SpellPerkItemDistributor.log").write_text("[info] loaded something else\n", encoding="utf-8")
            report = telemetry.correlate(mod, logs)
            self.assertEqual(report["findings"][0]["runtime_status"], "UNVERIFIED")
            self.assertFalse(report["findings"][0]["promoted"])


class SandboxInstallTests(unittest.TestCase):
    def test_self_test(self):
        self.assertEqual(vfs_sandbox.self_test()["result"], "PASS")

    def test_receipt_records_checks_and_evidence_boundary(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "source" / "Core" / "SKSE" / "Plugins"
            source.mkdir(parents=True)
            (source / "fixture.dll").write_bytes(b"dll")
            plan = {"schema": "skyrim-forge-fomod-plan/1", "module": {"name": "Fixture", "version": "1.0.0"},
                    "required_files": [{"kind": "folder", "source": "Core", "destination": "", "always_install": True}],
                    "strict_coverage": True}
            plan_path = root / "plan.json"
            json_dump(plan_path, plan)
            report = vfs_sandbox.test_install(plan_path, root / "source", root / "workspace", approved=True)
            receipt = json.loads(Path(report["receipt"]).read_text(encoding="utf-8"))
            self.assertEqual(receipt["schema"], "skyrim-forge-install-verification/1")
            self.assertEqual(receipt["result"], "PASS")
            self.assertIn("no Data/Data nesting", receipt["checks"])
            self.assertIn("No MO2, Vortex, USVFS", receipt["evidence"])


if __name__ == "__main__":
    unittest.main()
