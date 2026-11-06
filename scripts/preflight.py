"""Cheap deterministic preflight for every commit.

The everyday check answers "is this source internally consistent?" and reports
release state without treating a post-release docs commit as an error. The
strict `--release` mode additionally requires a clean tree and a taggable state.
"""
from __future__ import annotations

import argparse
import hashlib
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
EVIDENCE = {"README.md", "AGENTS.md", "CHANGELOG.md", "CHANGELOG.txt", "STATE.md", "PLAN.md",
            "DECISIONS.md", "MANIFEST.json", "VALIDATION.json", "BUILD-RECEIPT.json",
            "SBOM.spdx.json", "CHECKSUMS-SHA256.txt"}
REPORTS = {"VALIDATION.json", "BUILD-RECEIPT.json", "MANIFEST.json", "SBOM.spdx.json", "CHECKSUMS-SHA256.txt"}
HEALTHY = {"UNRELEASED", "TAGGED", "POST_RELEASE"}


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)


def version_sources(root: Path = ROOT) -> dict[str, str]:
    def read(name: str) -> str:
        return (root / name).read_text(encoding="utf-8")

    return {
        "version.py": re.search(r'VERSION = "([\d.]+)"', read("skyrim_forge/version.py")).group(1),
        "VERSION.txt": read("VERSION.txt").split()[-1],
        "CURRENT.txt": read("CURRENT.txt").strip(),
        "server.json": json.loads(read("server.json"))["version"],
        "START-HERE.bat": re.search(r"title Skyrim Forge ([\d.]+)", read("START-HERE.bat")).group(1),
    }


def control_offenders(root: Path = ROOT) -> list[str]:
    root = root.resolve()
    from skyrim_forge.delivery import source_files
    from scripts.validate_repository import control_characters
    skip = {".exe", ".dll", ".png", ".ico", ".zip", ".nif", ".dds", ".wav", ".fuz"}
    bad = []
    for path in source_files(root):
        if path.suffix.lower() in skip:
            continue
        try:
            text = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            continue
        if control_characters(text):
            bad.append(path.relative_to(root).as_posix())
    return bad


def manifest_report(root: Path = ROOT) -> dict:
    """Compare the complete canonical file set and hashes with MANIFEST.json."""
    root = root.resolve()
    manifest = root / "MANIFEST.json"
    if not manifest.is_file():
        return {"error": "missing"}
    try:
        rows = json.loads(manifest.read_text(encoding="utf-8"))["files"]
        recorded = {row["path"]: row for row in rows}
    except (ValueError, KeyError, TypeError):
        return {"error": "malformed"}
    from skyrim_forge.delivery import source_files
    from scripts.validate_repository import git_normalized
    expected = {p.relative_to(root).as_posix(): p for p in source_files(root) if p.name not in REPORTS}
    missing = sorted(expected.keys() - recorded.keys())
    unexpected = sorted(recorded.keys() - expected.keys())
    mismatch = []
    for name in sorted(expected.keys() & recorded.keys()):
        data = git_normalized(expected[name])
        row = recorded[name]
        if row.get("size") != len(data) or row.get("sha256") != hashlib.sha256(data).hexdigest():
            mismatch.append(name)
    return {"missing": missing[:20], "unexpected": unexpected[:20], "mismatch": mismatch[:20]}


def release_state(version: str, root: Path = ROOT) -> tuple[str, str]:
    """UNRELEASED / TAGGED / POST_RELEASE are healthy; the other two are not.

    A previously released version is not an error merely because HEAD advanced,
    but product code changed after the tag without a bump is.
    """
    tag = f"v{version}"
    tagged = _git(root, "rev-parse", "-q", "--verify", f"refs/tags/{tag}")
    if tagged.returncode != 0:
        return "UNRELEASED", tag
    tag_sha = tagged.stdout.strip()
    head = _git(root, "rev-parse", "HEAD").stdout.strip()
    if tag_sha == head:
        return "TAGGED", tag_sha
    if _git(root, "merge-base", "--is-ancestor", tag_sha, head).returncode != 0:
        return "FOREIGN_TAG", f"{tag} -> {tag_sha[:12]} is not in HEAD's history"
    changed = _git(root, "diff", "--name-only", f"{tag_sha}..{head}").stdout.splitlines()
    product = [name for name in changed if name not in EVIDENCE and not name.startswith("docs/")]
    if product:
        return "STALE_VERSION", f"{len(product)} product file(s) after {tag}: {', '.join(product[:5])}"
    return "POST_RELEASE", f"{len(changed)} documentation/evidence file(s) after {tag}"


def run(root: Path = ROOT, release: bool = False) -> dict:
    versions = version_sources(root)
    state, detail = release_state(versions["version.py"], root)
    manifest = manifest_report(root)
    tests = subprocess.run([sys.executable, "-m", "unittest", *CRITICAL, "-q"],
                           cwd=root, capture_output=True, text=True)
    dirty = _git(root, "status", "--porcelain").stdout.splitlines()
    checks = {
        "release": release,
        "versions_agree": len(set(versions.values())) == 1,
        "versions": versions,
        "control_characters": control_offenders(root),
        "manifest": manifest,
        "release_state": state,
        "release_detail": detail,
        "critical_tests": "PASS" if tests.returncode == 0 else "FAIL",
        "critical_tests_tail": (tests.stderr or tests.stdout).strip().splitlines()[-1:] or [],
        "dirty_files": len(dirty),
    }
    clean_manifest = not manifest.get("error") and not any(
        manifest.get(key) for key in ("missing", "unexpected", "mismatch"))
    ok = checks["versions_agree"] and clean_manifest and not checks["control_characters"] \
        and checks["critical_tests"] == "PASS" and state in HEALTHY
    if release:
        ok = ok and state in {"UNRELEASED", "TAGGED"} and not dirty
    checks["result"] = "PASS" if ok else "FAIL"
    return checks


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fast development or strict release preflight.")
    parser.add_argument("--release", action="store_true", help="require a clean tree and a taggable state")
    args = parser.parse_args()
    outcome = run(release=args.release)
    print(json.dumps(outcome, indent=2))
    raise SystemExit(0 if outcome["result"] == "PASS" else 2)
