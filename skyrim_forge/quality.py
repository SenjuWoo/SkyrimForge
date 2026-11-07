# Applicability-aware mod quality evidence gate.
# It selects the checks relevant to a mod type and refuses PASS rows that carry
# no evidence. It reports dimensions separately; there is no single quality score.
from __future__ import annotations

from typing import Any

from .errors import ValidationError

SCHEMA = "skyrim-forge-quality-report/1"
DIMENSIONS = ("functional", "compatibility", "performance", "resources", "save_safety",
              "conflicts", "assets", "installation", "reproducibility", "publication")
STATUSES = {"PASS", "FAIL", "WARNING", "NOT_APPLICABLE", "NOT_RUN", "BLOCKED", "UNVERIFIED"}

# Each type names only the dimensions that can actually be judged for it.
_REQUIRED: dict[str, tuple[str, ...]] = {
    "framework": ("functional", "compatibility", "conflicts", "installation", "reproducibility", "publication"),
    "plugin": ("functional", "compatibility", "conflicts", "save_safety", "installation", "reproducibility", "publication"),
    "papyrus": ("functional", "compatibility", "performance", "save_safety", "installation", "reproducibility", "publication"),
    "native": ("functional", "compatibility", "performance", "resources", "save_safety", "installation", "reproducibility", "publication"),
    "texture": ("functional", "assets", "performance", "installation", "reproducibility", "publication"),
    "mesh": ("functional", "assets", "resources", "installation", "reproducibility", "publication"),
    "animation": ("functional", "compatibility", "assets", "installation", "reproducibility", "publication"),
    "lod": ("functional", "assets", "performance", "installation", "reproducibility", "publication"),
    "audio": ("functional", "assets", "installation", "reproducibility", "publication"),
    "package": ("installation", "reproducibility", "publication"),
}


def _types(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [part.strip() for part in value.split(",") if part.strip()]
    if not isinstance(value, list) or not value:
        raise ValidationError("mod_types must be a non-empty list or comma-separated string")
    result: list[str] = []
    for item in value:
        if item not in _REQUIRED:
            raise ValidationError(f"Unknown mod type {item!r}; use one of {', '.join(sorted(_REQUIRED))}")
        if item not in result:
            result.append(item)
    return result


def plan(mod_types: Any) -> dict[str, Any]:
    """List the evidence a report must supply for these mod types."""
    types = _types(mod_types)
    required = sorted({dimension for kind in types for dimension in _REQUIRED[kind]},
                      key=DIMENSIONS.index)
    return {
        "schema": SCHEMA, "result": "PASS", "mod_types": types,
        "dimensions": required,
        "checks": {dimension: {"status": "NOT_RUN", "evidence": [], "notes": ""} for dimension in required},
        "rule": "Every required dimension must be PASS with evidence, or explicitly NOT_APPLICABLE with a reason. Static PASS is not runtime proof.",
    }


def _strings(value: Any, label: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValidationError(f"{label} must be a list of non-empty strings")
    return [item.strip() for item in value]


def audit(report: dict[str, Any]) -> dict[str, Any]:
    """Evaluate a report without allowing missing or unsupported claims to become PASS."""
    if not isinstance(report, dict):
        raise ValidationError("Quality report must be a JSON object")
    if report.get("schema") not in (None, SCHEMA):
        raise ValidationError(f"Unsupported quality report schema: {report.get('schema')}")
    types = _types(report.get("mod_types"))
    supplied = report.get("checks", {})
    if not isinstance(supplied, dict):
        raise ValidationError("checks must be an object")
    required = plan(types)["dimensions"]
    rows: dict[str, Any] = {}
    for dimension in required:
        raw = supplied.get(dimension)
        if not isinstance(raw, dict):
            rows[dimension] = {"status": "NOT_RUN", "evidence": [], "notes": "No evidence supplied for this required dimension."}
            continue
        state = str(raw.get("status", "NOT_RUN")).upper()
        if state not in STATUSES:
            raise ValidationError(f"Unknown quality status for {dimension}: {state}")
        evidence = _strings(raw.get("evidence"), f"{dimension}.evidence")
        notes = raw.get("notes", "")
        if not isinstance(notes, str):
            raise ValidationError(f"{dimension}.notes must be a string")
        if state == "PASS" and not evidence:
            state = "FAIL"
            notes = (notes + " " if notes else "") + "PASS requires at least one evidence item."
        if state == "NOT_APPLICABLE" and not notes.strip():
            state = "FAIL"
            notes = "NOT_APPLICABLE requires a reason."
        rows[dimension] = {"status": state, "evidence": evidence, "notes": notes.strip()}
    statuses = [row["status"] for row in rows.values()]
    if "FAIL" in statuses:
        verdict, result = "FAIL", "FAIL"
    elif any(item in {"BLOCKED", "NOT_RUN", "UNVERIFIED"} for item in statuses):
        verdict, result = "UNVERIFIED", "PARTIAL"
    elif "WARNING" in statuses:
        verdict, result = "WARNING", "PASS"
    else:
        verdict, result = "PASS", "PASS"
    counts = {state: statuses.count(state) for state in sorted(set(statuses))}
    return {"schema": SCHEMA, "result": result, "verdict": verdict, "mod_types": types,
            "dimensions": rows, "counts": counts,
            "evidence": "Static/workspace evidence only. Missing runtime evidence remains UNVERIFIED and is never converted to PASS."}


def self_test() -> dict[str, Any]:
    """Check applicability and the no-evidence PASS refusal."""
    papyrus_plan = plan(["papyrus"])
    texture_plan = plan(["texture"])
    weak = audit({"mod_types": ["papyrus"], "checks": {dimension: {"status": "PASS", "evidence": []}
                                                         for dimension in papyrus_plan["dimensions"]}})
    strong = audit({"mod_types": ["texture"], "checks": {
        "functional": {"status": "PASS", "evidence": ["load-order comparison"]},
        "assets": {"status": "PASS", "evidence": ["DDS header and mip inspection"]},
        "performance": {"status": "NOT_APPLICABLE", "notes": "No performance-sensitive claim."},
        "installation": {"status": "PASS", "evidence": ["branch extraction receipt"]},
        "reproducibility": {"status": "PASS", "evidence": ["deterministic ZIP hash"]},
        "publication": {"status": "PASS", "evidence": ["README and licence inventory"]},
    }})
    checks = {
        "papyrus_requires_performance": "performance" in papyrus_plan["dimensions"],
        "texture_excludes_native": "compatibility" not in texture_plan["dimensions"],
        "pass_without_evidence_fails": weak["verdict"] == "FAIL",
        "complete_texture_passes": strong["verdict"] == "PASS",
    }
    return {"result": "PASS" if all(checks.values()) else "FAIL", "checks": checks}
