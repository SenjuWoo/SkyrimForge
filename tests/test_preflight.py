"""Preflight must tell a post-release docs commit apart from stale product code."""
from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts import preflight
from scripts.validate_repository import git_normalized


def git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)


class PreflightTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.email", "t@example.invalid")
        git(self.repo, "config", "user.name", "Test")
        (self.repo / "skyrim_forge").mkdir()
        (self.repo / "skyrim_forge/version.py").write_text('VERSION = "1.0.0"\n', encoding="utf-8")
        (self.repo / "a.txt").write_text("one\n", encoding="utf-8")
        self.commit("base")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def commit(self, message: str) -> str:
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", message)
        return git(self.repo, "rev-parse", "HEAD").stdout.strip()

    def tag(self, name: str, sha: str) -> None:
        git(self.repo, "tag", name, sha)

    def test_unreleased_version_passes(self) -> None:
        self.assertEqual(preflight.release_state("1.0.0", self.repo)[0], "UNRELEASED")

    def test_head_at_tag_is_tagged(self) -> None:
        self.tag("v1.0.0", "HEAD")
        self.assertEqual(preflight.release_state("1.0.0", self.repo)[0], "TAGGED")

    def test_documentation_commit_after_release_is_post_release(self) -> None:
        self.tag("v1.0.0", "HEAD")
        (self.repo / "docs").mkdir()
        (self.repo / "docs/page.md").write_text("notes\n", encoding="utf-8")
        self.commit("docs")
        self.assertEqual(preflight.release_state("1.0.0", self.repo)[0], "POST_RELEASE")

    def test_product_change_after_release_is_stale(self) -> None:
        self.tag("v1.0.0", "HEAD")
        (self.repo / "skyrim_forge").mkdir(exist_ok=True)
        (self.repo / "skyrim_forge/code.py").write_text("x = 1\n", encoding="utf-8")
        self.commit("product")
        state, detail = preflight.release_state("1.0.0", self.repo)
        self.assertEqual(state, "STALE_VERSION")
        self.assertIn("skyrim_forge/code.py", detail)

    def test_tag_outside_history_is_foreign(self) -> None:
        base = git(self.repo, "rev-parse", "HEAD").stdout.strip()
        git(self.repo, "checkout", "-q", "-b", "side")
        (self.repo / "side.txt").write_text("side\n", encoding="utf-8")
        side = self.commit("side")
        self.tag("v1.0.0", side)
        git(self.repo, "checkout", "-q", "-")
        (self.repo / "main.txt").write_text("main\n", encoding="utf-8")
        self.commit("main")
        self.assertNotEqual(base, side)
        self.assertEqual(preflight.release_state("1.0.0", self.repo)[0], "FOREIGN_TAG")

    def manifest(self, rows: list[dict]) -> None:
        (self.repo / "MANIFEST.json").write_text(json.dumps({"files": rows}), encoding="utf-8")

    def row(self, name: str) -> dict:
        data = git_normalized(self.repo / name)
        return {"path": name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}

    def test_manifest_accepts_the_complete_set(self) -> None:
        self.manifest([self.row("a.txt"), self.row("skyrim_forge/version.py")])
        self.assertEqual(preflight.manifest_report(self.repo), {"missing": [], "unexpected": [], "mismatch": []})

    def test_manifest_missing_entry_is_reported(self) -> None:
        self.manifest([self.row("a.txt")])
        report = preflight.manifest_report(self.repo)
        self.assertEqual(report["missing"], ["skyrim_forge/version.py"])

    def test_manifest_unexpected_entry_is_reported(self) -> None:
        self.manifest([self.row("a.txt"), self.row("skyrim_forge/version.py"),
                       {"path": "ghost.txt", "size": 0, "sha256": "0" * 64}])
        self.assertEqual(preflight.manifest_report(self.repo)["unexpected"], ["ghost.txt"])

    def test_manifest_hash_mismatch_is_reported(self) -> None:
        self.manifest([self.row("a.txt"), self.row("skyrim_forge/version.py")])
        (self.repo / "a.txt").write_text("two\n", encoding="utf-8")
        self.assertEqual(preflight.manifest_report(self.repo)["mismatch"], ["a.txt"])

    def test_missing_or_malformed_manifest_is_an_error(self) -> None:
        self.assertEqual(preflight.manifest_report(self.repo)["error"], "missing")
        (self.repo / "MANIFEST.json").write_text("{not json", encoding="utf-8")
        self.assertEqual(preflight.manifest_report(self.repo)["error"], "malformed")

    def test_control_character_regression_is_detected(self) -> None:
        (self.repo / "bad.md").write_text("C:\\Users\\name\forge\n", encoding="utf-8")
        self.commit("bad")
        self.assertEqual(preflight.control_offenders(self.repo), ["bad.md"])


if __name__ == "__main__":
    unittest.main()
