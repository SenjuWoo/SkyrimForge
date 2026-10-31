"""Verify Forge's cross-project contracts without syncing either project.

Forge releases independently, so it must not copy another repository's state.
Two contracts are load-bearing and can be checked from the outside:

1. The Ultimate AI Starter Bundle's ``BUNDLED-TOOLS/CATALOG.json`` entry
   ``skyrim-forge`` names this repository, the release asset template and a
   ``min_version`` floor, and its installer verifies ``SHA256SUMS``.
2. Reverse THIS!'s ``kit.json`` / ``installed.json`` receipts supply the
   texconv and 7-Zip paths and hashes Forge binds without copying.

Everything is read-only. Exit 0 = no drift, 2 = drift, 3 = could not verify.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
BUNDLE_REPO = "SenjuWoo/Ultimate-AI-Starter-Bundle"
FORGE_REPO = "SenjuWoo/SkyrimForge"
REVERSE_REPO = "SenjuWoo/reverse-this"
RAW = "https://raw.githubusercontent.com/{repo}/main/{path}"
API_LATEST = "https://api.github.com/repos/{repo}/releases/latest"
TIMEOUT = 20


def _version() -> str:
    match = re.search(r'^VERSION\s*=\s*"([^"]+)"', (ROOT / "skyrim_forge" / "version.py").read_text(encoding="utf-8"), re.M)
    if match is None:
        raise RuntimeError("skyrim_forge/version.py has no VERSION declaration")
    return match.group(1)


VERSION = _version()


def _get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "skyrim-forge-ecosystem-check", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return response.read()


def fetch_json(url: str) -> Any:
    return json.loads(_get(url).decode("utf-8-sig"))


def fetch_text(url: str) -> str:
    return _get(url).decode("utf-8-sig", errors="replace")


def _row(check: str, status: str, detail: str) -> dict[str, str]:
    return {"check": check, "status": status, "detail": detail}


def local_checks(root: Path) -> list[dict[str, str]]:
    rows = []
    sources = {}
    for name, pattern in (("skyrim_forge/version.py", r'^VERSION\s*=\s*"([^"]+)"'),
                          ("CURRENT.txt", r"^\s*([0-9]+\.[0-9]+\.[0-9]+)\s*$"),
                          ("VERSION.txt", r"^Skyrim Forge ([0-9]+\.[0-9]+\.[0-9]+)")):
        found = re.search(pattern, (root / name).read_text(encoding="utf-8"), re.M)
        sources[name] = found.group(1) if found else None
    bad = {name: value for name, value in sources.items() if value != VERSION}
    rows.append(_row("local.version_sources", "PASS" if not bad else "DRIFT",
                     f"all sources say {VERSION}" if not bad else f"mismatched: {bad}"))

    pack = json.loads((root / "integrations" / "skyrim-pack" / "PACK.json").read_text(encoding="utf-8"))
    listed = set(pack.get("skills", []))
    on_disk = {path.name for path in (root / "integrations" / "skyrim-pack" / "skills").iterdir() if path.is_dir()}
    claims = {int(value) for value in re.findall(r"(\d+)-skill", (root / "README.md").read_text(encoding="utf-8"))}
    pack_ok = listed == on_disk and claims == {len(on_disk)}
    rows.append(_row("local.pack", "PASS" if pack_ok else "DRIFT",
                     f"{len(on_disk)} skills on disk, {len(listed)} listed, README claims {sorted(claims) or 'none'}"))

    installed = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Skyrim-Tools" / "Skyrim-Forge" / "VERSION.txt"
    if installed.is_file():
        live = re.search(r"([0-9]+\.[0-9]+\.[0-9]+)", installed.read_text(encoding="utf-8"))
        live_version = live.group(1) if live else "unknown"
        rows.append(_row("local.installed", "PASS" if live_version == VERSION else "INFO",
                         f"live install is {live_version}, source is {VERSION}"))
    else:
        rows.append(_row("local.installed", "SKIP", f"no live install at {installed}"))
    return rows


def reverse_kit_checks(root: Path) -> list[dict[str, str]]:
    """Validate the local Reverse THIS! receipts Forge binds to, when they exist."""
    pointer = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "ReverseThis" / "kit.json"
    if not pointer.is_file():
        return [_row("reverse.kit", "SKIP", f"no Reverse THIS! receipt at {pointer}")]
    try:
        kit = json.loads(pointer.read_text(encoding="utf-8-sig"))
        manifest_path = Path(kit["installed_json"])
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        problems = []
        if not kit.get("kit_root") or not manifest_path.is_file():
            problems.append("kit.json lacks kit_root or installed_json")
        if manifest.get("schema") != 1:
            problems.append(f"installed.json schema is {manifest.get('schema')!r}, Forge reads 1")
        if Path(manifest.get("kit_root", "")).resolve() != Path(kit.get("kit_root", "")).resolve():
            problems.append("installed.json kit_root does not match kit.json")
        for tool in ("directxtex", "7zip"):
            record = manifest.get("tools", {}).get(tool)
            if not record or not record.get("dir"):
                problems.append(f"installed.json has no {tool} record with a dir")
        detail = f"kit {manifest.get('kit_version', 'unknown')} at {kit.get('kit_root')}"
        return [_row("reverse.kit", "PASS" if not problems else "DRIFT", detail if not problems else "; ".join(problems))]
    except (OSError, ValueError, KeyError) as exc:
        return [_row("reverse.kit", "DRIFT", f"receipt is unreadable: {type(exc).__name__}: {exc}")]


def bundle_checks(fetch_json: Callable[[str], Any], fetch_text: Callable[[str], str]) -> list[dict[str, str]]:
    rows = []
    catalog_url = RAW.format(repo=BUNDLE_REPO, path="BUNDLED-TOOLS/CATALOG.json")
    try:
        catalog = fetch_json(catalog_url)
        component = next((item for item in catalog.get("components", []) if item.get("id") == "skyrim-forge"), None)
        if component is None:
            rows.append(_row("bundle.catalog", "DRIFT", "the bundle catalog has no skyrim-forge component"))
        else:
            problems = []
            github = component.get("github", {})
            if f"{github.get('owner')}/{github.get('repo')}" != FORGE_REPO:
                problems.append(f"points at {github.get('owner')}/{github.get('repo')}, not {FORGE_REPO}")
            if component.get("install") != "latest-release":
                problems.append(f"install is {component.get('install')!r}, not 'latest-release'")
            minimum = str(component.get("min_version", "0"))
            if tuple(map(int, minimum.split("."))) > tuple(map(int, VERSION.split("."))):
                problems.append(f"min_version {minimum} is above this release {VERSION}")
            template = component.get("asset_template", "")
            if template.format(version=VERSION) != f"Skyrim-Forge-{VERSION}.zip":
                problems.append(f"asset_template {template!r} does not name Skyrim-Forge-{VERSION}.zip")
            detail = f"min_version {minimum}, asset {template.format(version=VERSION)}, catalog {catalog.get('catalog_version', 'unknown')}"
            rows.append(_row("bundle.catalog", "PASS" if not problems else "DRIFT", detail if not problems else "; ".join(problems)))
    except (urllib.error.URLError, OSError, ValueError, KeyError) as exc:
        rows.append(_row("bundle.catalog", "UNKNOWN", f"could not read {catalog_url}: {type(exc).__name__}"))
    try:
        installer = fetch_text(RAW.format(repo=BUNDLE_REPO, path="TOOLS/Install-SkyrimForge.ps1"))
        missing = [token for token in ("SkyrimForge", "min_version", "SHA256SUMS") if token not in installer]
        rows.append(_row("bundle.installer", "PASS" if not missing else "DRIFT",
                         "installer still resolves the release, floor and checksums" if not missing else f"installer no longer mentions {missing}"))
    except (urllib.error.URLError, OSError) as exc:
        rows.append(_row("bundle.installer", "UNKNOWN", f"could not read the installer: {type(exc).__name__}"))
    return rows


def forge_release_checks(fetch_json: Callable[[str], Any]) -> list[dict[str, str]]:
    try:
        release = fetch_json(API_LATEST.format(repo=FORGE_REPO))
        tag = str(release.get("tag_name", ""))
        assets = {item.get("name") for item in release.get("assets", [])}
        wanted = f"Skyrim-Forge-{VERSION}.zip"
        problems = []
        if tag != f"v{VERSION}":
            problems.append(f"latest release is {tag or 'none'}, this tree is {VERSION}")
        for name in (wanted, "SHA256SUMS.txt"):
            if name not in assets:
                problems.append(f"release is missing {name}")
        rows = [_row("forge.release", "PASS" if not problems else "DRIFT",
                     f"{tag} carries {len(assets)} assets" if not problems else "; ".join(problems))]
    except (urllib.error.URLError, OSError, ValueError, KeyError) as exc:
        rows = [_row("forge.release", "UNKNOWN", f"could not read the release: {type(exc).__name__}")]
    try:
        installer = fetch_text(RAW.format(repo=REVERSE_REPO, path="Install-Modkit.ps1"))
        missing = [token for token in ("kit.json", "installed.json", "7zip") if token not in installer]
        rows.append(_row("reverse.installer", "PASS" if not missing else "DRIFT",
                         "owner installer still writes kit.json/installed.json with 7-Zip" if not missing else f"installer no longer mentions {missing}"))
    except (urllib.error.URLError, OSError) as exc:
        rows.append(_row("reverse.installer", "UNKNOWN", f"could not read the installer: {type(exc).__name__}"))
    try:
        latest = str(fetch_json(API_LATEST.format(repo=REVERSE_REPO)).get("tag_name", "")).lstrip("v")
        pointer = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "ReverseThis" / "kit.json"
        kit_version = ""
        if pointer.is_file():
            kit_version = str(json.loads(Path(json.loads(pointer.read_text(encoding="utf-8-sig"))["installed_json"]).read_text(encoding="utf-8-sig")).get("kit_version", ""))
        rows.append(_row("reverse.version", "PASS" if not kit_version or kit_version == latest else "INFO",
                         f"upstream {latest}, local kit {kit_version or 'not installed'}"))
    except (urllib.error.URLError, OSError, ValueError, KeyError) as exc:
        rows.append(_row("reverse.version", "UNKNOWN", f"could not compare versions: {type(exc).__name__}"))
    return rows


def run(root: Path = ROOT, offline: bool = False,
        fetch_json: Callable[[str], Any] = fetch_json, fetch_text: Callable[[str], str] = fetch_text) -> dict[str, Any]:
    checks = local_checks(root) + reverse_kit_checks(root)
    if not offline:
        checks += bundle_checks(fetch_json, fetch_text) + forge_release_checks(fetch_json)
    counts: dict[str, int] = {}
    for row in checks:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    result = "DRIFT" if counts.get("DRIFT") else "UNKNOWN" if counts.get("UNKNOWN") else "PASS"
    return {"product": "Skyrim Forge", "version": VERSION, "result": result, "counts": counts, "checks": checks,
            "rule": "Forge never copies another project's version. This check proves the contracts it actually consumes still exist and still name this release."}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Forge's bundle and Reverse THIS! contracts")
    parser.add_argument("--offline", action="store_true", help="run only checks that read this checkout and local receipts")
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    args = parser.parse_args(argv)
    report = run(offline=args.offline)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        for row in report["checks"]:
            print(f"{row['status']:<7} {row['check']}: {row['detail']}")
        print(f"\n{report['result']}: {report['counts']}")
    return 0 if report["result"] == "PASS" else 2 if report["result"] == "DRIFT" else 3


if __name__ == "__main__":
    raise SystemExit(main())
