"""Keep a Forge installation healthy: prune Forge-owned leftovers, detect moved
game/manager roots, and report the self-test.

The installer and updater create backups, spill files and sandbox runs that are
useful for a week and pure clutter afterwards. This module removes only paths
Forge itself can prove it owns:

  * <workspace>/.forge/spills/*.json older than -days
  * <workspace>/.forge/vfs-sandbox/* older than -days
  * <provider>/.skyrim-forge-skill-work/backup-<name>-<32 hex>, all but the newest -keep

It also compares the configured paths with the machine: a missing Skyrim Data,
Vortex staging, MO2 instance or workspace is reported with a discovered
candidate, and --fix-roots can write that candidate back (with a config backup).
Nothing outside those patterns is ever deleted.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from .config import ForgeConfig, save_config
from .errors import SafetyError, ValidationError
from .util import utc_now
from .version import VERSION

BACKUP_NAME = re.compile(r"^backup-.+-[0-9a-f]{32}$")
PROVIDER_HOMES = (
    Path.home() / ".claude", Path.home() / ".agents", Path.home() / ".grok",
    Path.home() / ".kimi", Path.home() / ".codex", Path.home() / ".hermes",
    Path(os.environ.get("LOCALAPPDATA", "")) / "hermes",
)
ROOT_KEYS = ("workspace_root", "skyrim_data", "vortex_staging", "mo2_profiles_root", "tools_root")


def _age_days(path: Path) -> float:
    return (datetime.now(timezone.utc) - datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)).total_seconds() / 86400


def _owned(path: Path, parent: Path) -> bool:
    try:
        resolved, base = path.resolve(), parent.resolve()
    except OSError:
        return False
    return resolved != base and resolved.is_relative_to(base) and not path.is_symlink()


def _stale_children(parent: Path, days: int, pattern: str = "*") -> list[Path]:
    if not parent.is_dir():
        return []
    return sorted((p for p in parent.glob(pattern) if _owned(p, parent) and _age_days(p) >= days),
                  key=lambda p: p.stat().st_mtime)


def _provider_backups(keep: int, homes: Iterable[Path] | None = None) -> tuple[list[Path], int]:
    """Return provider skill backups beyond the newest `keep`, per provider."""
    removable: list[Path] = []
    kept = 0
    for home in homes or PROVIDER_HOMES:
        work = home / ".skyrim-forge-skill-work"
        if not work.is_dir():
            continue
        backups = sorted((p for p in work.iterdir() if p.is_dir() and BACKUP_NAME.match(p.name)),
                         key=lambda p: p.stat().st_mtime, reverse=True)
        kept += min(keep, len(backups))
        for old in backups[keep:]:
            if _owned(old, work):
                removable.append(old)
    return removable, kept


def _steam_libraries(steam_roots: Iterable[Path] | None = None) -> list[Path]:
    """Every Steam library folder that holds a Skyrim Special Edition Data dir."""
    found: list[Path] = []
    roots = list(steam_roots or (Path("C:/Program Files (x86)/Steam"), Path("C:/Program Files/Steam")))
    for root in roots:
        vdf = root / "steamapps" / "libraryfolders.vdf"
        libraries = [root]
        if vdf.is_file():
            text = vdf.read_text(encoding="utf-8", errors="replace")
            libraries += [Path(match) for match in re.findall(r'"path"\s+"([^"]+)"', text)]
        for library in libraries:
            data = library / "steamapps" / "common" / "Skyrim Special Edition" / "Data"
            if data.is_dir():
                found.append(data)
    return found


def _candidate_options(steam_roots: Iterable[Path] | None = None) -> dict[str, list[Path]]:
    """Every plausible replacement per root.

    More than one option is reported as ambiguous rather than silently taking the
    first Steam library, which is how a multi-library machine ends up pointed at
    the wrong Data folder.
    """
    appdata = Path(os.environ.get("APPDATA", ""))
    options: dict[str, list[Path]] = {}
    steam = [path for path in _steam_libraries(steam_roots) if (path / "Skyrim.esm").is_file()]
    if steam:
        options["skyrim_data"] = steam
    vortex = appdata / "Vortex" / "skyrimse" / "mods"
    if vortex.is_dir():
        options["vortex_staging"] = [vortex]
    workspace = Path(__file__).resolve().parents[1] / "Workspaces"
    if workspace.is_dir():
        options["workspace_root"] = [workspace]
    return options


def root_report(config: ForgeConfig, steam_roots: Iterable[Path] | None = None) -> list[dict[str, Any]]:
    options = _candidate_options(steam_roots)
    rows = []
    for key in ROOT_KEYS:
        current = getattr(config, key, None)
        if current is None:
            continue
        path = Path(current)
        row = {"key": key, "configured": str(path), "status": "OK" if path.exists() else "MISSING"}
        if row["status"] == "MISSING":
            found = options.get(key, [])
            if len(found) == 1:
                row.update(status="MOVED", candidate=str(found[0]))
            elif len(found) > 1:
                row.update(status="AMBIGUOUS", candidates=[str(item) for item in found])
        rows.append(row)
    return rows


SCHEDULE_TASK = "SkyrimForge-Maintain"
SCHEDULE_MARKER = "Skyrim Forge check-only maintenance"
DAYS = {"SUN": "Sunday", "MON": "Monday", "TUE": "Tuesday", "WED": "Wednesday",
        "THU": "Thursday", "FRI": "Friday", "SAT": "Saturday"}


def _ps(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", script],
                          capture_output=True, text=True, timeout=60)


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _task_info() -> dict[str, Any] | None:
    """Machine-readable task state, or None when it does not exist.

    Get-ScheduledTask returns objects, so this does not depend on localized
    column labels the way `schtasks /V /FO LIST` did.
    """
    script = (
        "$ErrorActionPreference='Stop';"
        f"$t=Get-ScheduledTask -TaskName {_ps_quote(SCHEDULE_TASK)} -ErrorAction SilentlyContinue;"
        "if($null -eq $t){'null'}else{$t|Select-Object TaskName,Description,"
        "@{n='Execute';e={$_.Actions[0].Execute}},@{n='Arguments';e={$_.Actions[0].Arguments}}"
        "|ConvertTo-Json -Compress}"
    )
    proc = _ps(script)
    if proc.returncode != 0:
        raise SafetyError("Task Scheduler query failed: " + (proc.stderr or proc.stdout).strip())
    text = proc.stdout.strip()
    if not text or text.casefold() == "null":
        return None
    try:
        info = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SafetyError("Task Scheduler returned an unreadable definition") from exc
    return info if isinstance(info, dict) else None


def _check_only(arguments: str) -> bool:
    return "maintain --no-self-test" in arguments and "--apply" not in arguments and "--fix-roots" not in arguments


def _task_owned(info: dict[str, Any] | None, launcher: Path) -> bool:
    """Owned only when the action is a check-only Forge maintain call.

    The description marker is written at registration; a legacy task created by
    the old schtasks path is recognized by its exact python action.
    """
    if not info:
        return False
    arguments = str(info.get("Arguments") or "")
    execute = str(info.get("Execute") or "")
    if not _check_only(arguments):
        return False
    if SCHEDULE_MARKER in str(info.get("Description") or ""):
        return str(launcher) in arguments
    return execute.casefold().endswith("python.exe") and arguments.strip() == "-m skyrim_forge maintain --no-self-test"


def _task_healthy(info: dict[str, Any] | None, launcher: Path) -> bool:
    if not _task_owned(info, launcher):
        return False
    return str(launcher) in str(info.get("Arguments") or "") and "forge.cmd" in str(info.get("Arguments") or "")


def schedule_status() -> dict[str, Any]:
    """Report exists/owned/healthy without creating anything."""
    if os.name != "nt":
        return {"supported": False, "installed": False, "task": SCHEDULE_TASK}
    launcher = Path(__file__).resolve().parents[1] / "forge.cmd"
    try:
        info = _task_info()
    except SafetyError as exc:
        return {"supported": True, "installed": False, "owned": False, "healthy": False,
                "task": SCHEDULE_TASK, "reason": str(exc)}
    if info is None:
        return {"supported": True, "installed": False, "owned": False, "healthy": False, "task": SCHEDULE_TASK}
    owned = _task_owned(info, launcher)
    healthy = _task_healthy(info, launcher)
    reason = "" if healthy else ("legacy action; reinstall to refresh" if owned else "task exists but was not created by Forge")
    return {"supported": True, "installed": True, "owned": owned, "healthy": healthy,
            "task": SCHEDULE_TASK, "reason": reason}


def install_schedule(*, log_path: Path, day: str = "SUN", time: str = "12:00") -> dict[str, Any]:
    """Create a weekly CHECK-ONLY task. It never passes --apply or --fix-roots."""
    if os.name != "nt":
        raise SafetyError("Scheduled maintenance is Windows-only")
    launcher = Path(__file__).resolve().parents[1] / "forge.cmd"
    existing = _task_info()
    if existing is not None and not _task_owned(existing, launcher):
        raise SafetyError(f"A task named {SCHEDULE_TASK} already exists and was not created by Forge; refusing to overwrite it")
    week_day = DAYS.get(day.upper())
    if week_day is None:
        raise SafetyError(f"day must be one of {sorted(DAYS)}")
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    entry = f'"{launcher}" maintain --no-self-test' if launcher.is_file() else f'"{sys.executable}" -m skyrim_forge maintain --no-self-test'
    # Task Scheduler runs an action through CreateProcess, so redirection needs
    # cmd.exe; forge.cmd also puts the install root on PYTHONPATH.
    command = f'/c "{entry} >> "{log_path}" 2>&1"'
    script = (
        "$ErrorActionPreference='Stop';"
        f"$a=New-ScheduledTaskAction -Execute 'cmd.exe' -Argument {_ps_quote(command)};"
        f"$t=New-ScheduledTaskTrigger -Weekly -DaysOfWeek {week_day} -At {_ps_quote(time)};"
        f"Register-ScheduledTask -TaskName {_ps_quote(SCHEDULE_TASK)} -Action $a -Trigger $t "
        f"-Description {_ps_quote(SCHEDULE_MARKER)} -Force | Out-Null;'ok'"
    )
    proc = _ps(script)
    if proc.returncode != 0 or "ok" not in proc.stdout:
        raise SafetyError("Task registration failed: " + (proc.stderr or proc.stdout).strip())
    return {"installed": True, "task": SCHEDULE_TASK, "day": week_day, "time": time,
            "log": str(log_path), "mode": "check-only", "command": command}


def remove_schedule() -> dict[str, Any]:
    if os.name != "nt":
        raise SafetyError("Scheduled maintenance is Windows-only")
    launcher = Path(__file__).resolve().parents[1] / "forge.cmd"
    info = _task_info()
    if info is None:
        return {"installed": False, "task": SCHEDULE_TASK}
    if not _task_owned(info, launcher):
        raise SafetyError(f"Task {SCHEDULE_TASK} was not created by Forge; refusing to delete it")
    script = f"Unregister-ScheduledTask -TaskName {_ps_quote(SCHEDULE_TASK)} -Confirm:$false;'ok'"
    proc = _ps(script)
    if proc.returncode != 0 or "ok" not in proc.stdout:
        raise SafetyError("Task removal failed: " + (proc.stderr or proc.stdout).strip())
    return {"installed": False, "task": SCHEDULE_TASK}


def inspect(config: ForgeConfig, *, days: int = 7, keep_backups: int = 2,
            provider_homes: Iterable[Path] | None = None) -> dict[str, Any]:
    """List every Forge-owned path old enough to remove, without touching it."""
    if days < 1 or keep_backups < 0:
        raise ValidationError("days must be >= 1 and keep_backups >= 0")
    forge = Path(config.workspace_root) / ".forge"
    spills = _stale_children(forge / "spills", days, "*.json")
    sandboxes = _stale_children(forge / "vfs-sandbox", days)
    backups, kept = _provider_backups(keep_backups, provider_homes)
    removals: list[dict[str, Any]] = []
    for kind, paths in (("spill", spills), ("sandbox", sandboxes), ("skill-backup", backups)):
        for path in paths:
            size = sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) if path.is_dir() else path.stat().st_size
            removals.append({"kind": kind, "path": str(path), "files": 1 if path.is_file() else sum(1 for f in path.rglob("*") if f.is_file()), "bytes": size})
    return {"removals": removals, "kept_skill_backups": kept}


def _owned_bases(config: ForgeConfig, provider_homes: Iterable[Path] | None = None) -> list[Path]:
    forge = Path(config.workspace_root) / ".forge"
    bases = [forge / "spills", forge / "vfs-sandbox"]
    for home in provider_homes or PROVIDER_HOMES:
        bases.append(home / ".skyrim-forge-skill-work")
    return bases


def apply(config: ForgeConfig, report: dict[str, Any], provider_homes: Iterable[Path] | None = None) -> dict[str, Any]:
    """Delete exactly the paths inspect named, and only when they sit under a Forge-owned base."""
    bases = [base.resolve() for base in _owned_bases(config, provider_homes)]
    removed = []
    for item in report["removals"]:
        path = Path(item["path"])
        resolved = path.resolve()
        if resolved in bases or not any(resolved.is_relative_to(base) for base in bases):
            raise SafetyError(f"Refusing to remove a path outside Forge-owned storage: {path}")
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        removed.append(item["path"])
    return {"removed": removed, "count": len(removed)}


def fix_roots(config: ForgeConfig, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Write discovered replacements for MISSING/MOVED roots, keeping a config backup."""
    changed = []
    backup = ""
    for row in rows:
        if row["status"] == "MOVED" and Path(row["candidate"]).is_dir():
            setattr(config, row["key"], Path(row["candidate"]))
            changed.append({"key": row["key"], "value": row["candidate"]})
    if changed:
        backup = config.config_path.with_name(config.config_path.name + ".bak-maintain-" + utc_now().replace(":", "").replace("-", ""))
        shutil.copy2(config.config_path, backup)
        save_config(config)
    return {"changed": changed, "backup": str(backup) if changed else ""}


def run(config: ForgeConfig, *, days: int = 7, keep_backups: int = 2, apply_changes: bool = False,
        add_roots: bool = False, include_health: bool = True, provider_homes: Iterable[Path] | None = None,
        steam_roots: Iterable[Path] | None = None, approved: bool = False) -> dict[str, Any]:
    """Dry-run by default. apply_changes and add_roots are separate, explicit steps."""
    if apply_changes and not approved:
        raise SafetyError("Removing leftovers needs an explicit approval")
    if add_roots and not approved:
        raise SafetyError("Writing discovered roots into the configuration needs an explicit approval")
    found = inspect(config, days=days, keep_backups=keep_backups, provider_homes=provider_homes)
    rows = root_report(config, steam_roots)
    result: dict[str, Any] = {
        "result": "PASS",
        "version": VERSION,
        "removals_planned": len(found["removals"]),
        "removals": found["removals"],
        "kept_skill_backups": found["kept_skill_backups"],
        "roots": rows,
        "applied": False,
        "roots_changed": [],
    }
    if add_roots:
        result["roots_changed"] = fix_roots(config, rows)["changed"]
        result["roots"] = root_report(config, steam_roots)
    if apply_changes:
        result["applied"] = apply(config, found, provider_homes)
    if include_health:
        from .selftest import run_all
        health = run_all()
        result["version"] = health["version"]
        result["health"] = {"result": health["result"], "failed": health["failed"], "checks": len(health["checks"])}
        if health["result"] != "PASS":
            result["result"] = "FAIL"
    if any(row["status"] in {"MISSING", "MOVED", "AMBIGUOUS"} for row in result["roots"]):
        result["result"] = "WARN" if result["result"] == "PASS" else result["result"]
    return result


def self_test() -> dict[str, Any]:
    """Fixture: old files are found and removed, new files and unknown dirs survive."""
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        workspace = root / "Workspaces"
        spills = workspace / ".forge" / "spills"
        sandbox = workspace / ".forge" / "vfs-sandbox"
        provider = root / "provider"
        backups = provider / ".skyrim-forge-skill-work"
        for path in (spills, sandbox / "old-run", sandbox / "new-run", backups / f"backup-skill-{1:032x}", backups / f"backup-skill-{2:032x}"):
            path.mkdir(parents=True, exist_ok=True)
            (path / "payload").write_text("x", encoding="utf-8")
        import os as _os
        def age(path: Path, days: int) -> None:
            stamp = datetime.now().timestamp() - days * 86400
            _os.utime(path, (stamp, stamp))
        (spills / "old.json").write_text("{}", encoding="utf-8")
        (spills / "new.json").write_text("{}", encoding="utf-8")
        age(spills / "old.json", 10)
        age(sandbox / "old-run", 10)
        age(backups / f"backup-skill-{2:032x}", 10)
        foreign = sandbox / "keep-me"
        foreign.mkdir()

        config = ForgeConfig(config_path=root / "config.toml", workspace_root=workspace, audit_log=root / "audit.log")
        config.config_path.write_text("[paths]\n", encoding="utf-8")
        report = run(config, provider_homes=[provider], include_health=False, days=7, keep_backups=1)
        planned = {Path(item["path"]).name for item in report["removals"]}
        checks = {
            "finds_old_spill": "old.json" in planned,
            "finds_old_sandbox": "old-run" in planned,
            "finds_old_backup": f"backup-skill-{2:032x}" in planned,
            "keeps_new": "new.json" not in planned and "new-run" not in planned,
            "refuses_unapproved_apply": False,
        }
        try:
            run(config, provider_homes=[provider], include_health=False, apply_changes=True)
        except SafetyError:
            checks["refuses_unapproved_apply"] = True
        applied = run(config, provider_homes=[provider], include_health=False, days=7, keep_backups=1, apply_changes=True, approved=True)
        checks["deletes_planned"] = len(applied["applied"]["removed"]) == len(report["removals"])
        checks["keeps_foreign"] = foreign.is_dir() and (spills / "new.json").is_file()
        return {"result": "PASS" if all(checks.values()) else "FAIL", "checks": checks}
