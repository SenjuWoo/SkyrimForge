"""FOMOD sandbox regressions: per-run isolation, budget preflight, honest coverage."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from skyrim_forge import vfs_sandbox
from skyrim_forge.errors import SafetyError


def _plugin(name: str, folder: str, destination: str) -> dict:
    return {"name": name, "description": name,
            "files": [{"kind": "folder", "source": folder, "destination": destination}]}


def _plan(*, with_select_any: bool = False) -> dict:
    steps = [{
        "name": "Visuals",
        "groups": [{
            "name": "Style", "type": "SelectExactlyOne",
            "plugins": [_plugin("Red", "10 Red", "red"), _plugin("Blue", "20 Blue", "blue")],
        }],
    }]
    if with_select_any:
        steps.append({
            "name": "Extras",
            "groups": [{"name": "Patch", "type": "SelectAny", "plugins": [_plugin("Patch", "30 Patch", "patch")]}],
        })
    return {
        "schema": "skyrim-forge-fomod-plan/1",
        "module": {"name": "Sandbox Fixture", "version": "1.0.0"},
        "required_files": [{"kind": "folder", "source": "00 Core", "destination": "core", "always_install": True}],
        "steps": steps,
        "strict_coverage": True,
    }


class SandboxTests(unittest.TestCase):
    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.root = Path(self._td.name)
        self.source = self.root / "source"
        for folder in ("00 Core", "10 Red", "20 Blue"):
            target = self.source / folder
            target.mkdir(parents=True)
            (target / "payload.txt").write_text(folder, encoding="utf-8")
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()

    def tearDown(self) -> None:
        self._td.cleanup()

    def _write(self, plan: dict, name: str = "plan.json") -> Path:
        path = self.root / name
        path.write_text(json.dumps(plan), encoding="utf-8")
        return path

    def test_two_runs_in_the_same_second_do_not_share_a_directory(self) -> None:
        plan = self._write(_plan())
        first = vfs_sandbox.test_install(plan, self.source, self.workspace, approved=True)
        second = vfs_sandbox.test_install(plan, self.source, self.workspace, approved=True)
        self.assertNotEqual(first["sandbox"], second["sandbox"])
        self.assertTrue((Path(first["sandbox"]) / "install_verification_receipt.json").is_file())
        self.assertTrue((Path(second["sandbox"]) / "install_verification_receipt.json").is_file())
        self.assertTrue((Path(first["sandbox"]) / "branch-01" / "mo2").is_dir())
        self.assertFalse((Path(second["sandbox"]) / "branch-01" / "mo2" / "Sandbox Fixture" / "20 Blue").exists())

    def test_budget_is_checked_before_anything_is_copied(self) -> None:
        plan = self._write(_plan())
        with mock.patch.object(vfs_sandbox, "MAX_BYTES", 1):
            with self.assertRaises(SafetyError):
                vfs_sandbox.test_install(plan, self.source, self.workspace, approved=True)
        sandbox = self.workspace / ".forge" / "vfs-sandbox"
        self.assertEqual([p for p in sandbox.iterdir()] if sandbox.exists() else [], [])

    def test_all_branches_reports_the_group_types_it_does_not_enumerate(self) -> None:
        coverage = vfs_sandbox._coverage(_plan(with_select_any=True), all_branches=True)
        self.assertEqual(coverage["group_types_tested"], ["SelectExactlyOne"])
        self.assertEqual(coverage["group_types_uncovered"], ["SelectAny"])
        single = vfs_sandbox._coverage(_plan(with_select_any=True), all_branches=False)
        self.assertEqual(single["group_types_tested"], [])
        self.assertEqual(single["group_types_uncovered"], ["SelectAny", "SelectExactlyOne"])
        self.assertTrue(vfs_sandbox._coverage(_plan(), all_branches=False)["group_types_uncovered"])

    def test_single_branch_receipt_counts_planned_bytes(self) -> None:
        plan = self._write(_plan())
        receipt = vfs_sandbox.test_install(plan, self.source, self.workspace, approved=True)
        self.assertEqual(receipt["result"], "PASS")
        self.assertEqual(receipt["budget"]["planned_files"], 2)
        self.assertEqual(receipt["file_copies"], 2)


if __name__ == "__main__":
    unittest.main()
