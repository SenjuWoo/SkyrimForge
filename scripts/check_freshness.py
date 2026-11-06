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
import urllib.error
import urllib.request
from urllib.parse import urlparse
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


def _go_pin(root: Path = ROOT) -> str:
    text = (root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    match = re.search(r'go-version:\s*"([\d.]+)"', text)
    return match.group(1) if match else "unknown"


def vcpkg_pins(root: Path = ROOT) -> dict[str, str]:
    """The registry baseline and the SDK checkout are different pins; read both."""
    lock = json.loads((root / "references/NATIVE-SOURCE-LOCK.json").read_text(encoding="utf-8"))
    sdk_lock = json.loads((root / "references/SDK-LOCK.json").read_text(encoding="utf-8"))
    sdk = next((item for item in sdk_lock.get("sdks", []) if item.get("id") == "vcpkg"), {})
    return {"baseline": lock.get("commonlibsse_ng", {}).get("vcpkg_baseline", ""),
            "sdk_ref": sdk.get("ref", ""), "sdk_commit": sdk.get("commit", "")}


def pins(root: Path = ROOT) -> dict[str, dict[str, str]]:
    housecarl = json.loads((root / "integrations/skyrim-pack/housecarl-pin.json").read_text(encoding="utf-8"))
    lock = json.loads((root / "references/NATIVE-SOURCE-LOCK.json").read_text(encoding="utf-8"))
    commonlib = lock["commonlibsse_ng"]
    vcpkg = vcpkg_pins(root)
    protocol = re.search(r'MODERN_PROTOCOL = "([^"]+)"',
                         (root / "skyrim_forge/mcp_server.py").read_text(encoding="utf-8")).group(1)
    return {
        "forge": {"pinned": _version(), "kind": "product"},
        "houseCARL": {"pinned": housecarl["version"], "kind": "installer", "sha256": housecarl["sha256"]},
        "CommonLibSSE-NG": {"pinned": commonlib.get("tag") or "unknown",
                            "commit": commonlib.get("commit", ""), "kind": "source SDK"},
        "vcpkg": {"pinned": vcpkg["baseline"], "sdk_ref": vcpkg["sdk_ref"],
                  "sdk_commit": vcpkg["sdk_commit"], "kind": "registry baseline commit"},
        "Go": {"pinned": _go_pin(root), "kind": "toolchain"},
        "MCP": {"pinned": protocol, "kind": "protocol"},
    }


def _origin(url: str) -> tuple[str, str | None, int]:
    parsed = urlparse(url)
    return parsed.scheme, parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80)


class _SameOriginRedirect(urllib.request.HTTPRedirectHandler):
    """Never forward Authorization to another origin."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if _origin(req.full_url) != _origin(newurl):
            raise urllib.error.HTTPError(newurl, 403, "cross-origin redirect refused", headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_OPENER = urllib.request.build_opener(_SameOriginRedirect)


def _get_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                                   "User-Agent": "skyrim-forge-freshness"})
    scheme, host, port = _origin(url)
    token = os.environ.get("GITHUB_TOKEN")
    if token and scheme == "https" and host == "api.github.com" and port == 443:
        request.add_header("Authorization", f"Bearer {token}")
    with _OPENER.open(request, timeout=15) as response:
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
    try:
        release = _get_json(GITHUB.format(repo="SenjuWoo/SkyrimForge"))
        if release.get("html_url", "").startswith("https://github.com/SenjuWoo/SkyrimForge/releases/"):
            found["forge"] = {"latest": str(release.get("tag_name", "")).lstrip("v"),
                              "published": str(release.get("published_at", ""))[:10],
                              "url": release.get("html_url", "")}
        else:
            found["forge"] = {"latest": "unknown", "malformed": "release URL did not match the repository"}
    except Exception as exc:  # noqa: BLE001
        found["forge"] = {"latest": "unknown", "error": type(exc).__name__}
    found["MCP"] = {"latest": "unknown", "not_checked": "no machine-readable upstream endpoint is consulted"}
    return found


def classify(name: str, pinned: str, up: dict | None) -> tuple[str, str]:
    """Return (status, reason) without guessing when data is missing."""
    if name == "vcpkg":
        if not re.fullmatch(r"[0-9a-f]{40}", str(pinned or "")):
            return "UNKNOWN", "vcpkg baseline pin is missing or malformed"
        return "PINNED_COMMIT", "registry baseline commit; not comparable to a release tag"
    if name == "MCP":
        return "NOT_CHECKED", "the protocol revision has no release feed this report reads"
    if up is None:
        return "NOT_CHECKED", "offline report"
    if up.get("error"):
        return "ERROR", f"upstream lookup failed: {up['error']}"
    if up.get("malformed"):
        return "MALFORMED", up["malformed"]
    latest = str(up.get("latest") or "")
    if not latest or latest == "unknown":
        return "UNKNOWN", "upstream did not report a comparable version"
    if latest.lstrip("v") == pinned.lstrip("v"):
        return "CURRENT", ""
    return "DRIFT", f"upstream {latest} differs from pin {pinned}"


def report(online: bool) -> dict:
    pinned = pins()
    latest = upstream() if online else {}
    items = []
    for name, pin in pinned.items():
        up = latest.get(name)
        status, reason = classify(name, pin["pinned"], up)
        items.append({"name": name, "pinned": pin["pinned"], "latest": (up or {}).get("latest", "unknown"),
                      "status": status, "reason": reason,
                      "published": (up or {}).get("published", ""), "url": (up or {}).get("url", ""),
                      "gate": GATES.get(name, "Review the upstream change before adopting it."),
                      "kind": pin["kind"], "sdk_ref": pin.get("sdk_ref", ""),
                      "sdk_commit": pin.get("sdk_commit", "")})
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
