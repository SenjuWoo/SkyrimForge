from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from skyrim_forge.architecture import recommend, self_test


class ArchitectureTests(unittest.TestCase):
    def test_self_test(self):
        self.assertEqual(self_test()["result"], "PASS")

    def test_known_routes(self):
        cases = [
            ("Distribute spells and perks to NPCs with SPID", "distribution.spid"),
            ("Replace armor textures with DDS and normal maps", "assets.texture"),
            ("Add an SKSE native DLL hook using Address Library", "native.skse"),
            ("Patch NPC records and leveled lists for compatibility", "records.housecarl"),
            ("Add an MCM menu with SkyUI settings", "ui.mcm"),
        ]
        for description, expected in cases:
            with self.subTest(description=description):
                report = recommend({"description": description, "edition": "ae"})
                self.assertEqual(report["recommendation"]["id"], expected)
                self.assertIn(report["confidence"], {"medium", "high"})

    def test_frame_frequency_favours_native(self):
        report = recommend({"description": "Run a hook every frame in the engine", "runtime_frequency": "frame"})
        self.assertEqual(report["recommendation"]["id"], "native.skse")

    def test_explicit_exclusion_overrides_keyword(self):
        report = recommend({"description": "Avoid SPID, write a Papyrus script to give items", "edition": "ae"})
        self.assertEqual(report["recommendation"]["id"], "script.papyrus")
        self.assertIn("SPID", report["exclusions"])

    def test_explicit_request_still_selects_spid(self):
        report = recommend({"description": "Use SPID to distribute spells to NPCs", "edition": "ae"})
        self.assertEqual(report["recommendation"]["id"], "distribution.spid")

    def test_composite_requirements_are_reported(self):
        report = recommend({"description": "A quest with Papyrus scripting and an MCM menu for settings", "edition": "ae"})
        self.assertEqual(report["recommendation"]["id"], "script.papyrus")
        self.assertIn("ui.mcm", [item["id"] for item in report["components"]])

    def test_contradictory_requirements_are_not_recommended(self):
        report = recommend({"description": "Use SPID but avoid SPID for this mod", "edition": "ae"})
        self.assertIsNone(report["recommendation"])
        self.assertEqual(report["status"], "NEEDS_INPUT")
        self.assertEqual(report["confidence"], "low")
        self.assertTrue(report["conflicts"])

    def test_unknown_edition_caps_confidence(self):
        report = recommend({"description": "Use SPID to distribute spells to NPCs"})
        self.assertNotEqual(report["confidence"], "high")
        self.assertTrue(report["questions"])

    def test_vague_request_is_not_forced(self):
        report = recommend({"description": "Make my mod better"})
        self.assertIsNone(report["recommendation"])
        self.assertEqual(report["status"], "NEEDS_INPUT")
        self.assertEqual(report["confidence"], "low")
        self.assertTrue(report["questions"])

    def test_bad_input_is_rejected(self):
        with self.assertRaises(Exception):
            recommend({"description": "x", "edition": "le"})
        with self.assertRaises(Exception):
            recommend({"description": ""})

    def test_schema_file_is_valid_json(self):
        schema = json.loads((ROOT / "skyrim_forge" / "schemas" / "architecture-request.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(schema["properties"]["description"]["maxLength"], 4000)


if __name__ == "__main__":
    unittest.main()
