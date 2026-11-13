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

    def test_every_batch_launcher_pins_delayed_expansion_off(self) -> None:
        # Forge is installed in folders such as "!Skyrim". With delayed expansion on,
        # cmd removes the "!" from %~dp0 and the launcher looks in a folder that
        # does not exist.
        launchers = sorted(list(ROOT.glob("*.bat")) + list(ROOT.glob("*.cmd")))
        self.assertGreaterEqual(len(launchers), 8)
        for path in launchers:
            data = path.read_bytes()
            head = data.split(b"\r\n")[:6]
            self.assertTrue(any(b"disabledelayedexpansion" in line.lower() for line in head),
                            f"{path.name} must start with setlocal DisableDelayedExpansion")
            self.assertNotIn(b"\n", data.replace(b"\r\n", b""), f"{path.name} must stay CRLF")

    @unittest.skipUnless(os.name == "nt", "cmd shims are Windows-only")
    def test_launchers_survive_an_awkward_folder_with_delayed_expansion_on(self) -> None:
        import shutil

        with tempfile.TemporaryDirectory() as td:
            home = Path(td).resolve() / "!Sky tools (x) é"
            package = home / "skyrim_forge"
            package.mkdir(parents=True)
            (package / "__init__.py").write_text("", encoding="utf-8")
            (package / "__main__.py").write_text(
                "import json, os, sys\n"
                "print(json.dumps({'home': os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'args': sys.argv[1:]}))\n",
                encoding="utf-8")
            for name in ("forge.cmd", "Skyrim Forge.bat", "Skyrim Forge MCP.bat"):
                shutil.copyfile(ROOT / name, home / name)
            # "Skyrim Forge.bat" requires the private interpreter; a venv is the real thing.
            subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(home / ".venv")], check=True, capture_output=True)
            env = {key: value for key, value in os.environ.items() if key.upper() != "PYTHONPATH"}
            cases = (("forge.cmd", ["doctor", "a b"], ["doctor", "a b"]),
                     ("Skyrim Forge.bat", ["version"], ["version"]),
                     ("Skyrim Forge MCP.bat", [], ["mcp"]))
            for switch in ("/v:off", "/v:on"):
                for name, arguments, expected in cases:
                    line = subprocess.list2cmdline([str(home / name), *arguments])
                    proc = subprocess.run(f'cmd.exe /d {switch} /s /c "{line}"', capture_output=True, text=True,
                                          encoding="utf-8", errors="replace", cwd=home, env=env, timeout=120)
                    label = f"{name} under {switch}: {proc.stdout[-200:]} {proc.stderr[-200:]}"
                    self.assertEqual(proc.returncode, 0, label)
                    seen = json.loads(proc.stdout.strip().splitlines()[-1])
                    self.assertEqual(seen["args"], expected, label)
                    self.assertTrue(os.path.samefile(seen["home"], home), label)

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
