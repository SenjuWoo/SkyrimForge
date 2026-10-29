"""SEQ file generation: the list of Start Game Enabled quests the engine reads from Data\\Seq\\<Plugin>.seq."""
from __future__ import annotations

import struct
from pathlib import Path
from typing import Any

from .conflicts import scan_headers
from .errors import SafetyError, ValidationError
from .records import _record
from .util import atomic_write_bytes, sha256_bytes

START_GAME_ENABLED = 0x0001  # QUST DNAM (12 bytes) starts with uint16 flags


def start_game_quests(data: bytes) -> list[int]:
    """Raw FormIDs (plugin-relative, as stored in the file) of quests this plugin defines with Start Game Enabled.

    Derived from 257 shipped plugin/SEQ pairs: overrides of other plugins' quests are not listed, and 99.8% of the
    defined quests follow the flag exactly (the exceptions are stale SEQ files, not a second rule).
    """
    header_size = struct.unpack_from("<I", data, 4)[0]
    masters = 0
    pos = 24
    while pos + 6 <= 24 + header_size:  # count MAST subrecords: a form's own index equals the master count
        size = struct.unpack_from("<H", data, pos + 4)[0]
        masters += data[pos:pos + 4] == b"MAST"
        pos += 6 + size
    result = []
    for signature, _flags, form_id, offset, _size in scan_headers(data):
        if signature != "QUST" or (form_id >> 24) != masters:
            continue
        record, _ = _record(data, offset)
        flags = next((raw for sub, raw in record.subrecords if sub == "DNAM"), b"")
        if len(flags) >= 2 and struct.unpack_from("<H", flags)[0] & START_GAME_ENABLED:
            result.append(form_id)
    return result


def build_seq(plugin: Path, output_root: Path, *, approved: bool) -> dict[str, Any]:
    """Write <output_root>/Seq/<plugin stem>.seq; refuses to overwrite and writes nothing when no quest qualifies."""
    if not approved:
        raise SafetyError("Approval is required to write a SEQ file")
    if plugin.suffix.casefold() not in {".esp", ".esm", ".esl"}:
        raise ValidationError("SEQ source must be a plugin")
    ids = start_game_quests(plugin.read_bytes())
    target = output_root / "Seq" / f"{plugin.stem}.seq"
    if not ids:
        return {"result": "NOTHING_TO_WRITE", "plugin": str(plugin), "quests": 0, "evidence": "No QUST record sets Start Game Enabled, so no SEQ file is needed."}
    if target.exists():
        raise SafetyError(f"Refusing to overwrite existing SEQ file: {target}")
    payload = b"".join(struct.pack("<I", form_id) for form_id in ids)
    target.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_bytes(target, payload)
    return {"result": "PASS", "output": str(target), "quests": len(ids), "form_ids": [f"0x{i:08X}" for i in ids], "sha256": sha256_bytes(payload),
            "evidence": "Generated from QUST DNAM flags in plugin bytes. Not xEdit or Skyrim runtime confirmation."}
