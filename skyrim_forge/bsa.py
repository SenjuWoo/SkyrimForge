"""Native Skyrim BSA reader and writer (version 104 = LE, 105 = SE/AE), standard library only.

Layout (UESP "Skyrim Mod:Archive File Format", cross-checked against vanilla archives and BSArch output):
36-byte header ("BSA\\0", version, 36, archive flags, folder count, file count, total folder-name length,
total file-name length, file flags); folder records (v104: u64 hash, u32 count, u32 offset; v105: u64 hash,
u32 count, u32 unknown, u64 offset) where offset = start of that folder's file-record block + total
file-name length; per folder a bzstring name (when flag 0x1) and its file records (u64 hash, u32 size,
u32 data offset; size bit 30 inverts the archive's default compression); the file-name block; then data.
Data may start with a bstring "folder\\file" (flag 0x100). A compressed entry is u32 original size + payload:
zlib in v104, an LZ4 frame in v105. Folders and files are ordered by hash.
"""
from __future__ import annotations

import hashlib
import struct
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import ValidationError
from .safety import require_approval, require_within

MAGIC = b"BSA\x00"
HEADER = struct.Struct("<4sIIIIIIII")
FLAG_DIR_NAMES, FLAG_FILE_NAMES, FLAG_COMPRESSED, FLAG_EMBED_NAMES = 0x1, 0x2, 0x4, 0x100
SIZE_COMPRESS_TOGGLE = 0x40000000
FILE_FLAGS = {"meshes": 0x1, "textures": 0x2, "interface": 0x4, "sound": 0x8, "music": 0x8, "voices": 0x10,
              "shadersfx": 0x20, "trees": 0x40, "fonts": 0x80}
MAX_ENTRY = 512 * 1024 * 1024


# --- hashing ----------------------------------------------------------------------------------------

def _hash_part(text: bytes) -> int:
    value = 0
    for byte in text:
        value = (value * 0x1003F + byte) & 0xFFFFFFFF
    return value


def tes_hash(name: str, *, folder: bool = False) -> int:
    """The Oblivion/Skyrim archive hash of a lowercase backslash name (a folder hashes with no extension)."""
    name = name.replace("/", "\\").lower()
    if folder or "." not in name:
        stem, ext = name, ""
    else:
        stem, ext = name[: name.rfind(".")], name[name.rfind("."):]
    raw, ext_raw = stem.encode("cp1252"), ext.encode("cp1252")
    if not raw:
        return 0
    low = raw[-1] | ((raw[-2] << 8) if len(raw) > 2 else 0) | (len(raw) << 16) | (raw[0] << 24)
    low |= {".kf": 0x80, ".nif": 0x8000, ".dds": 0x8080, ".wav": 0x80000000}.get(ext, 0)
    high = (_hash_part(raw[1:-2]) + _hash_part(ext_raw)) & 0xFFFFFFFF
    return (high << 32) | (low & 0xFFFFFFFF)


# --- LZ4 frames ---------------------------------------------------------------------------------------

_P1, _P2, _P3, _P4, _P5 = 2654435761, 2246822519, 3266489917, 668265263, 374761393


def _rotl(value: int, count: int) -> int:
    return ((value << count) | (value >> (32 - count))) & 0xFFFFFFFF


def xxh32(data: bytes, seed: int = 0) -> int:
    length, index, mask = len(data), 0, 0xFFFFFFFF
    if length >= 16:
        v = [(seed + _P1 + _P2) & mask, (seed + _P2) & mask, seed & mask, (seed - _P1) & mask]
        while index + 16 <= length:
            for lane in range(4):
                v[lane] = (_rotl((v[lane] + struct.unpack_from("<I", data, index)[0] * _P2) & mask, 13) * _P1) & mask
                index += 4
        acc = (_rotl(v[0], 1) + _rotl(v[1], 7) + _rotl(v[2], 12) + _rotl(v[3], 18)) & mask
    else:
        acc = (seed + _P5) & mask
    acc = (acc + length) & mask
    while index + 4 <= length:
        acc = (_rotl((acc + struct.unpack_from("<I", data, index)[0] * _P3) & mask, 17) * _P4) & mask
        index += 4
    while index < length:
        acc = (_rotl((acc + data[index] * _P5) & mask, 11) * _P1) & mask
        index += 1
    acc ^= acc >> 15; acc = (acc * _P2) & mask
    acc ^= acc >> 13; acc = (acc * _P3) & mask
    return acc ^ (acc >> 16)


def _lz4_block(src: bytes, out: bytearray, limit: int) -> None:
    index, end = 0, len(src)
    while index < end:
        token = src[index]; index += 1
        literals = token >> 4
        if literals == 15:
            while True:
                extra = src[index]; index += 1; literals += extra
                if extra != 255:
                    break
        out += src[index:index + literals]; index += literals
        if index >= end:
            break
        offset = src[index] | (src[index + 1] << 8); index += 2
        if offset == 0 or offset > len(out):
            raise ValidationError("LZ4 match offset points before the start of the output")
        match = (token & 15) + 4
        if (token & 15) == 15:
            while True:
                extra = src[index]; index += 1; match += extra
                if extra != 255:
                    break
        start = len(out) - offset
        if offset >= match:
            out += out[start:start + match]
        else:
            for position in range(match):
                out.append(out[start + position])
        if len(out) > limit:
            raise ValidationError("LZ4 output exceeds the declared size")


def lz4_frame_decompress(data: bytes, expected: int | None = None) -> bytes:
    if len(data) < 7 or struct.unpack_from("<I", data)[0] != 0x184D2204:
        raise ValidationError("not an LZ4 frame")
    flags, index = data[4], 6
    if flags >> 6 != 1:
        raise ValidationError("unsupported LZ4 frame version")
    if flags & 0x08:
        index += 8
    if flags & 0x01:
        index += 4
    if data[index] != (xxh32(data[4:index]) >> 8) & 0xFF:
        raise ValidationError("LZ4 frame descriptor checksum mismatch")
    index += 1
    limit = expected if expected is not None else MAX_ENTRY
    out = bytearray()
    while True:
        size = struct.unpack_from("<I", data, index)[0]; index += 4
        if size == 0:
            break
        raw, size = bool(size & 0x80000000), size & 0x7FFFFFFF
        block = data[index:index + size]; index += size
        if raw:
            out += block
        else:
            _lz4_block(block, out, limit)
        if flags & 0x10:
            index += 4
    if expected is not None and len(out) != expected:
        raise ValidationError(f"LZ4 frame produced {len(out)} bytes, expected {expected}")
    return bytes(out)


def _lz4_compress_block(src: bytes) -> bytes:
    """Greedy LZ4 block encoder (4-byte hash chain of one); valid for any LZ4 decoder, not size-optimal."""
    out, table, anchor, index, end = bytearray(), {}, 0, 0, len(src)
    match_limit = end - 12  # the format keeps the last 12 bytes free of a match start and the last 5 literal

    def emit(literal: bytes, offset: int, match: int) -> None:
        lit = len(literal)
        token = (min(lit, 15) << 4) | (min(match - 4, 15) if match else 0)
        out.append(token)
        if lit >= 15:
            rest = lit - 15
            while rest >= 255:
                out.append(255); rest -= 255
            out.append(rest)
        out.extend(literal)
        if match:
            out.extend(struct.pack("<H", offset))
            if match - 4 >= 15:
                rest = match - 4 - 15
                while rest >= 255:
                    out.append(255); rest -= 255
                out.append(rest)

    while index < match_limit:
        key = src[index:index + 4]
        candidate = table.get(key)
        table[key] = index
        if candidate is not None and index - candidate <= 0xFFFF:
            length = 4
            while index + length < end - 5 and src[candidate + length] == src[index + length]:
                length += 1
            emit(src[anchor:index], index - candidate, length)
            index += length
            anchor = index
        else:
            index += 1
    emit(src[anchor:], 0, 0)
    return bytes(out)


def lz4_frame_compress(data: bytes) -> bytes:
    descriptor = bytes((0x60, 0x70))  # version 1, independent blocks, 4 MiB max block, no checksums
    frame = bytearray(struct.pack("<I", 0x184D2204) + descriptor + bytes(((xxh32(descriptor) >> 8) & 0xFF,)))
    for start in range(0, len(data), 4 * 1024 * 1024):
        chunk = data[start:start + 4 * 1024 * 1024]
        block = _lz4_compress_block(chunk)
        if len(block) >= len(chunk):
            frame += struct.pack("<I", len(chunk) | 0x80000000) + chunk
        else:
            frame += struct.pack("<I", len(block)) + block
    frame += b"\x00\x00\x00\x00"
    return bytes(frame)


# --- archive model ------------------------------------------------------------------------------------

@dataclass
class Entry:
    folder: str
    name: str
    hash: int
    size_field: int
    offset: int
    compressed: bool
    raw: bytes = b""

    @property
    def path(self) -> str:
        return f"{self.folder}\\{self.name}" if self.folder else self.name


@dataclass
class Archive:
    version: int
    flags: int
    file_flags: int
    folders: list[dict[str, Any]] = field(default_factory=list)
    entries: list[Entry] = field(default_factory=list)


def read(path: Path, *, with_data: bool = False) -> Archive:
    data = Path(path).read_bytes()
    if len(data) < HEADER.size:
        raise ValidationError(f"{Path(path).name}: too short for a BSA header")
    magic, version, offset, flags, folders, files, folder_len, file_len, file_flags = HEADER.unpack_from(data, 0)
    if magic != MAGIC or version not in (104, 105) or offset != 36:
        raise ValidationError(f"{Path(path).name}: not a Skyrim BSA (magic {magic!r}, version {version})")
    record = struct.Struct("<QIIQ" if version == 105 else "<QII")
    archive = Archive(version, flags, file_flags)
    position = 36
    rows = []
    for _ in range(folders):
        values = record.unpack_from(data, position); position += record.size
        rows.append({"hash": values[0], "count": values[1], "unknown": values[2] if version == 105 else 0,
                     "offset": values[-1]})
    for row in rows:
        name = ""
        if flags & FLAG_DIR_NAMES:
            length = data[position]
            name = data[position + 1:position + length].decode("cp1252"); position += 1 + length
        row["name"] = name
        row["records"] = []
        for _ in range(row["count"]):
            row["records"].append(struct.unpack_from("<QII", data, position)); position += 16
        archive.folders.append(row)
    names = data[position:position + file_len].split(b"\x00")[:files] if flags & FLAG_FILE_NAMES else []
    name_index = 0
    for row in archive.folders:
        for file_hash, size_field, data_offset in row["records"]:
            file_name = names[name_index].decode("cp1252") if names else f"{file_hash:016x}"
            name_index += 1
            compressed = bool(flags & FLAG_COMPRESSED) ^ bool(size_field & SIZE_COMPRESS_TOGGLE)
            entry = Entry(row["name"], file_name, file_hash, size_field, data_offset, compressed)
            if with_data:
                entry.raw = data[data_offset:data_offset + (size_field & 0x3FFFFFFF)]
            archive.entries.append(entry)
    archive.header_end = position + file_len  # type: ignore[attr-defined]
    archive.size = len(data)  # type: ignore[attr-defined]
    return archive


def entry_bytes(archive: Archive, entry: Entry, blob: bytes | None = None) -> bytes:
    """Decoded file contents of one entry (blob = its raw stored bytes, read from disk when omitted)."""
    raw = entry.raw if blob is None else blob
    if archive.flags & FLAG_EMBED_NAMES:
        raw = raw[1 + raw[0]:]
    if not entry.compressed:
        return raw
    original = struct.unpack_from("<I", raw)[0]
    if original > MAX_ENTRY:
        raise ValidationError(f"{entry.path}: declared size {original} is over the limit")
    payload = raw[4:]
    return zlib.decompress(payload) if archive.version == 104 else lz4_frame_decompress(payload, original)


def write_bytes(archive: Archive) -> bytes:
    """Serialize an archive whose entries carry their stored bytes in `raw` (copied verbatim)."""
    version, flags = archive.version, archive.flags
    record = struct.Struct("<QIIQ" if version == 105 else "<QII")
    folders = archive.folders
    by_folder: dict[str, list[Entry]] = {}
    for entry in archive.entries:
        by_folder.setdefault(entry.folder, []).append(entry)
    folder_names = sum(len(row["name"].encode("cp1252")) + 1 for row in folders) if flags & FLAG_DIR_NAMES else 0
    file_names = b"".join(entry.name.encode("cp1252") + b"\x00" for row in folders for entry in by_folder.get(row["name"], []))
    blocks_start = 36 + record.size * len(folders)
    position = blocks_start
    folder_offsets = []
    for row in folders:
        folder_offsets.append(position + len(file_names))
        if flags & FLAG_DIR_NAMES:
            position += 1 + len(row["name"].encode("cp1252")) + 1
        position += 16 * len(by_folder.get(row["name"], []))
    data_start = position + (len(file_names) if flags & FLAG_FILE_NAMES else 0)
    out = bytearray(HEADER.pack(MAGIC, version, 36, flags, len(folders), len(archive.entries),
                                folder_names, len(file_names) if flags & FLAG_FILE_NAMES else 0, archive.file_flags))
    data_position = data_start
    layout: list[tuple[Entry, int]] = []
    ordered = [entry for row in folders for entry in by_folder.get(row["name"], [])]
    # A parsed archive keeps its stored data order (some packers write data in name order, not record order).
    preserve = all(entry.offset for entry in ordered)
    if preserve:
        ordered.sort(key=lambda entry: entry.offset)
    shared: dict[int, int] = {}
    for entry in ordered:
        # Deduplicating packers point several records at one stored blob; keep it stored once.
        if preserve and entry.offset in shared:
            layout.append((entry, shared[entry.offset])); continue
        shared[entry.offset] = data_position
        layout.append((entry, data_position)); data_position += len(entry.raw)
    for row, offset in zip(folders, folder_offsets):
        count = len(by_folder.get(row["name"], []))
        out += record.pack(row["hash"], count, row.get("unknown", 0), offset) if version == 105 else record.pack(row["hash"], count, offset)
    offsets = {id(entry): offset for entry, offset in layout}
    for row in folders:
        if flags & FLAG_DIR_NAMES:
            name = row["name"].encode("cp1252") + b"\x00"
            out += bytes((len(name),)) + name
        for entry in by_folder.get(row["name"], []):
            toggle = SIZE_COMPRESS_TOGGLE if entry.compressed != bool(flags & FLAG_COMPRESSED) else 0
            out += struct.pack("<QII", entry.hash, len(entry.raw) | toggle, offsets[id(entry)])
    if flags & FLAG_FILE_NAMES:
        out += file_names
    written: set[int] = set()
    for entry, offset in layout:
        if offset not in written:
            written.add(offset)
            out += entry.raw
    return bytes(out)


def pack_folder(source: Path, *, compress: bool, version: int = 105) -> Archive:
    files = sorted(p for p in Path(source).rglob("*") if p.is_file())
    if not files:
        raise ValidationError(f"{source} has no files to pack")
    flags = FLAG_DIR_NAMES | FLAG_FILE_NAMES | (FLAG_COMPRESSED if compress else 0)
    groups: dict[str, list[Path]] = {}
    file_flags = 0
    for path in files:
        relative = path.relative_to(source).as_posix().lower()
        folder, _, _ = relative.rpartition("/")
        if not folder:
            raise ValidationError(f"{relative}: a BSA entry needs a folder (meshes\\..., textures\\...)")
        groups.setdefault(folder.replace("/", "\\"), []).append(path)
        file_flags |= FILE_FLAGS.get(relative.split("/")[0], 0x100)
    archive = Archive(version, flags, file_flags)
    for folder in sorted(groups, key=lambda name: tes_hash(name, folder=True)):
        archive.folders.append({"hash": tes_hash(folder, folder=True), "name": folder, "unknown": 0})
        for path in sorted(groups[folder], key=lambda p: tes_hash(p.name.lower())):
            payload = path.read_bytes()
            if compress:
                body = zlib.compress(payload, 9) if version == 104 else lz4_frame_compress(payload)
                raw = struct.pack("<I", len(payload)) + body
            else:
                raw = payload
            archive.entries.append(Entry(folder, path.name.lower(), tes_hash(path.name.lower()), len(raw), 0, compress, raw))
    if len({row["hash"] for row in archive.folders}) != len(archive.folders):
        raise ValidationError("two folders share an archive hash; rename one")
    return archive


# --- commands -----------------------------------------------------------------------------------------

def info(path: Path, *, limit: int = 50) -> dict[str, Any]:
    archive = read(path)
    compressed = sum(1 for entry in archive.entries if entry.compressed)
    return {"result": "PASS", "file": str(path), "version": archive.version, "game": "Skyrim SE/AE" if archive.version == 105 else "Skyrim LE",
            "archive_flags": f"0x{archive.flags:X}", "file_flags": f"0x{archive.file_flags:X}", "folders": len(archive.folders),
            "files": len(archive.entries), "compressed_files": compressed,
            "sample": [entry.path for entry in archive.entries[:limit]],
            "evidence": "Parsed natively from the header, folder and file records; contents are not decompressed by info."}


def verify_repack(path: Path) -> dict[str, Any]:
    """Parse, re-serialize with the stored payloads, and compare bytes: proves the reader and writer agree with the file."""
    original = Path(path).read_bytes()
    rebuilt = write_bytes(read(path, with_data=True))
    return {"file": str(path), "bytes": len(original), "identical": rebuilt == original,
            "sha256": hashlib.sha256(original).hexdigest(), "rebuilt_sha256": hashlib.sha256(rebuilt).hexdigest()}


def extract(path: Path, output: Path, workspace_root: Path, *, approved: bool, only: str = "") -> dict[str, Any]:
    require_approval(approved, "BSA extraction")
    output = require_within(output, workspace_root)
    archive = read(path, with_data=True)
    needle = only.replace("/", "\\").lower()
    written = []
    for entry in archive.entries:
        if needle and needle not in entry.path.lower():
            continue
        target = (output / entry.path.replace("\\", "/")).resolve()
        if output.resolve() not in target.parents:
            raise ValidationError(f"unsafe entry path {entry.path}")
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = entry_bytes(archive, entry)
        target.write_bytes(payload)
        written.append({"path": entry.path, "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()})
    return {"result": "PASS", "archive": str(path), "output": str(output), "files": len(written), "written": written[:200]}


def pack(source: Path, output: Path, workspace_root: Path, *, approved: bool, compress: bool = True, version: int = 105) -> dict[str, Any]:
    require_approval(approved, "BSA packing")
    output = require_within(output, workspace_root)
    archive = pack_folder(source, compress=compress, version=version)
    payload = write_bytes(archive)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(payload)
    check = read(output, with_data=True)
    for built, original in zip(check.entries, archive.entries):
        if entry_bytes(check, built) != entry_bytes(archive, original):
            raise ValidationError(f"{built.path} did not read back identically")
    return {"result": "PASS", "output": str(output), "version": version, "files": len(archive.entries), "folders": len(archive.folders),
            "compressed": compress, "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest(),
            "evidence": "Written natively and read back; every entry decodes to its source bytes. Loading in game is not tested."}


def self_test() -> dict[str, Any]:
    sample = b"Skyrim Forge " * 300 + bytes(range(256))
    assert lz4_frame_decompress(lz4_frame_compress(sample), len(sample)) == sample
    assert xxh32(b"") == 0x02CC5D05 and xxh32(b"abc") == 0x32D153FF
    assert tes_hash("meshes", folder=True) == tes_hash("MESHES", folder=True)
    return {"result": "PASS", "checks": ["lz4 round trip", "xxh32 vectors", "hash case-insensitive"]}
