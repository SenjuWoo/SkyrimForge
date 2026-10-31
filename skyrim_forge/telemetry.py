"""Correlate static framework-lint findings with the runtime logs that prove or disprove them.

Forge's evidence hierarchy says a runtime log beats a static heuristic when the
log shows the exact row was parsed. This module never upgrades a finding on its
own authority: it only reports what a log line says about a named file and line,
and leaves everything else UNVERIFIED.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .frameworks import lint_paths
from .util import iter_files, sha256_file

MAX_LOG_BYTES = 64 * 1024 * 1024
MAX_LOGS = 200
ERROR_RE = re.compile(r"\b(error|failed|invalid|unsupported|cannot|unable|rejected|skipped)\b", re.I)
WARN_RE = re.compile(r"\bwarn(?:ing)?\b", re.I)
POSITIVE_RE = re.compile(r"\b(applied|distributed|processed|loaded|added|entries|distributions)\b", re.I)
LINE_RE = re.compile(r"(?::|\bline\s+)(\d+)\b", re.I)
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _log_rows(log_dir: Path) -> tuple[list[dict[str, Any]], list[str]]:
    logs, warnings = [], []
    files = [path for path in iter_files(log_dir) if path.suffix.casefold() == ".log"][:MAX_LOGS]
    for path in files:
        size = path.stat().st_size
        if size > MAX_LOG_BYTES:
            warnings.append(f"log skipped, larger than {MAX_LOG_BYTES} bytes: {path.name}")
            continue
        text = ANSI_RE.sub("", path.read_text(encoding="utf-8-sig", errors="replace"))
        rows = []
        for number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            severity = "error" if ERROR_RE.search(line) else "warning" if WARN_RE.search(line) else "info"
            rows.append({"log": path.name, "log_line": number, "severity": severity, "text": line.strip()[:500]})
        logs.append({"path": str(path), "name": path.name, "size": size, "sha256": sha256_file(path), "rows": rows})
    return logs, warnings


def _mentions(row: dict[str, Any], name: str) -> tuple[bool, int | None]:
    """Return whether the line names this config file, and the row number it attributes, if any."""
    text = row["text"]
    position = text.casefold().find(name.casefold())
    if position < 0:
        return False, None
    match = LINE_RE.search(text[position + len(name):])
    if match:
        return True, int(match.group(1))
    match = LINE_RE.search(text)
    return True, int(match.group(1)) if match else None


def correlate(mod_root: Path, log_dir: Path) -> dict[str, Any]:
    """Attach runtime evidence to every static lint finding in one mod tree."""
    static = lint_paths([mod_root])
    logs, warnings = _log_rows(log_dir)
    findings = []
    for report in static["reports"]:
        name = Path(report["path"]).name
        rows = [row for log in logs for row in log["rows"]]
        file_positive = next((row for row in rows if _mentions(row, name)[0] and row["severity"] != "error" and POSITIVE_RE.search(row["text"])), None)
        file_error = next((row for row in rows if _mentions(row, name)[0] and row["severity"] == "error" and _mentions(row, name)[1] is None), None)
        for issue in report["issues"]:
            line = issue.get("line")
            exact = [row for row in rows if (hit := _mentions(row, name))[0] and hit[1] == line]
            exact_error = next((row for row in exact if row["severity"] == "error"), None)
            if exact_error:
                status, evidence = "RUNTIME_ERROR", [exact_error]
            elif exact:
                status, evidence = "RUNTIME_VERIFIED_PASS", exact
            elif file_error:
                status, evidence = "RUNTIME_ERROR_FILE", [file_error]
            elif file_positive and issue["severity"] == "warning":
                status, evidence = "RUNTIME_VERIFIED_PASS", [file_positive]
            else:
                status, evidence = "UNVERIFIED", []
            findings.append({
                "file": report["path"], "line": line, "static_severity": issue["severity"], "code": issue.get("code", ""),
                "message": issue["message"], "runtime_status": status,
                "promoted": status == "RUNTIME_VERIFIED_PASS" and issue["severity"] == "warning",
                "log_evidence": [{key: row[key] for key in ("log", "log_line", "severity", "text")} for row in evidence[:3]],
            })
    counts: dict[str, int] = {}
    for item in findings:
        counts[item["runtime_status"]] = counts.get(item["runtime_status"], 0) + 1
    return {
        "result": "PASS" if static["result"] == "PASS" else "FAIL",
        "mod_root": str(mod_root), "log_dir": str(log_dir),
        "files_scanned": static["files_scanned"], "logs_scanned": [{"name": log["name"], "size": log["size"], "sha256": log["sha256"]} for log in logs],
        "findings": findings, "status_counts": counts, "warnings": warnings,
        "rule": "RUNTIME_VERIFIED_PASS needs a log line that names this file and either this row or a positive distribution count with no error for the row. Static errors are never cleared by a runtime pass; they are recorded and left for review.",
        "evidence": "Log text matching only. Forge does not parse framework internals or prove that a log came from this exact deployed file unless its hash is recorded here.",
    }


def self_test() -> dict[str, Any]:
    """Prove a warning is promoted only by matching log evidence and an error stays an error."""
    import tempfile
    with tempfile.TemporaryDirectory(prefix="forge-telemetry-self-test-") as td:
        root = Path(td)
        mod = root / "mod"
        mod.mkdir()
        (mod / "test_DISTR.ini").write_text("Perk = 0x1~A.esp|||12(20)|||100\n", encoding="utf-8")
        logs = root / "logs"
        logs.mkdir()
        (logs / "po3_SpellPerkItemDistributor.log").write_text(
            "[info] loaded test_DISTR.ini: 1 entries\n[info] test_DISTR.ini:1 distributed 3 records\n", encoding="utf-8")
        report = correlate(mod, logs)
        promoted = [item for item in report["findings"] if item["promoted"]]
        (logs / "po3_SpellPerkItemDistributor.log").write_text("test_DISTR.ini:1 error: invalid trait\n", encoding="utf-8")
        errored = correlate(mod, logs)
        assertions = {
            "warning_found": any(item["static_severity"] == "warning" for item in report["findings"]),
            "promoted_by_log": bool(promoted),
            "error_status": any(item["runtime_status"] == "RUNTIME_ERROR" for item in errored["findings"]),
            "not_promoted_on_error": not any(item["promoted"] for item in errored["findings"]),
        }
        return {"result": "PASS" if all(assertions.values()) else "FAIL", "assertions": assertions}
