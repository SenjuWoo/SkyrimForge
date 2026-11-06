"""The shipped CLI shim and the approval gate on scheduled maintenance."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from skyrim_forge.delivery import PRODUCT_FILES, is_product_file

ROOT = Path(__file__).resolve().parents[1]


class CliShimTests(unittest.TestCase):
    def test_forge_cmd_ships_and_uses_crlf(self) -> None:
        path = ROOT / "forge.cmd"
        self.assertTrue(path.is_file(), "forge.cmd must exist beside START-HERE.bat")
        self.assertIn("forge.cmd", PRODUCT_FILES)
        self.assertTrue(is_product_file("forge.cmd"))
        data = path.read_bytes()
        self.assertIn(b"\r\n", data)
        self.assertNotIn(b"\n", data.replace(b"\r\n", b""), "batch files must stay CRLF")

    @unittest.skipUnless(os.name == "nt", "cmd shims are Windows-only")
    def test_forge_cmd_runs_the_cli_from_an_unrelated_directory(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as elsewhere:
            proc = subprocess.run(["cmd.exe", "/c", str(ROOT / "forge.cmd"), "version"],
                                  capture_output=True, text=True, cwd=elsewhere)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["version"], (ROOT / "VERSION.txt").read_text(encoding="utf-8").split()[-1])

    def test_schedule_without_approval_changes_nothing(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as td:
            config = Path(td) / "config.toml"
            env = dict(os.environ)
            env["SKYRIM_FORGE_CONFIG"] = str(config)
            proc = subprocess.run([sys.executable, "-m", "skyrim_forge", "maintain", "--schedule", "--no-self-test"],
                                  cwd=ROOT, env=env, capture_output=True, text=True)
        self.assertNotEqual(proc.returncode, 0, "an unapproved schedule request must fail")
        self.assertIn("approval", (proc.stdout + proc.stderr).lower())


if __name__ == "__main__":
    unittest.main()
