from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from skyrim_forge.config import load_config
from skyrim_forge.knowledge import load_registry, lookup, self_test, status


class KnowledgeTests(unittest.TestCase):
    def test_self_test(self):
        self.assertEqual(self_test()["result"], "PASS")

    def test_registry_has_provenance_and_no_machine_paths(self):
        data = load_registry()
        ids = {entry["id"] for entry in data["entries"]}
        self.assertTrue({"skse64", "commonlibsse_ng", "spid", "xedit"} <= ids)
        for entry in data["entries"]:
            self.assertTrue(entry["url"].startswith("https://"))
            probe = entry.get("probe", {}).get("path", "")
            self.assertFalse(str(probe).startswith(("C:", "Z:")), entry["id"])

    def test_unknown_id_stays_unknown(self):
        with tempfile.TemporaryDirectory() as td:
            report = lookup("definitely-not-an-api", _config(Path(td)))
        self.assertEqual(report["entry"]["status"], "UNKNOWN")

    def test_local_probe_is_detected_but_not_versioned(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            data = root / "Data"
            data.mkdir()
            (data / "SkyUI_SE.bsa").write_bytes(b"fixture")
            report = status(_config(root), path=ROOT / "references" / "SKYRIM-KNOWLEDGE.json")
            skyui = next(item for item in report["entries"] if item["id"] == "skyui")
            skse = next(item for item in report["entries"] if item["id"] == "skse64")
            self.assertEqual(skyui["status"], "DETECTED")
            self.assertIsNone(skyui.get("version_verified"))
            self.assertEqual(skse["status"], "MISSING")

    def test_documented_entry_has_no_local_claim(self):
        with tempfile.TemporaryDirectory() as td:
            report = lookup("presentmon", _config(Path(td)), path=ROOT / "references" / "SKYRIM-KNOWLEDGE.json")
        self.assertEqual(report["entry"]["status"], "DOCUMENTED")
        self.assertIsNone(report["entry"]["local_path"])


def _config(root: Path):
    config = root / "config.toml"
    data = root / "Data"
    data.mkdir(exist_ok=True)
    config.write_text(
        "[paths]\n"
        f'workspace_root = "{root.as_posix()}"\n'
        f'skyrim_data = "{data.as_posix()}"\n',
        encoding="utf-8",
    )
    return load_config(config)


if __name__ == "__main__":
    unittest.main()
