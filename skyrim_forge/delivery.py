"""Select release files from tracked or hash-bound source, never a raw private working tree."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess

REPORTS = {"VALIDATION.json", "BUILD-RECEIPT.json", "MANIFEST.json", "SBOM.spdx.json", "CHECKSUMS-SHA256.txt"}
PRODUCT_FILES = {
    "VERSION.txt", "README.md", "LICENSE", "NOTICE.md", "config.example.toml",
    "pyproject.toml", "forge_build_backend.py", "START-HERE.bat",
    "Forge Doctor.bat", "Skyrim Forge GUI.bat", "Skyrim Forge MCP.bat",
    "Skyrim Forge.bat", "Update Forge.bat", "Configure-Automation.ps1",
    "Configure-Forge.ps1", "Configure-Toolchain.ps1", "Install-AI-Bridge.ps1",
    "Install-Forge-Skill.ps1", "Install-HouseCarl.ps1", "Install-Skyrim-Pack.ps1",
    "Install-or-Update.ps1", "Register-MCP.ps1", "Update-Forge.ps1", "PowerShell-Parse-Gate.ps1", "Run Tests.bat",
}
PRODUCT_PREFIXES = ("skyrim_forge/", "integrations/", "references/", "resources/",
    "schemas/", "workers/", "assets/", "examples/", "docs/", "writer/published/")

def source_files(root: Path) -> list[Path]:
    root = root.resolve(strict=True)
    # Git is read-only here. A source archive instead uses the manifest shipped with it.
    manifest_rows = None
    if (root / ".git").exists():
        result = subprocess.run(["git", "-C", str(root), "ls-files", "-z"], capture_output=True, check=True)
        names = result.stdout.decode("utf-8").split("\0")
    else:
        manifest = json.loads((root / "MANIFEST.json").read_text(encoding="utf-8-sig"))
        manifest_rows = {row["path"]: row for row in manifest["files"]}
        if len(manifest_rows) != len(manifest["files"]):
            raise ValueError("Unsafe/duplicate manifest path")
        names = [*manifest_rows, "MANIFEST.json"]
    paths = []
    seen = set()
    for name in names:
        if not name:
            continue
        rel = PurePosixPath(name)
        if rel.is_absolute() or ".." in rel.parts or "\\" in name or ":" in name or name.casefold() in seen:
            raise ValueError(f"Unsafe/duplicate release path: {name}")
        seen.add(name.casefold())
        path = root / name
        for ancestor in (path, *path.parents):
            if ancestor == root.parent:
                break
            if ancestor.is_symlink() or getattr(ancestor, "is_junction", lambda: False)():
                raise ValueError(f"Linked release source: {name}")
        if not path.is_file() or not path.resolve().is_relative_to(root):
            raise ValueError(f"Missing or escaped release source: {name}")
        if manifest_rows is not None and name != "MANIFEST.json":
            if hashlib.sha256(path.read_bytes()).hexdigest() != manifest_rows[name]["sha256"]:
                raise ValueError(f"Source manifest mismatch: {name}")
        paths.append(path)
    return sorted(paths, key=lambda p: p.relative_to(root).as_posix().casefold())

def is_product_file(name: str) -> bool:
    # Templates are product inputs; developer progress/changelogs are not mod payloads.
    rel = PurePosixPath(name)
    template = any(p.casefold() in {"templates", "_project-template"} for p in rel.parts)
    development = rel.stem.casefold() in {"state","plan","decisions","current","validation","workspace_ownership","project_ownership","ownership"}
    if not template and (development or "changelog" in rel.stem.casefold()) and rel.suffix.casefold() in {".md", ".txt", ".rst"}:
        return False
    return name in PRODUCT_FILES or name.startswith(PRODUCT_PREFIXES)

def product_files(root: Path) -> list[Path]:
    return [p for p in source_files(root) if is_product_file(p.relative_to(root).as_posix())]
