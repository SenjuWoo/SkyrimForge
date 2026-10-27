"""Validate staged runtime mod payloads and build byte-checked archives without source paperwork."""
from __future__ import annotations

import os
import re
import hashlib
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from .errors import SafetyError, ValidationError
from .fomod import validate_fomod
from .safety import require_approval, require_within, validate_filename
from .util import sha256_file

BLOCKED_SUFFIXES = {".log", ".dmp", ".tmp", ".bak", ".pdb", ".ilk", ".obj", ".pyc"}
BLOCKED_NAMES = {"meta.ini", "desktop.ini", "thumbs.db", ".ds_store", ".env",
    "nexus-mod-page.bbcode", "rights-manifest.json", "nexus-compliance-audit.json",
    "publication-plan.normalized.json", "nexus-publish-checklist.md", "nexus-permissions.md", "ai-disclosure.md"}
BLOCKED_DIRS = {"__pycache__", ".git", ".github", ".venv", "venv", ".codex", ".claude",
    ".agents", "build", "dist", "tests", "logs", "backups"}
DEVELOPMENT_STEMS = {"state", "plan", "decisions", "current", "validation",
    "workspace_ownership", "ownership", "project_ownership", "agents", "claude", "readme"}
FIXED_TIME = (2026, 7, 23, 0, 0, 0)
TEXT_SCAN_SUFFIXES = {".txt", ".md", ".ini", ".json", ".toml", ".yaml", ".yml", ".xml", ".psc", ".pas", ".py", ".ps1", ".bat"}
PRIVATE_WINDOWS_PATH = re.compile(r"[A-Za-z]:\\Users\\(?!YOU(?:\\|$)|<)", re.I)


def validate_release_tree(root: Path) -> dict[str, Any]:
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValidationError("Release tree must be a directory")
    errors = []
    warnings = []
    files = []
    casefolded: dict[str, str] = {}
    # Walk explicitly so a rejected link/development directory is never traversed.
    pending = [root]
    while pending:
        directory = pending.pop()
        for path in directory.iterdir():
            rel = path.relative_to(root).as_posix()
            if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
                errors.append(f"link is not allowed: {rel}")
                continue
            key = rel.casefold()
            if key in casefolded and casefolded[key] != rel:
                errors.append(f"case-colliding paths: {casefolded[key]} and {rel}")
            casefolded[key] = rel
            if path.is_dir():
                if path.name.casefold() in BLOCKED_DIRS:
                    errors.append(f"development directory in release: {rel}")
                else:
                    pending.append(path)
                continue
            if not path.is_file():
                errors.append(f"unsupported payload entry: {rel}")
                continue
            stem = path.stem.casefold()
            text_metadata = path.suffix.casefold() in {".md", ".txt", ".rst"} and (
                stem in DEVELOPMENT_STEMS or "changelog" in stem or stem in {"changes", "history"})
            if text_metadata or path.name.casefold() in BLOCKED_NAMES or path.suffix.casefold() in BLOCKED_SUFFIXES:
                errors.append(f"development or manager artifact: {rel}")
            if path.suffix.casefold() in TEXT_SCAN_SUFFIXES and path.stat().st_size <= 16 * 1024 * 1024:
                text = path.read_text(encoding="utf-8-sig", errors="replace")
                if PRIVATE_WINDOWS_PATH.search(text):
                    errors.append(f"private Windows user path in release text: {rel}")
            files.append({"path": rel, "size": path.stat().st_size, "sha256": sha256_file(path)})
    if not files:
        errors.append("release payload is empty")
    fomod_dirs = [path for path in root.iterdir() if path.is_dir() and path.name.casefold() == "fomod"]
    fomod_report = None
    if fomod_dirs:
        fomod_report = validate_fomod(root, strict_coverage=True)
        errors.extend(f"FOMOD: {item}" for item in fomod_report["errors"])
        warnings.extend(f"FOMOD: {item}" for item in fomod_report["warnings"])
    return {
        "result": "PASS" if not errors else "FAIL",
        "root": str(root),
        "file_count": len(files),
        "errors": sorted(set(errors)),
        "warnings": warnings,
        "files": files,
        "fomod": fomod_report,
        "target": "private",
        "share_ready": False,
        "publication_status": "PRIVATE_ONLY",
        "evidence": "Release-tree hygiene only. This result is not Nexus/publication approval and must not be called share-ready. Gameplay and runtime behavior are not validated.",
    }


def build_release(root: Path, output: Path, workspace_root: Path, *, approved: bool) -> dict[str, Any]:
    require_approval(approved, "release archive creation")
    root = root.resolve(strict=True)
    output = require_within(output, workspace_root)
    if output == root or output.is_relative_to(root):
        raise SafetyError("Release output must be outside its staged runtime payload")
    report = validate_release_tree(root)
    if report["result"] != "PASS":
        raise ValidationError(f"Release tree failed validation: {report['errors']}")
    validate_filename(output.name, {".zip"})
    if output.exists():
        raise SafetyError(f"Refusing to overwrite release archive: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(prefix=f".{output.name}.", suffix=".forge.tmp", dir=output.parent)
    os.close(handle)
    temporary = Path(name)
    try:
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            # Pack the validated file set, streaming large BSAs/textures and rejecting changed bytes.
            for item in report["files"]:
                path = root / item["path"]
                if path.is_symlink() or not path.resolve().is_relative_to(root):
                    raise SafetyError(f"Payload path changed after validation: {item['path']}")
                info = zipfile.ZipInfo(item["path"], FIXED_TIME)
                info.create_system = 3
                info.external_attr = ((0o100755 if os.access(path, os.X_OK) else 0o100644) & 0xFFFF) << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                digest = hashlib.sha256()
                count = 0
                with path.open("rb") as source, archive.open(info, "w") as target:
                    for chunk in iter(lambda: source.read(1024 * 1024), b""):
                        target.write(chunk); digest.update(chunk); count += len(chunk)
                if count != item["size"] or digest.hexdigest() != item["sha256"]:
                    raise ValidationError(f"Payload changed after validation: {item['path']}")
        with zipfile.ZipFile(temporary) as archive:
            bad = archive.testzip()
            if bad:
                raise ValidationError(f"ZIP CRC failure: {bad}")
        # Windows rename and POSIX hard-link creation both refuse a concurrently created output.
        if os.name == "nt":
            os.rename(temporary, output)
        else:
            os.link(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    return {
        "result": "PASS",
        "target": "private",
        "share_ready": False,
        "publication_status": "PRIVATE_ONLY",
        "output": str(output),
        "size": output.stat().st_size,
        "sha256": sha256_file(output),
        "file_count": report["file_count"],
        "evidence": "Deterministic private archive only. Use target=nexus with a validated publication plan for share-ready status.",
    }
