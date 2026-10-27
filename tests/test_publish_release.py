"""Exercise the publication boundary without modifying GitHub releases or tags."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


# Model gh's status/header and binary download output, including failed API calls.
class PublishReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        script = Path(__file__).resolve().parents[1] / "scripts" / "publish_release.py"
        spec = importlib.util.spec_from_file_location("forge_publish_release", script)
        assert spec and spec.loader
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.directory = Path(temp.name).resolve()
        self.files = {"a.zip": b"original-a\x00\r\n", "b.whl": b"original-b\xff"}
        for name, data in self.files.items():
            (self.directory / name).write_bytes(data)
        self.assets = [self.asset(name, index) for index, name in enumerate(self.files, 1)]
        self.downloads = {asset["id"]: self.files[asset["name"]] for asset in self.assets}
        self.pages = None
        self.lookup_status = 200
        self.lookup_returncode = 0
        self.lookup_stdout = None
        self.failure_endpoint = None
        self.calls = []
        self.mutations = []
        runner = patch.object(self.module.subprocess, "run", side_effect=self.run_gh)
        runner.start()
        self.addCleanup(runner.stop)
        quiet = patch("builtins.print")
        quiet.start()
        self.addCleanup(quiet.stop)

    # Metadata can lie independently of bytes, so tests control both signals.
    def asset(self, name, asset_id):
        data = self.files[name]
        return {"id": asset_id, "name": name, "size": len(data), "state": "uploaded",
                "digest": "sha256:" + hashlib.sha256(data).hexdigest()}

    def run_gh(self, command, **kwargs):
        self.calls.append(command)
        if command[:3] == ["gh", "api", "--include"]:
            body = json.dumps({"id": 7}).encode()
            output = (f"HTTP/2.0 {self.lookup_status} Status\r\nContent-Type: application/json\r\n\r\n".encode() + body)
            if self.lookup_stdout is not None:
                output = self.lookup_stdout
            return subprocess.CompletedProcess(command, self.lookup_returncode, output, b"lookup failure (HTTP 404)")
        if command[:2] == ["gh", "api"]:
            if command[2] == self.failure_endpoint:
                if kwargs.get("check"):
                    raise subprocess.CalledProcessError(1, command, stderr=b"API failed")
                return subprocess.CompletedProcess(command, 1, b"", b"API failed")
            if command[2].endswith("/releases/7/assets"):
                self.assertIn("--paginate", command)
                self.assertIn("--slurp", command)
                output = json.dumps(self.pages if self.pages is not None else [self.assets]).encode()
            elif "/releases/assets/" in command[2]:
                self.assertEqual(command[-2:], ["--header", "Accept: application/octet-stream"])
                output = self.downloads[int(command[2].rsplit("/", 1)[1])]
            else:
                self.fail(f"Unexpected API call: {command}")
            self.assertTrue(kwargs.get("check"), "Asset/API failure must abort before mutation")
            return subprocess.CompletedProcess(command, 0, output, b"")
        self.assertIn(command[:3], (["gh", "release", "create"], ["gh", "release", "upload"]))
        self.assertTrue(kwargs.get("check"))
        self.assertNotIn("--clobber", command)
        self.mutations.append(command)
        return subprocess.CompletedProcess(command, 0)

    def publish(self):
        self.module.publish("v6.3.1", self.directory)

    def test_identical_release_succeeds_without_mutation(self):
        self.publish()
        self.assertEqual(self.mutations, [])
        self.assertEqual(sum("/releases/assets/" in command[2] for command in self.calls), 2)

    def test_only_actual_404_creates_release_and_verifies_tag(self):
        self.lookup_status = 404
        self.lookup_returncode = 1
        self.publish()
        self.assertEqual(self.mutations, [["gh", "release", "create", "--verify-tag", "--generate-notes", "--", "v6.3.1",
                                          str(self.directory / "a.zip"), str(self.directory / "b.whl")]])
        self.assertEqual(len(self.calls), 2)

    def test_partial_release_uploads_only_missing_after_verification(self):
        self.assets = self.assets[:1]
        self.publish()
        self.assertEqual(self.mutations, [["gh", "release", "upload", "--", "v6.3.1", str(self.directory / "b.whl")]])
        self.assertIn("/releases/assets/1", self.calls[-2][2])

    def test_empty_existing_release_recovers_without_recreation(self):
        self.assets = []
        self.publish()
        self.assertEqual(self.mutations, [["gh", "release", "upload", "--", "v6.3.1",
                                          str(self.directory / "a.zip"), str(self.directory / "b.whl")]])

    def test_size_mismatch_prevents_any_mutation(self):
        self.assets = self.assets[:1]
        self.assets[0]["size"] += 1
        with self.assertRaisesRegex(RuntimeError, "size mismatch"):
            self.publish()
        self.assertEqual(self.mutations, [])

    def test_digest_mismatch_prevents_any_mutation(self):
        self.assets = self.assets[:1]
        self.assets[0]["digest"] = "sha256:" + "0" * 64
        with self.assertRaisesRegex(RuntimeError, "digest mismatch"):
            self.publish()
        self.assertEqual(self.mutations, [])

    def test_same_size_changed_bytes_prevent_partial_recovery(self):
        self.assets = self.assets[:1]
        self.downloads[1] = b"x" * self.assets[0]["size"]
        with self.assertRaisesRegex(RuntimeError, "bytes mismatch"):
            self.publish()
        self.assertEqual(self.mutations, [])

    def test_missing_digest_requires_matching_download(self):
        self.assets[0]["digest"] = None
        self.assets[1].pop("digest")
        self.publish()
        self.assertEqual(self.mutations, [])
        self.downloads[2] = b"x" * self.assets[1]["size"]
        with self.assertRaisesRegex(RuntimeError, "bytes mismatch"):
            self.publish()
        self.assertEqual(self.mutations, [])

    def test_failed_upload_state_is_not_replaced(self):
        self.assets[0]["state"] = "starter"
        with self.assertRaisesRegex(RuntimeError, "state/size mismatch"):
            self.publish()
        self.assertEqual(self.mutations, [])

    def test_unverifiable_extra_asset_prevents_mutation(self):
        self.assets.append({"id": 3, "name": "unknown.zip"})
        with self.assertRaisesRegex(RuntimeError, "Unexpected or duplicate"):
            self.publish()
        self.assertEqual(self.mutations, [])

    def test_duplicate_asset_prevents_mutation(self):
        self.assets.append(self.assets[0])
        with self.assertRaisesRegex(RuntimeError, "Unexpected or duplicate"):
            self.publish()
        self.assertEqual(self.mutations, [])

    def test_every_asset_page_is_checked_before_upload(self):
        self.pages = [[self.assets[0]], [{"id": 3, "name": "unknown.zip"}]]
        with self.assertRaisesRegex(RuntimeError, "Unexpected or duplicate"):
            self.publish()
        self.assertEqual(self.mutations, [])

    def test_lookup_errors_are_never_treated_as_missing_release(self):
        for status in (401, 403, 429, 500, 502, 503):
            with self.subTest(status=status):
                self.lookup_status = status
                self.lookup_returncode = 1
                with self.assertRaisesRegex(RuntimeError, f"HTTP {status}"):
                    self.publish()
        self.assertEqual(self.mutations, [])

    def test_network_or_auth_error_without_response_is_not_404(self):
        self.lookup_returncode = 1
        self.lookup_stdout = b""
        with self.assertRaisesRegex(RuntimeError, "HTTP unavailable"):
            self.publish()
        self.assertEqual(self.mutations, [])

    def test_nonzero_exit_after_200_response_prevents_mutation(self):
        self.lookup_returncode = 1
        with self.assertRaisesRegex(RuntimeError, "lookup failed"):
            self.publish()
        self.assertEqual(self.mutations, [])

    def test_bad_lookup_json_prevents_mutation(self):
        self.lookup_stdout = b"HTTP/2.0 200 OK\n\nnot json"
        with self.assertRaises(json.JSONDecodeError):
            self.publish()
        self.assertEqual(self.mutations, [])

    def test_list_and_download_api_errors_prevent_mutation(self):
        self.assets = self.assets[:1]
        for endpoint in ("repos/{owner}/{repo}/releases/7/assets", "repos/{owner}/{repo}/releases/assets/1"):
            with self.subTest(endpoint=endpoint):
                self.failure_endpoint = endpoint
                with self.assertRaises(subprocess.CalledProcessError):
                    self.publish()
        self.assertEqual(self.mutations, [])

    def test_malformed_asset_pages_prevent_mutation(self):
        for pages in ({}, [{}], [None]):
            with self.subTest(pages=pages):
                self.pages = pages
                with self.assertRaisesRegex(RuntimeError, "Invalid release asset response"):
                    self.publish()
        self.assertEqual(self.mutations, [])

    def test_empty_build_directory_is_rejected_before_api_call(self):
        for path in self.directory.iterdir():
            path.unlink()
        with self.assertRaisesRegex(RuntimeError, "nonempty directory"):
            self.publish()
        self.assertEqual(self.calls, [])

    def test_subdirectories_are_rejected_before_api_call(self):
        (self.directory / "nested").mkdir()
        with self.assertRaisesRegex(RuntimeError, "regular files"):
            self.publish()
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
