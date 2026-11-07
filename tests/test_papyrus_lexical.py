from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from skyrim_forge.papyrus import analyze_sources


class PapyrusLexicalTests(unittest.TestCase):
    def _run(self, text: str, name: str = "LexicalProbe.psc"):
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        path = root / name
        path.write_text(text, encoding="utf-8")
        report = analyze_sources([path], imports=[])
        temp.cleanup()
        return report

    def test_comments_and_strings_do_not_create_warnings(self):
        report = self._run(
            "ScriptName LexicalProbe\n"
            "; RegisterForUpdate(0.1)\n"
            "Event OnInit()\n"
            '    Debug.Trace("RegisterForUpdate(0.1) FindAllReferencesOfType")\n'
            "EndEvent\n"
        )
        codes = {item["code"] for item in report["warnings"]}
        self.assertNotIn("PAPYRUS-HIGH-FREQUENCY-UPDATE", codes)
        self.assertNotIn("PAPYRUS-HOT-EVENT-SCAN", codes)

    def test_real_update_code_is_flagged(self):
        report = self._run(
            "ScriptName LexicalProbe\n"
            "Event OnInit()\n"
            "    RegisterForUpdate(0.1)\n"
            "EndEvent\n"
        )
        codes = {item["code"] for item in report["warnings"]}
        self.assertIn("PAPYRUS-HIGH-FREQUENCY-UPDATE", codes)
        self.assertIn("PAPYRUS-UPDATE-NO-UNREGISTER", codes)

    def test_block_comments_are_ignored(self):
        report = self._run(
            "ScriptName LexicalProbe\n"
            ";/\n"
            "Event OnUpdate()\n"
            "RegisterForUpdate(0.1)\n"
            "EndEvent\n"
            "/;\n"
            "Event OnInit()\n"
            "    RegisterForSingleUpdate(5.0)\n"
            "EndEvent\n"
        )
        codes = {item["code"] for item in report["warnings"]}
        self.assertNotIn("PAPYRUS-HIGH-FREQUENCY-UPDATE", codes)
        self.assertNotIn("PAPYRUS-LOOP-IN-UPDATE", codes)
        self.assertNotIn("OnUpdate", report["scripts"][0]["events"])

    def test_executable_code_after_block_comment_is_visible(self):
        report = self._run(
            "ScriptName LexicalProbe\n"
            ";/\n"
            "RegisterForUpdate(0.1)\n"
            "/;\n"
            "Event OnInit()\n"
            "    RegisterForUpdate(0.1)\n"
            "EndEvent\n"
        )
        codes = {item["code"] for item in report["warnings"]}
        self.assertIn("PAPYRUS-HIGH-FREQUENCY-UPDATE", codes)

    def test_unterminated_block_comment_is_reported(self):
        report = self._run(
            "ScriptName LexicalProbe\n"
            ";/\n"
            "RegisterForUpdate(0.1)\n"
        )
        self.assertIn("PAPYRUS-UNTERMINATED-COMMENT", {item["code"] for item in report["errors"]})

    def test_unterminated_string_is_reported(self):
        report = self._run("ScriptName LexicalProbe\nEvent OnInit()\nDebug.Trace(\"unterminated)\nEndEvent\n")
        self.assertIn("PAPYRUS-UNTERMINATED-STRING", {item["code"] for item in report["errors"]})

    def test_commented_scriptname_and_event_are_ignored(self):
        report = self._run(
            "; ScriptName WrongName\n"
            "ScriptName LexicalProbe\n"
            "; Event OnInit()\n"
            "; EndEvent\n"
        )
        self.assertEqual(report["errors"], [])
        self.assertEqual(report["scripts"][0]["script_name"], "LexicalProbe")
        self.assertEqual(report["scripts"][0]["events"], [])


if __name__ == "__main__":
    unittest.main()
