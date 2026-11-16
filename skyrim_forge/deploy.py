"""Deploy a mod folder into the game's Data (or a mod-manager mod folder with `to`) for testing, and undo it.

Dry run unless approved. Every approved deploy writes a receipt beside the Forge configuration
(deploy/<id>-<target>.json) listing each file it wrote with its SHA-256 and any backup it took.
A file this receipt does not own is never replaced unless `force` (which backs it up first). Files are replaced
by rename, so a file a mod manager hard-linked from its staging folder is never changed in staging.
Undeploy removes exactly what the receipt lists, restores the backups, and leaves alone any file changed since.
Development files (fomod/, .git, __pycache__, *.bak, Forge receipts) are never deployed.
"""
from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Any

from .config import ForgeConfig
from .errors import SafetyError, ValidationError
from .strictjson import load
from .util import json_dump, sha256_file, utc_now

SKIP_PARTS = {"fomod", ".git", "__pycache__", ".forge"}
SKIP_SUFFIXES = {".bak", ".tmp"}


def _home(config: ForgeConfig) -> Path:
    return config.config_path.parent / "deploy"


def _target(config: ForgeConfig, to: str | None) -> Path:
    if to:
        target = Path(to)
    elif config.skyrim_data:
        target = config.skyrim_data
    else:
        raise ValidationError("No target: set paths.skyrim_data or pass --to <mod folder>")
    if not target.is_dir():
        raise ValidationError(f"Deploy target is not a folder: {target}")
    return target.resolve()


def _receipt(config: ForgeConfig, mod_id: str, target: Path) -> Path:
    tag = "data" if target.name.casefold() == "data" else "to-" + re.sub(r"[^A-Za-z0-9]", "", target.name)[:40]
    return _home(config) / f"{mod_id}-{tag}.json"


def _mod_id(source: Path, explicit: str | None) -> str:
    value = explicit or source.name
    clean = re.sub(r"[^A-Za-z0-9_.-]", "_", value).strip("._")
    if not clean:
        raise ValidationError("Give an --id made of letters, digits, dot, dash or underscore")
    return clean


def payload(source: Path) -> list[tuple[str, Path]]:
    rows = []
    for path in sorted(source.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(source)
        if any(part.casefold() in SKIP_PARTS for part in relative.parts) or path.suffix.casefold() in SKIP_SUFFIXES:
            continue
        rows.append((relative.as_posix(), path))
    if not rows:
        raise ValidationError(f"{source} has no files to deploy")
    return rows


def deploy(config: ForgeConfig, source: Path, *, to: str | None = None, mod_id: str | None = None, approved: bool = False, force: bool = False) -> dict[str, Any]:
    source = source.resolve(strict=True)
    target = _target(config, to)
    if target == source or source in target.parents or target in source.parents:
        raise SafetyError("Source and target overlap; deploy from a separate mod folder")
    identity = _mod_id(source, mod_id)
    receipt_path = _receipt(config, identity, target)
    old = load(receipt_path) if receipt_path.is_file() else {"files": {}}
    actions, refused = [], []
    for relative, src in payload(source):
        dst = target / relative
        owned = relative in old["files"]
        if dst.exists():
            current = sha256_file(dst)
            if owned and current == old["files"][relative]["sha256"]:
                action = "same" if current == sha256_file(src) else "update"
            elif owned:
                action = "update-changed"
            elif force:
                action = "overwrite-backup"
            else:
                refused.append(relative)
                continue
        else:
            action = "create"
        actions.append({"file": relative, "action": action})
    report: dict[str, Any] = {"result": "PASS", "id": identity, "source": str(source), "target": str(target), "dry_run": not approved,
                              "actions": actions, "refused": refused, "receipt": str(receipt_path)}
    if refused:
        report["refused_reason"] = "exists and this deploy does not own it; pass --force to back it up and replace it"
    if not approved:
        report["hint"] = "rerun with --approve to copy; a mod manager's next deployment may revert direct Data changes"
        return report
    if refused and not force:
        raise SafetyError(f"{len(refused)} file(s) exist that this deploy does not own; review them or pass --force")
    backups = _home(config) / "backups" / identity / utc_now().replace(":", "").replace("-", "")
    record = {"schema": "skyrim-forge-deploy/1", "id": identity, "source": str(source), "target": str(target), "time": utc_now(), "files": dict(old["files"])}
    for row in actions:
        if row["action"] == "same":
            continue
        relative = row["file"]
        src, dst = source / relative, target / relative
        if dst.exists() and row["action"] in ("overwrite-backup", "update-changed"):
            backup = backups / relative
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dst, backup)
            record["files"].setdefault(relative, {})["backup"] = str(backup)
        dst.parent.mkdir(parents=True, exist_ok=True)
        temp = dst.with_name(dst.name + ".forge-tmp")
        shutil.copy2(src, temp)
        os.replace(temp, dst)  # rename: never writes through a hard link into a manager's staging copy
        record["files"][relative] = {**record["files"].get(relative, {}), "sha256": sha256_file(dst)}
        json_dump(receipt_path, record)  # after every file, so an interrupted deploy can still be undone
    json_dump(receipt_path, record)
    report["written"] = sum(1 for row in actions if row["action"] != "same")
    return report


def undeploy(config: ForgeConfig, source_or_id: str, *, to: str | None = None, approved: bool = False) -> dict[str, Any]:
    target = _target(config, to)
    identity = _mod_id(Path(source_or_id), None)
    receipt_path = _receipt(config, identity, target)
    if not receipt_path.is_file():
        raise ValidationError(f"No deploy receipt for {identity} at {target}; nothing to undo")
    record = load(receipt_path)
    plan, skipped = [], []
    for relative, entry in record["files"].items():
        dst = target / relative
        if dst.is_file() and entry.get("sha256") and sha256_file(dst) != entry["sha256"]:
            skipped.append(relative)
            continue
        plan.append({"file": relative, "action": "restore" if entry.get("backup") else "remove"})
    report: dict[str, Any] = {"result": "PASS", "id": identity, "target": str(target), "dry_run": not approved, "actions": plan,
                              "skipped_changed": skipped, "receipt": str(receipt_path)}
    if not approved:
        return report
    for row in plan:
        dst, entry = target / row["file"], record["files"][row["file"]]
        if row["action"] == "restore":
            shutil.copy2(entry["backup"], dst)
        elif dst.is_file():
            dst.unlink()
            parent = dst.parent
            while parent != target and parent.is_dir() and not any(parent.iterdir()):
                parent.rmdir(); parent = parent.parent
    if skipped:
        record["files"] = {key: value for key, value in record["files"].items() if key in skipped}
        json_dump(receipt_path, record)
    else:
        receipt_path.unlink()
    report["done"] = True
    return report
