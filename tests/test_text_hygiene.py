"""No tracked text file may carry a stray form feed or vertical tab."""
from __future__ import annotations

import unittest
from pathlib import Path

from scripts.validate_repository import control_characters
from skyrim_forge.delivery import source_files

ROOT = Path(__file__).resolve().parents[1]
SKIP = {".exe", ".dll", ".png", ".ico", ".zip", ".nif", ".dds", ".wav", ".fuz"}


class TextHygieneTests(unittest.TestCase):
    def test_detector_catches_the_escape_mistake(self) -> None:
        self.assertEqual(control_characters("C:\\Users\\name\forge"), ["\x0c"])
        self.assertEqual(control_characters("plain text\nwith tabs\t"), [])

    def test_no_tracked_text_contains_unexpected_controls(self) -> None:
        offenders = []
        for path in source_files(ROOT):
            if path.suffix.lower() in SKIP:
                continue
            try:
                text = path.read_text(encoding="utf-8-sig")
            except UnicodeDecodeError:
                continue
            found = control_characters(text)
            if found:
                offenders.append((path.relative_to(ROOT).as_posix(), found))
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
