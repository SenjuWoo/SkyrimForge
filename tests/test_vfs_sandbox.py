"""FOMOD sandbox regressions: per-run isolation, budget preflight, honest coverage."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from skyrim_forge import vfs_sandbox
from skyrim_forge.errors import SafetyError, ValidationError


def _plugin(name: str, folder: str, destination: str, kind: str = "Optional") -> dict:
    return {"name": name, "description": name, "type": kind,
            "files": [{"kind": "folder", "source": folder, "destination": destination}]}


def _plan(*, with_select_any: bool = False) -> dict:
    steps = [{
        "name": "Visuals",
        "groups": [{
            "name": "Style", "type": "SelectExactlyOne",
            "plugins": [_plugin("Red", "10 Red", "red", "Recommended"), _plugin("Blue", "20 Blue", "blue")],
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

    def test_unenumerated_required_group_cannot_pass_with_zero_branches(self) -> None:
        plan_data = _plan()
        plan_data["steps"][0]["groups"][0]["type"] = "SelectAtLeastOne"
        for plugin in plan_data["steps"][0]["groups"][0]["plugins"]:
            plugin["type"] = "Optional"
        plan = self._write(plan_data)
        receipt = vfs_sandbox.test_install(plan, self.source, self.workspace, approved=True, all_branches=True)
        self.assertNotEqual(receipt["result"], "PASS")
        self.assertEqual(receipt["branch_counts"]["passed"], 0)
        self.assertGreater(receipt["branch_counts"]["failed"], 0)
        self.assertIn("SelectAtLeastOne", receipt["coverage"]["group_types_uncovered"])

    def test_covered_pass_plus_unenumerated_group_is_partial(self) -> None:
        plan_data = _plan()
        plan_data["steps"].append({"name": "Extras", "groups": [{
            "name": "Patch", "type": "SelectAny",
            "plugins": [{"name": "Patch", "description": "no payload", "files": []}]}]})
        plan = self._write(plan_data)
        receipt = vfs_sandbox.test_install(plan, self.source, self.workspace, approved=True, all_branches=True)
        self.assertEqual(receipt["result"], "PARTIAL")
        self.assertGreaterEqual(receipt["branch_counts"]["passed"], 1)

    def test_unknown_selection_cannot_pass(self) -> None:
        plan = self._write(_plan())
        receipt = vfs_sandbox.test_install(plan, self.source, self.workspace, approved=True,
                                           selections={"Visuals/Style": "DoesNotExist"})
        self.assertEqual(receipt["result"], "FAIL")
        self.assertEqual(receipt["branch_counts"]["failed"], 1)
        self.assertTrue(any("unknown plugin" in error for error in receipt["branches"][0]["errors"]))
        self.assertEqual(receipt["file_copies"], 0)

    def test_all_branches_tests_the_real_empty_choice(self) -> None:
        plan_data = _plan()
        plan_data["steps"][0]["groups"][0]["type"] = "SelectAtMostOne"
        plan_data["steps"][0]["groups"][0]["plugins"][0]["type"] = "Recommended"
        plan = self._write(plan_data)
        receipt = vfs_sandbox.test_install(plan, self.source, self.workspace, approved=True, all_branches=True)
        self.assertEqual(receipt["result"], "PASS", receipt["branches"])
        self.assertEqual([row["selected_plugins"] for row in receipt["branches"]],
                         [["Visuals/Style/Red"], ["Visuals/Style/Blue"], []])

    def test_required_plugin_makes_a_combination_infeasible_not_failed(self) -> None:
        plan_data = _plan()
        plan_data["steps"][0]["groups"][0]["plugins"][0]["type"] = "Required"
        plan = self._write(plan_data)
        receipt = vfs_sandbox.test_install(plan, self.source, self.workspace, approved=True, all_branches=True)
        self.assertEqual(receipt["result"], "PASS")
        self.assertEqual(receipt["branch_counts"]["infeasible"], 1)
        self.assertEqual(receipt["branch_counts"]["failed"], 0)

    def test_selections_and_all_branches_together_are_rejected(self) -> None:
        plan = self._write(_plan())
        with self.assertRaises(ValidationError):
            vfs_sandbox.test_install(plan, self.source, self.workspace, approved=True,
                                     selections={"Visuals/Style": "Red"}, all_branches=True)

    def test_single_branch_receipt_counts_planned_bytes(self) -> None:
        plan = self._write(_plan())
        receipt = vfs_sandbox.test_install(plan, self.source, self.workspace, approved=True)
        self.assertEqual(receipt["result"], "PASS")
        self.assertEqual(receipt["budget"]["planned_files"], 4)
        self.assertEqual(receipt["file_copies"], 4)


if __name__ == "__main__":
    unittest.main()
