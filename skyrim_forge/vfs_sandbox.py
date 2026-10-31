"""Extract a FOMOD branch into MO2- and Vortex-shaped folders and check the installed layout.

This is the mechanical half of a real install test. It never touches a live
manager: everything lands under <workspace>/.forge/vfs-sandbox, and the receipt
says plainly that no USVFS, MO2 or Vortex process was run.
"""
from __future__ import annotations

import hashlib
import itertools
import shutil
from pathlib import Path, PurePosixPath
from typing import Any

from .errors import SafetyError, ValidationError
from .fomod import expand_branch, validate_plan
from .safety import require_approval, require_within
from .strictjson import load
from .util import json_dump, safe_name, sha256_file, utc_now

MAX_BRANCHES = 64
MAX_FILES = 200_000
MAX_BYTES = 4 * 1024 * 1024 * 1024
EXACT_GROUP_TYPES = {"SelectExactlyOne", "SelectAtMostOne"}


def _branch_selections(plan: dict[str, Any], selections: dict[str, Any] | None, everything: bool) -> list[dict[str, Any]]:
    """Return the selection sets to test: one explicit/default branch, or every exact/at-most choice."""
    if selections is not None:
        return [selections]
    if not everything:
        return [{}]
    axes: list[tuple[str, list[str | None]]] = []
    for step in plan["steps"]:
        for group in step["groups"]:
            if group["type"] in EXACT_GROUP_TYPES:
                names: list[str | None] = [plugin["name"] for plugin in group["plugins"]]
                axes.append((f"{step['name']}/{group['name']}", names + ([None] if group["type"] == "SelectAtMostOne" else [])))
    combinations = 1
    for _, values in axes:
        combinations *= len(values)
    if combinations > MAX_BRANCHES:
        raise ValidationError(f"{combinations} exact/at-most branches exceed the {MAX_BRANCHES}-branch cap; pass explicit selections instead")
    result = []
    for choice in itertools.product(*(values for _, values in axes)) if axes else [()]:
        result.append({key: value for (key, _), value in zip(axes, choice) if value is not None})
    return result


def _layout_checks(files: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    seen: dict[str, str] = {}
    plugins: dict[str, list[str]] = {}
    for row in files:
        destination = row["destination"].replace("\\", "/").lstrip("/")
        parts = PurePosixPath(destination).parts
        if not parts or ".." in parts or (parts and ":" in parts[0]):
            errors.append(f"unsafe destination: {row['destination']}")
            continue
        if parts[0].casefold() == "data":
            errors.append(f"destination already starts with Data/: {destination}")
        key = destination.casefold()
        if key in seen and seen[key] != row["source"]:
            errors.append(f"two sources install to {destination}: {seen[key]} and {row['source']}")
        seen[key] = row["source"]
        if len(parts) >= 2 and parts[0].casefold() == "skse" and parts[1].casefold() == "plugins":
            plugins.setdefault(PurePosixPath(destination).stem.casefold(), []).append(destination)
    for stem, destinations in sorted(plugins.items()):
        suffixes = {PurePosixPath(item).suffix.casefold() for item in destinations}
        if len(destinations) > 1 and {".dll", ".ini"} <= suffixes:
            warnings.append(f"SKSE plugin stem {stem!r} installs {len(destinations)} files: {destinations}")
        elif len([item for item in destinations if PurePosixPath(item).suffix.casefold() == ".dll"]) > 1:
            errors.append(f"the same SKSE DLL installs more than once: {destinations}")
    return sorted(set(errors)), sorted(set(warnings))


def _tree_digest(rows: list[tuple[str, str]]) -> str:
    digest = hashlib.sha256()
    for destination, file_hash in sorted(rows, key=lambda item: item[0].casefold()):
        digest.update(f"{destination}\x00{file_hash}\n".encode("utf-8"))
    return digest.hexdigest()


def test_install(plan_path: Path, source_root: Path, workspace_root: Path, *, approved: bool,
                 selections: dict[str, Any] | None = None, state: dict[str, Any] | None = None,
                 all_branches: bool = False) -> dict[str, Any]:
    """Simulate one or more FOMOD branches, materialise both manager layouts, and write a receipt."""
    require_approval(approved, "FOMOD sandbox install test")
    plan = validate_plan(plan_path, source_root)
    # expand_branch re-validates the raw plan; the validated copy carries file_analysis, which is not a plan field.
    raw_plan = load(plan_path)
    source = source_root.resolve(strict=True)
    sandbox = require_within(Path(workspace_root) / ".forge" / "vfs-sandbox", workspace_root)
    run = sandbox / utc_now().replace(":", "").replace("-", "")
    branches = _branch_selections(plan, selections, all_branches)
    reports = []
    total_files = total_bytes = 0
    for index, branch in enumerate(branches):
        expanded = expand_branch(raw_plan, branch, state, source)
        errors, warnings = _layout_checks(expanded["files"])
        errors.extend(expanded["problems"])
        label = safe_name(f"branch-{index + 1:02d}", fallback="branch")
        copied: list[tuple[str, str]] = []
        size = 0
        if not errors:
            for layout in ("mo2", "vortex"):
                for row in expanded["files"]:
                    origin = source.joinpath(*PurePosixPath(row["source"]).parts)
                    if not origin.is_file():
                        errors.append(f"missing payload: {row['source']}")
                        break
                    destination = run / label / layout / safe_name(plan["module"]["name"], fallback="mod") / PurePosixPath(row["destination"].replace("\\", "/").lstrip("/"))
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(origin, destination)
                    total_files += 1
                    size += destination.stat().st_size
                    if layout == "mo2":
                        copied.append((row["destination"], sha256_file(destination)))
            total_bytes += size
        if total_files > MAX_FILES or total_bytes > MAX_BYTES:
            raise SafetyError(f"Sandbox install exceeds the {MAX_FILES}-file / {MAX_BYTES}-byte budget")
        reports.append({
            "branch": label, "selections": branch, "selected_plugins": expanded["simulation"]["selected_plugins"],
            "file_count": len(expanded["files"]), "tree_sha256": _tree_digest(copied),
            "result": "PASS" if not errors else "FAIL", "errors": errors, "warnings": warnings,
        })
    receipt = {
        "schema": "skyrim-forge-install-verification/1", "generated_utc": utc_now(),
        "plan": str(plan_path.resolve()), "source_root": str(source), "sandbox": str(run),
        "module": {"name": plan["module"]["name"], "version": plan["module"]["version"]},
        "result": "PASS" if all(item["result"] == "PASS" for item in reports) else "FAIL",
        "branches": reports, "file_copies": total_files, "bytes_copied": total_bytes,
        "checks": ["no Data/Data nesting", "no destination collision", "no duplicate SKSE DLL", "payload present and hashed"],
        "evidence": "Branch extraction into MO2- and Vortex-shaped folders only. No MO2, Vortex, USVFS or game process was started; plugin loading and in-game behaviour are not tested.",
    }
    sandbox.mkdir(parents=True, exist_ok=True)
    receipt_path = sandbox / "install_verification_receipt.json"
    json_dump(receipt_path, receipt)
    receipt["receipt"] = str(receipt_path)
    return receipt


def self_test() -> dict[str, Any]:
    """Prove one clean branch passes and a Data/-nested destination is rejected."""
    import tempfile
    with tempfile.TemporaryDirectory(prefix="forge-vfs-self-test-") as td:
        root = Path(td)
        source = root / "source"
        payload = source / "Core" / "SKSE" / "Plugins"
        payload.mkdir(parents=True)
        (payload / "fixture.dll").write_bytes(b"dll")
        (payload / "fixture.ini").write_bytes(b"ini")
        plan = {"schema": "skyrim-forge-fomod-plan/1", "module": {"name": "Sandbox Fixture", "version": "1.0.0"},
                "required_files": [{"kind": "folder", "source": "Core", "destination": "", "always_install": True}],
                "strict_coverage": True}
        plan_path = root / "plan.json"
        json_dump(plan_path, plan)
        clean = test_install(plan_path, source, root / "workspace", approved=True)
        nested = dict(plan)
        nested["required_files"] = [{"kind": "folder", "source": "Core", "destination": "Data", "always_install": True}]
        nested_path = root / "nested.json"
        json_dump(nested_path, nested)
        broken = test_install(nested_path, source, root / "workspace2", approved=True)
        assertions = {
            "clean_pass": clean["result"] == "PASS",
            "receipt_written": Path(clean["receipt"]).is_file(),
            "mo2_layout": (Path(clean["sandbox"]) / "branch-01" / "mo2").is_dir(),
            "vortex_layout": (Path(clean["sandbox"]) / "branch-01" / "vortex").is_dir(),
            "data_nesting_rejected": broken["result"] == "FAIL",
        }
        return {"result": "PASS" if all(assertions.values()) else "FAIL", "assertions": assertions}
