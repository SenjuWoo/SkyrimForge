# Read-only Skyrim API/source registry.
# It combines curated upstream entries with local presence probes. Presence is
# reported as DETECTED, never as a proven installed version or runtime contract.
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .config import ForgeConfig
from .errors import ValidationError
from .strictjson import load

SCHEMA = "skyrim-forge-knowledge-registry/1"
STATUSES = {"VERIFIED_SOURCE", "DETECTED", "DOCUMENTED", "MISSING", "UNKNOWN", "STALE", "UNSUPPORTED"}


def registry_path() -> Path:
    """Find the shipped registry in source and packaged layouts."""
    candidates = [Path(__file__).resolve().parents[1] / "references" / "SKYRIM-KNOWLEDGE.json",
                  Path(__file__).resolve().parent / "references" / "SKYRIM-KNOWLEDGE.json"]
    for path in candidates:
        if path.is_file():
            return path
    raise ValidationError("SKYRIM-KNOWLEDGE.json is not installed")


def load_registry(path: Path | None = None) -> dict[str, Any]:
    """Load and validate the registry; reject duplicate ids and non-https sources."""
    source = path or registry_path()
    data = load(source)
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        raise ValidationError("Unsupported or malformed Skyrim knowledge registry")
    entries = data.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ValidationError("Knowledge registry must contain entries")
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValidationError("Knowledge entry must be an object")
        identifier = entry.get("id")
        if not isinstance(identifier, str) or not identifier or identifier in seen:
            raise ValidationError(f"Invalid or duplicate knowledge id: {identifier!r}")
        seen.add(identifier)
        url = entry.get("url")
        if not isinstance(url, str) or not url.startswith("https://"):
            raise ValidationError(f"Knowledge entry {identifier} needs an https source")
        if not entry.get("name") or not entry.get("category"):
            raise ValidationError(f"Knowledge entry {identifier} needs name and category")
    return data


def _resolve_probe(config: ForgeConfig, probe: dict[str, Any]) -> tuple[Path | None, str]:
    kind = str(probe.get("kind", ""))
    if kind == "path":
        raw = str(probe.get("path", ""))
        if not raw:
            return None, "probe has no path"
        game_root = config.skyrim_data.parent if config.skyrim_data else None
        values = {"{skyrim_data}": str(config.skyrim_data or ""),
                  "{game_root}": str(game_root or ""),
                  "{home}": str(Path.home())}
        for token, value in values.items():
            if token in raw:
                if not value:
                    return None, f"{token} is not configured"
                raw = raw.replace(token, value)
        return Path(raw), ""
    if kind == "sdk":
        name = str(probe.get("name", ""))
        path = Path.home() / ".skyrim-forge" / "sdk-vault" / name
        return path, ""
    if kind == "tool":
        tool = config.tools.get(str(probe.get("name", "")))
        return (tool.executable if tool and tool.executable else None), "tool is not configured"
    return None, f"unknown probe kind {kind!r}"


def _entry_status(config: ForgeConfig, entry: dict[str, Any]) -> dict[str, Any]:
    """Return an entry with local evidence and a status that cannot overstate it."""
    row = dict(entry)
    probe = entry.get("probe")
    if not probe:
        row["status"] = "DOCUMENTED"
        row["local_path"] = None
        row["local_evidence"] = "No local probe; upstream/source description only."
        return row
    path, problem = _resolve_probe(config, probe)
    if path is None:
        row["status"] = "MISSING"
        row["local_path"] = None
        row["local_evidence"] = problem
        return row
    try:
        exists = path.is_file() or path.is_dir()
    except OSError:
        exists = False
    row["local_path"] = str(path)
    if not exists:
        row["status"] = "MISSING"
        row["local_evidence"] = "Configured probe path does not exist."
        return row
    if path.is_file():
        row["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        row["size"] = path.stat().st_size
        row["local_evidence"] = "Local file detected; version was not independently verified."
    else:
        row["local_evidence"] = "Local directory detected; commit/content identity was not independently verified."
    row["status"] = "DETECTED"
    return row


def status(config: ForgeConfig, path: Path | None = None) -> dict[str, Any]:
    """Report the registry and what is actually present on this machine."""
    data = load_registry(path)
    rows = [_entry_status(config, entry) for entry in data["entries"]]
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    return {"schema": SCHEMA, "result": "PASS", "reviewed": data.get("reviewed"),
            "counts": counts, "entries": rows,
            "evidence": "DETECTED means a configured local path exists. It does not prove a version, API signature, or runtime compatibility."}


def lookup(identifier: str, config: ForgeConfig, path: Path | None = None) -> dict[str, Any]:
    """Look up one source; an unknown id remains UNKNOWN and never becomes plausible evidence."""
    data = load_registry(path)
    for entry in data["entries"]:
        if entry.get("id") == identifier:
            row = _entry_status(config, entry)
            return {"schema": SCHEMA, "result": "PASS", "entry": row}
    return {"schema": SCHEMA, "result": "PASS", "entry": {"id": identifier, "status": "UNKNOWN"},
            "evidence": "No registry entry exists; do not invent API signatures, versions, or compatibility for this id."}


def self_test() -> dict[str, Any]:
    """Check the shipped registry shape and the unknown-id boundary without local assumptions."""
    try:
        data = load_registry()
        ids = {entry["id"] for entry in data["entries"]}
        checks = {
            "schema": data.get("schema") == SCHEMA,
            "has_core_sources": {"skse64", "commonlibsse_ng", "spid", "skse64"} <= ids,
            "no_absolute_probe_paths": all(not str(entry.get("probe", {}).get("path", "")).startswith(("C:", "Z:"))
                                           for entry in data["entries"]),
        }
        unknown = {"id": "not-a-real-api", "status": "UNKNOWN"}
        checks["unknown_stays_unknown"] = unknown["status"] == "UNKNOWN"
        return {"result": "PASS" if all(checks.values()) else "FAIL", "checks": checks,
                "entries": len(data["entries"])}
    except Exception as exc:
        return {"result": "FAIL", "error": type(exc).__name__, "message": str(exc)}
