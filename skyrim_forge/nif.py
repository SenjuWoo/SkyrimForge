"""NIF meshes: header, block types, string table and texture-set references; headless Blender round trips through PyNifly.

Header per niftools nif.xml: "Gamebryo File Format, Version x\\n", u32 version, u8 endian, u32 user version,
u32 block count, BS stream header (u32 BS version, u8-length export strings: author, [u32 if BSVER > 130],
process script when BSVER < 131, export script, max filepath when BSVER >= 103), u16 block-type count and
u32-length type names, u16 type index per block, u32 size per block, u32 string count, u32 max length,
u32-length strings, u32 group count and sizes, then the blocks and a footer (u32 root count + refs).
Skyrim SE meshes: 20.2.0.7, user version 12, BS version 100; Skyrim LE uses BS version 83.
BSShaderTextureSet = i32 count + u32-length paths. Effect-shader textures stored inside other blocks are not read.
"""
from __future__ import annotations

import json
import struct
from pathlib import Path
from typing import Any

from .config import ForgeConfig
from .errors import ToolError, ValidationError
from .safety import require_approval, require_within
from .tools import resolve_tool, run_process

BLENDER_SCRIPT = Path(__file__).with_name("nif_blender.py")
RESULT_MARK = "SKYRIMFORGE_RESULT "


class _Reader:
    def __init__(self, data: bytes, index: int = 0):
        self.data, self.index = data, index

    def take(self, fmt: str) -> Any:
        values = struct.unpack_from("<" + fmt, self.data, self.index)
        self.index += struct.calcsize("<" + fmt)
        return values[0] if len(values) == 1 else values

    def short(self) -> str:
        length = self.data[self.index]
        text = self.data[self.index + 1:self.index + 1 + length].rstrip(b"\0").decode("cp1252", "replace")
        self.index += 1 + length
        return text

    def sized(self) -> str:
        length = self.take("I")
        if length > 1 << 20:
            raise ValidationError(f"string length {length} is not plausible")
        text = self.data[self.index:self.index + length].decode("cp1252", "replace")
        self.index += length
        return text


def read(path: Path) -> dict[str, Any]:
    data = Path(path).read_bytes()
    newline = data.find(b"\n", 0, 128)
    if newline < 0 or not data.startswith((b"Gamebryo File Format", b"NetImmerse File Format")):
        raise ValidationError(f"{Path(path).name}: not a NIF file")
    reader = _Reader(data, newline + 1)
    try:
        version = reader.take("I")
        text_version = ".".join(str((version >> shift) & 0xFF) for shift in (24, 16, 8, 0))
        if version != 0x14020007:
            raise ValidationError(f"NIF version {text_version}: only 20.2.0.7 (Skyrim, Fallout 4) is read")
        endian, user, count, bs_version = reader.take("B"), reader.take("I"), reader.take("I"), reader.take("I")
        author = reader.short()
        if bs_version > 130:
            reader.take("I")
        process = reader.short() if bs_version < 131 else ""
        export = reader.short()
        if bs_version >= 103:
            reader.short()
        types = [reader.sized() for _ in range(reader.take("H"))]
        type_index = [reader.take("H") for _ in range(count)]
        sizes = [reader.take("I") for _ in range(count)]
        strings_count = reader.take("I"); reader.take("I")
        strings = [reader.sized() for _ in range(strings_count)]
        groups = reader.take("I")  # read first: "index += 4 * take()" would lose take()'s own 4-byte advance
        reader.index += 4 * groups
    except struct.error as exc:
        raise ValidationError(f"{Path(path).name}: header truncated ({exc})") from exc
    blocks, position = [], reader.index
    for index, size in zip(type_index, sizes):
        blocks.append({"type": types[index & 0x7FFF], "offset": position, "size": size})
        position += size
    roots = None
    if position + 4 <= len(data):
        candidate = struct.unpack_from("<I", data, position)[0]
        if position + 4 + 4 * candidate == len(data):
            roots = candidate
    return {"file": str(path), "version": text_version, "endian": "little" if endian else "big", "user_version": user,
            "bs_version": bs_version, "game": {100: "Skyrim SE", 83: "Skyrim LE", 130: "Fallout 4"}.get(bs_version, f"BS {bs_version}"),
            "author": author, "process_script": process, "export_script": export, "blocks": blocks, "strings": strings,
            "roots": roots, "size_ok": roots is not None, "_data": data}


def info(path: Path) -> dict[str, Any]:
    nif = read(path)
    counts: dict[str, int] = {}
    for block in nif["blocks"]:
        counts[block["type"]] = counts.get(block["type"], 0) + 1
    return {"result": "PASS" if nif["size_ok"] else "FAIL", **{k: v for k, v in nif.items() if k not in ("_data", "blocks", "strings")},
            "block_count": len(nif["blocks"]), "block_counts": counts, "string_count": len(nif["strings"]),
            "evidence": "Header and block table parsed per nif.xml; block sizes sum to the footer when size_ok is true."}


def textures(path: Path) -> list[str]:
    nif = read(path)
    found: list[str] = []
    for block in nif["blocks"]:
        if block["type"] == "BSShaderTextureSet":
            reader = _Reader(nif["_data"], block["offset"])
            for _ in range(max(0, reader.take("i"))):
                value = reader.sized()
                if value:
                    found.append(value)
    return sorted(set(found))


def _normalize(value: str) -> str:
    key = value.replace("/", "\\").lower().lstrip("\\")
    if key.startswith("data\\"):
        key = key[5:]
    return key if key.startswith("textures\\") else "textures\\" + key


def refs(path: Path, *, data_roots: list[Path], archives: list[Path]) -> dict[str, Any]:
    """Texture paths a mesh names and whether each exists in the given loose folders or archive name tables."""
    from . import bsa
    known: set[str] = set()
    for root in data_roots:
        known |= {p.relative_to(root).as_posix().replace("/", "\\").lower() for p in root.rglob("*.dds")}
    for archive in archives:
        known |= {entry.path.lower() for entry in bsa.read(archive).entries}
    rows = [{"path": value, "resolved": _normalize(value), "found": _normalize(value) in known} for value in textures(path)]
    missing = [row for row in rows if not row["found"]]
    checked = bool(data_roots or archives)
    return {"result": "FAIL" if checked and missing else "PASS", "file": str(path), "textures": rows,
            "missing": len(missing) if checked else None, "checked_against": {"folders": len(data_roots), "archives": len(archives)},
            "evidence": "Texture-set paths only; effect-shader and material textures inside other blocks are not listed."}


def blender(config: ForgeConfig, mode: str, source: Path, output: Path, *, approved: bool) -> dict[str, Any]:
    """Headless Blender with PyNifly loaded by path for this process only: import (.nif -> .blend), export, roundtrip."""
    if mode not in ("import", "export", "roundtrip"):
        raise ValidationError("mode must be import, export or roundtrip")
    require_approval(approved, f"Blender {mode}")
    output = require_within(output, config.workspace_root)
    tool, exe = resolve_tool(config, "blender", require_pin=False)
    _, addon = resolve_tool(config, "pynifly", require_pin=True)
    addon_root = addon.parent.parent  # pinned file is io_scene_nifly/NiflyDLL.dll; Blender needs the folder above it
    output.parent.mkdir(parents=True, exist_ok=True)
    process = run_process(exe, ["-b", "--factory-startup", "--python", str(BLENDER_SCRIPT), "--", mode, str(addon_root), str(source), str(output)],
                          cwd=output.parent, timeout_seconds=tool.timeout_seconds)
    result = None
    for line in f"{process['stdout']}\n{process['stderr']}".splitlines():
        if line.startswith(RESULT_MARK):
            result = json.loads(line[len(RESULT_MARK):])
    if not result or not result.get("ok") or not output.is_file():
        raise ToolError(f"Blender {mode} failed: {(result or {}).get('error') or process['stderr'][-600:]}")
    report: dict[str, Any] = {"result": "PASS", "mode": mode, "input": str(source), "output": str(output), **{k: v for k, v in result.items() if k != "ok"}}
    if output.suffix.lower() == ".nif":
        report["output_header"] = {k: v for k, v in info(output).items() if k in ("version", "bs_version", "game", "block_count", "size_ok")}
    return report
