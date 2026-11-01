from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts" / "Prune-ForgeBackups.ps1"
POWERSHELL = shutil.which("powershell") or shutil.which("pwsh")


def _backup(parent: Path, index: int, days_old: int, *, product: bool = True) -> Path:
    name = f".forge-backup-{index:032x}"
    path = parent / name
    path.mkdir()
    if product:
        (path / "VERSION.txt").write_text(f"Skyrim Forge 6.{index}.0\n", encoding="utf-8")
        (path / "MANIFEST.json").write_text("{}\n", encoding="utf-8")
    stamp = time.time() - days_old * 86400
    os.utime(path, (stamp, stamp))
    return path


def _stage(parent: Path, index: int, days_old: int) -> Path:
    path = parent / f".forge-stage-{index:016x}-failed"
    path.mkdir()
    (path / "partial.txt").write_text("x", encoding="utf-8")
    stamp = time.time() - days_old * 86400
    os.utime(path, (stamp, stamp))
    return path


@unittest.skipUnless(os.name == "nt" and POWERSHELL, "backup retention runs on Windows PowerShell")
class BackupRetentionTests(unittest.TestCase):
    def _run(self, parent: Path, *extra: str) -> subprocess.CompletedProcess:
        assert POWERSHELL is not None
        return subprocess.run([POWERSHELL, "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(HELPER),
                               "-Parent", str(parent), *extra], capture_output=True, text=True, timeout=120)

    def test_keeps_two_newest_product_backups_and_one_failed_stage(self):
        with tempfile.TemporaryDirectory() as td:
            parent = Path(td)
            newest = _backup(parent, 4, 1)
            second = _backup(parent, 3, 2)
            older = [_backup(parent, 2, 3), _backup(parent, 1, 4)]
            foreign = _backup(parent, 9, 5, product=False)
            legacy = parent / "Skyrim-Forge.backup-91a6cdca17a84334b9c202b3dcedcd8a"
            legacy.mkdir()
            old_stages = [_stage(parent, 1, 30), _stage(parent, 2, 20)]
            recent_stage = _stage(parent, 3, 1)

            result = self._run(parent, "-Retain", "2")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(newest.is_dir() and second.is_dir())
            for path in older:
                self.assertFalse(path.exists(), path)
            self.assertTrue(foreign.is_dir(), "a directory without a Forge VERSION.txt must survive")
            self.assertTrue(legacy.is_dir(), "legacy backups are not Forge-owned and must survive")
            self.assertEqual(sum(1 for path in old_stages if path.is_dir()), 1, "the newest failed stage is kept for diagnosis")
            self.assertTrue(recent_stage.is_dir(), "a recent failed stage is kept")

    def test_what_if_deletes_nothing(self):
        with tempfile.TemporaryDirectory() as td:
            parent = Path(td)
            for index in range(1, 5):
                _backup(parent, index, index)
            result = self._run(parent, "-Retain", "1", "-WhatIf")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(len(list(parent.glob(".forge-backup-*"))), 4)


if __name__ == "__main__":
    unittest.main()
