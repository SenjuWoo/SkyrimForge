"""Native scaffold/build wiring to the pinned SDK vault; nothing is compiled or fetched."""
from pathlib import Path
from unittest.mock import patch
import json
import os
import tempfile
import unittest

from skyrim_forge.config import ForgeConfig, default_tools
from skyrim_forge.errors import SafetyError
from skyrim_forge.native import COMMONLIB, _commonlib_root, _msvc_environment, audit_project, scaffold
from skyrim_forge.sdk import load_lock

ROOT = Path(__file__).resolve().parents[1]
PLAN = {"schema": "skyrim-forge-native-plugin-plan/1", "project": "LinkPlugin", "display_name": "Link Plugin", "version": "1.0.0", "author": "T", "email": "", "description": "d", "minimum_skse_version": "0.0.0", "runtime_strategy": "address_library", "compatible_runtimes": [], "struct_dependent": False}


class LockAgreementTests(unittest.TestCase):
    def test_native_and_sdk_locks_pin_the_same_commonlib_commit(self):
        sdk = next(item for item in load_lock(ROOT / "references/SDK-LOCK.json")["sdks"] if item["id"] == COMMONLIB["sdk_id"])
        self.assertEqual(sdk["commit"], COMMONLIB["commit"])
        self.assertEqual(sdk["ref"], COMMONLIB["tag"])
        self.assertEqual((ROOT / "references/NATIVE-SOURCE-LOCK.json").read_bytes(), (ROOT / "skyrim_forge/references/NATIVE-SOURCE-LOCK.json").read_bytes())

    def test_scaffold_manifest_carries_every_locked_dependency(self):
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder); plan = work / "plan.json"; plan.write_text(json.dumps(PLAN))
            scaffold(plan, work / "project", work, approved=True)
            manifest = json.loads((work / "project" / "vcpkg.json").read_text())
            self.assertEqual(manifest["dependencies"], COMMONLIB["vcpkg_dependencies"])

    def test_audit_warns_but_does_not_fail_a_legacy_colorglass_project(self):
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder); plan = work / "plan.json"; plan.write_text(json.dumps(PLAN))
            scaffold(plan, work / "project", work, approved=True)
            (work / "project" / "vcpkg-configuration.json").write_text(json.dumps({"registries": [{"kind": "git", "repository": "https://gitlab.com/colorglass/vcpkg-colorglass", "baseline": "0" * 40, "packages": ["commonlibsse-ng"]}]}))
            report = audit_project(work / "project")
            self.assertEqual(report["result"], "PASS", report)
            self.assertTrue(any("colorglass" in warning for warning in report["warnings"]))


class BuildInputTests(unittest.TestCase):
    def test_build_refuses_when_the_sdk_is_not_the_pinned_checkout(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config = ForgeConfig(config_path=root / "c" / "config.toml", workspace_root=root / "ws", audit_log=root / "a.jsonl", tool_vault_root=root / "c" / "tool-vault", tools=default_tools())
            with self.assertRaisesRegex(SafetyError, "forge sdk-install"):
                _commonlib_root(config)

    @unittest.skipUnless(os.name == "nt", "vcvars64.bat is a Windows batch file")
    def test_msvc_environment_is_imported_from_vcvars_in_a_path_with_spaces(self):
        with tempfile.TemporaryDirectory() as folder:
            install = Path(folder) / "Fake VS (x86)" / "BuildTools"
            script = install / "VC" / "Auxiliary" / "Build" / "vcvars64.bat"
            script.parent.mkdir(parents=True)
            script.write_text("@echo off\r\nset FORGE_PROBE=imported\r\n", encoding="ascii")
            with patch("skyrim_forge.native.msvc_install_path", return_value=str(install)):
                environment = _msvc_environment()
            self.assertEqual(environment.get("FORGE_PROBE"), "imported")
            self.assertTrue(environment.get("PATH"))

    def test_msvc_environment_is_empty_without_visual_studio(self):
        with patch("skyrim_forge.native.msvc_install_path", return_value=""):
            self.assertEqual(_msvc_environment(), {})


if __name__ == "__main__":
    unittest.main()
