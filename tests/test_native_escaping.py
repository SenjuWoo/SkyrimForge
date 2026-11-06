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
    def test_display_name_cannot_break_out_of_the_cpp_literal(self) -> None:
        cpp = _plugin_cpp(_plan(display_name=INJECTION))
        self.assertNotIn('"MyMod"); static_assert(false, "INJECTED 1.2.3', cpp)
        line = next(item for item in cpp.splitlines() if "INJECTED" in item)
        self.assertIn('MyMod\\");', line)
        self.assertIn('\\"INJECTED', line)

    def test_cmake_metadata_is_a_single_quoted_argument(self) -> None:
        cmake = _cmake(_plan(display_name='A"B\\C', author="x;y$z", email="a$b;c"))
        for expected in (r'NAME "A\"B\\C"', r'AUTHOR "x\;y\$z"', r'EMAIL "a\$b\;c"'):
            self.assertIn(expected, cmake)
        self.assertEqual(cmake.count("project(Probe VERSION 1.2.3 LANGUAGES CXX)"), 1)

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
