"""Pinned third-party tools (references/TOOLS-LOCK.json): status and a sync that downloads nothing it already has.

For each tool, in order: a receipt-owned copy under <config dir>/tools whose pinned file still matches -> present;
an existing copy at <reuse root>/<folder>/<pin_file> with the same SHA-256 -> bound in place (no copy, no download);
otherwise, when approved, the release asset is downloaded, its SHA-256 checked before extraction, extracted into the
receipt-owned tools root, and the pinned file checked again. A tool you configured yourself elsewhere is kept.
Reuse roots: UABS_TOOL_ROOTS (path-separated), the configured tools_root and its parent, and the profile's TOOL-ROOTS.txt.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

from .config import ForgeConfig, save_config
from .errors import SafetyError, ToolError, ValidationError
from .strictjson import load
from .util import json_dump, sha256_file, utc_now
from .version import VERSION


def lock_path() -> Path:
    return Path(__file__).resolve().parent / "references" / "TOOLS-LOCK.json"


def load_lock(path: Path | None = None) -> dict[str, Any]:
    document = load(path or lock_path())
    for tool in document["tools"]:
        for key in ("id", "config_key", "repo", "tag", "asset", "asset_sha256", "folder", "pin_file", "pin_sha256", "safe_tools"):
            if not tool.get(key):
                raise ValidationError(f"TOOLS-LOCK {tool.get('id')}: missing {key}")
    return document


def tools_root(config: ForgeConfig) -> Path:
    return config.config_path.parent / "tools"


def _receipt(root: Path) -> dict[str, Any]:
    path = root / "tools.receipt.json"
    return load(path) if path.is_file() else {"schema": "skyrim-forge-tools-receipt/1", "owner": "skyrim-forge", "tools": {}}


def reuse_roots(config: ForgeConfig) -> list[Path]:
    roots: list[Path] = []
    for value in os.environ.get("UABS_TOOL_ROOTS", "").split(os.pathsep):
        if value.strip():
            roots.append(Path(value.strip()))
    if config.tools_root:
        roots += [config.tools_root, config.tools_root.parent]
    profile = Path.home() / ".uabs" / "profile" / "TOOL-ROOTS.txt"
    if profile.is_file():
        roots += [Path(line.strip()) for line in profile.read_text(encoding="utf-8-sig").splitlines() if line.strip() and not line.startswith("#")]
    unique: list[Path] = []
    for root in roots:
        if root.is_dir() and root not in unique:
            unique.append(root)
    return unique


def _find_existing(tool: dict[str, Any], roots: list[Path]) -> Path | None:
    for root in roots:
        candidate = root / tool["folder"] / tool["pin_file"]
        if candidate.is_file() and sha256_file(candidate) == tool["pin_sha256"]:
            return candidate
    return None


def _owned_pin(root: Path, receipt: dict[str, Any], tool: dict[str, Any]) -> Path | None:
    entry = receipt["tools"].get(tool["id"])
    if not entry:
        return None
    pin = Path(entry["pin_path"])
    return pin if pin.is_file() and sha256_file(pin) == tool["pin_sha256"] else None


def status(config: ForgeConfig, *, lock: dict[str, Any] | None = None) -> dict[str, Any]:
    root = tools_root(config)
    receipt = _receipt(root)
    roots = reuse_roots(config)
    rows = []
    for tool in (lock or load_lock())["tools"]:
        owned = _owned_pin(root, receipt, tool)
        existing = owned or _find_existing(tool, roots)
        configured = config.tools.get(tool["config_key"])
        rows.append({"id": tool["id"], "tag": tool["tag"], "state": "present" if owned else ("reusable" if existing else "missing"),
                     "path": str(existing) if existing else None,
                     "configured": str(configured.executable) if configured and configured.executable else None,
                     "configured_matches_pin": bool(configured and configured.sha256 and configured.sha256.casefold() == tool["pin_sha256"])})
    return {"result": "PASS", "tools_root": str(root), "reuse_roots": [str(r) for r in roots], "tools": rows}


def _download(url: str, target: Path) -> int:
    request = urllib.request.Request(url, headers={"User-Agent": f"SkyrimForge/{VERSION}"})
    with urllib.request.urlopen(request, timeout=600) as response, target.open("wb") as stream:
        shutil.copyfileobj(response, stream)
    return target.stat().st_size


def _extract(config: ForgeConfig, archive: Path, destination: Path) -> None:
    if archive.suffix.casefold() == ".zip":
        with zipfile.ZipFile(archive) as bundle:
            for member in bundle.infolist():
                target = (destination / member.filename).resolve()
                if destination.resolve() not in target.parents and target != destination.resolve():
                    raise SafetyError(f"unsafe archive member {member.filename}")
            bundle.extractall(destination)
        return
    from .tools import resolve_tool, run_process
    tool, seven = resolve_tool(config, "archive", require_pin=True)
    process = run_process(seven, ["x", "-y", f"-o{destination}", str(archive)], cwd=destination, timeout_seconds=tool.timeout_seconds)
    if process["returncode"] != 0:
        raise ToolError(f"7-Zip could not extract {archive.name}: {process['stderr'][-300:]}")


def _flatten(stage: Path, pin_file: str) -> Path:
    """Release archives often wrap everything in one folder; find the folder that holds the pinned file."""
    if (stage / pin_file).is_file():
        return stage
    for candidate in stage.rglob(Path(pin_file).name):
        root = candidate
        for _ in Path(pin_file).parts:
            root = root.parent
        if (root / pin_file).is_file():
            return root
    raise ToolError(f"{pin_file} is not in the extracted asset")


def _record_safe_tools(line: str) -> bool:
    path = Path.home() / ".uabs" / "profile" / "SAFE-TOOLS.md"
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8")
    repo_url = line.split("|")[1].strip()
    if repo_url in text:
        return False
    with path.open("a", encoding="utf-8") as stream:
        stream.write(("" if text.endswith("\n") else "\n") + line + "\n")
    return True


def sync(config: ForgeConfig, *, only: list[str] | None = None, approved: bool = False, lock: dict[str, Any] | None = None) -> dict[str, Any]:
    lock = lock or load_lock()
    wanted = {name.casefold() for name in only or []}
    unknown = wanted - {tool["id"] for tool in lock["tools"]}
    if unknown:
        raise ValidationError(f"unknown tool(s): {', '.join(sorted(unknown))}")
    root = tools_root(config)
    receipt = _receipt(root)
    roots = reuse_roots(config)
    rows, downloaded, changed_config = [], 0, False
    for tool in lock["tools"]:
        if wanted and tool["id"] not in wanted:
            continue
        row: dict[str, Any] = {"id": tool["id"], "tag": tool["tag"], "downloaded_bytes": 0}
        pin = _owned_pin(root, receipt, tool)
        if pin:
            row["action"] = "present"
        else:
            pin = _find_existing(tool, roots)
            row["action"] = "bind-existing" if pin else "download"
        row["path"] = str(pin) if pin else str(root / tool["folder"] / tool["pin_file"])
        configured = config.tools.get(tool["config_key"])
        mine = configured and configured.executable and (str(configured.executable).startswith(str(root)) or (pin and configured.executable == pin))
        row["configure"] = "set" if not (configured and configured.executable) or mine else f"kept your configured {configured.executable}"
        if not approved:
            rows.append(row); continue
        if row["action"] == "download":
            stage_root = root / ".staging"
            stage_root.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(dir=stage_root) as temp:
                archive = Path(temp) / tool["asset"]
                url = f"https://github.com/{tool['repo']}/releases/download/{tool['tag']}/{tool['asset']}"
                row["downloaded_bytes"] = _download(url, archive)
                downloaded += row["downloaded_bytes"]
                if sha256_file(archive) != tool["asset_sha256"]:
                    raise SafetyError(f"{tool['id']}: {tool['asset']} SHA-256 differs from the lock; nothing was extracted")
                extracted = Path(temp) / "x"; extracted.mkdir()
                _extract(config, archive, extracted)
                source = _flatten(extracted, tool["pin_file"])
                if sha256_file(source / tool["pin_file"]) != tool["pin_sha256"]:
                    raise SafetyError(f"{tool['id']}: {tool['pin_file']} SHA-256 differs from the lock")
                target = root / tool["folder"]
                if target.exists():
                    shutil.rmtree(target)
                shutil.move(str(source), str(target))
            pin = root / tool["folder"] / tool["pin_file"]
            receipt["tools"][tool["id"]] = {"tag": tool["tag"], "asset_sha256": tool["asset_sha256"], "pin_path": str(pin), "installed": utc_now()}
            json_dump(root / "tools.receipt.json", receipt)
            row["path"] = str(pin)
        if row["configure"] == "set" and pin:
            config.tools[tool["config_key"]].executable = pin
            config.tools[tool["config_key"]].sha256 = tool["pin_sha256"]
            config.tools[tool["config_key"]].version = tool["tag"]
            changed_config = True
        row["safe_tools_recorded"] = _record_safe_tools(tool["safe_tools"])
        rows.append(row)
    if changed_config:
        save_config(config)
    return {"result": "PASS", "dry_run": not approved, "tools_root": str(root), "downloaded_bytes": downloaded, "tools": rows,
            "evidence": "Assets are checked against the lock's SHA-256 before extraction and the pinned file after it."}
