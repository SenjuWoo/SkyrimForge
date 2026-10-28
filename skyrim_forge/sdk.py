from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import sys
from pathlib import Path
from typing import Any

from .config import ForgeConfig
from .errors import SafetyError, ToolError, ValidationError
from .safety import require_approval
from .util import sha256_file, truncate

SCHEMA = "skyrim-forge-sdk-lock/1"
ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,47}$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SCRIPT_RE = re.compile(r"^[A-Za-z0-9_.-]+\.(bat|cmd)$")
GIT_TIMEOUT = 1800


def lock_path() -> Path:
    return Path(__file__).resolve().parent / "references" / "SDK-LOCK.json"


def _relative(value: Any, label: str) -> str:
    path = Path(str(value))
    if not value or path.is_absolute() or ".." in path.parts or "\\" in str(value):
        raise ValidationError(f"{label} must be a safe relative path")
    return str(value)


def load_lock(path: Path | None = None) -> dict[str, Any]:
    lock = json.loads((path or lock_path()).read_text(encoding="utf-8"))
    if lock.get("schema") != SCHEMA:
        raise ValidationError("Unsupported Forge SDK lock schema")
    seen: set[str] = set()
    for entry in lock["sdks"]:
        ident = entry.get("id", "")
        if not ID_RE.fullmatch(ident) or ident in seen:
            raise ValidationError(f"Invalid or duplicate SDK id: {ident!r}")
        seen.add(ident)
        if not str(entry.get("repository", "")).startswith("https://github.com/"):
            raise ValidationError(f"{ident}: repository must be an https://github.com/ URL")
        if not SHA_RE.fullmatch(str(entry.get("commit", ""))):
            raise ValidationError(f"{ident}: commit must be a full lowercase 40-hex SHA")
        _relative(entry.get("probe"), f"{ident}: probe")
        boot = entry.get("bootstrap")
        if boot:
            if not SCRIPT_RE.fullmatch(str(boot.get("script", ""))):
                raise ValidationError(f"{ident}: bootstrap script must be a plain .bat/.cmd file name")
            _relative(boot.get("artifact"), f"{ident}: bootstrap artifact")
    return lock


# shortcut: sibling of the tool vault instead of its own config key; add one if users need to place it apart.
def sdk_root(config: ForgeConfig) -> Path:
    return config.tool_vault_root.parent / "sdk-vault"


def _git(args: list[str], cwd: Path | None = None) -> str:
    git = shutil.which("git")
    if not git:
        raise ToolError("git was not found on PATH; install Git for Windows")
    done = subprocess.run(
        [git, "-c", "core.longpaths=true", "-c", "advice.detachedHead=false", *args],
        cwd=cwd, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        capture_output=True, text=True, timeout=GIT_TIMEOUT, check=False,
    )
    if done.returncode:
        raise ToolError(f"git {args[0]} failed: {truncate(done.stderr.strip(), 2000)}")
    return done.stdout.strip()


def _rmtree(path: Path) -> None:
    def unlock(function, target, _error):  # read-only .git objects block rmtree on Windows
        os.chmod(target, stat.S_IWRITE)
        function(target)
    shutil.rmtree(path, **({"onexc": unlock} if sys.version_info >= (3, 12) else {"onerror": unlock}))


def _state(entry: dict[str, Any], dest: Path) -> tuple[str, str]:
    if not dest.is_dir():
        return "absent", ""
    if not (dest / ".git").exists():  # without this git would walk up and describe a parent repository
        return "invalid", ""
    head = _git(["rev-parse", "HEAD"], dest)
    if head != entry["commit"]:
        return "mismatch", head
    if _git(["status", "--porcelain", "--untracked-files=no"], dest):
        return "modified", head
    if not (dest / entry["probe"]).exists():
        return "incomplete", head
    return "current", head


def _row(entry: dict[str, Any], dest: Path) -> dict[str, Any]:
    try:
        state, head = _state(entry, dest)
    except (ToolError, subprocess.TimeoutExpired) as error:
        state, head = "unknown", str(error)
    row = {"id": entry["id"], "state": state, "path": str(dest), "ref": entry["ref"], "pinned_commit": entry["commit"], "actual_commit": head, "default": bool(entry["default"]), "license": entry["license"], "role": entry["role"]}
    if entry.get("bootstrap"):
        artifact = dest / entry["bootstrap"]["artifact"]
        row.update({"artifact": str(artifact), "artifact_present": artifact.is_file()})
    return row


def sdk_rows(config: ForgeConfig, lock: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    root = sdk_root(config)
    return [_row(entry, root / entry["id"]) for entry in (lock or load_lock())["sdks"]]


def msvc_install_path() -> str:
    base = os.environ.get("ProgramFiles(x86)")
    vswhere = Path(base, "Microsoft Visual Studio", "Installer", "vswhere.exe") if base else None
    if not vswhere or not vswhere.is_file():
        return ""
    done = subprocess.run([str(vswhere), "-latest", "-products", "*", "-requires", "Microsoft.VisualStudio.Component.VC.Tools.x86.x64", "-property", "installationPath"], capture_output=True, text=True, timeout=30, check=False)
    return done.stdout.strip()


def require_current(config: ForgeConfig, sdk_id: str, lock: dict[str, Any] | None = None) -> Path:
    """Return the vault directory only when it is the clean pinned commit; builds must not consume anything else."""
    entry = next((item for item in (lock or load_lock())["sdks"] if item["id"] == sdk_id), None)
    if entry is None:
        raise ValidationError(f"Unknown SDK id: {sdk_id}")
    dest = sdk_root(config) / sdk_id
    state, _ = _state(entry, dest)
    if state != "current":
        raise SafetyError(f"SDK {sdk_id} is {state}, not the clean pinned commit; run: forge sdk-install {sdk_id} --approve")
    return dest


def sdk_status(config: ForgeConfig, lock: dict[str, Any] | None = None) -> dict[str, Any]:
    host = {name: shutil.which(name) or "" for name in ("git", "cmake", "ninja", "xmake", "vcpkg")}
    return {"result": "PASS", "sdk_vault_root": str(sdk_root(config)), "sdks": sdk_rows(config, lock), "host_tools": host, "msvc_cpp_tools": msvc_install_path(), "public_binary_bundling": "disabled"}


def _fetch(entry: dict[str, Any], dest: Path) -> None:
    # A unique owned stage keeps retries and concurrent fetches away from one another's recovery data.
    partial = Path(tempfile.mkdtemp(prefix=f".{dest.name}.", suffix=".partial", dir=dest.parent))
    try:
        _git(["init", "--quiet"], partial)
        _git(["remote", "add", "origin", entry["repository"]], partial)
        _git(["fetch", "--quiet", "--depth", "1", "origin", entry["commit"]], partial)
        _git(["checkout", "--quiet", "--detach", "FETCH_HEAD"], partial)
        if entry["submodules"]:
            _git(["submodule", "update", "--init", "--recursive", "--depth", "1", "--quiet"], partial)
        head = _git(["rev-parse", "HEAD"], partial)
        if head != entry["commit"]:
            raise ValidationError(f"{entry['id']}: fetched {head}, expected {entry['commit']}")
        if dest.exists():
            raise ToolError(f"{entry['id']}: destination appeared during fetch; preserved it without replacement")
        partial.rename(dest)
    except BaseException:
        _rmtree(partial)
        raise


def _bootstrap(entry: dict[str, Any], dest: Path) -> dict[str, Any]:
    spec = entry["bootstrap"]
    artifact = dest / spec["artifact"]
    if artifact.is_file():
        return {"artifact": str(artifact), "sha256": sha256_file(artifact), "bootstrapped": False}
    if os.name != "nt":
        raise ToolError(f"{entry['id']}: the bootstrap script is Windows-only")
    # ".\" is required: cmd skips the current directory when NoDefaultCurrentDirectoryInExePath is set.
    done = subprocess.run(["cmd.exe", "/c", ".\\" + spec["script"], *spec.get("args", [])], cwd=dest, env={**os.environ, "VCPKG_DISABLE_METRICS": "1"}, capture_output=True, text=True, timeout=GIT_TIMEOUT, check=False)
    if done.returncode or not artifact.is_file():
        raise ToolError(f"{entry['id']}: bootstrap failed: {truncate((done.stderr or done.stdout).strip(), 2000)}")
    return {"artifact": str(artifact), "sha256": sha256_file(artifact), "bootstrapped": True}


def _select(lock: dict[str, Any], ids: list[str], everything: bool) -> list[dict[str, Any]]:
    known = {entry["id"]: entry for entry in lock["sdks"]}
    unknown = sorted(set(ids) - set(known))
    if unknown:
        raise ValidationError(f"Unknown SDK id(s) {unknown}; choose from {sorted(known)}")
    if everything:
        return list(known.values())
    return [known[ident] for ident in ids] if ids else [entry for entry in known.values() if entry["default"]]


def sdk_install(config: ForgeConfig, ids: list[str], *, approved: bool, everything: bool = False, bootstrap: bool = False, lock: dict[str, Any] | None = None) -> dict[str, Any]:
    require_approval(approved, "download of pinned SDK sources into the Forge SDK vault")
    root = sdk_root(config)
    root.mkdir(parents=True, exist_ok=True)
    results = []
    for entry in _select(lock or load_lock(), ids, everything):
        dest = root / entry["id"]
        result: dict[str, Any] = {"id": entry["id"], "path": str(dest)}
        try:
            state, head = _state(entry, dest)
            if state == "absent":
                _fetch(entry, dest)
                result.update(result="PASS", action="fetched", commit=entry["commit"])
            elif state == "current":
                result.update(result="PASS", action="kept", commit=head)
            else:  # never overwrite: the directory may hold the user's edits or another pin
                result.update(result="FAIL", action="refused", state=state, reason="existing vault directory is not the clean pinned commit; inspect or remove it yourself")
            if result["result"] == "PASS" and bootstrap and entry.get("bootstrap"):
                result.update(_bootstrap(entry, dest))
        except (ToolError, ValidationError, subprocess.TimeoutExpired, OSError) as error:
            result.update(result="FAIL", action="failed", reason=str(error))
        results.append(result)
    failed = [item["id"] for item in results if item["result"] != "PASS"]
    return {"result": "INCOMPLETE" if failed else "PASS", "sdk_vault_root": str(root), "results": results, "failed": failed, "next": "Pin the bootstrapped vcpkg with: forge tool-configure vcpkg <vcpkg.exe> --approve"}
