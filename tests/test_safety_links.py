"""Path-confinement regression tests: junctions and dangling symlinks.

A dangling link has exists() == False but is_symlink() == True, so the old
`exists() and is_symlink()` test let a write path through a link whose target
was already gone. These tests nail the link chain down on both platforms.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from skyrim_forge.errors import SafetyError
from skyrim_forge.safety import require_within


class ConfinementTests(unittest.TestCase):
    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.root = Path(self._td.name)
        self.workspace = self.root / "workspace"
        self.outside = self.root / "outside"
        for path in (self.workspace, self.outside):
            path.mkdir()

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_plain_nested_path_is_allowed(self) -> None:
        target = self.workspace / "mod" / "Textures" / "stone.dds"
        self.assertEqual(require_within(target, self.workspace), target)

    @unittest.skipUnless(os.name == "nt", "junctions are a Windows reparse point")
    def test_junction_parent_is_refused(self) -> None:
        link = self.workspace / "linked"
        made = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(self.outside)],
                              capture_output=True, text=True)
        if made.returncode != 0:
            self.skipTest("could not create a junction: " + (made.stderr or made.stdout).strip())
        with self.assertRaises(SafetyError):
            require_within(link / "escape.dds", self.workspace)

    def test_dangling_symlink_is_refused(self) -> None:
        link = self.workspace / "dangling"
        try:
            os.symlink(self.outside / "missing", link, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"symlinks unavailable: {exc}")
        self.assertFalse(link.exists())
        with self.assertRaises(SafetyError):
            require_within(link / "escape.dds", self.workspace)

    @unittest.skipIf(os.name == "nt", "POSIX symlink semantics")
    def test_symlinked_parent_outside_workspace_is_refused(self) -> None:
        link = self.workspace / "linked"
        os.symlink(self.outside, link, target_is_directory=True)
        with self.assertRaises(SafetyError):
            require_within(link / "escape.dds", self.workspace)


if __name__ == "__main__":
    unittest.main()
