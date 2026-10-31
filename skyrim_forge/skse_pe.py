"""Read an x64 SKSE plugin DLL without loading it: PE headers, exports, imports, PluginVersionData.

Forge never launches a DLL to inspect it. The offsets below come from
CommonLibSSE-NG's `SKSE::PluginVersionData` static asserts (0x350 bytes) and
`REL::Version::pack`; anything Forge cannot prove from those bytes is reported
as unknown rather than guessed.
"""
from __future__ import annotations

import struct
from pathlib import Path
from typing import Any

from .errors import ValidationError
from .util import sha256_bytes, sha256_file

PE32PLUS = 0x20B
MACHINE_AMD64 = 0x8664
DIR_EXPORT = 0
DIR_IMPORT = 1
DIR_DEBUG = 6
# PluginVersionData layout, asserted by CommonLibSSE-NG include/SKSE/Interfaces.h.
PVD_SIZE = 0x350
PVD_NAME = 0x008
PVD_AUTHOR = 0x108
PVD_EMAIL = 0x208
PVD_INDEPENDENCE_EX = 0x304
PVD_INDEPENDENCE = 0x308
PVD_VERSIONS = 0x30C
PVD_XSE_MINIMUM = 0x34C
INDEPENDENCE = {0x1: "AddressLibraryPostAE", 0x2: "SignatureScanning", 0x4: "StructsPost629"}
INDEPENDENCE_EX = {0x1: "NoStructUse", 0x2: "AddressLibraryV5"}
NETWORK_DLLS = {"ws2_32.dll", "winhttp.dll", "wininet.dll", "urlmon.dll", "dnsapi.dll", "mswsock.dll"}
PROCESS_FUNCTIONS = ("CreateProcess", "ShellExecute", "WinExec", "CreateRemoteThread", "LoadLibrary")
STORAGE_DLLS = {"dstorage.dll", "dstoragecore.dll"}


def _unpack(fmt: str, data: bytes, offset: int) -> tuple[Any, ...]:
    if offset < 0 or offset + struct.calcsize(fmt) > len(data):
        raise ValidationError(f"PE structure at 0x{offset:X} runs past the file")
    return struct.unpack_from(fmt, data, offset)


def _text(data: bytes, offset: int, size: int) -> str:
    return data[offset:offset + size].split(b"\x00", 1)[0].decode("utf-8", "replace")


def parse_version(packed: int) -> dict[str, int]:
    """Decode REL::Version::pack: major<<24 | minor<<16 | patch<<4 | build."""
    return {"major": (packed >> 24) & 0xFF, "minor": (packed >> 16) & 0xFF, "patch": (packed >> 4) & 0xFFF, "build": packed & 0xF}


class PEImage:
    """Minimal read-only PE32+ view: headers, sections, RVA translation and data directories."""

    def __init__(self, data: bytes):
        self.data = data
        if len(data) < 0x40 or data[:2] != b"MZ":
            raise ValidationError("Not a Windows PE binary (missing MZ header)")
        self.pe_offset = _unpack("<I", data, 0x3C)[0]
        if data[self.pe_offset:self.pe_offset + 4] != b"PE\x00\x00":
            raise ValidationError("Not a Windows PE binary (missing PE signature)")
        (self.machine, self.section_count, self.timestamp, _, _, optional_size,
         self.characteristics) = _unpack("<HHIIIHH", data, self.pe_offset + 4)
        self.optional = self.pe_offset + 24
        self.magic = _unpack("<H", data, self.optional)[0]
        if self.magic != PE32PLUS:
            raise ValidationError(f"Expected a PE32+ image, got optional-header magic 0x{self.magic:04X}")
        self.checksum_offset = self.optional + 64
        self.entry_point = _unpack("<I", data, self.optional + 16)[0]
        self.image_base = _unpack("<Q", data, self.optional + 24)[0]
        directory_count = _unpack("<I", data, self.optional + 108)[0]
        self.directories = [_unpack("<II", data, self.optional + 112 + index * 8) for index in range(min(directory_count, 16))]
        self.sections = []
        table = self.optional + optional_size
        for index in range(self.section_count):
            name, virtual_size, virtual_address, raw_size, raw_pointer = _unpack("<8sIIII", data, table + index * 40)
            self.sections.append({"name": name.rstrip(b"\x00").decode("latin-1"), "virtual_address": virtual_address,
                                  "virtual_size": virtual_size, "raw_size": raw_size, "raw_pointer": raw_pointer})

    def directory(self, index: int) -> tuple[int, int]:
        return self.directories[index] if index < len(self.directories) else (0, 0)

    def offset(self, rva: int) -> int | None:
        for section in self.sections:
            start = section["virtual_address"]
            span = max(section["virtual_size"], section["raw_size"])
            if start <= rva < start + span:
                delta = rva - start
                if delta >= section["raw_size"]:
                    return None  # uninitialised data has no file bytes
                return section["raw_pointer"] + delta
        return rva if rva < len(self.data) else None

    def exports(self) -> list[dict[str, Any]]:
        rva, size = self.directory(DIR_EXPORT)
        if not rva or not size:
            return []
        start = self.offset(rva)
        if start is None:
            return []
        _, _, _, name_rva, _, count, names, functions, ordinals = _unpack("<IIHHIIIII", self.data, start)
        rows = []
        names_offset = self.offset(names) if names else None
        ordinals_offset = self.offset(ordinals) if ordinals else None
        functions_offset = self.offset(functions) if functions else None
        for index in range(min(count, 4096)):
            name_offset = self.offset(_unpack("<I", self.data, names_offset + index * 4)[0]) if names_offset is not None else None
            ordinal = _unpack("<H", self.data, ordinals_offset + index * 2)[0] if ordinals_offset is not None else index
            function_rva = _unpack("<I", self.data, functions_offset + ordinal * 4)[0] if functions_offset is not None else 0
            rows.append({"name": _text(self.data, name_offset, 512) if name_offset is not None else f"ordinal_{ordinal}",
                         "rva": function_rva})
        return rows

    def imports(self) -> list[dict[str, Any]]:
        rva, size = self.directory(DIR_IMPORT)
        if not rva or not size:
            return []
        start = self.offset(rva)
        if start is None:
            return []
        rows = []
        position = start
        while position + 20 <= len(self.data):
            original_thunk, _, _, name_rva, first_thunk = _unpack("<IIIII", self.data, position)
            if not (original_thunk or name_rva or first_thunk):
                break
            name_offset = self.offset(name_rva)
            dll = _text(self.data, name_offset, 260) if name_offset is not None else "?"
            functions = []
            thunk = self.offset(original_thunk or first_thunk)
            if thunk is not None:
                for index in range(4096):
                    entry = _unpack("<Q", self.data, thunk + index * 8)[0]
                    if not entry:
                        break
                    if entry & 0x8000000000000000:
                        functions.append(f"#{entry & 0xFFFF}")
                    else:
                        hint_offset = self.offset(entry & 0x7FFFFFFF)
                        functions.append(_text(self.data, hint_offset + 2, 256) if hint_offset is not None else "?")
            rows.append({"dll": dll, "functions": functions})
            position += 20
        return rows

    def file_version(self) -> dict[str, int] | None:
        """Find VS_FIXEDFILEINFO by its unique signature; the resource tree is not walked."""
        signature = struct.pack("<I", 0xFEEF04BD)
        offset = self.data.find(signature)
        if offset < 0 or offset + 52 > len(self.data):
            return None
        _, _, version_ms, version_ls = _unpack("<IIII", self.data, offset)
        return {"major": version_ms >> 16, "minor": version_ms & 0xFFFF, "patch": version_ls >> 16, "build": version_ls & 0xFFFF}


def _version_data(image: PEImage, exports: list[dict[str, Any]]) -> dict[str, Any] | None:
    entry = next((row for row in exports if row["name"] == "SKSEPlugin_Version"), None)
    if entry is None:
        return None
    start = image.offset(entry["rva"])
    if start is None or start + PVD_SIZE > len(image.data):
        return {"error": "SKSEPlugin_Version export does not point at a readable 0x350-byte structure"}
    data = image.data
    compatible = [value for value in _unpack("<16I", data, start + PVD_VERSIONS) if value]
    independence = _unpack("<I", data, start + PVD_INDEPENDENCE)[0]
    independence_ex = _unpack("<I", data, start + PVD_INDEPENDENCE_EX)[0]
    return {
        "data_version": _unpack("<I", data, start)[0],
        "plugin_version": _unpack("<I", data, start + 4)[0],
        "plugin_version_decoded": parse_version(_unpack("<I", data, start + 4)[0]),
        "name": _text(data, start + PVD_NAME, 256),
        "author": _text(data, start + PVD_AUTHOR, 256),
        "support_email": _text(data, start + PVD_EMAIL, 252),
        "address_independence": [label for bit, label in INDEPENDENCE.items() if independence & bit],
        "structure_independence": [label for bit, label in INDEPENDENCE_EX.items() if independence_ex & bit],
        "compatible_versions": [parse_version(value) for value in compatible],
        "xse_minimum": parse_version(_unpack("<I", data, start + PVD_XSE_MINIMUM)[0]) if _unpack("<I", data, start + PVD_XSE_MINIMUM)[0] else None,
    }


def _load(path: Path) -> tuple[Path, PEImage]:
    target = path.resolve(strict=True)
    if target.suffix.casefold() not in {".dll", ".exe"}:
        raise ValidationError("SKSE inspection expects a .dll (or .exe) image")
    return target, PEImage(target.read_bytes())


def inspect(path: Path) -> dict[str, Any]:
    """Report architecture, exports, PluginVersionData and the imported DLL surface."""
    target, image = _load(path)
    exports = image.exports()
    names = {row["name"] for row in exports}
    imports = image.imports()
    errors = []
    if image.machine != MACHINE_AMD64:
        errors.append(f"Expected x86-64 machine 0x{MACHINE_AMD64:04X}, got 0x{image.machine:04X}")
    if not image.characteristics & 0x2000:
        errors.append("PE image is not marked as a DLL")
    if "SKSEPlugin_Version" not in names and not {"SKSEPlugin_Load", "SKSEPlugin_Query"} & names:
        errors.append("No SKSE plugin exports (SKSEPlugin_Version or SKSEPlugin_Load/Query) found")
    return {
        "result": "PASS" if not errors else "FAIL",
        "path": str(target), "size": len(image.data), "sha256": sha256_file(target),
        "machine": f"0x{image.machine:04X}", "architecture": "PE32+" if image.magic == PE32PLUS else "unknown",
        "timestamp": image.timestamp, "image_base": f"0x{image.image_base:X}", "entry_point_rva": f"0x{image.entry_point:X}",
        "sections": image.sections, "exports": exports, "imports": [row["dll"] for row in imports],
        "skse": {"version_export": "SKSEPlugin_Version" in names, "load_export": "SKSEPlugin_Load" in names,
                 "query_export": "SKSEPlugin_Query" in names, "version_data": _version_data(image, exports)},
        "file_version": image.file_version(), "errors": errors,
        "evidence": "Static PE and export-table evidence. Loading, address-library resolution and coexistence with other plugins require a real SKSE session.",
    }


def audit_imports(path: Path) -> dict[str, Any]:
    """Inventory every imported DLL and flag network, process-execution and DirectStorage use."""
    target, image = _load(path)
    imports = image.imports()
    categories: dict[str, list[str]] = {"network": [], "process_execution": [], "directstorage": []}
    for row in imports:
        dll = row["dll"].casefold()
        if dll in NETWORK_DLLS:
            categories["network"].append(row["dll"])
        if dll in STORAGE_DLLS:
            categories["directstorage"].append(row["dll"])
        for function in row["functions"]:
            if function.startswith(PROCESS_FUNCTIONS):
                categories["process_execution"].append(f"{row['dll']}!{function}")
    return {"result": "PASS", "path": str(target), "sha256": sha256_file(target), "imports": imports,
            "categories": {key: sorted(set(value)) for key, value in categories.items()},
            "flags": {key: bool(value) for key, value in categories.items()},
            "evidence": "Import table only. Delayed/dynamic resolution (GetProcAddress) and behaviour at runtime are not proven."}


def _normalized(image: PEImage) -> bytes:
    """Zero the linker-owned bytes that differ between identical builds: COFF time, checksum, debug timestamps."""
    data = bytearray(image.data)
    struct.pack_into("<I", data, image.pe_offset + 8, 0)
    struct.pack_into("<I", data, image.checksum_offset, 0)
    rva, size = image.directory(DIR_DEBUG)
    start = image.offset(rva) if rva else None
    if start is not None:
        for offset in range(start, min(start + size, len(data)), 28):  # sizeof(IMAGE_DEBUG_DIRECTORY)
            struct.pack_into("<I", data, offset + 4, 0)
    return bytes(data)


def verify_reproducible(built: Path, reference: Path) -> dict[str, Any]:
    """Compare two DLLs byte-for-byte, then with linker timestamps normalised."""
    left_path, left = _load(built)
    right_path, right = _load(reference)
    identical = left.data == right.data
    normalized = _normalized(left) == _normalized(right) if not identical else True
    differing = []
    if not normalized and len(left.data) == len(right.data):
        cursor = 0
        while cursor < len(left.data) and len(differing) < 20:
            if left.data[cursor] != right.data[cursor]:
                run = cursor
                while run < len(left.data) and left.data[run] != right.data[run]:
                    run += 1
                section = next((item["name"] for item in left.sections
                                if item["raw_pointer"] <= cursor < item["raw_pointer"] + item["raw_size"]), "headers")
                differing.append({"offset": f"0x{cursor:X}", "length": run - cursor, "section": section})
                cursor = run
            else:
                cursor += 1
    return {
        "result": "PASS" if identical or normalized else "FAIL",
        "built": {"path": str(left_path), "size": len(left.data), "sha256": sha256_bytes(left.data)},
        "reference": {"path": str(right_path), "size": len(right.data), "sha256": sha256_bytes(right.data)},
        "byte_for_byte_identical": identical, "identical_after_timestamp_normalisation": normalized,
        "differing_ranges": differing,
        "normalised_fields": ["COFF TimeDateStamp", "PE CheckSum", "debug directory timestamps"],
        "evidence": "Two files only. A match proves these builds agree; it does not prove either matches the published source.",
    }


def self_test() -> dict[str, Any]:
    """Build a minimal PE32+ image in memory and prove export/version parsing and timestamp normalisation."""
    import tempfile
    # One section at RVA 0x1000 / raw 0x200. Export directory and 0x350-byte version data live in it.
    section = bytearray(0x600)
    export_rva, version_rva = 0x1000, 0x1100
    struct.pack_into("<IIHHIIIII", section, 0x00, 0, 0, 0, 0x1040, 1, 2, 0x1050, 0x1060, 0x1070)
    struct.pack_into("<I", section, 0x40, 0x1080)                       # DLL name RVA
    struct.pack_into("<I", section, 0x50, 0x1090)                       # addressOfNames[0]
    struct.pack_into("<I", section, 0x60, version_rva)                  # addressOfFunctions[0]
    struct.pack_into("<H", section, 0x70, 0)                            # addressOfNameOrdinals[0]
    section[0x80:0x8C] = b"fixture.dll\x00"
    section[0x90:0x90 + 18] = b"SKSEPlugin_Version"
    struct.pack_into("<III", section, 0x100, 1, (1 << 24) | (0 << 16) | (2 << 4), 0)
    section[0x108:0x10D] = b"Test\x00"
    section[0x208:0x20D] = b"Auth\x00"
    struct.pack_into("<I", section, 0x100 + 0x308, 0x1)
    struct.pack_into("<I", section, 0x100 + 0x30C, (1 << 24) | (6 << 16) | (1170 << 4))
    optional = bytearray(0xF0)
    struct.pack_into("<H", optional, 0, PE32PLUS)
    struct.pack_into("<Q", optional, 24, 0x140000000)
    struct.pack_into("<I", optional, 108, 16)
    struct.pack_into("<II", optional, 112 + DIR_EXPORT * 8, export_rva, 0x90)
    header = bytearray(0x200)
    header[0:2] = b"MZ"
    struct.pack_into("<I", header, 0x3C, 0x80)
    header[0x80:0x84] = b"PE\x00\x00"
    struct.pack_into("<HHIIIHH", header, 0x84, MACHINE_AMD64, 1, 0x12345678, 0, 0, len(optional), 0x2000)
    header[0x98:0x98 + len(optional)] = optional
    struct.pack_into("<8sIIII", header, 0x98 + len(optional), b".rdata", 0x600, 0x1000, 0x600, 0x200)
    image = bytes(header) + bytes(section)
    with tempfile.TemporaryDirectory(prefix="forge-skse-self-test-") as td:
        root = Path(td)
        first, second = root / "a.dll", root / "b.dll"
        first.write_bytes(image)
        changed = bytearray(image)
        struct.pack_into("<I", changed, 0x88, 0x99999999)   # different COFF timestamp only
        second.write_bytes(bytes(changed))
        report = inspect(first)
        repro = verify_reproducible(first, second)
        assertions = {
            "architecture": report["architecture"] == "PE32+" and report["machine"] == "0x8664",
            "exports": {"SKSEPlugin_Version"} <= {row["name"] for row in report["exports"]},
            "version_data": (report["skse"]["version_data"] or {}).get("name") == "Test",
            "compatible_version": (report["skse"]["version_data"] or {}).get("compatible_versions") == [{"major": 1, "minor": 6, "patch": 1170, "build": 0}],
            "timestamp_normalised": repro["identical_after_timestamp_normalisation"] is True,
            "raw_differs": repro["byte_for_byte_identical"] is False,
        }
        return {"result": "PASS" if all(assertions.values()) else "FAIL", "assertions": assertions}
