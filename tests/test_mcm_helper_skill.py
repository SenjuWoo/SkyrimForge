"""The MCM Helper skill's template must validate clean, and the validator must reject the documented traps."""
import importlib.util
import json
import re
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1] / "integrations/skyrim-pack/skills/mcm-helper-authoring"
spec = importlib.util.spec_from_file_location("validate_mcm", SKILL / "scripts/validate_mcm.py")
validate_mcm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validate_mcm)


def template_block(heading: str) -> str:
    text = (SKILL / "references/templates.md").read_text(encoding="utf-8")
    match = re.search(r"^## `?[^\n]*" + re.escape(heading) + r"[^\n]*\n+```[a-z]*\n(.*?)```", text, re.S | re.M)
    assert match, heading
    return match.group(1)


class McmValidatorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cfg = self.root / "MCM/Config/MyMod"
        self.cfg.mkdir(parents=True)
        self.config = json.loads(template_block("config.json"))
        self.write_config()
        (self.cfg / "settings.ini").write_text(template_block("settings.ini"), encoding="utf-8")
        (self.cfg / "keybinds.json").write_text(template_block("keybinds.json"), encoding="utf-8")
        (self.root / "Interface/Translations").mkdir(parents=True)
        self.write_translation(template_block("MyMod_ENGLISH.txt"))
        (self.root / "MyMod.esp").write_bytes(b"TES4")

    def write_config(self, raw: bytes | None = None):
        (self.cfg / "config.json").write_bytes(raw if raw is not None else json.dumps(self.config, indent=2).encode("utf-8"))

    def write_translation(self, text: str, bom: bool = True):
        data = text.encode("utf-16-le")
        (self.root / "Interface/Translations/MyMod_ENGLISH.txt").write_bytes((b"\xff\xfe" if bom else b"") + data)

    def findings(self, level):
        return [m for lv, _f, m in validate_mcm.validate(self.root).items if lv == level]

    def controls(self):
        return self.config["pages"][0]["content"]

    def test_template_is_clean(self):
        report = validate_mcm.validate(self.root)
        self.assertEqual([i for i in report.items if i[0] in ("ERROR", "WARNING")], [])

    def test_exit_codes(self):
        self.assertEqual(validate_mcm.main([str(self.root)]), 0)
        self.config["modName"] = "Other"
        self.write_config()
        self.assertEqual(validate_mcm.main([str(self.root)]), 1)
        self.assertEqual(validate_mcm.main([str(self.root / "Interface")]), 2)

    def test_comments_trailing_commas_and_bom_are_errors(self):
        self.write_config(b'{ // c\n "modName": "MyMod" }')
        self.assertTrue(any("strict JSON" in m for m in self.findings("ERROR")))
        self.write_config(b'{"modName": "MyMod",}')
        self.assertTrue(any("strict JSON" in m for m in self.findings("ERROR")))
        self.write_config(b"\xef\xbb\xbf" + json.dumps(self.config).encode())
        self.assertTrue(any("BOM" in m for m in self.findings("ERROR")))

    def test_modname_must_match_folder_and_have_no_extension(self):
        self.config["modName"] = "MyMod.esp"
        self.write_config()
        errors = self.findings("ERROR")
        self.assertTrue(any("folder name" in m for m in errors) and any("extension" in m for m in errors))

    def test_modsetting_id_needs_section_and_settings_default(self):
        self.controls()[1]["id"] = "bEnabled"
        self.write_config()
        self.assertTrue(any("key:Section" in m for m in self.findings("ERROR")))
        self.controls()[1]["id"] = "bBrandNew:Main"
        self.write_config()
        self.assertTrue(any("no default" in m for m in self.findings("WARNING")))

    def test_property_source_requires_property_name(self):
        del self.controls()[-1]["valueOptions"]["propertyName"]
        self.write_config()
        self.assertTrue(any("propertyName" in m for m in self.findings("ERROR")))

    def test_unknown_keys_and_types_and_slider_bounds(self):
        self.controls()[1]["bogus"] = 1
        self.controls()[2]["valueOptions"].update(min=5, max=1)
        self.controls().append({"type": "dropdown"})
        self.write_config()
        errors = self.findings("ERROR")
        for needle in ("unknown control key 'bogus'", "min < max", "type must be one of"):
            self.assertTrue(any(needle in m for m in errors), needle)

    def test_options_and_shortnames_lengths(self):
        self.controls()[3]["valueOptions"]["shortNames"] = ["only one"]
        self.write_config()
        self.assertTrue(any("shortNames" in m for m in self.findings("ERROR")))

    def test_group_control_on_enum_is_flagged_as_ignored(self):
        self.controls()[3]["groupControl"] = 2
        self.write_config()
        self.assertTrue(any("ignored at runtime" in m for m in self.findings("WARNING")))

    def test_group_condition_shapes(self):
        self.controls()[2]["groupCondition"] = {"XOR": [1]}
        self.write_config()
        self.assertTrue(any("keys must be from" in m for m in self.findings("ERROR")))
        self.controls()[2]["groupCondition"] = {"AND": [1, 0]}
        self.write_config()
        self.assertTrue(any("start at 1" in m for m in self.findings("ERROR")))

    def test_hotkey_needs_keybind_and_vice_versa(self):
        (self.cfg / "keybinds.json").write_text(json.dumps({"modName": "MyMod", "keybinds": []}), encoding="utf-8")
        self.assertTrue(any("no entry in keybinds.json" in m for m in self.findings("ERROR")))
        (self.cfg / "keybinds.json").unlink()
        self.assertTrue(any("need keybinds.json" in m for m in self.findings("ERROR")))

    def test_keybind_action_requirements(self):
        bad = {"modName": "MyMod", "keybinds": [{"id": "toggleThing", "action": {"type": "CallFunction", "function": "x"}}]}
        (self.cfg / "keybinds.json").write_text(json.dumps(bad), encoding="utf-8")
        self.assertTrue(any("requires 'form'" in m for m in self.findings("ERROR")))

    def test_translation_encoding_and_coverage(self):
        self.write_translation(template_block("MyMod_ENGLISH.txt"), bom=False)
        self.assertTrue(any("UTF-16 LE with BOM" in m for m in self.findings("ERROR")))
        self.write_translation("$MyMod\tMy Mod\n")
        self.assertTrue(any("no key '$MyMod_General'" in m for m in self.findings("WARNING")))

    def test_form_string_pattern(self):
        self.controls()[-1]["valueOptions"]["sourceForm"] = "MyMod|800"
        self.write_config()
        self.assertTrue(any("Plugin.esp|HEXID" in m for m in self.findings("ERROR")))


if __name__ == "__main__":
    unittest.main()
