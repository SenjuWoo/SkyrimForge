"""houseCARL pin agreement: installer, pack manifest and pin file must match.

The 6.11.0 regression shipped 2.1.2's URL with 2.1.1's digest, so every
download failed at the checksum. This test reads the three places the pin
lives and refuses to let them drift apart again.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import unittest
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "Install-HouseCarl.ps1"
PIN = ROOT / "integrations/skyrim-pack/housecarl-pin.json"
PACK = ROOT / "integrations/skyrim-pack/PACK.json"


def _script_pin() -> dict[str, str]:
    text = SCRIPT.read_text(encoding="utf-8")
    version = re.search(r"\$version=\[version\]'([\d.]+)'", text)
    digest = re.search(r"\$digest='([0-9a-f]{64})'", text)
    asset = re.search(r"houseCARL-([\d.]+)\.zip", text)
    url = re.search(r"https://github\.com/Avick3110/houseCARL/releases/download/v([\d.]+)/", text)
    assert version and digest and asset and url, "Install-HouseCarl.ps1 lost its pin constants"
    return {"version": version.group(1), "sha256": digest.group(1),
            "asset": f"houseCARL-{asset.group(1)}.zip", "url_version": url.group(1)}


class HouseCarlPinTests(unittest.TestCase):
    def test_installer_pack_and_pin_file_agree(self) -> None:
        script = _script_pin()
        pin = json.loads(PIN.read_text(encoding="utf-8"))
        pack = json.loads(PACK.read_text(encoding="utf-8"))["housecarl"]
        self.assertEqual(script["version"], pin["version"])
        self.assertEqual(script["version"], pack["version"])
        self.assertEqual(script["version"], script["url_version"], "download URL and version disagree")
        self.assertEqual(script["sha256"], pin["sha256"])
        self.assertEqual(script["sha256"], pack["sha256"])
        self.assertEqual(script["asset"], pin["url"].rsplit("/", 1)[-1])
        self.assertEqual(script["asset"], pack["asset"])

    def test_pin_file_records_the_snapshot_it_does_not_replace(self) -> None:
        pin = json.loads(PIN.read_text(encoding="utf-8"))
        self.assertNotEqual(pin["snapshot_version"], pin["version"],
                            "if the skill snapshot moves to the app version, drop snapshot_version")

    @unittest.skipUnless(os.environ.get("FORGE_HOUSECARL_ONLINE") == "1",
                         "set FORGE_HOUSECARL_ONLINE=1 to download the release asset")
    def test_official_asset_matches_the_pin(self) -> None:
        pin = json.loads(PIN.read_text(encoding="utf-8"))
        with urllib.request.urlopen(pin["url"], timeout=120) as response:
            digest = hashlib.sha256(response.read()).hexdigest()
        self.assertEqual(digest, pin["sha256"])


if __name__ == "__main__":
    unittest.main()
