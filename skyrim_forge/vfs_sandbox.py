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
from uuid import uuid4

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
    """Return the selection sets to test: one explicit/default branch, or every exact/at-most choice.

    "Select none" is an explicit empty array. An omitted key means "use the
    FOMOD defaults", which can select a Recommended plugin, so dropping the
    empty choice silently replaced the zero-selection branch with Red.
    """
    if selections is not None and everything:
        raise ValidationError("pass explicit selections or all_branches=True, not both")
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
        branch: dict[str, Any] = {}
        for (key, _), value in zip(axes, choice):
            branch[key] = [] if value is None else value
        result.append(branch)
    return result


def _coverage(plan: dict[str, Any], all_branches: bool) -> dict[str, Any]:
    """Name the group types a run actually enumerated, and the ones it did not."""
    present = {group["type"] for step in plan.get("steps", []) for group in step.get("groups", [])}
    if all_branches:
        return {"mode": "all-branches", "group_types_tested": sorted(present & EXACT_GROUP_TYPES),
                "group_types_uncovered": sorted(present - EXACT_GROUP_TYPES)}
    # One branch proves the default path only; name every group it did not vary.
    return {"mode": "single", "group_types_tested": [], "group_types_uncovered": sorted(present)}


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


def _create_run_dir(sandbox: Path) -> Path:
    """Create a unique run directory with an exclusive mkdir.

    The timestamp alone has one-second resolution, so two runs started in the same
    second used to share a directory. The random suffix makes collisions
    vanishingly unlikely; mkdir(exist_ok=False) makes the check atomic anyway.
    """
    stamp = utc_now().replace(":", "").replace("-", "")
    for _ in range(8):
        candidate = sandbox / f"{stamp}-{uuid4().hex[:8]}"
        try:
            candidate.mkdir(parents=True, exist_ok=False)
            return candidate
        except FileExistsError:
            continue
    raise SafetyError("Could not create a unique sandbox run directory")


def test_install(plan_path: Path, source_root: Path, workspace_root: Path, *, approved: bool,
                 selections: dict[str, Any] | None = None, state: dict[str, Any] | None = None,
                 all_branches: bool = False) -> dict[str, Any]:
    """Simulate one or more FOMOD branches, materialise both manager layouts, and write a receipt."""
    require_approval(approved, "FOMOD sandbox install test")
    plan = validate_plan(plan_path, source_root)
    # expand_branch re-validates the raw plan; the validated copy carries file_analysis, which is not a plan field.
    raw_plan = load(plan_path)
    source = source_root.resolve(strict=True)
    branches = _branch_selections(plan, selections, all_branches)
    expanded_all = [expand_branch(raw_plan, branch, state, source) for branch in branches]

    planned_files = sum(len(item["files"]) for item in expanded_all) * 2
    planned_bytes = 0
    for item in expanded_all:
        for row in item["files"]:
            origin = source.joinpath(*PurePosixPath(row["source"]).parts)
            planned_bytes += (origin.stat().st_size if origin.is_file() else 0) * 2
    if planned_files > MAX_FILES or planned_bytes > MAX_BYTES:
        raise SafetyError(
            f"Sandbox install would copy {planned_files} files / {planned_bytes} bytes; "
            f"the budget is {MAX_FILES} files / {MAX_BYTES} bytes"
        )

    sandbox = require_within(Path(workspace_root) / ".forge" / "vfs-sandbox", workspace_root)
    sandbox.mkdir(parents=True, exist_ok=True)
    run = _create_run_dir(sandbox)
    coverage = _coverage(plan, all_branches)
    reports = []
    total_files = total_bytes = 0
    partial = False
    try:
        for index, expanded in enumerate(expanded_all):
            branch = branches[index]
            simulation = expanded["simulation"]
            simulation_errors = list(simulation.get("errors", []))
            layout_errors, warnings = _layout_checks(expanded["files"])
            problems = list(expanded["problems"])
            errors = [*simulation_errors, *layout_errors, *problems]
            # In an all-branches sweep every plugin name is real, so a simulation
            # rejection means the combination is impossible (e.g. a Required
            # plugin plus an explicit choice in SelectExactlyOne), not a broken
            # installation.
            # Only an enumerated, fully covered selection can be called
            # infeasible. With an unenumerated group type the simulator may be
            # rejecting a default we never explored, which is untested, not
            # impossible.
            infeasible = bool(all_branches and simulation.get("result") != "PASS"
                              and not layout_errors and not problems
                              and not coverage["group_types_uncovered"])
            if all_branches and coverage["group_types_uncovered"]:
                warnings.append("not enumerated by --all-branches: " + ", ".join(coverage["group_types_uncovered"]))
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
                        if total_files > MAX_FILES or total_bytes + size > MAX_BYTES:
                            raise SafetyError(f"Sandbox install exceeded the {MAX_FILES}-file / {MAX_BYTES}-byte budget while copying")
                        if layout == "mo2":
                            copied.append((row["destination"], sha256_file(destination)))
                total_bytes += size
            if infeasible:
                result = "INFEASIBLE"
            elif errors:
                result = "FAIL"
            else:
                result = "PASS"
            reports.append({
                "branch": label, "selections": branch, "selected_plugins": simulation["selected_plugins"],
                "simulation_result": simulation.get("result"), "file_count": len(expanded["files"]),
                "tree_sha256": _tree_digest(copied), "result": result,
                "errors": errors, "warnings": warnings,
            })
    except Exception:
        partial = True
        raise
    finally:
        if partial:
            json_dump(run / "install_verification_receipt.json", {
                "schema": "skyrim-forge-install-verification/1", "generated_utc": utc_now(),
                "sandbox": str(run), "result": "FAIL", "partial": True,
                "evidence": "The run was interrupted by a resource or copy failure; the directory holds only this run's files.",
            })
    counts = {
        "total": len(reports),
        "passed": sum(item["result"] == "PASS" for item in reports),
        "failed": sum(item["result"] == "FAIL" for item in reports),
        "infeasible": sum(item["result"] == "INFEASIBLE" for item in reports),
    }
    if counts["failed"]:
        overall = "FAIL"
    elif all_branches and (coverage["group_types_uncovered"] or counts["passed"] == 0):
        # A sweep that did not exercise every group type, or that produced no
        # usable installation, is not a pass. Say so instead of implying
        # exhaustive validation.
        overall = "PARTIAL"
    elif counts["passed"] == 0:
        overall = "FAIL"
    else:
        overall = "PASS"
    receipt = {
        "schema": "skyrim-forge-install-verification/1", "generated_utc": utc_now(),
        "plan": str(plan_path.resolve()), "source_root": str(source), "sandbox": str(run),
        "module": {"name": plan["module"]["name"], "version": plan["module"]["version"]},
        "result": overall,
        "branch_counts": counts,
        "branches": reports, "file_copies": total_files, "bytes_copied": total_bytes,
        "coverage": coverage,
        "budget": {"max_files": MAX_FILES, "max_bytes": MAX_BYTES,
                   "planned_files": planned_files, "planned_bytes": planned_bytes},
        "checks": ["no Data/Data nesting", "no destination collision", "no duplicate SKSE DLL", "payload present and hashed"],
        "evidence": "Branch extraction into MO2- and Vortex-shaped folders only. No MO2, Vortex, USVFS or game process was started; plugin loading and in-game behaviour are not tested.",
    }
    receipt_path = run / "install_verification_receipt.json"
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
