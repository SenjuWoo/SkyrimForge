"""Windows path rules for FOMOD plans, and no leftover run dir on preflight failure."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from skyrim_forge import vfs_sandbox
from skyrim_forge.errors import ValidationError
from skyrim_forge.fomod import validate_plan_data


def _plan(destination: str, source: str = "Core") -> dict:
    return {
        "schema": "skyrim-forge-fomod-plan/1",
        "module": {"name": "Paths", "version": "1.0.0"},
        "required_files": [{"kind": "folder", "source": source, "destination": destination, "always_install": True}],
    }


class WindowsPathTests(unittest.TestCase):
    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.root = Path(self._td.name)
        self.source = self.root / "source" / "Core"
        self.source.mkdir(parents=True)
        (self.source / "payload.txt").write_text("x", encoding="utf-8")

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_reproduced_invalid_destinations_are_rejected(self) -> None:
        for destination in ("Textures/normal:stream.dds", "SKSE/Plugins/CON.dll", "Meshes/folder./model.nif"):
            with self.subTest(destination=destination):
                with self.assertRaises(ValidationError):
                    validate_plan_data(_plan(destination), self.root / "source")

    def test_invalid_source_component_is_rejected(self) -> None:
        bad = self.root / "source" / "CON"
        bad.mkdir()
        (bad / "payload.txt").write_text("x", encoding="utf-8")
        with self.assertRaises(ValidationError):
            validate_plan_data(_plan("", source="CON"), self.root / "source")

    def test_legitimate_names_still_validate(self) -> None:
        plan = validate_plan_data(_plan("Textures/Actors/Character Assets/Normal.dds"), self.root / "source")
        self.assertEqual(plan["required_files"][0]["destination"], "Textures/Actors/Character Assets/Normal.dds")

    def test_branch_cap_failure_leaves_no_run_directory(self) -> None:
        plan = _plan("")
        plan["steps"] = [{
            "name": f"Step {index}", "groups": [{
                "name": "Choice", "type": "SelectExactlyOne",
                "plugins": [{"name": "A", "description": "a", "files": []},
                            {"name": "B", "description": "b", "files": []}],
            }],
        } for index in range(7)]
        plan_path = self.root / "plan.json"
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        workspace = self.root / "workspace"
        with self.assertRaises(ValidationError):
            vfs_sandbox.test_install(plan_path, self.root / "source", workspace, approved=True, all_branches=True)
        sandbox = workspace / ".forge" / "vfs-sandbox"
        self.assertEqual(list(sandbox.iterdir()) if sandbox.exists() else [], [])


if __name__ == "__main__":
    unittest.main()
