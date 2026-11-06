"""Report pinned vs upstream versions. Read-only: it never edits a pin or a release.

Offline by default so it can run in any checkout; `--online` asks the official
GitHub/Go endpoints. Output is JSON so a human, CI or an agent can read it.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GITHUB = "https://api.github.com/repos/{repo}/releases/latest"
GOINDEX = "https://go.dev/dl/?mode=json"

# What a newer release would need before it may be adopted. Kept here so the
# report carries the decision, not just a version number.
GATES = {
    "houseCARL": "Install the release asset, verify SHA-256, then run Install-HouseCarl.ps1 -CheckOnly.",
    "CommonLibSSE-NG": "A representative scaffold must build with pinned MSVC/vcpkg; otherwise keep the pin.",
    "vcpkg": "A full native rebuild plus the reproducibility gate must match byte-for-byte.",
    "Go": "Rebuild both helpers and pass the reproducible repository gate on the pinned toolchain.",
}


def _version() -> str:
    return (ROOT / "VERSION.txt").read_text(encoding="utf-8").split()[-1]


def _go_pin() -> str:
    text = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    match = re.search(r'go-version:\s*"([\d.]+)"', text)
    return match.group(1) if match else "unknown"


def pins() -> dict[str, dict[str, str]]:
    housecarl = json.loads((ROOT / "integrations/skyrim-pack/housecarl-pin.json").read_text(encoding="utf-8"))
    lock = json.loads((ROOT / "references/NATIVE-SOURCE-LOCK.json").read_text(encoding="utf-8"))
    commonlib = lock["commonlibsse_ng"]
    return {
        "forge": {"pinned": _version(), "kind": "product"},
        "houseCARL": {"pinned": housecarl["version"], "kind": "installer", "sha256": housecarl["sha256"]},
        "CommonLibSSE-NG": {"pinned": commonlib.get("tag") or "unknown",
                            "commit": commonlib.get("commit", ""), "kind": "source SDK"},
        "vcpkg": {"pinned": lock.get("vcpkg_baseline", "unknown"), "kind": "dependency baseline"},
        "Go": {"pinned": _go_pin(), "kind": "toolchain"},
        "MCP": {"pinned": "2026-07-28", "kind": "protocol"},
    }


def _get_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                                   "User-Agent": "skyrim-forge-freshness"})
    token = os.environ.get("GITHUB_TOKEN")
    if token and "api.github.com" in url:
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def upstream() -> dict[str, dict[str, str]]:
    found: dict[str, dict[str, str]] = {}
    for name, repo in (("houseCARL", "Avick3110/houseCARL"),
                       ("CommonLibSSE-NG", "alandtse/CommonLibSSE-NG"),
                       ("vcpkg", "microsoft/vcpkg")):
        try:
            release = _get_json(GITHUB.format(repo=repo))
            found[name] = {"latest": str(release.get("tag_name", "")).lstrip("v"),
                           "published": str(release.get("published_at", ""))[:10],
                           "url": release.get("html_url", "")}
        except Exception as exc:  # noqa: BLE001 - a failed lookup is reported, not hidden
            found[name] = {"latest": "unknown", "error": type(exc).__name__}
    try:
        go = _get_json(GOINDEX)
        stable = next(item["version"] for item in go if item.get("stable"))
        found["Go"] = {"latest": stable.lstrip("go"), "published": "", "url": "https://go.dev/dl/"}
    except Exception as exc:  # noqa: BLE001
        found["Go"] = {"latest": "unknown", "error": type(exc).__name__}
    found["forge"] = {"latest": "unknown", "url": "https://github.com/SenjuWoo/SkyrimForge/releases"}
    found["MCP"] = {"latest": "2026-07-28", "url": "https://blog.modelcontextprotocol.io/posts/2026-07-28/"}
    return found


def report(online: bool) -> dict:
    pinned = pins()
    latest = upstream() if online else {}
    items = []
    for name, pin in pinned.items():
        up = latest.get(name, {})
        newest = up.get("latest", "unknown")
        if newest == "unknown":
            status = "UNKNOWN"
        elif newest.lstrip("v") == pin["pinned"].lstrip("v"):
            status = "CURRENT"
        else:
            status = "DRIFT"
        items.append({"name": name, "pinned": pin["pinned"], "latest": newest, "status": status,
                      "published": up.get("published", ""), "url": up.get("url", ""),
                      "gate": GATES.get(name, "Review the upstream change before adopting it."),
                      "kind": pin["kind"]})
    return {"schema": "skyrim-forge-freshness/1",
            "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "online": online, "items": items,
            "note": "Read-only. This report never changes a pin, installs anything or triggers a release."}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--online", action="store_true", help="ask GitHub and go.dev for the latest releases")
    args = parser.parse_args(argv)
    result = report(args.online)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
