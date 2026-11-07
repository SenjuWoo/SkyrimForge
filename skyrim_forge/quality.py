# Applicability-aware mod quality evidence gate.
# It selects the checks relevant to a mod type and refuses PASS rows that carry
# no evidence. It reports dimensions separately; there is no single quality score.
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .errors import ValidationError

SCHEMA = "skyrim-forge-quality-report/1"
DIMENSIONS = ("functional", "compatibility", "performance", "resources", "save_safety",
              "conflicts", "assets", "installation", "reproducibility", "publication")
STATUSES = {"PASS", "FAIL", "WARNING", "NOT_APPLICABLE", "NOT_RUN", "BLOCKED", "UNVERIFIED"}
# A missing core outcome is never waived; optional dimensions may be waived with
# a specific reason. This prevents an all-NOT_APPLICABLE report from passing.
NON_WAIVABLE = {"functional", "installation", "reproducibility", "publication"}
# Only these Forge verifier identities may establish tool-verified evidence.
# "forge" is the generic CLI report producer; the rest are concrete checks.
VERIFIERS = {"forge", "framework-lint", "framework-build", "fomod-validate", "papyrus-analyze",
             "native-binary-audit", "texture-inspect", "audio-inspect", "skse-inspect-pe", "validate-release"}

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
        "rule": "Every required dimension must carry hash-verified forge-tool evidence, or be NOT_APPLICABLE under policy with a specific reason. Bare strings are self-reports and cannot establish a verified PASS. Static PASS is not runtime proof.",
    }


def _evidence(value: Any, label: str, dimension: str) -> tuple[list[str], int, int, str | None]:
    """Return claims, verified/self-reported counts and an evidence error.

    A bare string is a useful manual claim but never machine verification. A
    tool receipt is authoritative only when its verifier is known, it is bound
    to this dimension, its artifact exists, its SHA-256 matches and the artifact
    is a JSON report whose own result is PASS.
    """
    if value is None:
        return [], 0, 0, None
    if not isinstance(value, list):
        return [], 0, 0, f"{label} must be a list"
    claims: list[str] = []
    verified = 0
    self_reported = 0
    for item in value:
        if isinstance(item, str):
            if not item.strip():
                return [], verified, self_reported, f"{label} must not contain empty strings"
            claims.append(item.strip())
            self_reported += 1
            continue
        if not isinstance(item, dict) or item.get("type") != "forge-tool":
            return [], verified, self_reported, f"{label} items must be strings or forge-tool receipts"
        tool = item.get("tool")
        artifact = item.get("artifact")
        digest = item.get("sha256")
        bound = item.get("dimension")
        if not isinstance(tool, str) or tool not in VERIFIERS:
            return [], verified, self_reported, f"{label} names an unknown verifier {tool!r}"
        if bound != dimension:
            return [], verified, self_reported, f"{label} receipt is bound to {bound!r}, not {dimension!r}"
        if item.get("result") != "PASS":
            return [], verified, self_reported, f"{label} tool receipt must record result PASS"
        if not isinstance(artifact, str) or not artifact.strip():
            return [], verified, self_reported, f"{label} tool receipt requires an artifact path"
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdefABCDEF" for c in digest):
            return [], verified, self_reported, f"{label} tool receipt requires a 64-character SHA-256"
        path = Path(artifact)
        if not path.is_file():
            return [], verified, self_reported, f"{label} artifact does not exist: {artifact}"
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != digest.casefold():
            return [], verified, self_reported, f"{label} artifact hash does not match its receipt"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return [], verified, self_reported, f"{label} artifact is not a JSON verification report"
        if not isinstance(payload, dict) or payload.get("result") != "PASS":
            return [], verified, self_reported, f"{label} artifact's own result is not PASS"
        claims.append(f"{tool}: {path.name} (sha256 verified, result PASS)")
        verified += 1
    return claims, verified, self_reported, None


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
            rows[dimension] = {"status": "NOT_RUN", "evidence": [], "notes": "No evidence supplied for this required dimension.",
                               "evidence_kind": "none", "verified_evidence": 0, "self_reported_evidence": 0}
            continue
        state = str(raw.get("status", "NOT_RUN")).upper()
        if state not in STATUSES:
            raise ValidationError(f"Unknown quality status for {dimension}: {state}")
        evidence, verified_count, self_reported_count, evidence_error = _evidence(
            raw.get("evidence"), f"{dimension}.evidence", dimension)
        notes = raw.get("notes", "")
        if not isinstance(notes, str):
            raise ValidationError(f"{dimension}.notes must be a string")
        notes = notes.strip()
        if evidence_error:
            state = "FAIL"
            notes = (notes + " " if notes else "") + evidence_error
            evidence = []
            verified_count = self_reported_count = 0
        elif state == "PASS" and not evidence:
            state = "FAIL"
            notes = (notes + " " if notes else "") + "PASS requires at least one evidence item."
        elif state == "PASS" and not verified_count:
            notes = (notes + " " if notes else "") + "Only self-reported claims were supplied; review is required."
        if state == "NOT_APPLICABLE":
            if dimension in NON_WAIVABLE:
                state = "FAIL"
                notes = f"{dimension} is not waivable; supply verified evidence."
            elif len(notes) < 8:
                state = "FAIL"
                notes = "NOT_APPLICABLE requires a specific reason."
        kind = "verified" if state == "PASS" and verified_count else (
            "self_reported" if state == "PASS" else ("waived" if state == "NOT_APPLICABLE" else "none"))
        rows[dimension] = {"status": state, "evidence": evidence, "notes": notes, "evidence_kind": kind,
                           "verified_evidence": verified_count, "self_reported_evidence": self_reported_count}
    statuses = [row["status"] for row in rows.values()]
    verified = [name for name, row in rows.items() if row["evidence_kind"] == "verified"]
    self_reported = [name for name, row in rows.items() if row["evidence_kind"] == "self_reported"]
    waived = [name for name, row in rows.items() if row["status"] == "NOT_APPLICABLE"]
    missing = [name for name, row in rows.items() if row["status"] in {"NOT_RUN", "BLOCKED", "UNVERIFIED"}]
    failed = [name for name, row in rows.items() if row["status"] == "FAIL"]
    if failed:
        verdict, result = "FAIL", "FAIL"
    elif missing:
        verdict, result = "UNVERIFIED", "PARTIAL"
    elif self_reported:
        verdict, result = "REVIEW_REQUIRED", "PARTIAL"
    elif not verified:
        verdict, result = "INCOMPLETE", "PARTIAL"
    elif "WARNING" in statuses:
        verdict, result = "WARNING", "PARTIAL"
    else:
        verdict, result = "PASS", "PASS"
    counts = {state: statuses.count(state) for state in sorted(set(statuses))}
    return {"schema": SCHEMA, "result": result, "verdict": verdict, "mod_types": types,
            "dimensions": rows, "counts": counts,
            "summary": {"verified": verified, "self_reported": self_reported, "waived": waived,
                        "missing": missing, "failed": failed},
            "evidence": "Only hash-verified forge-tool receipts establish verified PASS. Bare strings remain self-reports; missing runtime evidence is never converted to PASS."}


def self_test() -> dict[str, Any]:
    """Check applicability, waiver policy and the no-evidence/self-report refusal."""
    papyrus_plan = plan(["papyrus"])
    texture_plan = plan(["texture"])
    weak = audit({"mod_types": ["papyrus"], "checks": {dimension: {"status": "PASS", "evidence": []}
                                                         for dimension in papyrus_plan["dimensions"]}})
    text_only = audit({"mod_types": ["papyrus"], "checks": {
        dimension: {"status": "PASS", "evidence": ["trust me"]} for dimension in papyrus_plan["dimensions"]}})
    all_na = audit({"mod_types": ["papyrus"], "checks": {
        dimension: {"status": "NOT_APPLICABLE", "notes": "No applicable evidence for this build."}
        for dimension in papyrus_plan["dimensions"]}})
    checks = {
        "papyrus_requires_performance": "performance" in papyrus_plan["dimensions"],
        "texture_excludes_save_safety": "save_safety" not in texture_plan["dimensions"],
        "pass_without_evidence_fails": weak["verdict"] == "FAIL",
        "self_report_requires_review": text_only["verdict"] == "REVIEW_REQUIRED",
        "all_not_applicable_cannot_pass": all_na["verdict"] != "PASS",
    }
    return {"result": "PASS" if all(checks.values()) else "FAIL", "checks": checks}
