"""SDK vault regressions against a local fixture repository; nothing is fetched from the network."""
from pathlib import Path
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock
import json
import os
import shutil
import subprocess
import tempfile
import unittest

from skyrim_forge.config import ForgeConfig, default_tools
from skyrim_forge.errors import ApprovalError, ToolError, ValidationError
from skyrim_forge import sdk
from skyrim_forge.sdk import load_lock, sdk_install, sdk_rows, sdk_status

ROOT = Path(__file__).resolve().parents[1]
GIT = shutil.which("git")


def _git(cwd, *args):
    return subprocess.run([GIT, "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


class LockTests(unittest.TestCase):
    def test_shipped_lock_is_valid_and_mirrored(self):
        lock = load_lock(ROOT / "references/SDK-LOCK.json")
        ids = [entry["id"] for entry in lock["sdks"]]
        self.assertIn("commonlibsse_ng", ids)
        self.assertEqual(sorted(ids), sorted(set(ids)))
        self.assertEqual((ROOT / "references/SDK-LOCK.json").read_bytes(), (ROOT / "skyrim_forge/references/SDK-LOCK.json").read_bytes())

    def test_lock_rejects_unpinned_or_unsafe_entries(self):
        base = json.loads((ROOT / "references/SDK-LOCK.json").read_text(encoding="utf-8"))
        for field, value in (("commit", "main"), ("repository", "file:///c:/x"), ("probe", "../x"), ("id", "Bad Id")):
            broken = json.loads(json.dumps(base))
            broken["sdks"][0][field] = value
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "lock.json"
                path.write_text(json.dumps(broken), encoding="utf-8")
                with self.assertRaises(ValidationError, msg=field):
                    load_lock(path)


@unittest.skipUnless(GIT, "git is required")
class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.upstream = root / "upstream"
        self.upstream.mkdir()
        _git(self.upstream, "init", "--quiet")
        (self.upstream / "probe.txt").write_text("sdk", encoding="utf-8")
        _git(self.upstream, "add", ".")
        _git(self.upstream, "commit", "--quiet", "-m", "pin")
        self.commit = _git(self.upstream, "rev-parse", "HEAD")
        self.config = ForgeConfig(config_path=root / "forge" / "config.toml", workspace_root=root / "ws", audit_log=root / "audit.jsonl", tool_vault_root=root / "forge" / "tool-vault", tools=default_tools())
        self.lock = {"schema": "skyrim-forge-sdk-lock/1", "sdks": [{"id": "fixture", "default": True, "role": "r", "repository": self.upstream.as_posix(), "ref": "main", "commit": self.commit, "submodules": False, "probe": "probe.txt", "license": "MIT"}]}
        self.dest = root / "forge" / "sdk-vault" / "fixture"

    def install(self, **kwargs):
        return sdk_install(self.config, [], approved=True, lock=self.lock, **kwargs)

    def test_requires_approval(self):
        with self.assertRaises(ApprovalError):
            sdk_install(self.config, [], approved=False, lock=self.lock)
        self.assertFalse(self.dest.exists())

    def test_fetch_then_keep_is_idempotent_and_status_reports_current(self):
        first = self.install()
        self.assertEqual((first["result"], first["results"][0]["action"]), ("PASS", "fetched"))
        self.assertEqual(_git(self.dest, "rev-parse", "HEAD"), self.commit)
        self.assertEqual(self.install()["results"][0]["action"], "kept")
        self.assertEqual(sdk_rows(self.config, self.lock)[0]["state"], "current")
        self.assertEqual(sdk_status(self.config, self.lock)["sdks"][0]["state"], "current")
        self.assertFalse(list(self.dest.parent.glob(".*.partial")))

    def test_modified_or_foreign_directory_is_never_overwritten(self):
        self.install()
        (self.dest / "probe.txt").write_text("edited", encoding="utf-8")
        self.assertEqual(sdk_rows(self.config, self.lock)[0]["state"], "modified")
        again = self.install()
        self.assertEqual((again["result"], again["results"][0]["action"]), ("INCOMPLETE", "refused"))
        self.assertEqual((self.dest / "probe.txt").read_text(encoding="utf-8"), "edited")

    def test_wrong_commit_fails_cleanly_without_leaving_partial_state(self):
        self.lock["sdks"][0]["commit"] = "0" * 40
        result = self.install()
        self.assertEqual((result["result"], result["results"][0]["action"]), ("INCOMPLETE", "failed"))
        self.assertFalse(self.dest.exists())
        self.assertFalse(list(self.dest.parent.glob(".*.partial")))

    @unittest.skipUnless(os.name == "nt", "bootstrap scripts are Windows batch files")
    def test_bootstrap_runs_script_even_when_cwd_is_not_on_the_command_path(self):
        (self.upstream / "make.bat").write_text("@echo off\r\necho built> %1\r\n", encoding="utf-8")
        _git(self.upstream, "add", ".")
        _git(self.upstream, "commit", "--quiet", "-m", "bootstrap")
        self.lock["sdks"][0].update(commit=_git(self.upstream, "rev-parse", "HEAD"), bootstrap={"script": "make.bat", "args": ["tool.txt"], "artifact": "tool.txt"})
        with patch.dict(os.environ, {"NoDefaultCurrentDirectoryInExePath": "1"}):
            first = self.install(bootstrap=True)
        self.assertEqual(first["result"], "PASS", first)
        self.assertTrue(first["results"][0]["bootstrapped"])
        self.assertEqual(len(first["results"][0]["sha256"]), 64)
        self.assertFalse(self.install(bootstrap=True)["results"][0]["bootstrapped"])

    def test_preexisting_partial_directory_is_never_removed(self):
        legacy = self.dest.parent / ".fixture.partial"
        legacy.mkdir(parents=True)
        sentinel = legacy / "keep.txt"
        sentinel.write_text("private recovery data", encoding="utf-8")
        self.assertEqual(self.install()["result"], "PASS")
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "private recovery data")

    def test_failed_fetch_removes_only_its_own_stage(self):
        legacy = self.dest.parent / ".fixture.partial"
        legacy.mkdir(parents=True)
        sentinel = legacy / "keep.txt"
        sentinel.write_text("private recovery data", encoding="utf-8")
        original = sdk._git
        def fail_fetch(args, cwd=None):
            if args[0] == "fetch":
                raise ToolError("fixture failure")
            return original(args, cwd)
        with patch("skyrim_forge.sdk._git", side_effect=fail_fetch):
            result = self.install()
        self.assertEqual(result["result"], "INCOMPLETE")
        self.assertFalse(self.dest.exists())
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "private recovery data")
        self.assertEqual(list(self.dest.parent.iterdir()), [legacy])

    def test_interleaved_fetches_use_distinct_stages_and_keep_winner(self):
        ready = Barrier(2)
        mutex = Lock()
        stages = set()
        original = sdk._git
        def interleave(args, cwd=None):
            if args[0] == "fetch":
                with mutex:
                    stages.add(cwd)
                ready.wait(timeout=20)
            return original(args, cwd)
        with patch("skyrim_forge.sdk._git", side_effect=interleave):
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(lambda _: self.install(), range(2)))
        self.assertEqual(len(stages), 2)
        self.assertEqual(sum(r["result"] == "PASS" for r in results), 1, results)
        self.assertEqual(sdk_rows(self.config, self.lock)[0]["state"], "current")
        self.assertEqual((self.dest / "probe.txt").read_text(encoding="utf-8"), "sdk")
        self.assertFalse(list(self.dest.parent.glob(".*.partial")))

    def test_unknown_id_is_rejected(self):
        with self.assertRaises(ValidationError):
            sdk_install(self.config, ["nope"], approved=True, lock=self.lock)


if __name__ == "__main__":
    unittest.main()
