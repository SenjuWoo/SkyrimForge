from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from skyrim_forge.skse_pe import audit_imports, inspect, self_test, verify_reproducible


class SksePeTests(unittest.TestCase):
    def test_self_test(self):
        self.assertEqual(self_test()["result"], "PASS")

    def _fixture(self, root: Path) -> Path:
        """Reuse the module self-test image by round-tripping through a temp file it already proves."""
        import struct
        from skyrim_forge import skse_pe
        # Build the same minimal image the self-test validates, with an import descriptor added.
        section = bytearray(0x600)
        struct.pack_into("<IIHHIIIIIII", section, 0x00, 0, 0, 0, 0, 0x1040, 1, 1, 1, 0x1060, 0x1050, 0x1070)
        struct.pack_into("<I", section, 0x40, 0x1080)
        struct.pack_into("<I", section, 0x50, 0x1090)
        struct.pack_into("<I", section, 0x60, 0x1100)
        struct.pack_into("<H", section, 0x70, 0)
        section[0x80:0x8C] = b"fixture.dll\x00"
        section[0x90:0x90 + 18] = b"SKSEPlugin_Version"
        struct.pack_into("<III", section, 0x100, 1, (1 << 24) | (2 << 4), 0)
        section[0x108:0x10D] = b"Test\x00"
        # Import descriptor at 0x200 (two entries, 40 bytes), thunk at 0x240, DLL name at 0x260, hint/name at 0x280.
        struct.pack_into("<IIIII", section, 0x200, 0x1240, 0, 0, 0x1260, 0x1240)
        struct.pack_into("<Q", section, 0x240, 0x127E)
        struct.pack_into("<Q", section, 0x248, 0)
        section[0x260:0x26A] = b"ws2_32.dll"
        struct.pack_into("<H", section, 0x27E, 0)
        section[0x280:0x28F] = b"CreateProcessW\x00"
        optional = bytearray(0xF0)
        struct.pack_into("<H", optional, 0, 0x20B)
        struct.pack_into("<Q", optional, 24, 0x140000000)
        struct.pack_into("<I", optional, 108, 16)
        struct.pack_into("<II", optional, 112 + 0 * 8, 0x1000, 0x90)
        struct.pack_into("<II", optional, 112 + 1 * 8, 0x1200, 0xA0)
        header = bytearray(0x200)
        header[0:2] = b"MZ"
        struct.pack_into("<I", header, 0x3C, 0x80)
        header[0x80:0x84] = b"PE\x00\x00"
        struct.pack_into("<HHIIIHH", header, 0x84, 0x8664, 1, 0x12345678, 0, 0, len(optional), 0x2000)
        header[0x98:0x98 + len(optional)] = optional
        struct.pack_into("<8sIIII", header, 0x98 + len(optional), b".rdata", 0x600, 0x1000, 0x600, 0x200)
        path = root / "plugin.dll"
        path.write_bytes(bytes(header) + bytes(section))
        return path

    def test_inspect_reads_exports_and_version_data(self):
        with tempfile.TemporaryDirectory() as td:
            path = self._fixture(Path(td))
            report = inspect(path)
            self.assertEqual(report["result"], "PASS")
            self.assertEqual(report["architecture"], "PE32+")
            self.assertTrue(report["skse"]["version_export"])
            self.assertEqual(report["skse"]["version_data"]["name"], "Test")

    def test_import_audit_categorises_network_and_process(self):
        with tempfile.TemporaryDirectory() as td:
            path = self._fixture(Path(td))
            report = audit_imports(path)
            self.assertIn("ws2_32.dll", report["categories"]["network"])
            self.assertTrue(any("CreateProcessW" in item for item in report["categories"]["process_execution"]))

    def test_reproducibility_normalises_only_linker_fields(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            first = self._fixture(root)
            data = bytearray(first.read_bytes())
            data[0x88:0x8C] = b"\x99\x99\x99\x99"
            second = root / "second.dll"
            second.write_bytes(bytes(data))
            same = verify_reproducible(first, second)
            self.assertTrue(same["identical_after_timestamp_normalisation"])
            self.assertFalse(same["byte_for_byte_identical"])
            data[0x300] ^= 0xFF  # change a section byte, not a linker field
            third = root / "third.dll"
            third.write_bytes(bytes(data))
            self.assertFalse(verify_reproducible(first, third)["identical_after_timestamp_normalisation"])


if __name__ == "__main__":
    unittest.main()
