"""Load-order resolution and cross-plugin record winners, read straight from plugin bytes.

This is Forge's own answer to "which plugins override this record and who wins" so the workflow does not
depend on one external MCP. It reads the Skyrim plugin format directly (public UESP layout); it carries no
schema, so field names are not decoded and byte differences can include master-index remaps.
"""
from __future__ import annotations

import configparser
import os
import struct
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from .errors import ValidationError
from .loadorder import parse_plugins_file
from .plugin_header import inspect_plugin_header
from .records import COMPRESSED_FLAG, _record

OFFICIAL = ("skyrim.esm", "update.esm", "dawnguard.esm", "hearthfires.esm", "dragonborn.esm")
SUFFIXES = (".esm", ".esp", ".esl")
DELETED = 0x20
_HEADER = struct.Struct("<4sIII")


@dataclass(slots=True)
class LoadedPlugin:
    name: str
    path: Path
    masters: list[str]
    is_master: bool
    is_light: bool
    index: int = -1          # full-plugin index, -1 for light
    light_index: int = -1    # ESL slot, -1 for full
    lower: str = field(init=False)

    def __post_init__(self) -> None:
        self.lower = self.name.casefold()

    @property
    def load_index(self) -> str:
        return f"FE{self.light_index:03X}" if self.is_light else f"{self.index:02X}"


def _ini_value(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("@ByteArray(") and raw.endswith(")"):
        raw = raw[11:-1]
    return raw


def mo2_sources(instance: Path) -> dict[str, Any]:
    """Profile files and plugin search roots of an MO2 instance, highest priority first.

    modlist.txt is written highest priority first (the reverse of MO2's left pane), '+' = enabled.
    """
    ini_path = instance / "ModOrganizer.ini"
    if not ini_path.is_file():
        raise ValidationError(f"No ModOrganizer.ini in {instance}")
    ini = configparser.ConfigParser(interpolation=None, strict=False, allow_no_value=True)
    ini.optionxform = str
    ini.read_string(ini_path.read_text(encoding="utf-8-sig", errors="replace"))
    get = lambda section, key, default="": _ini_value(ini.get(section, key, fallback=default) or default)
    profile = get("General", "selected_profile", "Default")
    base = Path(get("Settings", "base_directory", str(instance)))
    profiles = Path(get("Settings", "profiles_directory", str(base / "profiles")))
    mods = Path(get("Settings", "mod_directory", str(base / "mods")))
    overwrite = Path(get("Settings", "overwrite_directory", str(base / "overwrite")))
    game = get("General", "gamePath")
    profile_dir = profiles / profile
    roots = [overwrite]
    modlist = profile_dir / "modlist.txt"
    if modlist.is_file():
        for line in modlist.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            if line.startswith("+") and not line.rstrip().endswith("_separator"):
                roots.append(mods / line[1:].strip())
    if game:
        roots.append(Path(game) / "Data")
    plugins = next((p for p in (profile_dir / "plugins.txt", profile_dir / "loadorder.txt") if p.is_file()), None)
    # the folders the caller must be allowed to read; every mod folder lives under `mods`
    top = [overwrite, mods, *([Path(game) / "Data"] if game else [])]
    return {"profile": profile, "profile_dir": profile_dir, "roots": roots, "plugins_file": plugins, "top_roots": top}


def index_plugins(roots: list[Path]) -> dict[str, Path]:
    found: dict[str, Path] = {}
    for root in roots:
        try:
            with os.scandir(root) as entries:
                for entry in entries:
                    if entry.name.casefold().endswith(SUFFIXES) and entry.is_file():
                        found.setdefault(entry.name.casefold(), Path(entry.path))
        except OSError:
            continue
    return found


def resolve_load_order(plugins_file: Path, roots: list[Path]) -> dict[str, Any]:
    """Ordered, indexed plugin list. Official masters first, then plugins.txt order with ESM-flagged files ahead."""
    entries = parse_plugins_file(plugins_file)
    starred = any(entry.enabled for entry in entries)  # plugins.txt marks enabled with '*'; loadorder.txt does not
    wanted: list[str] = []
    seen: set[str] = set()
    for name in [*OFFICIAL, *(e.name for e in entries if e.enabled or not starred)]:
        if name.casefold() not in seen:
            seen.add(name.casefold())
            wanted.append(name)
    files = index_plugins(roots)
    loaded: list[LoadedPlugin] = []
    missing: list[str] = []
    for name in wanted:
        path = files.get(name.casefold())
        if path is None:
            missing.append(name)
            continue
        header = inspect_plugin_header(path, with_hash=False)
        loaded.append(LoadedPlugin(name, path, header.masters, header.is_master_flag or name.casefold().endswith(".esm"),
                                   header.is_light_flag or name.casefold().endswith(".esl")))
    loaded = [p for p in loaded if p.is_master] + [p for p in loaded if not p.is_master]
    full = light = 0
    for plugin in loaded:
        if plugin.is_light:
            plugin.light_index, light = light, light + 1
        else:
            plugin.index, full = full, full + 1
    return {"plugins": loaded, "missing": missing, "full": full, "light": light}


def scan_headers(data: bytes) -> Iterator[tuple[str, int, int, int, int]]:
    """(signature, flags, raw form id, offset, data size) for every record; group headers are stepped into."""
    if data[:4] != b"TES4":
        raise ValidationError("Not a Bethesda plugin")
    offset = 24 + struct.unpack_from("<I", data, 4)[0]
    end = len(data)
    while offset + 24 <= end:
        signature, size, flags, form_id = _HEADER.unpack_from(data, offset)
        if signature == b"GRUP":
            offset += 24
            continue
        yield signature.decode("ascii", "replace"), flags, form_id, offset, size
        offset += 24 + size
    if offset != end:
        raise ValidationError("Plugin ends inside a record or group header")


def peek_editor_id(data: bytes, offset: int, size: int, flags: int) -> str:
    """EditorID without parsing the whole record; looks only in the first 1 KiB of the (decompressed) body."""
    body = offset + 24
    if flags & COMPRESSED_FLAG:
        try:
            chunk = zlib.decompressobj().decompress(data[body + 4:body + size], 1024)
        except zlib.error:
            return ""
    else:
        chunk = data[body:body + min(size, 1024)]
    pos = 0
    while pos + 6 <= len(chunk):
        sub, length = chunk[pos:pos + 4], struct.unpack_from("<H", chunk, pos + 4)[0]
        pos += 6
        if sub == b"EDID":
            return chunk[pos:pos + length].split(b"\0", 1)[0].decode("utf-8", "replace")
        if sub == b"XXXX":
            return ""
        pos += length
    return ""


class _KeyMaker:
    """Raw form id -> (origin plugin, local id), honouring ESL's 12-bit local ids."""

    def __init__(self, plugin: LoadedPlugin, by_lower: dict[str, LoadedPlugin]):
        names = [*plugin.masters, plugin.name]
        self.table = []
        for name in names:
            origin = by_lower.get(name.casefold())
            self.table.append((name.casefold(), 0xFFF if (origin.is_light if origin else name.casefold().endswith(".esl")) else 0xFFFFFF))
        self.own = len(plugin.masters)

    def __call__(self, form_id: int) -> tuple[str, int]:
        high = form_id >> 24
        name, mask = self.table[high] if high < len(self.table) else ("<invalid>", 0xFFFFFF)
        return name, form_id & mask


def parse_form_key(text: str) -> tuple[str, int]:
    """'0x12EB7~Skyrim.esm' or 'Skyrim.esm|12EB7' -> ('skyrim.esm', 0x12EB7)."""
    left, sep, right = text.partition("~")
    if not sep:
        right, sep, left = text.partition("|")
    try:
        return right.strip().casefold(), int(left.strip(), 16)
    except ValueError as error:
        raise ValidationError(f"Form key must look like 0x12EB7~Skyrim.esm: {text!r}") from error


def _printable(raw: bytes) -> str:
    body = raw[:-1] if raw.endswith(b"\0") else raw
    return body.decode("ascii") if body and all(32 <= b < 127 for b in body) else ""


def _dump(subrecords: list[tuple[str, bytes]], plugin: LoadedPlugin) -> list[dict[str, Any]]:
    rows = []
    for signature, raw in subrecords[:200]:
        row: dict[str, Any] = {"sig": signature, "size": len(raw), "hex": raw[:48].hex()}
        text = _printable(raw)
        if text:
            row["text"] = text
        elif len(raw) == 4:
            value = struct.unpack("<I", raw)[0]
            if (value >> 24) <= len(plugin.masters) and value:
                row["maybe_form_key"] = f"0x{value & 0xFFFFFF:X}~{([*plugin.masters, plugin.name])[value >> 24]}"
        rows.append(row)
    return rows


def find_records(order: dict[str, Any], *, editor_id: str = "", form_key: str = "", signature: str = "", exact: bool = True,
                 only_plugins: set[str] | None = None, limit: int = 20, dump: bool = False) -> dict[str, Any]:
    """Every version of the matching records across the load order, winner last.

    editor_id matches records *defined* by a plugin (their first appearance); form_key matches any version.
    Pass `signature` to skip EDID peeks on other record types: it is the main speed lever.
    """
    if not (editor_id or form_key):
        raise ValidationError("Give an editor_id or a form_key")
    plugins: list[LoadedPlugin] = order["plugins"]
    by_lower = {p.lower: p for p in plugins}
    wanted_sig = signature.upper().strip()
    targets: dict[tuple[str, int], dict[str, str]] = {}
    if form_key:
        targets[parse_form_key(form_key)] = {"editor_id": "", "signature": wanted_sig}
    else:
        needle = editor_id.casefold()
        for plugin in plugins:
            if only_plugins is not None and plugin.lower not in only_plugins:
                continue
            data = plugin.path.read_bytes()
            maker = _KeyMaker(plugin, by_lower)
            for sig, flags, fid, offset, size in scan_headers(data):
                if (wanted_sig and sig != wanted_sig) or (fid >> 24) != maker.own:
                    continue
                name = peek_editor_id(data, offset, size, flags)
                if name and ((name.casefold() == needle) if exact else (needle in name.casefold())):
                    targets[maker(fid)] = {"editor_id": name, "signature": sig}
                    if len(targets) >= limit:
                        break
            if len(targets) >= limit:
                break
    versions: dict[tuple[str, int], list[dict[str, Any]]] = {key: [] for key in targets}
    if targets:
        for plugin in plugins:
            data = plugin.path.read_bytes()
            maker = _KeyMaker(plugin, by_lower)
            for sig, flags, fid, offset, size in scan_headers(data):
                key = maker(fid)
                if key not in targets:
                    continue
                record, _ = _record(data, offset)
                versions[key].append({"plugin": plugin, "record": record, "flags": flags, "origin": key[0] == plugin.lower})
    results = []
    for key, chain_src in versions.items():
        if not chain_src:
            results.append({"form_key": f"0x{key[1]:X}~{key[0]}", "found": False})
            continue
        meta = targets[key]
        editor = meta["editor_id"] or next((v["record"].editor_id for v in chain_src if v["record"].editor_id), "")
        chain = []
        previous: dict[str, list[bytes]] | None = None
        for version in chain_src:
            current: dict[str, list[bytes]] = {}
            for sub, raw in version["record"].subrecords:
                current.setdefault(sub, []).append(raw)
            entry = {
                "plugin": version["plugin"].name, "load_index": version["plugin"].load_index,
                "role": "origin" if version["origin"] else "override",
                "signature": version["record"].signature, "flags_hex": f"0x{version['flags']:08X}",
                "deleted": bool(version["flags"] & DELETED), "data_size": version["record"].data_size,
                "subrecords": len(version["record"].subrecords),
            }
            if previous is not None:
                changed = sorted(sig for sig in current.keys() | previous.keys() if current.get(sig) != previous.get(sig))
                entry["changed_subrecords"] = changed
                entry["itm_candidate"] = not changed and not (version["flags"] & DELETED)
            chain.append(entry)
            previous = current
        winner = chain_src[-1]
        row = {
            "form_key": f"0x{key[1]:X}~{key[0]}", "origin_plugin": chain[0]["plugin"] if chain[0]["role"] == "origin" else key[0],
            "editor_id": editor, "signature": chain[-1]["signature"], "winner": chain[-1]["plugin"],
            "conflict": len(chain) > 1, "overrides": len(chain) - 1, "chain": chain,
        }
        if dump:
            row["winner_subrecords"] = _dump(winner["record"].subrecords, winner["plugin"])
        results.append(row)
    return {
        "result": "PASS" if results else "NO_MATCH",
        "load_order": {"plugins": len(plugins), "full": order["full"], "light": order["light"], "missing": order["missing"]},
        "records": results,
        "evidence": "Parsed from plugin bytes by Forge. changed_subrecords is a raw byte comparison: a subrecord holding FormIDs can differ only because "
                    "the plugins' master lists differ. Not xEdit, houseCARL or Skyrim runtime confirmation.",
    }
