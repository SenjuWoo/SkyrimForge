"""Typed record work through Forge's own .NET worker (workers/SkyrimForge.Records, Mutagen.Bethesda.Skyrim 0.54.4).

`worker-build` publishes it under <config dir>/worker with a receipt holding the source hash and the built exe's
SHA-256 (building runs the .NET SDK, so it needs allow_external_processes). Running the built worker is a
Forge-owned binary checked against that receipt on every call; a changed exe or stale source is refused.
Each verb sends one JSON request and reads one JSON line; override/new write only the target plugin in the workspace.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from .config import ForgeConfig
from .errors import SafetyError, ToolError, ValidationError
from .safety import require_approval, require_within
from .strictjson import load
from .tools import run_process
from .util import json_dump, sha256_file, utc_now

WORKER = "SkyrimForge.Records"


def source_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "workers" / WORKER


def worker_dir(config: ForgeConfig) -> Path:
    return config.config_path.parent / "worker" / WORKER


def worker_exe(config: ForgeConfig) -> Path:
    return worker_dir(config) / f"{WORKER}.exe"


def source_hash() -> str:
    digest = hashlib.sha256()
    for path in sorted(source_dir().glob("*")):
        if path.is_file() and path.suffix in (".cs", ".csproj", ".json"):
            digest.update(path.name.encode() + sha256_file(path).encode())
    return digest.hexdigest()


def status(config: ForgeConfig) -> dict[str, Any]:
    exe, receipt_path = worker_exe(config), worker_dir(config) / "worker.receipt.json"
    receipt = load(receipt_path) if receipt_path.is_file() else {}
    built = exe.is_file()
    source_present = source_dir().is_dir()
    return {"result": "PASS" if built and receipt else "INCOMPLETE", "built": built, "path": str(exe),
            "stale": (receipt.get("source_sha256") != source_hash()) if built and receipt and source_present else None,
            "exe_matches_receipt": bool(built and receipt and sha256_file(exe) == receipt.get("exe_sha256")),
            "dotnet": bool(shutil.which("dotnet")), "mutagen": receipt.get("mutagen"),
            "hint": None if built else "forge worker-build --approve (needs the .NET 10 SDK and allow_external_processes)"}


def build(config: ForgeConfig, *, approved: bool) -> dict[str, Any]:
    require_approval(approved, "records worker build")
    if not config.allow_external_processes:
        raise SafetyError("Building the worker runs the .NET SDK; enable safety.allow_external_processes first")
    dotnet = shutil.which("dotnet")
    if not dotnet:
        raise ToolError("the .NET SDK (dotnet) is not on PATH; install the .NET 10 SDK")
    project = source_dir() / f"{WORKER}.csproj"
    if not project.is_file():
        raise ToolError(f"worker source missing: {project}")
    out = worker_dir(config)
    process = run_process(Path(dotnet), ["publish", str(project), "-c", "Release", "-o", str(out), "--nologo", "-p:RestoreLockedMode=true"],
                          cwd=source_dir(), timeout_seconds=1800)
    if process["returncode"] != 0 or not worker_exe(config).is_file():
        raise ToolError("worker build failed: " + (process["stdout"] + process["stderr"])[-1200:])
    receipt = {"source_sha256": source_hash(), "exe_sha256": sha256_file(worker_exe(config)), "built": utc_now()}
    json_dump(out / "worker.receipt.json", receipt)
    version = call(config, {"verb": "version"})
    receipt["mutagen"] = version.get("mutagen")
    json_dump(out / "worker.receipt.json", receipt)
    return {"result": "PASS", "path": str(worker_exe(config)), "worker": version.get("worker"), "mutagen": version.get("mutagen")}


def call(config: ForgeConfig, request: dict[str, Any], *, timeout: int = 3600) -> dict[str, Any]:
    exe, receipt_path = worker_exe(config), worker_dir(config) / "worker.receipt.json"
    if not exe.is_file() or not receipt_path.is_file():
        raise ToolError("records worker not built; run forge worker-build --approve")
    if sha256_file(exe) != load(receipt_path).get("exe_sha256"):
        raise SafetyError("records worker exe differs from its build receipt; rebuild it with forge worker-build --approve")
    process = run_process(exe, ["-"], cwd=worker_dir(config), timeout_seconds=timeout, stdin_text=json.dumps(request))
    lines = [line for line in process["stdout"].splitlines() if line.strip()]
    if not lines:
        raise ToolError(f"records worker gave no output: {process['stderr'][-400:]}")
    try:
        result = json.loads(lines[-1])
    except ValueError as exc:
        raise ToolError("records worker output is not JSON: " + lines[-1][-300:]) from exc
    if process["returncode"] == 2:
        raise ValidationError(result.get("error", "worker failure") + (f" ({result['fix']})" if result.get("fix") else ""))
    if process["returncode"] == 3:
        raise ToolError(result.get("error", "worker exception"))
    result["result"] = "PASS" if result.pop("ok", True) else "FAIL"
    return result


def load_order_paths(order: dict[str, Any]) -> list[str]:
    return [str(plugin.path) for plugin in order["plugins"]]


def write_target(config: ForgeConfig, target: str, approved: bool, action: str) -> str:
    require_approval(approved, action)
    path = require_within(Path(target), config.workspace_root)
    if path.suffix.casefold() not in (".esp", ".esm", ".esl"):
        raise ValidationError("target must be an .esp, .esm or .esl in the workspace")
    return str(path)


def find_index(path: Path, text: str, *, limit: int = 50) -> dict[str, Any]:
    if not path.is_file():
        raise ValidationError(f"no record index at {path}; run forge records-index first")
    needle, rows = text.casefold(), []
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if needle in (row.get("edid") or "").casefold():
                rows.append(row)
                if len(rows) >= limit:
                    break
    return {"result": "PASS", "index": str(path), "count": len(rows), "results": rows}
