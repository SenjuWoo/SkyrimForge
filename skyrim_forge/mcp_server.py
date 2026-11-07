from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable

from .config import load_config
from .service import ForgeService
from .strictjson import loads
from .util import atomic_write_text, utc_now
from .version import VERSION

MODERN_PROTOCOL = "2026-07-28"
LEGACY_PROTOCOLS = ("2025-11-25", "2025-06-18", "2024-11-05")
PROTOCOLS = {MODERN_PROTOCOL, *LEGACY_PROTOCOLS}
SUPPORTED_VERSIONS = [MODERN_PROTOCOL, *LEGACY_PROTOCOLS]

# 2026-07-28 carries version, identity and capabilities as per-request metadata
# instead of an `initialize` handshake. Forge is a dual-era server: a request
# that declares the modern version in `_meta` is answered statelessly under that
# revision, and an `initialize` request still selects legacy list/read shapes so
# handshake-era Codex and Grok keep working. tools/call always names its result:
# Claude Code 2026-07-28 rejects a server that advertised that revision and then
# omitted resultType, including when the call itself has no `_meta`.
META_PROTOCOL_VERSION = "io.modelcontextprotocol/protocolVersion"
META_SERVER_INFO = "io.modelcontextprotocol/serverInfo"
UNSUPPORTED_PROTOCOL_VERSION = -32022

SERVER_INFO = {"name": "skyrim-forge", "version": VERSION}
INSTRUCTIONS = "Use typed Forge jobs. Never send arbitrary shell commands or write to live Skyrim Data."
CAPABILITIES = {"tools": {"listChanged": False}, "resources": {"subscribe": False, "listChanged": False}, "prompts": {"listChanged": False}}

# Forge's tool, prompt and resource inventories are fixed for the lifetime of an
# installed version, so they are safe to cache and identical for every caller.
STATIC_TTL_MS = 3600000
# Sanitized configuration reflects local machine state and can be changed by
# forge_config_set, so it is never shared between callers and never held fresh.
CONFIG_URIS = {"forge://config"}


def _schema(properties: dict[str, Any] | None = None, required: list[str] | None = None) -> dict[str, Any]:
    return {"type": "object", "properties": properties or {}, "required": required or [], "additionalProperties": False}


def _string(description: str = "") -> dict[str, Any]: return {"type": "string", "description": description}
def _boolean(description: str = "") -> dict[str, Any]: return {"type": "boolean", "description": description}
def _integer(description: str = "") -> dict[str, Any]: return {"type": "integer", "description": description}
def _array(description: str = "") -> dict[str, Any]: return {"type": "array", "items": {"type": "string"}, "description": description}


TOOL_SPECS: dict[str, dict[str, Any]] = {
    "forge_version": {"description": "Return Skyrim Forge version.", "inputSchema": _schema()},
    "forge_doctor": {"description": "Inspect Forge configuration and automation readiness.", "inputSchema": _schema()},
    "forge_self_test": {"description": "Run all built-in deterministic Forge regression fixtures.", "inputSchema": _schema()},
    "forge_config_show": {"description": "Read sanitized Forge configuration.", "inputSchema": _schema()},
    "forge_config_set": {"description": "Change one allowlisted Forge configuration value.", "inputSchema": _schema({"key": _string(), "value": _string(), "approved": _boolean()}, ["key", "value", "approved"])},
    "forge_discover_tools": {"description": "Find known Skyrim tool executables without changing configuration.", "inputSchema": _schema()},
    "forge_tool_status": {"description": "Inspect one configured tool, including pinned hash status.", "inputSchema": _schema({"name": _string()}, ["name"])},
    "forge_tool_scan": {"description": "Recursively inspect a tool directory or ZIP without launching executables.", "inputSchema": _schema({"source": _string()}, ["source"])},
    "forge_tool_import": {"description": "Transactionally import a recognized local tool into the private Forge tool vault and SHA-256 pin it.", "inputSchema": _schema({"source": _string(), "identifier": _string(), "sha256": _string(), "approved": _boolean()}, ["source", "identifier", "approved"])},
    "forge_tool_import_all": {"description": "Import all unambiguous recognized automation tools from one local source; GUI tools are opt-in.", "inputSchema": _schema({"source": _string(), "include_gui": _boolean(), "approved": _boolean()}, ["source", "approved"])},
    "forge_tool_configure": {"description": "Configure and SHA-256 pin an existing legal tool installation without copying it.", "inputSchema": _schema({"identifier": _string(), "executable": _string(), "approved": _boolean()}, ["identifier", "executable", "approved"])},
    "forge_tool_reuse_reverse": {"description": "Reuse and SHA-256 pin Reverse THIS! texconv/7-Zip in place; preserve existing tool configuration.", "inputSchema": _schema({"pointer": _string(), "approved": _boolean()}, ["approved"])},
    "forge_tool_resolve": {"description": "Resolve the best configured hash-pinned real tool for one exact capability.", "inputSchema": _schema({"capability": _string()}, ["capability"])},
    "forge_toolchain_status": {"description": "Report the private tool vault and all configured catalog tools.", "inputSchema": _schema()},
    "forge_bsarch_info": {"description": "Inspect BSA/BA2 through the configured hash-pinned BSArch.", "inputSchema": _schema({"archive": _string(), "dump": _boolean()}, ["archive"])},
    "forge_bsarch_unpack": {"description": "Extract BSA/BA2 through BSArch into Forge workspace staging.", "inputSchema": _schema({"archive": _string(), "output_dir": _string(), "approved": _boolean()}, ["archive", "output_dir", "approved"])},
    "forge_bsarch_pack": {"description": "Create a Skyrim SE/AE BSA from a Forge workspace directory and reopen it with BSArch.", "inputSchema": _schema({"source_dir": _string(), "output_archive": _string(), "compress": _boolean(), "approved": _boolean()}, ["source_dir", "output_archive", "approved"])},
    "forge_deadmesh_scan": {"description": "Run the configured hash-pinned DeadMesh dmscan and capture reports in the workspace.", "inputSchema": _schema({"source": _string(), "output_report": _string(), "scan_bsa": _boolean(), "approved": _boolean()}, ["source", "output_report", "approved"])},
    "forge_champollion_decompile": {"description": "Decompile PEX files using a configured hash-pinned Champollion into workspace staging.", "inputSchema": _schema({"pex": _string(), "output_dir": _string(), "recursive": _boolean(), "approved": _boolean()}, ["pex", "output_dir", "approved"])},
    "forge_synthesis_run": {"description": "Run the dedicated Synthesis.Bethesda.CLI pipeline command. The GUI executable is not accepted.", "inputSchema": _schema({"pipeline_settings": _string(), "output_dir": _string(), "data_folder": _string(), "load_order": _string(), "profile": _string(), "target_runtime": _string(), "approved": _boolean()}, ["pipeline_settings", "output_dir", "approved"])},
    "forge_plugin_info": {"description": "Inspect TES4 header and masters. Header evidence only.", "inputSchema": _schema({"path": _string()}, ["path"])},
    "forge_record_query": {"description": "Query plugin records by signature, EditorID, or raw FormID.", "inputSchema": _schema({"path": _string(), "signature": _string(), "editor_id": _string(), "form_id": _string(), "limit": _integer()}, ["path"])},
    "forge_plugins": {"description": "Read plugins.txt.", "inputSchema": _schema({"path": _string()})},
    "forge_load_order": {"description": "Resolve the ordered, indexed plugin list from an MO2 instance, or from a plugins.txt plus search roots. Reads plugin headers only.", "inputSchema": _schema({"mo2_instance": _string(), "plugins_file": _string(), "roots": _array()})},
    "forge_record_conflicts": {"description": "Find records by EditorID or form key across the load order and show every version, the winner, and which subrecords each override changed. Independent of houseCARL; pass signature to keep it fast.", "inputSchema": _schema({"mo2_instance": _string(), "plugins_file": _string(), "roots": _array(), "editor_id": _string(), "form_key": _string(), "signature": _string(), "exact": _boolean(), "only_plugins": _array(), "limit": _integer(), "dump": _boolean()})},
    "forge_seq_build": {"description": "Write Seq/<plugin>.seq for the Start Game Enabled quests a plugin defines, inside the Forge workspace.", "inputSchema": _schema({"plugin": _string(), "output_root": _string(), "approved": _boolean()}, ["plugin", "output_root", "approved"])},
    "forge_archive_info": {"description": "Inspect ZIP/7z/RAR contents safely.", "inputSchema": _schema({"path": _string()}, ["path"])},
    "forge_mod_tree": {"description": "Inspect a loose mod directory.", "inputSchema": _schema({"path": _string()}, ["path"])},
    "forge_capabilities": {"description": "Return the evidence-level capability registry or one capability.", "inputSchema": _schema({"identifier": _string()})},
    "forge_lint_frameworks": {"description": "Lint source-locked SPID, KID, BOS, SkyPatcher, FLM, and CDF/CID profiles without rewriting unknown syntax.", "inputSchema": _schema({"paths": _array()}, ["paths"])},
    "forge_framework_plan_validate": {"description": "Validate a typed framework configuration plan.", "inputSchema": _schema({"plan": _string()}, ["plan"])},
    "forge_framework_build": {"description": "Build a source-locked framework configuration transactionally and lint the result.", "inputSchema": _schema({"plan": _string(), "output_root": _string(), "approved": _boolean()}, ["plan", "output_root", "approved"])},
    "forge_papyrus_analyze": {"description": "Analyze Papyrus identity, inheritance, import conflicts, and optimization heuristics without rewriting source.", "inputSchema": _schema({"scripts": _array(), "imports": _array()}, ["scripts"])},
    "forge_papyrus_compile": {"description": "Compile Papyrus through a hash-pinned Bethesda compiler into Forge staging, verify fresh PEX files, and emit a build manifest.", "inputSchema": _schema({"scripts": _array(), "output_dir": _string(), "imports": _array(), "flags_file": _string(), "optimize": _boolean(), "approved": _boolean()}, ["scripts", "output_dir", "approved"])},
    "forge_native_plan_validate": {"description": "Validate a source-locked CommonLibSSE-NG native plugin plan.", "inputSchema": _schema({"plan": _string()}, ["plan"])},
    "forge_native_scaffold": {"description": "Generate a bounded CommonLibSSE-NG project inside the Forge workspace.", "inputSchema": _schema({"plan": _string(), "output_dir": _string(), "approved": _boolean()}, ["plan", "output_dir", "approved"])},
    "forge_native_audit": {"description": "Statically audit a CommonLibSSE-NG project and its lifecycle/runtime declarations.", "inputSchema": _schema({"project": _string()}, ["project"])},
    "forge_native_binary_audit": {"description": "Inspect a Windows x64 SKSE DLL PE structure and imports.", "inputSchema": _schema({"dll": _string()}, ["dll"])},
    "forge_native_build": {"description": "Build an audited native project with pinned CMake/vcpkg tools into Forge staging.", "inputSchema": _schema({"project": _string(), "output_root": _string(), "configuration": _string(), "approved": _boolean()}, ["project", "output_root", "approved"])},
    "forge_fomod_validate": {"description": "Validate FOMOD XML, file coverage, branch metadata, flags, source paths, and destination collisions.", "inputSchema": _schema({"root": _string(), "strict_coverage": _boolean()}, ["root"])},
    "forge_fomod_plan_validate": {"description": "Validate a typed Forge FOMOD generation plan.", "inputSchema": _schema({"plan": _string(), "source_root": _string()}, ["plan"])},
    "forge_fomod_build": {"description": "Generate a complete transactional FOMOD tree from a typed plan and staged payload.", "inputSchema": _schema({"plan": _string(), "source_root": _string(), "output_root": _string(), "approved": _boolean()}, ["plan", "source_root", "output_root", "approved"])},
    "forge_fomod_scaffold": {"description": "Create an install-everything FOMOD plan from a staged payload tree.", "inputSchema": _schema({"source_root": _string(), "output_plan": _string(), "module_name": _string(), "module_version": _string(), "approved": _boolean()}, ["source_root", "output_plan", "module_name", "approved"])},
    "forge_fomod_simulate": {"description": "Simulate typed FOMOD selections and dependencies without launching a mod manager.", "inputSchema": _schema({"plan": _string(), "selections": _string(), "state": _string(), "source_root": _string()}, ["plan"])},
    "forge_release_validate": {"description": "Validate a private release tree or run the Nexus publication gate.", "inputSchema": _schema({"root": _string(), "target": _string(), "publication_plan": _string()}, ["root"])},
    "forge_release_build": {"description": "Build a private deterministic ZIP or a Nexus-compliant publication bundle.", "inputSchema": _schema({"root": _string(), "output": _string(), "target": _string(), "publication_plan": _string(), "approved": _boolean()}, ["root", "output", "approved"])},
    "forge_nexus_policy_status": {"description": "Return the required official Nexus policy sources and review freshness boundary.", "inputSchema": _schema()},
    "forge_nexus_scaffold": {"description": "Create an intentionally incomplete Nexus publication plan from a release tree.", "inputSchema": _schema({"release_root": _string(), "output_plan": _string(), "mod_name": _string(), "mod_version": _string(), "uploader": _string(), "approved": _boolean()}, ["release_root", "output_plan", "mod_name", "mod_version", "uploader", "approved"])},
    "forge_nexus_plan_validate": {"description": "Validate Nexus publication-plan structure; optionally audit its release tree.", "inputSchema": _schema({"plan": _string(), "release_root": _string()}, ["plan"])},
    "forge_nexus_audit": {"description": "Audit rights, credits, permissions, content, policy review, claims, binaries and file coverage for Nexus sharing.", "inputSchema": _schema({"plan": _string(), "release_root": _string()}, ["plan", "release_root"])},
    "forge_nexus_build": {"description": "Build the final Nexus release tree, public rights documents, private audit and ZIP after the gate passes.", "inputSchema": _schema({"plan": _string(), "release_root": _string(), "output_root": _string(), "approved": _boolean()}, ["plan", "release_root", "output_root", "approved"])},
    "forge_nexus_page_render": {"description": "Render Nexus BBCode from a validated publication plan.", "inputSchema": _schema({"plan": _string(), "output": _string(), "approved": _boolean()}, ["plan"])},
    "forge_plugin_plan_validate": {"description": "Validate typed plugin creation plan.", "inputSchema": _schema({"path": _string()}, ["path"])},
    "forge_plugin_build": {"description": "Build KYWD, GLOB, FLST, or OTFT plugin from typed plan.", "inputSchema": _schema({"path": _string(), "output_dir": _string(), "approved": _boolean()}, ["path", "output_dir", "approved"])},
    "forge_automation_validate": {"description": "Validate a typed Automation Fabric job.", "inputSchema": _schema({"path": _string()}, ["path"])},
    "forge_automation_run": {"description": "Execute a typed transactional automation job.", "inputSchema": _schema({"path": _string(), "approved": _boolean(), "keep_transaction": _boolean()}, ["path", "approved"])},
    "forge_audio_inspect": {"description": "Inspect a FUZ, XWM, WAV or LIP container: FUZE header, RIFF/WMA format, sample rate and voice readiness.", "inputSchema": _schema({"path": _string()}, ["path"])},
    "forge_audio_extract_fuz": {"description": "Split a FUZ into its .lip and .xwm payloads inside Forge workspace staging.", "inputSchema": _schema({"fuz": _string(), "output_dir": _string(), "approved": _boolean()}, ["fuz", "output_dir", "approved"])},
    "forge_audio_create_fuz": {"description": "Pack an .xwm (and optional .lip) into a FUZ container inside Forge workspace staging.", "inputSchema": _schema({"xwm": _string(), "output": _string(), "lip": _string(), "approved": _boolean()}, ["xwm", "output", "approved"])},
    "forge_voice_path_validate": {"description": "Check a staged mod keeps voice files at Sound/Voice/<plugin>/<voice type>/<file>.", "inputSchema": _schema({"root": _string()}, ["root"])},
    "forge_architect_recommend": {"description": "Rank Skyrim implementation routes from a plain-English task description and explicit constraints; state unknowns and verification steps. It does not claim a framework is installed.", "inputSchema": _schema({"request": _string()}, ["request"])},
    "forge_knowledge_status": {"description": "Report curated Skyrim API/source entries and whether their configured local probes exist; DETECTED is not a version or runtime claim.", "inputSchema": _schema()},
    "forge_knowledge_lookup": {"description": "Look up one Skyrim source/API registry entry by id; unknown ids stay UNKNOWN.", "inputSchema": _schema({"id": _string()}, ["id"])},
    "forge_quality_plan": {"description": "List the evidence dimensions required for one or more mod types; unrelated dimensions are excluded.", "inputSchema": _schema({"mod_types": _array()}, ["mod_types"])},
    "forge_quality_audit": {"description": "Audit a mod-quality evidence report; PASS requires evidence and missing runtime checks stay UNVERIFIED.", "inputSchema": _schema({"report": _string()}, ["report"])},
    "forge_performance_compare": {"description": "Compare two frame-time benchmark reports with matching scenario metadata; report percentiles and reject incompatible captures.", "inputSchema": _schema({"baseline": _string(), "candidate": _string(), "tolerance_percent": {"type": "number"}}, ["baseline", "candidate"])},
    "forge_performance_ingest": {"description": "Convert a PresentMon CSV with an explicit metric and process into a benchmark report in the workspace.", "inputSchema": _schema({"csv": _string(), "output": _string(), "scenario": _string(), "metric": {"type": "string", "enum": ["msBetweenPresents", "msBetweenDisplayChange", "MsGPUActive"]}, "process": _string(), "approved": _boolean()}, ["csv", "output", "scenario", "approved"])},
    "forge_maintain": {"description": "Report or remove Forge-owned leftovers (spills, sandbox runs, old provider skill backups), flag configured roots that moved and name a discovered replacement; optionally run the self-test. Dry-run unless apply is true.", "inputSchema": _schema({"days": _integer(), "keep_backups": _integer(), "apply": _boolean(), "fix_roots": _boolean(), "self_test": _boolean(), "approved": _boolean()})},
    "forge_texture_inspect": {"description": "Read a DDS header: format (BC1/BC3/A8R8G8B8), dimensions, mip chain and payload consistency.", "inputSchema": _schema({"path": _string()}, ["path"])},
    "forge_texture_generate": {"description": "Generate a deterministic procedural DDS texture inside the workspace: solid, checker, gradient, noise, bricks or a tangent-space normal map, with full mip chains and an optional PNG preview.", "inputSchema": _schema({
        "kind": {"type": "string", "enum": ["solid", "checker", "gradient", "noise", "bricks", "normal"]},
        "output": _string(), "size": _integer(), "format": {"type": "string", "enum": ["bc1", "bc3", "rgba"]},
        "seed": _integer(), "primary": _string(), "secondary": _string(), "octaves": _integer(),
        "frequency": {"type": "number"}, "cells": _integer(), "strength": {"type": "number"},
        "flip_green": _boolean(), "preview": _string(), "approved": _boolean(),
    }, ["kind", "output", "approved"])},
    "forge_skse_inspect_pe": {"description": "Read an x64 SKSE DLL without loading it: PE32+ headers, exports, PluginVersionData and file version.", "inputSchema": _schema({"dll": _string()}, ["dll"])},
    "forge_skse_audit_imports": {"description": "Inventory a DLL's imported DLLs and functions and flag network, process-execution and DirectStorage use.", "inputSchema": _schema({"dll": _string()}, ["dll"])},
    "forge_skse_verify_reproducible": {"description": "Compare a built DLL with a reference DLL byte-for-byte, then with linker timestamps normalised.", "inputSchema": _schema({"built": _string(), "reference": _string()}, ["built", "reference"])},
    "forge_framework_correlate_logs": {"description": "Match static framework-lint findings against SKSE framework logs and report which rows runtime evidence proves.", "inputSchema": _schema({"mod_root": _string(), "log_dir": _string()}, ["mod_root", "log_dir"])},
    "forge_fomod_test_install": {"description": "Extract a FOMOD branch into MO2- and Vortex-shaped folders in the workspace sandbox and write an install receipt.", "inputSchema": _schema({"plan": _string(), "source_root": _string(), "selections": _string(), "state": _string(), "all_branches": _boolean(), "approved": _boolean()}, ["plan", "source_root", "approved"])},
}


# Tool annotations are advisory hints the MCP revision defines so a host can
# auto-approve reads and pause before destructive calls. Forge classifies every
# tool exactly once; the compact surface reuses the same classification.
READ_ONLY_TOOLS = {
    "forge_version", "forge_doctor", "forge_self_test", "forge_config_show", "forge_discover_tools",
    "forge_tool_status", "forge_tool_scan", "forge_tool_resolve", "forge_toolchain_status",
    "forge_capabilities", "forge_plugin_info", "forge_record_query", "forge_plugins", "forge_load_order",
    "forge_record_conflicts", "forge_archive_info", "forge_mod_tree", "forge_bsarch_info",
    "forge_audio_inspect", "forge_voice_path_validate", "forge_texture_inspect", "forge_skse_inspect_pe", "forge_skse_audit_imports",
    "forge_skse_verify_reproducible", "forge_framework_correlate_logs", "forge_fomod_simulate",
    "forge_nexus_policy_status", "forge_lint_frameworks", "forge_framework_plan_validate", "forge_fomod_validate",
    "forge_fomod_plan_validate", "forge_release_validate", "forge_nexus_plan_validate", "forge_nexus_audit",
    "forge_native_plan_validate", "forge_native_audit", "forge_native_binary_audit", "forge_plugin_plan_validate",
    "forge_automation_validate", "forge_architect_recommend", "forge_knowledge_status",
    "forge_knowledge_lookup", "forge_quality_plan", "forge_quality_audit", "forge_performance_compare",
}
DESTRUCTIVE_TOOLS = {
    "forge_config_set", "forge_tool_import", "forge_tool_import_all", "forge_tool_configure",
    "forge_tool_reuse_reverse", "forge_automation_run", "forge_maintain",
}
COMPACT_GROUPS: dict[str, set[str]] = {
    "inspect": {
        "forge_version", "forge_doctor", "forge_self_test", "forge_config_show", "forge_discover_tools",
        "forge_tool_status", "forge_tool_scan", "forge_tool_resolve", "forge_toolchain_status",
        "forge_capabilities", "forge_papyrus_analyze", "forge_plugin_info", "forge_record_query", "forge_plugins", "forge_load_order",
        "forge_record_conflicts", "forge_archive_info", "forge_mod_tree", "forge_bsarch_info",
        "forge_audio_inspect", "forge_voice_path_validate", "forge_texture_inspect", "forge_skse_inspect_pe", "forge_skse_audit_imports",
        "forge_skse_verify_reproducible", "forge_framework_correlate_logs", "forge_fomod_simulate",
        "forge_nexus_policy_status", "forge_knowledge_status", "forge_knowledge_lookup",
        "forge_performance_compare",
    },
    "validate": {
        "forge_lint_frameworks", "forge_framework_plan_validate", "forge_fomod_validate", "forge_fomod_plan_validate",
        "forge_release_validate", "forge_nexus_plan_validate", "forge_nexus_audit", "forge_native_plan_validate",
        "forge_native_audit", "forge_native_binary_audit", "forge_plugin_plan_validate", "forge_automation_validate",
        "forge_architect_recommend", "forge_quality_plan", "forge_quality_audit",
    },
    "execute": {
        "forge_config_set", "forge_tool_import", "forge_tool_import_all", "forge_tool_configure",
        "forge_tool_reuse_reverse", "forge_bsarch_unpack", "forge_bsarch_pack",
        "forge_deadmesh_scan", "forge_champollion_decompile", "forge_synthesis_run", "forge_seq_build",
        "forge_framework_build", "forge_papyrus_compile", "forge_native_scaffold", "forge_native_build",
        "forge_fomod_scaffold", "forge_fomod_build", "forge_fomod_test_install", "forge_plugin_build",
        "forge_automation_run", "forge_audio_extract_fuz", "forge_audio_create_fuz", "forge_texture_generate", "forge_maintain",
        "forge_performance_ingest",
    },
    "release": {"forge_release_build", "forge_nexus_scaffold", "forge_nexus_build", "forge_nexus_page_render"},
}


def _annotations(name: str) -> dict[str, bool]:
    if name in READ_ONLY_TOOLS:
        return {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
    if name in DESTRUCTIVE_TOOLS:
        return {"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False, "openWorldHint": False}
    # A writer that is not known to be destructive still creates or replaces
    # output, so it is not idempotent. Only the read-only path may claim that.
    return {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False}


def _compact_specs() -> dict[str, dict[str, Any]]:
    """Expose four orthogonal meta-tools instead of every schema, for hosts with a server-slot or token ceiling."""
    covered = [member for members in COMPACT_GROUPS.values() for member in members]
    assert sorted(covered) == sorted(TOOL_SPECS), "compact surface must cover every tool exactly once"
    specs = {}
    for group, members in COMPACT_GROUPS.items():
        specs[f"skyrim_forge_{group}"] = {
            "description": f"{group.capitalize()} through one typed Forge entry point. Name an operation and pass its arguments; the underlying tool and its approval rules are unchanged.",
            "inputSchema": _schema({
                "operation": {"type": "string", "enum": sorted(members), "description": "Underlying Forge tool to run."},
                "arguments": {"type": "object", "description": "Arguments for that tool, exactly as its own schema defines them.", "additionalProperties": True},
                "approved": _boolean("Explicit approval, forwarded to the underlying tool."),
            }, ["operation"]),
            # A group is only as safe as its riskiest member: the host sees one
            # annotation, so one destructive operation makes the whole group so.
            "annotations": {
                "readOnlyHint": all(member in READ_ONLY_TOOLS for member in members),
                "destructiveHint": any(member in DESTRUCTIVE_TOOLS for member in members),
                "idempotentHint": all(member in READ_ONLY_TOOLS for member in members),
                "openWorldHint": False,
            },
        }
    return specs


COMPACT_TOOLS = _compact_specs()

# A host that silently truncates a large JSON payload leaves the agent with
# invalid input. Forge spills the complete result to a workspace artifact and
# returns a bounded envelope naming the file instead.
MAX_CHARS_DEFAULT = 24000


def _max_chars() -> int:
    try:
        value = int(os.environ.get("SKYRIM_FORGE_MAX_CHARS", ""))
    except ValueError:
        value = 0
    return value if value >= 1000 else MAX_CHARS_DEFAULT


def _bounded(service: ForgeService, name: str, value: Any) -> dict[str, Any]:
    text = json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True, default=str)
    if len(text) <= _max_chars():
        return {"content": [{"type": "text", "text": text}], "isError": False}
    directory = Path(service.config.workspace_root) / ".forge" / "spills"
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]
    artifact = directory / f"{name}_{utc_now().replace(':', '').replace('-', '')}_{digest}.json"
    atomic_write_text(artifact, text + "\n")
    summary = ({key: (len(item) if isinstance(item, (list, dict)) else item[:200] if isinstance(item, str) else item)
                for key, item in value.items()} if isinstance(value, dict) else {"type": type(value).__name__})
    envelope = {"result": "PARTIAL_SPILL", "max_chars_overrun": True, "total_chars": len(text),
                "artifact_path": str(artifact), "summary": summary}
    return {"content": [{"type": "text", "text": json.dumps(envelope, indent=2, sort_keys=True, default=str)}], "isError": False}


def _call(service: ForgeService, name: str, args: dict[str, Any]) -> Any:
    approved = bool(args.get("approved", False))
    match name:
        case "forge_version": return service.version()
        case "forge_doctor": return service.doctor()
        case "forge_self_test": return service.self_test()
        case "forge_config_show": return service.config_show()
        case "forge_config_set":
            if not approved: raise PermissionError("approved=true is required to change configuration")
            return service.config_set(args["key"], args["value"])
        case "forge_discover_tools": return service.discover()
        case "forge_tool_status": return service.tool_status(args["name"])
        case "forge_tool_scan": return service.tool_scan(args["source"])
        case "forge_tool_import": return service.tool_import(args["source"], args["identifier"], approved, args.get("sha256") or None)
        case "forge_tool_import_all": return service.tool_import_all(args["source"], approved, bool(args.get("include_gui", False)))
        case "forge_tool_configure": return service.tool_configure(args["identifier"], args["executable"], approved)
        case "forge_tool_reuse_reverse": return service.tool_reuse_reverse(approved, args.get("pointer"))
        case "forge_tool_resolve": return service.tool_resolve(args["capability"])
        case "forge_toolchain_status": return service.toolchain_status()
        case "forge_bsarch_info": return service.bsarch_info(args["archive"], bool(args.get("dump", False)))
        case "forge_bsarch_unpack": return service.bsarch_unpack(args["archive"], args["output_dir"], approved)
        case "forge_bsarch_pack": return service.bsarch_pack(args["source_dir"], args["output_archive"], approved, bool(args.get("compress", True)))
        case "forge_deadmesh_scan": return service.deadmesh_scan(args["source"], args["output_report"], approved, bool(args.get("scan_bsa", True)))
        case "forge_champollion_decompile": return service.champollion_decompile(args["pex"], args["output_dir"], approved, bool(args.get("recursive", False)))
        case "forge_synthesis_run": return service.synthesis_run(args["pipeline_settings"], args["output_dir"], approved, args.get("data_folder") or None, args.get("load_order") or None, args.get("profile", ""), args.get("target_runtime", ""))
        case "forge_plugin_info": return service.plugin_info(args["path"])
        case "forge_record_query": return service.record_query(args["path"], args.get("signature", ""), args.get("editor_id", ""), args.get("form_id", ""), int(args.get("limit", 5000)))
        case "forge_plugins": return service.plugins(args.get("path") or None)
        case "forge_load_order": return service.load_order(args.get("mo2_instance") or None, args.get("plugins_file") or None, args.get("roots") or None)
        case "forge_record_conflicts": return service.record_conflicts(args.get("mo2_instance") or None, args.get("plugins_file") or None, args.get("roots") or None, args.get("editor_id", ""), args.get("form_key", ""), args.get("signature", ""), bool(args.get("exact", True)), args.get("only_plugins") or None, int(args.get("limit", 20)), bool(args.get("dump", False)))
        case "forge_seq_build": return service.seq_build(args["plugin"], args["output_root"], approved)
        case "forge_archive_info": return service.archive(args["path"])
        case "forge_mod_tree": return service.mod_tree(args["path"])
        case "forge_capabilities": return service.capabilities(args.get("identifier") or None)
        case "forge_lint_frameworks": return service.lint(args["paths"])
        case "forge_framework_plan_validate": return service.framework_plan_validate(args["plan"])
        case "forge_framework_build": return service.framework_build(args["plan"], args["output_root"], approved)
        case "forge_papyrus_analyze": return service.papyrus_analyze(args["scripts"], args.get("imports") or [])
        case "forge_papyrus_compile": return service.papyrus_compile(args["scripts"], args["output_dir"], args.get("imports") or None, args.get("flags_file") or None, approved, bool(args.get("optimize", True)))
        case "forge_native_plan_validate": return service.native_plan_validate(args["plan"])
        case "forge_native_scaffold": return service.native_scaffold(args["plan"], args["output_dir"], approved)
        case "forge_native_audit": return service.native_audit(args["project"])
        case "forge_native_binary_audit": return service.native_binary_audit(args["dll"])
        case "forge_native_build": return service.native_build(args["project"], args["output_root"], approved, args.get("configuration", "Release"))
        case "forge_fomod_validate": return service.fomod_validate(args["root"], bool(args.get("strict_coverage", True)))
        case "forge_fomod_plan_validate": return service.fomod_plan_validate(args["plan"], args.get("source_root") or None)
        case "forge_fomod_build": return service.fomod_build(args["plan"], args["source_root"], args["output_root"], approved)
        case "forge_fomod_scaffold": return service.fomod_scaffold(args["source_root"], args["output_plan"], args["module_name"], args.get("module_version", "1.0.0"), approved)
        case "forge_fomod_simulate": return service.fomod_simulate(args["plan"], args.get("selections") or None, args.get("state") or None, args.get("source_root") or None)
        case "forge_release_validate": return service.release_validate(args["root"], args.get("target", "private"), args.get("publication_plan") or None)
        case "forge_release_build": return service.release_build(args["root"], args["output"], approved, args.get("target", "private"), args.get("publication_plan") or None)
        case "forge_nexus_policy_status": return service.nexus_policy_status()
        case "forge_nexus_scaffold": return service.nexus_scaffold(args["release_root"], args["output_plan"], args["mod_name"], args["mod_version"], args["uploader"], approved)
        case "forge_nexus_plan_validate": return service.nexus_plan_validate(args["plan"], args.get("release_root") or None)
        case "forge_nexus_audit": return service.nexus_audit(args["plan"], args["release_root"])
        case "forge_nexus_build": return service.nexus_build(args["plan"], args["release_root"], args["output_root"], approved)
        case "forge_nexus_page_render": return service.nexus_page_render(args["plan"], args.get("output") or None, approved)
        case "forge_plugin_plan_validate": return service.plan_validate(args["path"])
        case "forge_plugin_build": return service.plugin_build(args["path"], args["output_dir"], approved)
        case "forge_automation_validate": return service.automation_validate(args["path"])
        case "forge_automation_run": return service.automation_run(args["path"], approved, bool(args.get("keep_transaction", True)))
        case "forge_audio_inspect": return service.audio_inspect(args["path"])
        case "forge_audio_extract_fuz": return service.audio_extract_fuz(args["fuz"], args["output_dir"], approved)
        case "forge_audio_create_fuz": return service.audio_create_fuz(args["xwm"], args["output"], approved, args.get("lip") or None)
        case "forge_voice_path_validate": return service.voice_path_validate(args["root"])
        case "forge_texture_inspect": return service.texture_inspect(args["path"])
        case "forge_architect_recommend": return service.architecture_recommend(args["request"])
        case "forge_knowledge_status": return service.knowledge_status()
        case "forge_knowledge_lookup": return service.knowledge_lookup(args["id"])
        case "forge_quality_plan": return service.quality_plan(args["mod_types"])
        case "forge_quality_audit": return service.quality_audit(args["report"])
        case "forge_performance_compare": return service.performance_compare(args["baseline"], args["candidate"], float(args.get("tolerance_percent", 2.0)))
        case "forge_performance_ingest": return service.performance_ingest(args["csv"], args["output"], args["scenario"], approved, args.get("metric"), args.get("process"))
        case "forge_maintain": return service.maintain(int(args.get("days", 7)), int(args.get("keep_backups", 2)), bool(args.get("apply", False)), bool(args.get("fix_roots", False)), bool(args.get("self_test", True)), approved)
        case "forge_texture_generate": return service.texture_generate(args["kind"], args["output"], size=int(args.get("size", 512)), fmt=args.get("format", "bc1"), seed=int(args.get("seed", 0)), primary=args.get("primary", "#808080"), secondary=args.get("secondary", "#303030"), octaves=int(args.get("octaves", 5)), frequency=float(args.get("frequency", 4.0)), cells=int(args.get("cells", 8)), strength=float(args.get("strength", 0.12)), flip_green=bool(args.get("flip_green", False)), preview=args.get("preview") or None, approved=approved)
        case "forge_skse_inspect_pe": return service.skse_inspect_pe(args["dll"])
        case "forge_skse_audit_imports": return service.skse_audit_imports(args["dll"])
        case "forge_skse_verify_reproducible": return service.skse_verify_reproducible(args["built"], args["reference"])
        case "forge_framework_correlate_logs": return service.framework_correlate_logs(args["mod_root"], args["log_dir"])
        case "forge_fomod_test_install": return service.fomod_test_install(args["plan"], args["source_root"], approved, args.get("selections") or None, args.get("state") or None, bool(args.get("all_branches", False)))
        case _: raise KeyError(name)


def _error(exc: Exception) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": json.dumps({"result": "FAIL", "error": type(exc).__name__, "message": str(exc)}, indent=2)}], "isError": True}


def _resource_root() -> Path:
    return Path(__file__).resolve().parent


def _declared_version(request: dict[str, Any]) -> str | None:
    """Return the protocol version a modern request declares in `_meta`."""
    params = request.get("params")
    meta = params.get("_meta") if isinstance(params, dict) else None
    version = meta.get(META_PROTOCOL_VERSION) if isinstance(meta, dict) else None
    return version if isinstance(version, str) else None


def _cacheable(result: dict[str, Any], uri: str | None = None) -> dict[str, Any]:
    """Attach the caching hints the revision requires on a complete result."""
    private = uri in CONFIG_URIS
    return {**result, "resultType": "complete", "ttlMs": 0 if private else STATIC_TTL_MS, "cacheScope": "private" if private else "public"}


def _complete(result: dict[str, Any]) -> dict[str, Any]:
    """Name a successful result so a 2026-07-28 client can parse it.

    Caching hints stay on list/read/discover only. tools/call, prompts/get,
    ping, and a modern initialize still have to carry `resultType`, or a client
    that already learned the server implements 2026-07-28 rejects the payload.
    Handshake-era clients ignore the extra field.
    """
    if result.get("resultType"):
        return result
    return {**result, "resultType": "complete"}


def _call_compact(service: ForgeService, name: str, args: dict[str, Any]) -> Any:
    """Route one compact meta-tool call to the underlying Forge tool and its own approval rules."""
    group = name.removeprefix("skyrim_forge_")
    operation = args.get("operation")
    if operation not in COMPACT_GROUPS.get(group, set()):
        raise ValueError(f"{operation!r} is not an operation of {name}")
    inner = args.get("arguments") or {}
    if not isinstance(inner, dict):
        raise ValueError("arguments must be an object")
    inner = dict(inner)
    if "approved" in args:
        inner["approved"] = args["approved"]
    return _call(service, operation, inner)


def handle(service: ForgeService, request: dict[str, Any], surface: str = "full") -> dict[str, Any] | None:
    if request.get("jsonrpc") != "2.0":
        raise ValueError("JSON-RPC 2.0 required")
    method = request.get("method")
    request_id = request.get("id")
    if method in {"notifications/initialized", "notifications/cancelled"}:
        return None
    declared = _declared_version(request)
    if declared is not None and declared not in PROTOCOLS:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": UNSUPPORTED_PROTOCOL_VERSION, "message": "Unsupported protocol version", "data": {"supported": SUPPORTED_VERSIONS, "requested": declared}}}
    # List/read caching hints are modern-only so handshake-era inventory
    # responses stay byte-identical. tools/call always carries resultType: a
    # client that saw 2026-07-28 in server/discover or initialize requires it
    # even when the call itself has no `_meta`.
    modern = declared == MODERN_PROTOCOL or method == "server/discover"
    cache = _cacheable if modern else (lambda result, uri=None: result)
    if method == "server/discover":
        result = cache({"supportedVersions": SUPPORTED_VERSIONS, "capabilities": CAPABILITIES, "instructions": INSTRUCTIONS, "_meta": {META_SERVER_INFO: SERVER_INFO}})
    elif method == "initialize":
        params = request.get("params") if isinstance(request.get("params"), dict) else {}
        requested = params.get("protocolVersion", "2025-11-25")
        protocol = requested if requested in PROTOCOLS else "2025-11-25"
        result = {"protocolVersion": protocol, "capabilities": CAPABILITIES, "serverInfo": SERVER_INFO, "instructions": INSTRUCTIONS}
        if protocol == MODERN_PROTOCOL:
            result = _complete(result)
    elif method == "ping":
        result = _complete({})
    elif method == "tools/list":
        if surface == "compact":
            result = cache({"tools": [{"name": name, **spec} for name, spec in sorted(COMPACT_TOOLS.items())]})
        else:
            result = cache({"tools": [{"name": name, "annotations": _annotations(name), **spec} for name, spec in sorted(TOOL_SPECS.items())]})
    elif method == "tools/call":
        params = request.get("params", {})
        name = params.get("name")
        args = params.get("arguments", {})
        known = COMPACT_TOOLS if surface == "compact" else TOOL_SPECS
        if name not in known or not isinstance(args, dict):
            raise ValueError("Unknown tool or invalid arguments")
        try:
            value = _call_compact(service, name, args) if surface == "compact" else _call(service, name, args)
            result = _complete(_bounded(service, name, value))
        except Exception as exc:
            result = _complete(_error(exc))
    elif method == "resources/list":
        result = cache({"resources": [
            {"uri": "forge://docs/automation-fabric", "name": "Automation Fabric", "mimeType": "text/markdown"},
            {"uri": "forge://docs/toolchain-broker", "name": "Verified Toolchain Broker", "mimeType": "text/markdown"},
            {"uri": "forge://references/tool-catalog", "name": "Tool Catalog", "mimeType": "application/json"},
            {"uri": "forge://schemas/automation-job", "name": "Automation Job Schema", "mimeType": "application/json"},
            {"uri": "forge://schemas/fomod-plan", "name": "FOMOD Plan Schema", "mimeType": "application/json"},
            {"uri": "forge://docs/fomod", "name": "FOMOD Engineering", "mimeType": "text/markdown"},
            {"uri": "forge://docs/nexus-publication", "name": "Nexus Publication Gate", "mimeType": "text/markdown"},
            {"uri": "forge://schemas/nexus-publication-plan", "name": "Nexus Publication Plan Schema", "mimeType": "application/json"},
            {"uri": "forge://references/nexus-policy-lock", "name": "Nexus Policy Source Lock", "mimeType": "application/json"},
            {"uri": "forge://capabilities", "name": "Capability Registry", "mimeType": "application/json"},
            {"uri": "forge://docs/capability-matrix", "name": "Capability Matrix", "mimeType": "text/markdown"},
            {"uri": "forge://schemas/framework-plan", "name": "Framework Plan Schema", "mimeType": "application/json"},
            {"uri": "forge://docs/framework-engineering", "name": "Framework Engineering", "mimeType": "text/markdown"},
            {"uri": "forge://schemas/native-plugin-plan", "name": "Native Plugin Plan Schema", "mimeType": "application/json"},
            {"uri": "forge://docs/native-plugin-engineering", "name": "Native Plugin Engineering", "mimeType": "text/markdown"},
            {"uri": "forge://docs/papyrus-engineering", "name": "Papyrus Engineering", "mimeType": "text/markdown"},
            {"uri": "forge://references/framework-source-lock", "name": "Framework Source Lock", "mimeType": "application/json"},
            {"uri": "forge://references/native-source-lock", "name": "Native Source Lock", "mimeType": "application/json"},
            {"uri": "forge://config", "name": "Forge Configuration", "mimeType": "application/json"},
        ]})
    elif method == "resources/read":
        uri = request.get("params", {}).get("uri")
        if uri == "forge://docs/toolchain-broker":
            text = (_resource_root() / "docs" / "TOOLCHAIN-BROKER.md").read_text(encoding="utf-8")
            mime = "text/markdown"
        elif uri == "forge://references/tool-catalog":
            text = (_resource_root() / "references" / "TOOL-CATALOG.json").read_text(encoding="utf-8")
            mime = "application/json"
        elif uri == "forge://docs/automation-fabric":
            text = (_resource_root() / "docs" / "AUTOMATION-FABRIC.md").read_text(encoding="utf-8")
            mime = "text/markdown"
        elif uri == "forge://schemas/automation-job":
            text = (_resource_root() / "schemas" / "automation-job.schema.json").read_text(encoding="utf-8")
            mime = "application/json"
        elif uri == "forge://schemas/fomod-plan":
            text = (_resource_root() / "schemas" / "fomod-plan.schema.json").read_text(encoding="utf-8")
            mime = "application/json"
        elif uri == "forge://docs/fomod":
            text = (_resource_root() / "docs" / "FOMOD-ENGINEERING.md").read_text(encoding="utf-8")
            mime = "text/markdown"
        elif uri == "forge://docs/nexus-publication":
            text = (_resource_root() / "docs" / "NEXUS-PUBLICATION.md").read_text(encoding="utf-8")
            mime = "text/markdown"
        elif uri == "forge://schemas/nexus-publication-plan":
            text = (_resource_root() / "schemas" / "nexus-publication-plan.schema.json").read_text(encoding="utf-8")
            mime = "application/json"
        elif uri == "forge://references/nexus-policy-lock":
            text = (_resource_root() / "references" / "NEXUS-POLICY-LOCK.json").read_text(encoding="utf-8")
            mime = "application/json"
        elif uri == "forge://capabilities":
            text = json.dumps(service.capabilities(), indent=2, default=str)
            mime = "application/json"
        elif uri == "forge://docs/capability-matrix":
            text = (_resource_root() / "docs" / "CAPABILITY-MATRIX.md").read_text(encoding="utf-8")
            mime = "text/markdown"
        elif uri == "forge://schemas/framework-plan":
            text = (_resource_root() / "schemas" / "framework-plan.schema.json").read_text(encoding="utf-8")
            mime = "application/json"
        elif uri == "forge://docs/framework-engineering":
            text = (_resource_root() / "docs" / "FRAMEWORK-ENGINEERING.md").read_text(encoding="utf-8")
            mime = "text/markdown"
        elif uri == "forge://schemas/native-plugin-plan":
            text = (_resource_root() / "schemas" / "native-plugin-plan.schema.json").read_text(encoding="utf-8")
            mime = "application/json"
        elif uri == "forge://docs/native-plugin-engineering":
            text = (_resource_root() / "docs" / "NATIVE-PLUGIN-ENGINEERING.md").read_text(encoding="utf-8")
            mime = "text/markdown"
        elif uri == "forge://docs/papyrus-engineering":
            text = (_resource_root() / "docs" / "PAPYRUS-ENGINEERING.md").read_text(encoding="utf-8")
            mime = "text/markdown"
        elif uri == "forge://references/framework-source-lock":
            text = (_resource_root() / "references" / "FRAMEWORK-SOURCE-LOCK.json").read_text(encoding="utf-8")
            mime = "application/json"
        elif uri == "forge://references/native-source-lock":
            text = (_resource_root() / "references" / "NATIVE-SOURCE-LOCK.json").read_text(encoding="utf-8")
            mime = "application/json"
        elif uri == "forge://config":
            text = json.dumps(service.config_show(), indent=2, default=str)
            mime = "application/json"
        else:
            raise ValueError(f"Unknown resource URI: {uri}")
        result = cache({"contents": [{"uri": uri, "mimeType": mime, "text": text}]}, uri)
    elif method == "prompts/list":
        result = cache({"prompts": [
            {"name": "configure_verified_toolchain", "description": "Discover, import, hash-pin and resolve real installed Skyrim tools without bundling them publicly.", "arguments": [{"name": "source", "required": True}, {"name": "capability", "required": True}]},
            {"name": "verify_mod_release", "description": "Plan a Forge verification pipeline for a mod release.", "arguments": [{"name": "release_root", "required": True}]},
            {"name": "build_compatibility_patch", "description": "Plan a typed compatibility patch without GUI handoff.", "arguments": [{"name": "mod_a", "required": True}, {"name": "mod_b", "required": True}]},
            {"name": "build_fomod_installer", "description": "Plan a complete FOMOD installer with payload coverage and branch simulation.", "arguments": [{"name": "source_root", "required": True}, {"name": "module_name", "required": True}]},
            {"name": "prepare_nexus_release", "description": "Prepare a rights-mapped Nexus Mods publication bundle and block unsupported sharing claims.", "arguments": [{"name": "release_root", "required": True}, {"name": "mod_name", "required": True}, {"name": "version", "required": True}, {"name": "uploader", "required": True}]},
            {"name": "build_native_plugin", "description": "Plan a source-locked CommonLibSSE-NG DLL project and verification pipeline.", "arguments": [{"name": "project", "required": True}, {"name": "purpose", "required": True}]},
            {"name": "build_framework_config", "description": "Generate a typed source-locked SPID/KID/BOS/SkyPatcher/FLM configuration.", "arguments": [{"name": "profile", "required": True}, {"name": "purpose", "required": True}]},
        ]})
    elif method == "prompts/get":
        params = request.get("params", {})
        name = params.get("name")
        args = params.get("arguments", {})
        if name == "configure_verified_toolchain":
            prompt = f"Scan {args.get('source','<tool directory or ZIP>')} with forge_tool_scan. Select only a recognized exact-capability tool for {args.get('capability','<capability>')}. Import it into the private tool vault or configure it in place, verify the SHA-256 pin, then call forge_tool_resolve. Never copy a third-party executable into the Forge repository or a mod release, and never substitute a GUI executable for a CLI."
        elif name == "verify_mod_release":
            prompt = f"Create a skyrim-forge-automation/1 verify_release job for {args.get('release_root','<release>')}. Use xEdit only if configured. Do not claim Skyrim runtime validation."
        elif name == "build_compatibility_patch":
            prompt = f"Inspect {args.get('mod_a','<A>')} and {args.get('mod_b','<B>')}. Produce a typed Forge plugin plan or a fixed allowlisted xEdit job. Never leave the user in a GUI."
        elif name == "build_fomod_installer":
            prompt = f"Inspect staged payload {args.get('source_root','<payload>')} and create a skyrim-forge-fomod-plan/1 installer for {args.get('module_name','<module>')}. Require complete payload coverage, validate all branches, simulate selection groups, and build transactionally. Do not hand-edit XML or leave Vortex/MO2 work to the user."
        elif name == "prepare_nexus_release":
            prompt = f"Prepare {args.get('mod_name','<mod>')} {args.get('version','<version>')} from {args.get('release_root','<release>')} for Nexus Mods under uploader {args.get('uploader','<uploader>')}. Refresh only official Nexus policy sources, create a typed Nexus publication plan, map every bundled file to rights and permission evidence, verify credits, game terms, DP eligibility, content classification, binaries, network behavior, AI disclosure and claim evidence, obtain the uploader attestation, run forge_nexus_audit, then use forge_nexus_build. Never invent permission or sign on the uploader's behalf."
        elif name == "build_native_plugin":
            prompt = f"Design {args.get('project','<plugin>')} for {args.get('purpose','<purpose>')} using forge_capabilities first. Create a skyrim-forge-native-plugin-plan/1 file, choose exactly one runtime strategy based on evidence, scaffold with forge_native_scaffold, audit the project, build only with hash-pinned CMake/vcpkg tools into Forge staging, audit the DLL, and require real SKSE/Skyrim testing before claiming runtime compatibility."
        elif name == "build_framework_config":
            prompt = f"Build a {args.get('profile','<profile>')} configuration for {args.get('purpose','<purpose>')}. Use the exact source-locked profile, create a typed framework plan, validate and build it with Forge, preserve unknown/version-specific syntax as unverified rather than rewriting it, and treat runtime logs as stronger evidence than static lint."
        else:
            raise ValueError(f"Unknown prompt: {name}")
        result = _complete({"description": name, "messages": [{"role": "user", "content": {"type": "text", "text": prompt}}]})
    else:
        raise ValueError(f"Unsupported method: {method}")
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def serve(config_path: str | None = None, surface: str = "full") -> None:
    service = ForgeService(load_config(config_path))
    for raw in sys.stdin:
        if not raw.strip():
            continue
        request_id = None
        try:
            request = loads(raw)
            request_id = request.get("id") if isinstance(request, dict) else None
            response = handle(service, request, surface)
            if response is not None:
                sys.stdout.write(json.dumps(response, ensure_ascii=False, separators=(",", ":"), default=str) + "\n")
                sys.stdout.flush()
        except Exception as exc:
            response = {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32603, "message": str(exc), "data": {"type": type(exc).__name__}}}
            sys.stdout.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
            sys.stdout.flush()
