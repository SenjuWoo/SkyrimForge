from __future__ import annotations

import json
import struct
import tempfile
import unittest
import wave
from pathlib import Path

from skyrim_forge.audio import create_fuz, extract_fuz, inspect, self_test, validate_voice_tree
from skyrim_forge.errors import ApprovalError, SafetyError, ValidationError
from skyrim_forge.util import atomic_write_bytes


def _xwm(path: Path) -> None:
    body = b"XWMA" + b"fmt " + struct.pack("<I", 18) + struct.pack("<HHIIHH", 0x0161, 1, 44100, 8000, 2, 16) + b"\x00\x00"
    body += b"dpds" + struct.pack("<I", 4) + b"\x00" * 4
    atomic_write_bytes(path, b"RIFF" + struct.pack("<I", 4 + len(body)) + body)


def _wav(path: Path, rate: int = 44100, channels: int = 1, width: int = 2) -> None:
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(channels)
        stream.setsampwidth(width)
        stream.setframerate(rate)
        stream.writeframes(b"\x00" * (width * channels * 441))


class AudioTests(unittest.TestCase):
    def test_self_test(self):
        self.assertEqual(self_test()["result"], "PASS")

    def test_fuz_round_trip_is_byte_identical(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _xwm(root / "line.xwm")
            (root / "line.lip").write_bytes(b"LIPDATA")
            packed = create_fuz(root / "line.xwm", root / "line.fuz", root, lip_path=root / "line.lip", approved=True)
            self.assertEqual(packed["result"], "PASS")
            self.assertEqual(packed["container"]["lip_size"], 7)
            extracted = extract_fuz(root / "line.fuz", root / "out", root, approved=True)
            self.assertEqual((root / "out" / "line.lip").read_bytes(), b"LIPDATA")
            self.assertEqual((root / "out" / "line.xwm").read_bytes(), (root / "line.xwm").read_bytes())

    def test_inspect_reports_voice_readiness(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _wav(root / "good.wav")
            _wav(root / "bad.wav", rate=22050, width=1)
            _xwm(root / "line.xwm")
            self.assertTrue(inspect(root / "good.wav")["audio"]["voice_ready"])
            self.assertFalse(inspect(root / "bad.wav")["audio"]["voice_ready"])
            self.assertEqual(inspect(root / "line.xwm")["audio"]["format"], "WMAudio2 (xWMA)")

    def test_bad_fuz_header_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "bad.fuz"
            path.write_bytes(b"FUZZ" + b"\x00" * 8)
            with self.assertRaises(ValidationError):
                inspect(path)

    def test_writes_require_approval_and_stay_in_workspace(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _xwm(root / "line.xwm")
            with self.assertRaises(ApprovalError):
                create_fuz(root / "line.xwm", root / "line.fuz", root, approved=False)
            with self.assertRaises(SafetyError):
                create_fuz(root / "line.xwm", root.parent / "escape.fuz", root, approved=True)

    def test_voice_path_rules(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "mod"
            good = root / "Sound" / "Voice" / "Test.esp" / "FemaleEvenToned"
            good.mkdir(parents=True)
            (good / "Topic_0001.fuz").write_bytes(b"FUZE")
            self.assertEqual(validate_voice_tree(root)["result"], "PASS")
            (root / "Sound" / "Voice" / "NoPlugin" / "Female").mkdir(parents=True)
            (root / "Sound" / "Voice" / "NoPlugin" / "Female" / "Topic.fuz").write_bytes(b"FUZE")
            report = validate_voice_tree(root)
            self.assertEqual(report["result"], "FAIL")
            self.assertTrue(any("not named after a plugin" in item for item in report["errors"]))


if __name__ == "__main__":
    unittest.main()
