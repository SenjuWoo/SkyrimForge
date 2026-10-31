from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from skyrim_forge import mcp_server
from skyrim_forge.config import load_config
from skyrim_forge.service import ForgeService


def _service(root: Path) -> ForgeService:
    with patch("pathlib.Path.home", return_value=root):
        return ForgeService(load_config(root / "config.toml"))


class CompactSurfaceTests(unittest.TestCase):
    def test_every_tool_is_in_exactly_one_compact_group(self):
        members = [tool for group in mcp_server.COMPACT_GROUPS.values() for tool in group]
        self.assertEqual(sorted(members), sorted(mcp_server.TOOL_SPECS))
        self.assertEqual(len(mcp_server.COMPACT_TOOLS), 4)

    def test_compact_list_and_routing(self):
        with tempfile.TemporaryDirectory() as td:
            service = _service(Path(td))
            listed = mcp_server.handle(service, {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}, "compact")
            self.assertEqual([tool["name"] for tool in listed["result"]["tools"]],
                             ["skyrim_forge_execute", "skyrim_forge_inspect", "skyrim_forge_release", "skyrim_forge_validate"])
            called = mcp_server.handle(service, {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
                "name": "skyrim_forge_inspect", "arguments": {"operation": "forge_version"}}}, "compact")
            self.assertIn("Skyrim Forge", called["result"]["content"][0]["text"])
            refused = mcp_server.handle(service, {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
                "name": "skyrim_forge_inspect", "arguments": {"operation": "forge_nexus_build"}}}, "compact")
            self.assertTrue(refused["result"]["isError"])

    def test_annotations_split_reads_from_destructive_tools(self):
        with tempfile.TemporaryDirectory() as td:
            service = _service(Path(td))
            listed = mcp_server.handle(service, {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
            by_name = {tool["name"]: tool["annotations"] for tool in listed["result"]["tools"]}
            self.assertTrue(by_name["forge_doctor"]["readOnlyHint"])
            self.assertTrue(by_name["forge_skse_inspect_pe"]["readOnlyHint"])
            self.assertTrue(by_name["forge_automation_run"]["destructiveHint"])
            self.assertFalse(by_name["forge_fomod_build"]["destructiveHint"])
            self.assertEqual(set(by_name), set(mcp_server.TOOL_SPECS))


class BoundedOutputTests(unittest.TestCase):
    def test_large_result_spills_to_artifact(self):
        with tempfile.TemporaryDirectory() as td:
            service = _service(Path(td))
            with patch.dict(os.environ, {"SKYRIM_FORGE_MAX_CHARS": "1000"}):
                response = mcp_server.handle(service, {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
                    "name": "forge_capabilities", "arguments": {}}})
            envelope = json.loads(response["result"]["content"][0]["text"])
            self.assertEqual(envelope["result"], "PARTIAL_SPILL")
            self.assertTrue(envelope["max_chars_overrun"])
            artifact = Path(envelope["artifact_path"])
            self.assertTrue(artifact.is_file())
            self.assertEqual(len(json.loads(artifact.read_text(encoding="utf-8"))["capabilities"]), envelope["summary"]["capabilities"])

    def test_small_result_is_not_spilled(self):
        with tempfile.TemporaryDirectory() as td:
            service = _service(Path(td))
            response = mcp_server.handle(service, {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
                "name": "forge_version", "arguments": {}}})
            payload = json.loads(response["result"]["content"][0]["text"])
            self.assertEqual(payload["version"], mcp_server.VERSION)
            self.assertFalse(any((Path(td) / "Workspaces").rglob("*.json")))


if __name__ == "__main__":
    unittest.main()
