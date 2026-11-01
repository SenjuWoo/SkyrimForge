from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path

from skyrim_forge import textures
from skyrim_forge.errors import SafetyError, ValidationError
from skyrim_forge.util import sha256_bytes

FORMAT_NAMES = {8: 4, 16: 5, 32: 6, 64: 7}


class TextureTests(unittest.TestCase):
    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.root = Path(self._td.name)

    def tearDown(self) -> None:
        self._td.cleanup()

    def make(self, name: str = "t.dds", **options):
        options.setdefault("size", 64)
        options.setdefault("approved", True)
        return textures.generate(options.pop("kind", "checker"), self.root / name, workspace_root=self.root, **options)

    def test_bc1_header_mips_and_payload(self):
        self.make(fmt="bc1")
        info = textures.inspect(self.root / "t.dds")
        self.assertEqual((info["width"], info["height"]), (64, 64))
        self.assertEqual(info["format"], "bc1")
        self.assertEqual(info["mips"], FORMAT_NAMES[64])
        self.assertTrue(info["payload_matches"])
        self.assertEqual(info["expected_payload_bytes"], info["payload_bytes"])

    def test_bc3_and_rgba_headers(self):
        self.make("alpha.dds", fmt="bc3")
        self.assertEqual(textures.inspect(self.root / "alpha.dds")["format"], "bc3")
        self.make("raw.dds", fmt="rgba")
        raw = textures.inspect(self.root / "raw.dds")
        self.assertEqual(raw["format"], "rgba")
        self.assertTrue(raw["payload_matches"])

    def test_deterministic_and_seeded(self):
        first = self.make("a.dds", kind="noise", seed=7)
        second = self.make("b.dds", kind="noise", seed=7)
        other = self.make("c.dds", kind="noise", seed=8)
        self.assertEqual(first["sha256"], second["sha256"])
        self.assertNotEqual(first["sha256"], other["sha256"])

    def test_checker_has_two_colours(self):
        self.make("check.dds", size=64, cells=8, primary="#FF0000", secondary="#0000FF")
        data = (self.root / "check.dds").read_bytes()
        first = textures._decode_bc1_colour(data[128:136])
        second = textures._decode_bc1_colour(data[128 + 2 * 8:128 + 3 * 8])
        self.assertGreater(first[0][0], 200)      # red cell
        self.assertGreater(second[0][2], 200)     # blue cell, two blocks to the right

    def test_normal_map_flat_field_is_flat(self):
        self.make("n.dds", kind="normal", size=8, fmt="rgba", strength=0.0)
        data = (self.root / "n.dds").read_bytes()[128:]
        for offset in range(0, 8 * 8 * 4, 4):
            self.assertEqual(data[offset + 2], 255)
            self.assertIn(data[offset], (127, 128))
            self.assertIn(data[offset + 1], (127, 128))

    def test_preview_is_a_real_png(self):
        report = self.make("p.dds", kind="gradient", preview=self.root / "p.png")
        png = (self.root / "p.png").read_bytes()
        self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
        width, height = struct.unpack_from(">II", png, 16)
        self.assertEqual((width, height), (64, 64))
        self.assertEqual(report["preview"]["sha256"], sha256_bytes(png))

    def test_refuses_writes_outside_the_workspace(self):
        with self.assertRaises(SafetyError):
            textures.generate("solid", self.root.parent / "escaped.dds", workspace_root=self.root, approved=True)

    def test_requires_approval(self):
        with self.assertRaises(SafetyError):
            textures.generate("solid", self.root / "no.dds", workspace_root=self.root, approved=False)

    def test_rejects_non_dds(self):
        target = self.root / "fake.dds"
        target.write_bytes(b"not a dds")
        with self.assertRaises(ValidationError):
            textures.inspect(target)

    def test_rejects_bad_inputs(self):
        for kind, size, fmt in (("plasma", 64, "bc1"), ("solid", 63, "bc1"), ("solid", 64, "dxt9")):
            with self.assertRaises(ValidationError):
                textures.generate(kind, self.root / "x.dds", workspace_root=self.root, size=size, fmt=fmt, approved=True)


if __name__ == "__main__":
    unittest.main()
