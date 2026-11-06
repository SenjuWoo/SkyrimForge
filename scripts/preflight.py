"""Cheap deterministic preflight for every commit. Full release validation stays separate."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
CRITICAL = ("tests.test_text_hygiene", "tests.test_vfs_sandbox", "tests.test_native_escaping",
            "tests.test_windows_paths", "tests.test_schedule_ownership", "tests.test_maintenance",
            "tests.test_freshness", "tests.test_publish_release")


def version_sources() -> dict[str, str]:
    def read(name: str) -> str:
        return (ROOT / name).read_text(encoding="utf-8")

    values = {
        "version.py": re.search(r'VERSION = "([\d.]+)"', read("skyrim_forge/version.py")).group(1),
        "VERSION.txt": read("VERSION.txt").split()[-1],
        "CURRENT.txt": read("CURRENT.txt").strip(),
        "server.json": json.loads(read("server.json"))["version"],
        "START-HERE.bat": re.search(r"title Skyrim Forge ([\d.]+)", read("START-HERE.bat")).group(1),
    }
    return values


def control_offenders() -> list[str]:
    from skyrim_forge.delivery import source_files
    from scripts.validate_repository import control_characters
    skip = {".exe", ".dll", ".png", ".ico", ".zip", ".nif", ".dds", ".wav", ".fuz"}
    bad = []
    for path in source_files(ROOT):
        if path.suffix.lower() in skip:
            continue
        try:
            text = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            continue
        if control_characters(text):
            bad.append(path.relative_to(ROOT).as_posix())
    return bad


def manifest_mismatch() -> list[str]:
    import hashlib
    manifest = ROOT / "MANIFEST.json"
    if not manifest.is_file():
        return []
    from scripts.validate_repository import git_normalized
    rows = json.loads(manifest.read_text(encoding="utf-8"))["files"]
    bad = []
    for row in rows:
        path = ROOT / row["path"]
        if not path.is_file() or hashlib.sha256(git_normalized(path)).hexdigest() != row["sha256"]:
            bad.append(row["path"])
    return bad[:10]


def tag_conflict(version: str) -> str:
    tag = f"v{version}"
    result = subprocess.run(["git", "rev-list", "-n", "1", tag], cwd=ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        return ""
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    return "" if result.stdout.strip() == head else f"{tag} already points at {result.stdout.strip()[:12]}, not HEAD"


def run() -> dict:
    versions = version_sources()
    unique = set(versions.values())
    tests = subprocess.run([sys.executable, "-m", "unittest", *CRITICAL, "-q"], cwd=ROOT, capture_output=True, text=True)
    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True).stdout.splitlines()
    checks = {
        "versions_agree": len(unique) == 1,
        "versions": versions,
        "control_characters": control_offenders(),
        "manifest_mismatch": manifest_mismatch(),
        "tag_conflict": tag_conflict(versions["version.py"]),
        "critical_tests": "PASS" if tests.returncode == 0 else "FAIL",
        "critical_tests_tail": (tests.stderr or tests.stdout).strip().splitlines()[-1:] or [],
        "dirty_files": len(dirty),
    }
    ok = (checks["versions_agree"] and not checks["control_characters"] and not checks["manifest_mismatch"]
          and not checks["tag_conflict"] and checks["critical_tests"] == "PASS")
    return {"result": "PASS" if ok else "FAIL", **checks}


if __name__ == "__main__":
    outcome = run()
    print(json.dumps(outcome, indent=2))
    raise SystemExit(0 if outcome["result"] == "PASS" else 2)
