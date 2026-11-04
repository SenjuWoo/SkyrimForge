from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from .config import ForgeConfig
from .tools import discover_executable, index_executables, tool_status
from .toolchain import toolchain_status
from .version import VERSION

# A venv built from a provider's cached interpreter dies when that cache is
# pruned, taking every registered MCP client with it. These are the paths that
# have been observed to disappear; a stable system or Python-install-manager
# base never matches.
EPHEMERAL_BASE_MARKERS = (
    "\\.cache\\", "/.cache/", "codex-runtimes", "claude-code", "appdata\\local\\temp",
    "appdata/local/temp", "pipx\\venvs", "/pipx/venvs/", "\\uv\\cache\\", "/uv/cache/",
)


def _parse_pyvenv(cfg: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in cfg.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        key, sep, value = line.partition("=")
        if sep:
            values[key.strip().casefold()] = value.strip()
    return values


def virtualenv_status() -> dict[str, Any]:
    """Report whether Forge runs inside a venv whose base interpreter will still exist tomorrow."""
    prefix = Path(sys.prefix)
    inside = sys.prefix != sys.base_prefix
    report: dict[str, Any] = {"check": "virtualenv", "in_venv": inside, "prefix": str(prefix),
                              "base_python": sys.base_prefix, "python": sys.executable}
    if not inside:
        report.update({"status": "PASS", "note": "Forge is running on an interpreter directly; no venv base to lose."})
        return report
    cfg = prefix / "pyvenv.cfg"
    if not cfg.is_file():
        report.update({"status": "FAIL", "code": "VENV_NO_PYVENV_CFG", "note": "sys.prefix reports a venv but pyvenv.cfg is missing."})
        return report
    values = _parse_pyvenv(cfg)
    home = values.get("home", "")
    executable = values.get("executable", "")
    base = home or executable
    normalized = base.replace("/", "\\").casefold()
    ephemeral = next((marker for marker in EPHEMERAL_BASE_MARKERS if marker in normalized), "")
    base_python = Path(home) / "python.exe" if home else Path(sys.base_prefix) / "python.exe"
    report.update({"pyvenv_cfg": str(cfg), "home": home, "executable": executable,
                   "base_exists": base_python.is_file()})
    if ephemeral:
        report.update({"status": "FAIL", "code": "VENV_EPHEMERAL_BASE_PYTHON", "marker": ephemeral,
                       "note": "The venv base lives in a provider cache. Rebuild with py -3.12 -m venv <root>/.venv."})
    elif not base_python.is_file():
        report.update({"status": "FAIL", "code": "VENV_BASE_MISSING",
                       "note": "The base interpreter recorded in pyvenv.cfg no longer exists on disk."})
    else:
        report.update({"status": "PASS", "code": ""})
    return report


def doctor(config: ForgeConfig) -> dict[str, Any]:
    core = []
    core.append({"check": "workspace_root", "status": "PASS" if config.workspace_root.is_dir() else "FAIL", "path": str(config.workspace_root)})
    core.append({"check": "config", "status": "PASS" if config.config_path.is_file() else "FAIL", "path": str(config.config_path)})
    virtualenv = virtualenv_status()
    if virtualenv["status"] == "FAIL":
        core.append({"check": "virtualenv", "status": "FAIL", "code": virtualenv.get("code", ""), "path": virtualenv.get("prefix", "")})
    skyrim_ok = bool(config.skyrim_data and config.skyrim_data.is_dir())
    tools = {name: tool_status(config, name) for name in config.tools}
    xedit_ready = bool(tools["xedit"].get("exists") and tools["xedit"].get("hash_match", True))
    mo2_ready = bool(tools["mo2"].get("exists"))
    plugin_write_ready = config.workspace_root.is_dir()
    return {
        "product": "Skyrim Forge",
        "version": VERSION,
        "result": "PASS" if all(item["status"] == "PASS" for item in core) else "FAIL",
        "core": core,
        "read_only_ready": config.workspace_root.is_dir(),
        "plugin_write_ready": plugin_write_ready,
        "skyrim_data_ready": skyrim_ok,
        "xedit_automation_ready": config.allow_external_processes and xedit_ready,
        "mo2_automation_ready": config.allow_external_processes and mo2_ready,
        "external_processes_enabled": config.allow_external_processes,
        "ui_automation_enabled": config.allow_ui_automation,
        "virtualenv": virtualenv,
        "tools": tools,
        "toolchain": toolchain_status(config),
        "warnings": config.load_warnings,
    }


def discover_tools(config: ForgeConfig) -> dict[str, str]:
    roots = [path for path in (config.tool_vault_root, config.tools_root, Path("C:/Modding"), Path("C:/Games"), Path("C:/Program Files"), Path("C:/Program Files (x86)")) if path and path.exists()]
    names = {
        "xedit": ["SSEEdit64.exe", "SSEEdit.exe"],
        "mo2": ["ModOrganizer.exe"],
        "loot": ["LOOT.exe"],
        "wrye_bash": ["Wrye Bash.exe", "WryeBash.exe"],
        "creation_kit": ["CreationKit.exe"],
        "ckpe_loader": ["ckpe_loader.exe"],
        "papyrus_compiler": ["PapyrusCompiler.exe"],
        "archive": ["Archive.exe", "7z.exe", "7zz.exe"],
        "bsarch": ["BSArch.exe"],
        "champollion": ["Champollion.exe"],
        "synthesis_cli": ["Synthesis.Bethesda.CLI.exe"],
        "synthesis_gui": ["Synthesis.exe"],
        "deadmesh_cli": ["dmscan.exe"],
        "deadmesh_gui": ["DeadMesh.exe"],
        "audio_xwma_encode": ["xWMAEncode.exe"],
        "audio_lip_generate": ["FaceFXWrapper.exe", "LipGen.exe"],
        "resaverpp_cli": ["resaverpp-cli.exe"],
        "resaverpp_gui": ["ReSaverPP.exe"],
        "pgpatcher": ["PGPatcher.exe"],
        "pgtools": ["pgtools.exe"],
        "easynpc": ["EasyNPC.exe"],
        "clibdt": ["ClibDT.exe"],
        "texture_analyzer": ["TextureAnalyzer.exe"],
        "bethini": ["Bethini.exe"],
        "pca_se": ["PCA SE.exe"],
        "hkxcmd": ["hkxcmd.exe"],
        "cmake": ["cmake.exe", "cmake"],
        "xmake": ["xmake.exe", "xmake"],
        "vcpkg": ["vcpkg.exe", "vcpkg"],
        "ninja": ["ninja.exe", "ninja"],
    }
    found = {}
    # MO2's Python plugin is evidence of an installed plugin, never a standalone CLI.
    if config.tools_root:
        for candidate in (config.tools_root / "NIF Analyzer" / "__init__.py", config.tools_root / "__init__.py"):
            if candidate.is_file():
                text=candidate.read_text(encoding="utf-8-sig")
                if "createPlugin" in text and "mobase.IPluginTool" in text and "NifAnalyzer" in text:
                    found["nif_analyzer_mo2_plugin"]=str(candidate.parent)
    index = index_executables(roots, [name for group in names.values() for name in group])
    for name, executable_names in names.items():
        path = discover_executable(executable_names, roots, index)
        if path:
            found[name] = str(path)
    # The Creation Kit's own compiler beside the game is the authority; copies elsewhere are older or unknown.
    game = config.skyrim_data.parent if config.skyrim_data else None
    for name, relative in (("creation_kit", "CreationKit.exe"), ("papyrus_compiler", "Papyrus Compiler/PapyrusCompiler.exe")):
        if game and (game / relative).is_file():
            found[name] = str((game / relative).resolve())
    return found
