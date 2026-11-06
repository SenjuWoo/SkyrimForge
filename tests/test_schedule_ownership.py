"""Scheduled-task ownership must be structural, not a substring match."""
from __future__ import annotations

import unittest
from pathlib import Path

from skyrim_forge import maintenance

LAUNCHER = Path(maintenance.__file__).resolve().parents[1] / "forge.cmd"
LOG = r"C:\Logs\maintain.log"


def _info(execute: str, arguments: str, *, marker: bool = True, actions: int = 1) -> dict:
    return {"TaskName": maintenance.SCHEDULE_TASK,
            "Description": maintenance.SCHEDULE_MARKER if marker else "",
            "ActionCount": actions, "Execute": execute, "Arguments": arguments}


class ScheduleOwnershipTests(unittest.TestCase):
    def canonical(self) -> str:
        return maintenance._expected_command(LAUNCHER, LOG)

    def test_canonical_task_is_owned_and_healthy(self) -> None:
        info = _info("cmd.exe", self.canonical())
        self.assertTrue(maintenance._task_owned(info, LAUNCHER))
        self.assertTrue(maintenance._task_healthy(info, LAUNCHER))

    def test_same_arguments_under_another_executable_are_not_owned(self) -> None:
        info = _info("notepad.exe", self.canonical())
        self.assertFalse(maintenance._task_owned(info, LAUNCHER))

    def test_multiple_actions_are_not_owned(self) -> None:
        info = _info("cmd.exe", self.canonical(), actions=2)
        self.assertFalse(maintenance._task_owned(info, LAUNCHER))

    def test_apply_or_fix_roots_are_not_check_only(self) -> None:
        for extra in ("--apply", "--fix-roots"):
            arguments = self.canonical().replace("maintain --no-self-test", f"maintain --no-self-test {extra}")
            with self.subTest(extra=extra):
                self.assertFalse(maintenance._task_owned(_info("cmd.exe", arguments), LAUNCHER))

    def test_legacy_python_task_is_a_candidate_never_owned(self) -> None:
        legacy = _info("C:\\Unrelated\\python.exe", "-m skyrim_forge maintain --no-self-test", marker=False)
        self.assertFalse(maintenance._task_owned(legacy, LAUNCHER))
        self.assertFalse(maintenance._task_healthy(legacy, LAUNCHER))
        self.assertTrue(maintenance._task_legacy_candidate(legacy, LAUNCHER))

    def test_unmarked_cmd_task_is_a_candidate_never_owned(self) -> None:
        legacy = _info("cmd.exe", self.canonical(), marker=False)
        self.assertFalse(maintenance._task_owned(legacy, LAUNCHER))
        self.assertTrue(maintenance._task_legacy_candidate(legacy, LAUNCHER))

    def test_foreign_python_without_matching_arguments_is_not_even_a_candidate(self) -> None:
        foreign = _info("C:\\Unrelated\\python.exe", "-c print(1)", marker=False)
        self.assertFalse(maintenance._task_legacy_candidate(foreign, LAUNCHER))

    def test_substring_mention_without_the_canonical_command_is_not_owned(self) -> None:
        info = _info("cmd.exe", '/c echo "forge.cmd" maintain --no-self-test', marker=True)
        self.assertFalse(maintenance._task_owned(info, LAUNCHER))

    def test_missing_task_is_not_owned(self) -> None:
        self.assertFalse(maintenance._task_owned(None, LAUNCHER))


if __name__ == "__main__":
    unittest.main()
