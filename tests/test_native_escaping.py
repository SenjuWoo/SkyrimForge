"""Generated native source must not let metadata escape a literal or CMake arg."""
from __future__ import annotations

import re
import unittest

from skyrim_forge.errors import ValidationError
from skyrim_forge.native import _cmake, _plugin_cpp, validate_plan

INJECTION = 'MyMod"); static_assert(false, "INJECTED'


def _plan(**overrides):
    data = {
        "schema": "skyrim-forge-native-plugin-plan/1",
        "project": "Probe",
        "version": "1.2.3",
        "display_name": "Probe Mod",
        "author": "Author",
        "email": "a@example.com",
        "description": "Probe",
        "log_name": "Probe",
    }
    data.update(overrides)
    return validate_plan(data)


class NativeEscapingTests(unittest.TestCase):
    def test_hostile_display_name_is_rejected_before_generation(self) -> None:
        with self.assertRaises(ValidationError):
            _plan(display_name=INJECTION)

    def test_safe_punctuation_is_escaped_in_forge_generated_cpp(self) -> None:
        cpp = _plugin_cpp(_plan(display_name="Probe (SE) — 100%"))
        self.assertIn('"Probe (SE) — 100% 1.2.3 loaded"', cpp)

    def test_cmake_metadata_is_a_single_quoted_argument(self) -> None:
        cmake = _cmake(_plan(display_name="A B", author="x;y$z", email="a$b;c"))
        for expected in (r'NAME "A B"', r'AUTHOR "x\;y\$z"', r'EMAIL "a\$b\;c"'):
            self.assertIn(expected, cmake)
        self.assertEqual(cmake.count("project(Probe VERSION 1.2.3 LANGUAGES CXX)"), 1)

    def test_sdk_generated_cpp_metadata_cannot_contain_quotes_or_backslashes(self) -> None:
        for field, value in (("display_name", 'A"B'), ("author", "A\\B"), ("email", 'a"b@c')):
            with self.subTest(field=field):
                with self.assertRaises(ValidationError):
                    _plan(**{field: value})

    def test_struct_dependent_must_be_a_json_boolean(self) -> None:
        with self.assertRaises(ValidationError):
            _plan(struct_dependent="false")
        self.assertTrue(_plan(struct_dependent=True)["struct_dependent"])

    def test_sdk_version_fields_are_numeric_and_bounded(self) -> None:
        with self.assertRaises(ValidationError):
            _plan(minimum_skse_version="1.2.3-beta")
        with self.assertRaises(ValidationError):
            _plan(runtime_strategy="explicit_runtimes", compatible_runtimes=[f"1.{index}.0" for index in range(17)])
        plan = _plan(runtime_strategy="explicit_runtimes", compatible_runtimes=["1.6.1170"])
        self.assertEqual(plan["compatible_runtimes"], ["1.6.1170"])

    def test_sdk_versions_reject_unicode_digits_and_oversized_components(self) -> None:
        with self.assertRaises(ValidationError):
            _plan(minimum_skse_version="١.٢.٣")
        with self.assertRaises(ValidationError):
            _plan(minimum_skse_version="1.70000")

    def test_plugin_helper_receives_a_numeric_version(self) -> None:
        cmake = _cmake(_plan(version="2.0.0-rc.2"))
        self.assertIn('VERSION "2.0.0"', cmake)

    def test_prerelease_is_kept_for_the_plugin_but_numeric_for_cmake_project(self) -> None:
        plan = _plan(version="1.2.3-beta.1")
        self.assertIn("project(Probe VERSION 1.2.3 LANGUAGES CXX)", _cmake(plan))
        self.assertIn('"Probe Mod 1.2.3-beta.1 loaded"', _plugin_cpp(plan))

    def test_control_characters_are_rejected_before_generation(self) -> None:
        with self.assertRaises(ValidationError):
            _plan(display_name="Bad\x00Name")
        with self.assertRaises(ValidationError):
            _plan(author="line\nbreak")


if __name__ == "__main__":
    unittest.main()
