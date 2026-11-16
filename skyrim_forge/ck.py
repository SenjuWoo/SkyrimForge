"""Creation Kit command-line jobs. The switch list is read from CreationKit.exe's own strings, never assumed.

CreationKit.exe (file version 1.7.99 on the reference install) carries: -OptimizeMasterFile -BuildShaderList -ExportDialogue -GenerateLips
-GenerateSingleLip -ExportFaceGenData -TagifyMasterfile -TagifyPlugin -ExportText -CompileTextExport
-DelocalizeMasterfile -DelocalizeLocalMasterfile -DumpNeededFiles -OptimizeDLC -GenerateSEQ -ConvertToESL
(fact creation_kit.switches, tier installed). The `-<Switch>:<Plugin>` argument form is the documented community
convention (tier secondary), so every run is a dry run until approved and the receipt records exactly what ran.
An approved run snapshots Data before and after and lists every file the Creation Kit changed.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from .config import ForgeConfig
from .errors import ValidationError
from .tools import resolve_tool, run_process
from .util import json_dump, utc_now

SWITCH_RX = re.compile(rb"-(OptimizeMasterFile|BuildShaderList|ExportDialogue|GenerateLips|GenerateSingleLip|ExportFaceGenData|"
                       rb"TagifyMasterfile|TagifyPlugin|ExportText|CompileTextExport|DelocalizeMasterfile|DelocalizeLocalMasterfile|"
                       rb"DumpNeededFiles|OptimizeDLC|GenerateSEQ|ConvertToESL|GeneratePreCombined|GeneratePreVisData|[A-Z][A-Za-z]{5,40})\x00")
KNOWN = {"OptimizeMasterFile", "BuildShaderList", "ExportDialogue", "GenerateLips", "GenerateSingleLip", "ExportFaceGenData",
         "TagifyMasterfile", "TagifyPlugin", "ExportText", "CompileTextExport", "DelocalizeMasterfile", "DelocalizeLocalMasterfile",
         "DumpNeededFiles", "OptimizeDLC", "GenerateSEQ", "ConvertToESL"}
NO_PLUGIN = {"BuildShaderList", "OptimizeDLC"}


def _game_root(config: ForgeConfig) -> Path:
    if not config.skyrim_data:
        raise ValidationError("paths.skyrim_data is not set; the Creation Kit lives beside the game")
    return config.skyrim_data.parent


def switches(exe: Path) -> list[str]:
    data = exe.read_bytes()
    found = {match.group(1).decode() for match in SWITCH_RX.finditer(data)}
    return sorted(found & KNOWN)


def info(config: ForgeConfig) -> dict[str, Any]:
    game = _game_root(config)
    exe = game / "CreationKit.exe"
    if not exe.is_file():
        return {"result": "BLOCKED", "creation_kit": None, "reason": f"CreationKit.exe not found in {game}", "fix": "install the Creation Kit from Steam"}
    from .skse_pe import inspect as pe_inspect
    version = None
    try:
        version = pe_inspect(exe).get("file_version")
    except Exception:  # version is informative only
        version = None
    return {"result": "PASS", "creation_kit": str(exe), "file_version": version, "switches": switches(exe),
            "ckpe": (game / "CKPE.dll").is_file(), "papyrus_compiler": (game / "Papyrus Compiler" / "PapyrusCompiler.exe").is_file(),
            "tools": {name: (game / rel).is_file() for name, rel in (("xwmaencode", "Tools/Audio/xwmaencode.exe"),
                                                                       ("LipGenerator", "Tools/LipGen/LipGenerator/LipGenerator.exe"))},
            "evidence": "Switch names read from CreationKit.exe's string table; argument forms are convention (secondary)."}


def plan(config: ForgeConfig, switch: str, plugin: str | None, extra: list[str]) -> list[str]:
    game = _game_root(config)
    exe = game / "CreationKit.exe"
    if not exe.is_file():
        raise ValidationError(f"CreationKit.exe not found in {game}")
    available = switches(exe)
    if switch not in available:
        raise ValidationError(f"-{switch} is not among this CreationKit.exe's switches: {', '.join(available)}")
    if switch in NO_PLUGIN:
        return [f"-{switch}", *extra]
    if not plugin:
        raise ValidationError(f"-{switch} needs --plugin <file in Data>")
    if not (config.skyrim_data / plugin).is_file():
        raise ValidationError(f"{plugin} is not in the game's Data; deploy it first (forge deploy --approve)")
    return [f"-{switch}:{plugin}", *extra]


def _snapshot(data: Path) -> dict[str, tuple[int, float]]:
    rows: dict[str, tuple[int, float]] = {}
    for folder, _, files in os.walk(data):
        for name in files:
            path = Path(folder) / name
            try:
                stat = path.stat()
            except OSError:
                continue
            rows[str(path.relative_to(data))] = (stat.st_size, stat.st_mtime)
    return rows


def run(config: ForgeConfig, switch: str, plugin: str | None = None, extra: list[str] | None = None, *, approved: bool = False) -> dict[str, Any]:
    args = plan(config, switch, plugin, list(extra or []))
    game = _game_root(config)
    report: dict[str, Any] = {"result": "PASS", "switch": switch, "argv": ["CreationKit.exe", *args], "cwd": str(game), "dry_run": not approved,
                              "writes_into": str(config.skyrim_data), "argument_form": "secondary (community convention)"}
    if not approved:
        report["hint"] = "review the argv and back up the plugin, then rerun with --approve; the Creation Kit may show a window"
        return report
    tool, exe = resolve_tool(config, "creation_kit", require_pin=True)
    before = _snapshot(config.skyrim_data)
    process = run_process(exe, args, cwd=game, timeout_seconds=max(tool.timeout_seconds, 3600))
    after = _snapshot(config.skyrim_data)
    written = sorted(key for key, value in after.items() if before.get(key) != value)
    receipt = config.config_path.parent / "ck-runs" / f"{utc_now().replace(':', '').replace('-', '')}-{switch}.json"
    json_dump(receipt, {"switch": switch, "argv": process["command"], "returncode": process["returncode"], "written": written, "time": utc_now()})
    report.update(returncode=process["returncode"], written=written, receipt=str(receipt),
                  result="PASS" if process["returncode"] == 0 else "FAIL")
    return report
