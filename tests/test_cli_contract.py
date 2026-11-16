"""CLI contract: JSON on every outcome, exit 0/1/2/3, the command list comes from the parser, one log line per run;
plus repository hygiene: no personal machine paths in tracked files."""
from __future__ import annotations

import contextlib
import io
import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from skyrim_forge import cli
from skyrim_forge.delivery import source_files

ROOT = Path(__file__).resolve().parents[1]
BINARY = {".exe", ".dll", ".png", ".ico", ".zip", ".nif", ".dds", ".wav", ".fuz", ".bsa", ".pex"}
HOMES = "Us" + "ers"  # spelled in pieces so this file does not itself contain a home path
PERSONAL = re.compile(
    r"(?i)\b[A-Z]:[\\/]+(?:" + HOMES + r"|Documents and Settings)[\\/]+"
    r"(?!Public\b|Default\b|<|%|\{|name\b|user\b|USERNAME\b|YourUserName\b|x\b|you\b|me\b)[A-Za-z0-9_.-]+"
    r"|[A-Z]:[\\/]+Backup[\\/]|/c/" + HOMES + r"/[a-z0-9]+|/home/(?!runner\b|user\b)[a-z0-9]+")


def sample(drive: str, *parts: str) -> str:
    return drive + "/" + "/".join(parts)


def run(argv: list[str], log: Path) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with mock.patch.dict(os.environ, {"SKYRIM_FORGE_INVOCATION_LOG": str(log)}), \
            contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(argv)
    return code, out.getvalue(), err.getvalue()


class CliContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.log = Path(self.temp.name) / "invocations.jsonl"

    def test_usage_error_is_json_with_exit_2(self) -> None:
        code, _, err = run(["no-such-command"], self.log)
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(err)["error"], "UsageError")
        code, _, err = run(["plugin-info"], self.log)  # missing positional
        self.assertEqual((code, json.loads(err)["error"]), (2, "UsageError"))

    def test_named_failure_is_2_and_unexpected_exception_is_3(self) -> None:
        code, _, err = run(["plugin-info", str(Path(self.temp.name) / "missing.esp")], self.log)
        self.assertEqual((code, json.loads(err)["exit"]), (2, 2))
        with mock.patch("skyrim_forge.service.ForgeService.plugin_info", side_effect=KeyError("boom")):
            code, _, err = run(["plugin-info", "x.esp"], self.log)
        self.assertEqual(code, 3)
        self.assertIn("Forge defect", json.loads(err)["fix"])

    def test_findings_exit_1(self) -> None:
        self.assertEqual(cli._exit_code({"result": "FAIL"}), 1)
        self.assertEqual(cli._exit_code({"result": "PASS"}), 0)

    def test_command_list_comes_from_the_parser(self) -> None:
        code, out, _ = run(["capabilities"], self.log)
        self.assertEqual(code, 0)
        commands = json.loads(out)["commands"]
        self.assertEqual(set(commands), set(cli.subcommands()))
        self.assertIn("--approve", commands["bsa-pack"])

    def test_every_run_appends_one_log_line(self) -> None:
        run(["version"], self.log); run(["no-such-command"], self.log)
        rows = [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([(row["command"], row["exit"]) for row in rows], [("version", 0), ("", 2)])


class RepositoryHygieneTests(unittest.TestCase):
    def test_pattern_catches_personal_paths_and_spares_placeholders(self) -> None:
        for text in (sample("C:", HOMES, "alice", "mods"), sample("Z:", "Backup", "tools"), "/ho" + "me/alice/x", "/c/" + HOMES + "/alice"):
            self.assertTrue(PERSONAL.search(text), text)
        for text in (sample("C:", HOMES, "YourUserName"), sample("C:", HOMES, "Public"), "%USERPROFILE%/x", "/home/runner/work"):
            self.assertFalse(PERSONAL.search(text), text)

    def test_no_tracked_file_names_a_personal_machine_path(self) -> None:
        offenders = []
        for path in source_files(ROOT):
            if path.suffix.lower() in BINARY or path.name.startswith("SkyrimForge.Native"):
                continue
            try:
                text = path.read_text(encoding="utf-8-sig")
            except UnicodeDecodeError:
                continue
            offenders += [f"{path.relative_to(ROOT).as_posix()}: {m.group(0)}" for m in PERSONAL.finditer(text)]
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
