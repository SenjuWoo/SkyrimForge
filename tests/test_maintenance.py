from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from skyrim_forge import maintenance
from skyrim_forge.config import ForgeConfig
from skyrim_forge.errors import SafetyError


def _write_vdf(steam: Path, libraries: list[Path]) -> None:
    """Write the minimal libraryfolders.vdf Steam actually produces."""
    (steam / "steamapps").mkdir(parents=True, exist_ok=True)
    lines = ['"libraryfolders"', "{"]
    for index, library in enumerate(libraries, start=1):
        lines += [f'	"{index}"', "	{", f'		"path"		"{str(library).replace(chr(92), chr(92) * 2)}"', "	}"]
    lines.append("}")
    (steam / "steamapps" / "libraryfolders.vdf").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _age(path: Path, days: float) -> None:
    stamp = time.time() - days * 86400
    os.utime(path, (stamp, stamp))


class MaintenanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.root = Path(self._td.name)
        self.workspace = self.root / "Workspaces"
        self.spills = self.workspace / ".forge" / "spills"
        self.sandbox = self.workspace / ".forge" / "vfs-sandbox"
        self.provider = self.root / "provider"
        self.backups = self.provider / ".skyrim-forge-skill-work"
        for path in (self.spills, self.sandbox / "old-run", self.sandbox / "new-run",
                     self.backups / f"backup-skill-{1:032x}", self.backups / f"backup-skill-{2:032x}"):
            path.mkdir(parents=True, exist_ok=True)
            (path / "payload.txt").write_text("x", encoding="utf-8")
        (self.spills / "old.json").write_text("{}", encoding="utf-8")
        (self.spills / "new.json").write_text("{}", encoding="utf-8")
        _age(self.spills / "old.json", 10)
        _age(self.sandbox / "old-run", 10)
        _age(self.backups / f"backup-skill-{2:032x}", 10)
        self.config = ForgeConfig(config_path=self.root / "config.toml", workspace_root=self.workspace,
                                  audit_log=self.root / "audit.log")
        self.config.config_path.write_text("[paths]\n", encoding="utf-8")

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_dry_run_lists_only_stale_owned_paths(self):
        report = maintenance.run(self.config, provider_homes=[self.provider], include_health=False, keep_backups=1)
        names = {Path(item["path"]).name for item in report["removals"]}
        self.assertEqual(names, {"old.json", "old-run", f"backup-skill-{2:032x}"})
        self.assertTrue((self.spills / "old.json").exists(), "dry-run must not delete")

    def test_apply_removes_planned_and_keeps_the_rest(self):
        report = maintenance.run(self.config, provider_homes=[self.provider], include_health=False, keep_backups=1)
        result = maintenance.run(self.config, provider_homes=[self.provider], include_health=False, keep_backups=1,
                                 apply_changes=True, approved=True)
        self.assertEqual(len(result["applied"]["removed"]), len(report["removals"]))
        self.assertFalse((self.spills / "old.json").exists())
        self.assertFalse((self.sandbox / "old-run").exists())
        self.assertTrue((self.spills / "new.json").exists())
        self.assertTrue((self.sandbox / "new-run").exists())
        self.assertTrue((self.backups / f"backup-skill-{1:032x}").exists())

    def test_apply_needs_approval(self):
        with self.assertRaises(SafetyError):
            maintenance.run(self.config, provider_homes=[self.provider], include_health=False, apply_changes=True)

    def test_refuses_a_path_outside_its_parent(self):
        with self.assertRaises(SafetyError):
            maintenance.apply(self.config, {"removals": [{"kind": "spill", "path": str(self.root / "outside.txt"), "files": 1, "bytes": 1}]})

    def test_missing_root_is_reported_and_replaced(self):
        library = self.root / "SteamLibrary"
        data = library / "steamapps" / "common" / "Skyrim Special Edition" / "Data"
        data.mkdir(parents=True)
        (data / "Skyrim.esm").write_bytes(b"TES4")
        steam = self.root / "Steam"
        (steam / "steamapps").mkdir(parents=True)
        (steam / "steamapps" / "libraryfolders.vdf").write_text(
            '"libraryfolders"\n{\n\t"1"\n\t{\n\t\t"path"\t\t"' + str(library).replace("\\", "\\\\") + '"\n\t}\n}\n', encoding="utf-8")
        self.config.skyrim_data = self.root / "gone" / "Data"
        rows = maintenance.root_report(self.config, steam_roots=[steam])
        row = next(item for item in rows if item["key"] == "skyrim_data")
        self.assertEqual(row["status"], "MOVED")
        self.assertEqual(Path(row["candidate"]), data)

        changed = maintenance.fix_roots(self.config, rows)
        self.assertEqual(changed["changed"][0]["key"], "skyrim_data")
        self.assertTrue((self.root / "config.toml").read_text(encoding="utf-8").count("SteamLibrary") >= 1)
        backup = Path(changed["backup"])
        self.assertTrue(backup.is_file() and backup.name.startswith("config.toml.bak-maintain-"))

    def test_add_roots_without_approval_refuses_and_leaves_config_alone(self):
        library = self.root / "SteamLibrary"
        data = library / "steamapps" / "common" / "Skyrim Special Edition" / "Data"
        data.mkdir(parents=True)
        (data / "Skyrim.esm").write_bytes(b"TES4")
        steam = self.root / "Steam"
        _write_vdf(steam, [library])
        self.config.skyrim_data = self.root / "gone" / "Data"
        before = self.config.config_path.read_text(encoding="utf-8")
        with self.assertRaises(SafetyError):
            maintenance.run(self.config, provider_homes=[self.provider], include_health=False,
                            steam_roots=[steam], add_roots=True, approved=False)
        self.assertEqual(self.config.config_path.read_text(encoding="utf-8"), before)
        self.assertEqual(self.config.skyrim_data, self.root / "gone" / "Data")

    def test_two_libraries_are_ambiguous_and_are_not_written(self):
        libraries = []
        for name in ("LibraryA", "LibraryB"):
            data = self.root / name / "steamapps" / "common" / "Skyrim Special Edition" / "Data"
            data.mkdir(parents=True)
            (data / "Skyrim.esm").write_bytes(b"TES4")
            libraries.append(self.root / name)
        steam = self.root / "Steam"
        _write_vdf(steam, libraries)
        self.config.skyrim_data = self.root / "gone" / "Data"
        rows = maintenance.root_report(self.config, steam_roots=[steam])
        row = next(item for item in rows if item["key"] == "skyrim_data")
        self.assertEqual(row["status"], "AMBIGUOUS")
        self.assertEqual(len(row["candidates"]), 2)
        before = self.config.config_path.read_text(encoding="utf-8")
        changed = maintenance.fix_roots(self.config, rows)
        self.assertEqual(changed["changed"], [])
        self.assertEqual(self.config.config_path.read_text(encoding="utf-8"), before)
        report = maintenance.run(self.config, provider_homes=[self.provider], include_health=False,
                                 steam_roots=[steam], add_roots=True, approved=True)
        self.assertEqual(report["result"], "WARN")
        self.assertEqual(report["roots_changed"], [])

    def test_relative_localappdata_cannot_create_a_relative_provider_root(self):
        with mock.patch.dict(os.environ, {"LOCALAPPDATA": "relative-root"}, clear=False):
            homes = maintenance.default_provider_homes()
        self.assertTrue(all(home.is_absolute() for home in homes))
        self.assertFalse(any(home.parts == ("hermes",) for home in homes))

    def test_explicit_empty_provider_list_means_none_not_defaults(self):
        self.assertEqual(maintenance._provider_backups(2, []), ([], 0))

    def test_missing_root_without_candidate_is_warn(self):
        self.config.skyrim_data = self.root / "gone" / "Data"
        report = maintenance.run(self.config, provider_homes=[self.provider], include_health=False, steam_roots=[self.root])
        self.assertEqual(report["result"], "WARN")


if __name__ == "__main__":
    unittest.main()
