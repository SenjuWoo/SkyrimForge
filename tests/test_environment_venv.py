from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from skyrim_forge.environment import virtualenv_status


def scratch() -> tempfile.TemporaryDirectory:
    """A temp root outside %TEMP%: the ephemeral check correctly rejects anything under it."""
    return tempfile.TemporaryDirectory(dir=Path.cwd())


def _venv(root: Path, home: str) -> Path:
    prefix = root / ".venv"
    prefix.mkdir(parents=True)
    (prefix / "pyvenv.cfg").write_text(f"home = {home}\ninclude-system-site-packages = false\nversion = 3.12.9\n", encoding="utf-8")
    return prefix


class VirtualenvStatusTests(unittest.TestCase):
    def test_running_outside_a_venv_is_not_a_failure(self):
        with patch.object(sys, "prefix", "C:/Python312"), patch.object(sys, "base_prefix", "C:/Python312"):
            report = virtualenv_status()
        self.assertEqual(report["status"], "PASS")
        self.assertFalse(report["in_venv"])

    def test_stable_base_passes(self):
        with scratch() as td:
            root = Path(td)
            base = root / "Python312"
            base.mkdir()
            (base / "python.exe").write_bytes(b"MZ")
            prefix = _venv(root, str(base))
            with patch.object(sys, "prefix", str(prefix)), patch.object(sys, "base_prefix", str(base)), patch.object(sys, "executable", str(prefix / "Scripts" / "python.exe")):
                report = virtualenv_status()
            self.assertEqual(report["status"], "PASS")
            self.assertTrue(report["base_exists"])

    def test_provider_cache_base_is_rejected(self):
        with scratch() as td:
            root = Path(td)
            cache = root / ".cache" / "codex-runtimes" / "python"
            cache.mkdir(parents=True)
            (cache / "python.exe").write_bytes(b"MZ")
            prefix = _venv(root, str(cache))
            with patch.object(sys, "prefix", str(prefix)), patch.object(sys, "base_prefix", str(cache)):
                report = virtualenv_status()
            self.assertEqual(report["status"], "FAIL")
            self.assertEqual(report["code"], "VENV_EPHEMERAL_BASE_PYTHON")

    def test_missing_base_is_rejected(self):
        with scratch() as td:
            root = Path(td)
            prefix = _venv(root, str(root / "gone"))
            with patch.object(sys, "prefix", str(prefix)), patch.object(sys, "base_prefix", str(root / "gone")):
                report = virtualenv_status()
            self.assertEqual(report["status"], "FAIL")
            self.assertEqual(report["code"], "VENV_BASE_MISSING")

    def test_doctor_includes_virtualenv_without_changing_pass_shape(self):
        from skyrim_forge.config import load_config
        from skyrim_forge.environment import doctor
        with scratch() as td:
            root = Path(td)
            with patch("pathlib.Path.home", return_value=root):
                config = load_config(root / "config.toml")
                config.workspace_root.mkdir(parents=True, exist_ok=True)
                config.config_path.parent.mkdir(parents=True, exist_ok=True)
                config.config_path.write_text("", encoding="utf-8")
                report = doctor(config)
            self.assertIn("virtualenv", report)
            self.assertIn("result", report)
            self.assertIn("read_only_ready", report)


if __name__ == "__main__":
    unittest.main()
