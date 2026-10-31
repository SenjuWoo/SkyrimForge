from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from urllib.error import URLError

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("forge_ecosystem", ROOT / "scripts" / "check_ecosystem.py")
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class EcosystemCheckTests(unittest.TestCase):
    def _fetchers(self, min_version: str = "6.0.0", asset: str = "Skyrim-Forge-{version}.zip",
                  tag: str | None = None, assets: list[str] | None = None):
        version = module.VERSION
        tag = tag or f"v{version}"
        names = assets if assets is not None else [f"Skyrim-Forge-{version}.zip", "SHA256SUMS.txt"]
        catalog = {"catalog_version": "9.9.9", "components": [{
            "id": "skyrim-forge", "github": {"owner": "SenjuWoo", "repo": "SkyrimForge"},
            "install": "latest-release", "min_version": min_version, "asset_template": asset}]}

        def fetch_json(url: str):
            if "CATALOG" in url:
                return catalog
            if "SkyrimForge" in url:
                return {"tag_name": tag, "assets": [{"name": name} for name in names]}
            return {"tag_name": "v1.0.0"}

        def fetch_text(url: str) -> str:
            return "SkyrimForge min_version SHA256SUMS" if "Install-SkyrimForge" in url else "kit.json installed.json 7zip"

        return fetch_json, fetch_text

    def test_current_tree_satisfies_the_contracts(self):
        fetch_json, fetch_text = self._fetchers()
        report = module.run(ROOT, fetch_json=fetch_json, fetch_text=fetch_text)
        self.assertEqual(report["result"], "PASS", report["checks"])
        self.assertTrue(any(row["check"] == "bundle.catalog" for row in report["checks"]))
        self.assertTrue(any(row["check"] == "forge.release" for row in report["checks"]))

    def test_floor_above_this_release_is_drift(self):
        fetch_json, fetch_text = self._fetchers(min_version="99.0.0")
        report = module.run(ROOT, fetch_json=fetch_json, fetch_text=fetch_text)
        self.assertEqual(report["result"], "DRIFT")
        self.assertTrue(any("min_version 99.0.0" in row["detail"] for row in report["checks"]))

    def test_missing_release_asset_is_drift(self):
        fetch_json, fetch_text = self._fetchers(assets=["SHA256SUMS.txt"])
        report = module.run(ROOT, fetch_json=fetch_json, fetch_text=fetch_text)
        self.assertEqual(report["result"], "DRIFT")
        self.assertTrue(any("missing Skyrim-Forge-" in row["detail"] for row in report["checks"]))

    def test_network_failure_is_unknown_not_drift(self):
        def broken_json(url: str):
            raise URLError("offline")

        def broken_text(url: str) -> str:
            raise URLError("offline")

        report = module.run(ROOT, fetch_json=broken_json, fetch_text=broken_text)
        self.assertEqual(report["result"], "UNKNOWN")
        self.assertGreaterEqual(report["counts"].get("UNKNOWN", 0), 2)

    def test_offline_runs_only_local_checks(self):
        report = module.run(ROOT, offline=True)
        names = {row["check"] for row in report["checks"]}
        self.assertNotIn("bundle.catalog", names)
        self.assertNotIn("forge.release", names)
        self.assertIn("local.pack", names)
        self.assertIn("local.version_sources", names)


if __name__ == "__main__":
    unittest.main()
