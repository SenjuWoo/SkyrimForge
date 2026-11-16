"""Plugin <-> YAML tree through the pinned Spriggit CLI (TOOLS-LOCK: Spriggit 0.41.0).

The YAML tree is an editable, diffable source of truth; the plugin is rebuilt from it. Serialization package:
Spriggit.Yaml.Skyrim at the pinned Spriggit version (Spriggit fetches that NuGet package on first use), game
release SkyrimSE. `roundtrip` exports, rebuilds and compares every record (signature, FormID, EditorID) with
Forge's own parser; byte equality is reported separately because Spriggit may reorder or recompress records.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from .config import ForgeConfig
from .conflicts import peek_editor_id, scan_headers
from .errors import ToolError, ValidationError
from .safety import require_approval, require_within
from .tools import resolve_tool, run_process

PACKAGE = "Spriggit.Yaml.Skyrim"
VERSION = "0.41.0"
RELEASE = "SkyrimSE"


def _run(config: ForgeConfig, args: list[str], cwd: Path) -> tuple[dict[str, Any], str]:
    tool, exe = resolve_tool(config, "spriggit", require_pin=True)
    process = run_process(exe, args, cwd=cwd, timeout_seconds=max(tool.timeout_seconds, 3600))
    return process, f"{process['stdout']}\n{process['stderr']}"


def export(config: ForgeConfig, plugin: Path, output: Path, *, approved: bool) -> dict[str, Any]:
    require_approval(approved, "Spriggit export")
    output = require_within(output, config.workspace_root)
    output.mkdir(parents=True, exist_ok=True)
    started = time.time()
    process, text = _run(config, ["serialize", "-i", str(plugin), "-o", str(output), "-g", RELEASE, "-p", PACKAGE, "-v", VERSION], output)
    if process["returncode"] != 0 or not (output / "spriggit-meta.json").is_file():
        raise ToolError("Spriggit serialize failed: " + text[-800:])
    return {"result": "PASS", "plugin": str(plugin), "yaml": str(output), "yaml_files": sum(1 for _ in output.rglob("*.yaml")),
            "package": f"{PACKAGE} {VERSION}", "seconds": round(time.time() - started, 1)}


def build(config: ForgeConfig, yaml_dir: Path, output: Path, *, approved: bool) -> dict[str, Any]:
    require_approval(approved, "Spriggit build")
    if not (yaml_dir / "spriggit-meta.json").is_file():
        raise ValidationError(f"{yaml_dir} is not a Spriggit tree (no spriggit-meta.json)")
    output = require_within(output, config.workspace_root)
    output.parent.mkdir(parents=True, exist_ok=True)
    started = time.time()
    process, text = _run(config, ["deserialize", "-i", str(yaml_dir), "-o", str(output), "-p", PACKAGE, "-v", VERSION], output.parent)
    if process["returncode"] != 0 or not output.is_file():
        raise ToolError("Spriggit deserialize failed: " + text[-800:])
    return {"result": "PASS", "yaml": str(yaml_dir), "plugin": str(output), "records": len(record_index(output)),
            "package": f"{PACKAGE} {VERSION}", "seconds": round(time.time() - started, 1)}


def record_index(plugin: Path) -> dict[str, tuple[str, str]]:
    """{raw FormID hex: (signature, EditorID)} from Forge's raw parser; the round-trip oracle."""
    data = Path(plugin).read_bytes()
    return {f"{form_id:08X}": (signature, peek_editor_id(data, offset, size, flags))
            for signature, flags, form_id, offset, size in scan_headers(data)}


def roundtrip(config: ForgeConfig, plugin: Path, work: Path, *, approved: bool) -> dict[str, Any]:
    work = require_within(work, config.workspace_root)
    yaml_dir, rebuilt = work / "yaml", work / "rebuilt" / plugin.name
    exported = export(config, plugin, yaml_dir, approved=approved)
    build(config, yaml_dir, rebuilt, approved=approved)
    before, after = record_index(plugin), record_index(rebuilt)
    equal = before == after
    return {"result": "PASS" if equal else "FAIL", "plugin": str(plugin), "records": len(before), "record_equal": equal,
            "byte_equal": plugin.read_bytes() == rebuilt.read_bytes(), "yaml_files": exported["yaml_files"],
            "only_in_source": sorted(set(before) - set(after))[:5], "only_in_rebuilt": sorted(set(after) - set(before))[:5],
            "changed": sorted(key for key in set(before) & set(after) if before[key] != after[key])[:5], "package": f"{PACKAGE} {VERSION}"}
