"""Publish release files without replacing bytes that downstream users may have pinned.

Requires the authenticated GitHub CLI; failures are recorded in the CI job log.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from urllib.parse import quote


# Only an actual HTTP 404 permits creation; auth/network failures must stop publication.
def release_for_tag(tag: str) -> dict | None:
    result = subprocess.run(
        ["gh", "api", "--include", f"repos/{{owner}}/{{repo}}/releases/tags/{quote(tag, safe='')}"],
        capture_output=True,
    )
    headers, separator, body = result.stdout.replace(b"\r\n", b"\n").partition(b"\n\n")
    line = headers.splitlines()[0].split() if headers else []
    status = int(line[1]) if len(line) > 1 and line[0].startswith(b"HTTP/") and line[1].isdigit() else None
    if status == 404:
        return None
    if result.returncode or status != 200 or not separator:
        raise RuntimeError(f"Release lookup failed (HTTP {status or 'unavailable'}); no assets changed")
    return json.loads(body)


# Verify every existing asset before adding missing files, so failed reruns cannot rewrite a release.
def publish(tag: str, directory: Path) -> None:
    paths = sorted(directory.resolve(strict=True).iterdir())
    if not paths or any(not path.is_file() or path.is_symlink() or "#" in path.name for path in paths):
        raise RuntimeError("Release assets must be a nonempty directory of regular files without '#' in their names")
    local = {path.name: path for path in paths}
    release = release_for_tag(tag)
    if release is None:
        subprocess.run(["gh", "release", "create", "--verify-tag", "--generate-notes", "--", tag, *map(str, paths)], check=True)
        return

    release_id = release["id"]
    if type(release_id) is not int or release_id <= 0:
        raise RuntimeError("Invalid release ID; no assets changed")
    # Paginate the dedicated endpoint so a truncated embedded asset list cannot hide a mismatch.
    result = subprocess.run(
        ["gh", "api", f"repos/{{owner}}/{{repo}}/releases/{release_id}/assets", "--paginate", "--slurp"],
        capture_output=True, check=True,
    )
    pages = json.loads(result.stdout)
    if not isinstance(pages, list) or any(not isinstance(page, list) for page in pages):
        raise RuntimeError("Invalid release asset response; no assets changed")
    seen = set()
    for page in pages:
        for asset in page:
            name = asset["name"]
            if name not in local or name in seen:
                raise RuntimeError(f"Unexpected or duplicate release asset: {name}; no assets changed")
            seen.add(name)
            data = local[name].read_bytes()
            digest = "sha256:" + hashlib.sha256(data).hexdigest()
            if asset.get("state") != "uploaded" or asset["size"] != len(data):
                raise RuntimeError(f"Release asset state/size mismatch: {name}; no assets changed")
            if asset.get("digest") is not None and asset["digest"] != digest:
                raise RuntimeError(f"Release asset digest mismatch: {name}; no assets changed")
            asset_id = asset["id"]
            if type(asset_id) is not int or asset_id <= 0:
                raise RuntimeError(f"Invalid release asset ID: {name}; no assets changed")
            result = subprocess.run(
                ["gh", "api", f"repos/{{owner}}/{{repo}}/releases/assets/{asset_id}", "--header", "Accept: application/octet-stream"],
                capture_output=True, check=True,
            )
            if result.stdout != data:
                raise RuntimeError(f"Release asset bytes mismatch: {name}; no assets changed")
    missing = [str(path) for name, path in local.items() if name not in seen]
    if missing:
        subprocess.run(["gh", "release", "upload", "--", tag, *missing], check=True)
    print(f"Verified {len(seen)} existing release assets; uploaded {len(missing)} missing assets")


# Keep the workflow invocation small and make the same safety check available locally.
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag")
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    publish(args.tag, args.directory)


if __name__ == "__main__":
    main()
