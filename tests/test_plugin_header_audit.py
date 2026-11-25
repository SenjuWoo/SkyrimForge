"""The pack's plugin-header audit script stays correct, including its --master-root chain rules.

The fixture script lives beside the skill so it ships with the pack; this runs it in the suite
so CI covers it. It holds the regression for a false FAIL on every HEDR 1.70 plugin that masters
the AE Skyrim.esm (HEDR 1.71).
"""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "integrations/skyrim-pack/skills/skyrim-plugin-authoring/scripts"


class PluginHeaderAuditTests(unittest.TestCase):
    def test_fixture_suite_passes(self):
        run = subprocess.run([sys.executable, str(SCRIPTS / "test_plugin_header_fixtures.py")],
                             capture_output=True, text=True, timeout=120)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn("PLUGIN FIXTURE TESTS: PASS", run.stdout)


if __name__ == "__main__":
    unittest.main()
