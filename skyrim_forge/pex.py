"""Compiled Papyrus (.pex) reader and one diagnostics format for the official compiler and Caprica.

PEX layout (UESP "Compiled Script File Format"): u32 magic 0xFA57C0DE, u8 major, u8 minor, u16 game id
(1 Skyrim, 2 Fallout 4, 3 Fallout 76, 4 Starfield), u64 compile time, wstrings source / user / machine,
string table (u16 count of u16-length strings), debug info (u8 flag; u64 time; functions: u16 object, u16 state,
u16 name, u8 type, u16 count, u16 line per instruction; Fallout 4 adds property groups and struct orders),
user flags (u16 count of u16 name + u8 bit), objects (u16 name, u32 size including itself, data whose
first u16 is the parent class). Skyrim files are big-endian; Fallout 4 files are little-endian.

Diagnostics: both compilers print `<file>.psc(<line>,<col>): <message>`; Caprica adds a space before the
parenthesis and an `Error:`/`Warning:` label, and counts columns from 1 where the official compiler counts from 0.
Every compiler line becomes {"file", "line", "column" (1-based), "severity", "message", "compiler"}.
"""
from __future__ import annotations

import re
import struct
import tempfile
from pathlib import Path
from typing import Any

from .config import ForgeConfig
from .errors import ValidationError
from .tools import resolve_tool, run_process

MAGIC = 0xFA57C0DE
GAMES = {1: "Skyrim", 2: "Fallout 4", 3: "Fallout 76", 4: "Starfield"}
DIAG_OFFICIAL = re.compile(r"^(?P<file>.+?\.psc)\((?P<line>\d+),(?P<col>\d+)\):\s*(?P<msg>.+)$", re.I)
DIAG_CAPRICA = re.compile(r"^(?P<file>.+?\.psc)\s*\((?P<line>\d+),\s*(?P<col>\d+)(?::\d+)?\):\s*"
                          r"(?P<sev>Fatal Error|Error|Warning)?(?:\s+(?P<code>W?\d+))?:?\s*(?P<msg>.+)$", re.I)


class _Reader:
    def __init__(self, data: bytes, endian: str):
        self.data, self.index, self.endian = data, 0, endian

    def take(self, fmt: str) -> int:
        value = struct.unpack_from(self.endian + fmt, self.data, self.index)[0]
        self.index += struct.calcsize(fmt)
        return value

    def wstr(self) -> str:
        length = self.take("H")
        text = self.data[self.index:self.index + length].decode("cp1252", "replace")
        self.index += length
        return text


def parse(data: bytes) -> dict[str, Any]:
    if len(data) < 8:
        raise ValidationError("not a PEX file (too short)")
    if struct.unpack_from(">I", data)[0] == MAGIC:
        reader = _Reader(data, ">")
    elif struct.unpack_from("<I", data)[0] == MAGIC:
        reader = _Reader(data, "<")
    else:
        raise ValidationError("not a PEX file (bad magic)")
    reader.take("I")
    major, minor, game = reader.take("B"), reader.take("B"), reader.take("H")
    out: dict[str, Any] = {"endian": "big" if reader.endian == ">" else "little", "version": f"{major}.{minor}", "game_id": game,
                           "game": GAMES.get(game, str(game)), "compile_time": reader.take("Q"), "source": reader.wstr(),
                           "user": reader.wstr(), "machine": reader.wstr()}
    try:
        strings = [reader.wstr() for _ in range(reader.take("H"))]
        out["strings"] = len(strings)
        functions = 0
        if reader.take("B"):
            reader.take("Q")
            for _ in range(reader.take("H")):
                reader.take("H"); reader.take("H"); reader.take("H"); reader.take("B")
                count = reader.take("H")
                reader.index += 2 * count
                functions += 1
            if game == 2:
                for _ in range(reader.take("H")):
                    reader.take("H"); reader.take("H"); reader.take("H"); reader.take("I")
                    count = reader.take("H"); reader.index += 2 * count
                for _ in range(reader.take("H")):
                    reader.take("H"); reader.take("H")
                    count = reader.take("H"); reader.index += 2 * count
        out["debug_functions"] = functions
        flags = []
        for _ in range(reader.take("H")):
            flags.append(strings[reader.take("H")])
            reader.take("B")
        out["user_flags"] = flags
        objects = []
        for _ in range(reader.take("H")):
            name = strings[reader.take("H")]
            size = reader.take("I")
            start = reader.index
            parent = strings[struct.unpack_from(reader.endian + "H", data, start)[0]] if size >= 6 else ""
            objects.append({"name": name, "parent": parent})
            reader.index = start + size - 4
        out["objects"] = objects
    except (IndexError, struct.error) as exc:
        raise ValidationError(f"PEX tables unreadable: {exc}") from exc
    return out


def info(path: Path) -> dict[str, Any]:
    report = parse(Path(path).read_bytes())
    return {"result": "PASS", "file": str(path), **report,
            "evidence": "Header, string table, debug and object tables parsed; bytecode is not disassembled."}


def parse_diagnostics(text: str, compiler: str) -> list[dict[str, Any]]:
    rule = DIAG_OFFICIAL if compiler == "official" else DIAG_CAPRICA
    found = []
    for line in text.splitlines():
        match = rule.match(line.strip())
        if not match:
            continue
        label = (match.groupdict().get("sev") or "").lower()
        message = match.group("msg").strip()
        warning = "warn" in label or (compiler == "official" and message.lower().startswith("warning"))
        # The official compiler counts columns from 0 and Caprica from 1 (same planted error: 4 vs 5); report 1-based.
        column = int(match.group("col")) + (1 if compiler == "official" else 0)
        found.append({"file": match.group("file"), "line": int(match.group("line")), "column": column,
                      "severity": "warning" if warning else "error", "message": message, "compiler": compiler})
    return found


def check(config: ForgeConfig, scripts: list[Path], *, imports: list[Path], flags_file: Path, compiler: str = "official") -> dict[str, Any]:
    """Compile into a throwaway folder and return structured diagnostics; nothing is written to the workspace."""
    if compiler not in ("official", "caprica"):
        raise ValidationError("compiler must be official or caprica")
    tool, exe = resolve_tool(config, "papyrus_compiler" if compiler == "official" else "caprica", require_pin=True)
    if not flags_file.is_file():
        raise FileNotFoundError(flags_file)
    results, diagnostics = [], []
    with tempfile.TemporaryDirectory(prefix="forge-papyrus-check-") as temp:
        out = Path(temp)
        for script in scripts:
            script = script.resolve(strict=True)
            folders = ";".join(dict.fromkeys([str(script.parent)] + [str(p.resolve(strict=True)) for p in imports]))
            if compiler == "official":
                args = [str(script), f"-f={flags_file}", f"-i={folders}", f"-o={out}"]
            else:
                args = ["-g", "skyrim", "-f", str(flags_file), "-i", folders, "-o", str(out), "--ignorecwd", str(script)]
            process = run_process(exe, args, cwd=out, timeout_seconds=tool.timeout_seconds)
            text = f"{process['stdout']}\n{process['stderr']}"
            found = parse_diagnostics(text, compiler)
            pex = out / f"{script.stem}.pex"
            if not found and (process["returncode"] != 0 or not pex.is_file()):
                tail = [line for line in text.strip().splitlines() if line.strip()][-1:] or ["compile failed"]
                found = [{"file": str(script), "line": 0, "column": 0, "severity": "error", "message": tail[0][:300], "compiler": compiler}]
            diagnostics += found
            row: dict[str, Any] = {"script": str(script), "compiled": pex.is_file(), "returncode": process["returncode"]}
            if pex.is_file():
                row["pex"] = {key: value for key, value in parse(pex.read_bytes()).items() if key in ("game", "endian", "version", "objects")}
            results.append(row)
    errors = sum(item["severity"] == "error" for item in diagnostics)
    return {"result": "FAIL" if errors or not all(r["compiled"] for r in results) else "PASS", "compiler": compiler,
            "scripts": results, "diagnostics": diagnostics, "errors": errors,
            "warnings": len(diagnostics) - errors, "evidence": "Compiler output parsed into one format; PEX written to a temporary folder only."}
