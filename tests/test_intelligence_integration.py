from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from skyrim_forge.config import load_config
from skyrim_forge.service import ForgeService

SUBJECT = "fixture-mod"
VERIFIER = {
    "functional": ("lint", "framework-source"),
    "compatibility": ("lint", "framework-source"),
    "conflicts": ("framework-plan-validate", "framework-plan"),
    "installation": ("framework-build", "framework-build"),
    "reproducibility": ("framework-build", "framework-build"),
    "publication": ("release-validate", "release-package"),
}


class IntelligenceIntegrationTests(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)
        self.workspace = self.root / "Workspaces"
        self.workspace.mkdir()
        self.data = self.root / "Data"
        self.data.mkdir()
        config = self.root / "config.toml"
        config.write_text(
            "[paths]\n"
            f'workspace_root = "{self.workspace.as_posix()}"\n'
            f'skyrim_data = "{self.data.as_posix()}"\n',
            encoding="utf-8",
        )
        self.service = ForgeService(load_config(config))

    def tearDown(self):
        self._temp.cleanup()

    def _json(self, name: str, payload: dict) -> Path:
        path = self.workspace / name
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def _receipt(self, name: str, dimension: str = "functional") -> dict[str, str]:
        tool, scope = VERIFIER[dimension]
        path = self.workspace / f"{name}.receipt.json"
        path.write_text(json.dumps({"schema": "skyrim-forge-quality-evidence/1", "tool": tool,
                                    "dimension": dimension, "subject": SUBJECT, "scope": scope,
                                    "result": "PASS"}), encoding="utf-8")
        return {"type": "forge-tool", "tool": tool, "dimension": dimension, "subject": SUBJECT,
                "scope": scope, "result": "PASS", "artifact": str(path),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

    def test_architecture_and_quality_workflow(self):
        request = self._json("request.json", {"description": "Distribute spells to NPCs with SPID"})
        architecture = self.service.architecture_recommend(str(request))
        self.assertEqual(architecture["recommendation"]["id"], "distribution.spid")
        plan = self.service.quality_plan(["framework"])
        self.assertIn("conflicts", plan["dimensions"])
        report = self._json("quality.json", {"mod_types": ["framework"], "subject": SUBJECT, "checks": {
            item: {"status": "PASS", "evidence": [self._receipt(f"quality-{item}", item)]} for item in plan["dimensions"]}})
        self.assertEqual(self.service.quality_audit(str(report))["verdict"], "PASS")

    def test_knowledge_status_and_lookup(self):
        status = self.service.knowledge_status()
        self.assertEqual(status["result"], "PASS")
        self.assertIn("entries", status)
        self.assertEqual(self.service.knowledge_lookup("not-real")["entry"]["status"], "UNKNOWN")

    def test_performance_ingest_and_compare(self):
        scenario = self._json("scenario.json", {
            "name": "fixture", "game_version": "1.6.1170", "load_order": "profile",
            "resolution": "1920x1080", "graphics_preset": "high", "hardware": "fixture gpu",
            "metric": "msBetweenPresents"})
        csv_path = self.workspace / "capture.csv"
        csv_path.write_text("Application,MsBetweenPresents\n" +
                            "\n".join(f"SkyrimSE.exe,{16.0 + i % 3}" for i in range(130)) + "\n",
                            encoding="utf-8")
        output = self.workspace / "imported.json"
        converted = self.service.performance_ingest(str(csv_path), str(output), str(scenario), True)
        self.assertEqual(converted["result"], "PASS")
        self.assertTrue(output.is_file())
        baseline = self._json("baseline.json", {
            "schema": "skyrim-forge-benchmark/1",
            "scenario": json.loads(scenario.read_text()) | {"source": "fixture"},
            "frames_ms": [16.0] * 130})
        candidate = self._json("candidate.json", {
            "schema": "skyrim-forge-benchmark/1",
            "scenario": json.loads(scenario.read_text()) | {"source": "fixture"},
            "frames_ms": [15.0] * 130})
        self.assertEqual(self.service.performance_compare(str(baseline), str(candidate))["verdict"], "IMPROVEMENT")

    def test_ingest_requires_approval(self):
        csv_path = self.workspace / "capture.csv"
        csv_path.write_text("MsBetweenPresents\n16\n", encoding="utf-8")
        scenario = self._json("scenario.json", {
            "name": "fixture", "game_version": "1.6.1170", "load_order": "profile",
            "resolution": "1920x1080", "graphics_preset": "high", "hardware": "fixture gpu",
            "metric": "msBetweenPresents"})
        with self.assertRaises(Exception):
            self.service.performance_ingest(str(csv_path), str(self.workspace / "out.json"), str(scenario), False)


if __name__ == "__main__":
    unittest.main()
