"""One `check` over a mod folder: runs every validator that applies and reports the evidence tier reached.

Tiers: static (headers, configs, layout, references), compiled (every .psc has a .pex no older than it),
packaged (a release archive passed release-validate's checks; given with --package), runtime (never claimed:
no Skyrim session is started, so it is always NOT RUN). A report never presents static evidence as runtime proof.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from . import datakinds, nif, pex
from .audio import validate_voice_tree
from .errors import ForgeError
from .frameworks import lint_paths
from .plugin_header import inspect_plugin_header

PLUGIN_SUFFIXES = {".esp", ".esm", ".esl"}


def _add(report: dict[str, Any], check: str, items: int, errors: list[str], warnings: list[str]) -> None:
    report["checked"].append({"check": check, "items": items, "errors": len(errors), "warnings": len(warnings)})
    report["errors"] += [{"check": check, "message": message} for message in errors]
    report["warnings"] += [{"check": check, "message": message} for message in warnings]


def check(root: Path, *, package: Path | None = None) -> dict[str, Any]:
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ForgeError(f"check needs a mod folder: {root}")
    files = [path for path in root.rglob("*") if path.is_file() and ".git" not in path.parts]
    report: dict[str, Any] = {"root": str(root), "files": len(files), "checked": [], "errors": [], "warnings": [], "gaps": []}

    plugins = [path for path in files if path.suffix.casefold() in PLUGIN_SUFFIXES]
    errors, warnings = [], []
    for path in plugins:
        try:
            header = inspect_plugin_header(path, with_hash=False)
            if path.suffix.casefold() == ".esl" and not header.is_light_flag:
                warnings.append(f"{path.name}: .esl extension without the light flag")
        except Exception as exc:
            errors.append(f"{path.name}: {exc}")
    if plugins:
        _add(report, "plugin-header", len(plugins), errors, warnings)
        report["gaps"].append("masters and record links are not resolved against a load order (use records-validate)")

    configs = [path for path in files if path.suffix.casefold() in {".ini", ".json"}]
    if configs:
        lint = lint_paths(configs)
        errs = [f"{row['path']}:{issue['line']}: {issue['message']}" for row in lint.get("reports", []) for issue in row["issues"] if issue["severity"] == "error"]
        warns = [f"{row['path']}:{issue['line']}: {issue['message']}" for row in lint.get("reports", []) for issue in row["issues"] if issue["severity"] != "error"]
        _add(report, "framework-configs", len(configs), errs, warns)

    kinds = [path for path in files if path.suffix.casefold() == ".xml" and ("sliderpresets" in path.as_posix().casefold() or "slidergroups" in path.as_posix().casefold())]
    kinds += [path for path in files if path.suffix.casefold() == ".ini" and not path.name.casefold().endswith(datakinds.FRAMEWORK_SUFFIXES)
              and "skypatcher" not in [part.casefold() for part in path.parts]]
    if kinds:
        rows = [datakinds.validate(path) for path in kinds]
        _add(report, "data-kinds", len(rows), [f"{r['file']}: {i['message']}" for r in rows for i in r["issues"] if i["severity"] == "error"],
             [f"{r['file']}: {i['message']}" for r in rows for i in r["issues"] if i["severity"] != "error"])

    meshes = [path for path in files if path.suffix.casefold() == ".nif"]
    if meshes:
        data_roots = [p for p in (root, root / "Data") if (p / "textures").is_dir() or (p / "Textures").is_dir()]
        errs, warns = [], []
        for path in meshes:
            try:
                for row in nif.refs(path, data_roots=data_roots, archives=[])["textures"]:
                    if not row["found"]:
                        warns.append(f"{path.relative_to(root).as_posix()}: texture {row['path']} is not in this mod (may come from the game)")
            except ForgeError as exc:
                errs.append(f"{path.relative_to(root).as_posix()}: {exc}")
        _add(report, "meshes", len(meshes), errs, warns)

    sources = [path for path in files if path.suffix.casefold() == ".psc"]
    compiled = [path for path in files if path.suffix.casefold() == ".pex"]
    stale = []
    if sources:
        by_name = {path.stem.casefold(): path for path in compiled}
        for source in sources:
            built = by_name.get(source.stem.casefold())
            if built is None or built.stat().st_mtime + 1 < source.stat().st_mtime:
                stale.append(source.stem)
    errs = []
    for path in compiled:
        try:
            if pex.parse(path.read_bytes())["game_id"] != 1:
                errs.append(f"{path.name}: compiled for another game")
        except ForgeError as exc:
            errs.append(f"{path.name}: {exc}")
    if sources or compiled:
        _add(report, "scripts", len(sources) + len(compiled), errs, [f"{name}: no PEX or PEX older than its source" for name in stale])

    if any(part.casefold() == "voice" for path in files for part in path.parts):
        voice = validate_voice_tree(root)
        _add(report, "voice-layout", voice.get("voice_files", 0), voice.get("errors", []), voice.get("warnings", []))

    fomod = root / "fomod" / "ModuleConfig.xml"
    if fomod.is_file():
        from .fomod import validate_fomod
        result = validate_fomod(root)
        _add(report, "fomod", 1, [str(item) for item in result.get("errors", [])], [str(item) for item in result.get("warnings", [])])

    report["result"] = "FAIL" if report["errors"] else "PASS"
    tiers = {"static": report["result"], "compiled": "NOT APPLICABLE" if not sources else ("PASS" if not stale and not errs else "FAIL"),
             "packaged": "NOT RUN", "runtime": "NOT RUN"}
    if package is not None:
        from .release import validate_release_tree
        if package.is_dir():
            tiers["packaged"] = validate_release_tree(package).get("result", "FAIL")
        else:
            report["gaps"].append("--package must be an extracted release folder")
    report["evidence"] = tiers
    report["evidence_note"] = "runtime is never claimed: no game session, SKSE load or save round trip happened"
    return report
