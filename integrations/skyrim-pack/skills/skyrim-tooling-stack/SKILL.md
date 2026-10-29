---
name: skyrim-tooling-stack
description: Choose Skyrim Forge for typed offline jobs and houseCARL for live load-order evidence; keep generic AI tooling with its own owner.
metadata:
  version: 6.2.0
---

# Skyrim tooling stack

Forge owns this specialist index. The general `ai-tooling-stack` skill belongs to the Ultimate AI Starter Bundle; do not overwrite it with Skyrim instructions.

## Choose the evidence source

| Need | Tool and boundary |
|---|---|
| Installed winner, conflict tree, MO2 VFS or live patch plan | houseCARL MCP first. If it is unavailable: `forge load-order` + `forge record-conflicts` (byte-level winners and changed subrecords from the same MO2 profile; no field schema, no VFS asset view) |
| Start Game Enabled quest SEQ file | houseCARL `write_seq`, or `forge seq-build` (checked against 257 shipped SEQ files) |
| Offline plugin headers/queries, bounded typed writes, framework lint, FOMOD, release gates | Forge CLI; exact capability comes from `forge capabilities` |
| Papyrus compile/decompile, xEdit, BSA operations | Forge's configured hash-pinned adapters; inspect `tool-resolve` first |
| Native SKSE project builds | Forge scaffold/build plus installed CMake/vcpkg/VS; project pins stay intact |
| Collision report | Existing configured DeadMesh dmscan; static findings need runtime review |
| Other editor, mesh, LOD, animation or save workflow | Discover the actual tool, then its exact worker/API; catalog presence is not a runner |
| General code navigation, browser tools or context/cost tools | General bundle `ai-tooling-stack` and task-scoped discovery; optional to Forge |

## Standalone setup and reuse

Run Forge's own `START-HERE.bat` or `Install-AI-Bridge.ps1 -BootstrapPython -Provider All -WithHouseCarl`. Forge reuses `UABS_PYTHON` and healthy app venvs. The official shared install manager bootstraps a runtime only when no compatible base exists; managed bases receive patch updates on the same feature line. Manual bases stay intact with an explicit update-unverified result.

Use the installed `INSTALLATION.json` CLI/MCP arrays rather than guessing machine paths. `Update Forge.bat` selects the latest stable owner release, verifies its GitHub SHA-256 digest and archive manifest, keeps newer installs and Git development roots, and retains a rollback backup. Provider model/reasoning settings are not toolchain settings.

When Reverse THIS! is installed, Forge can configure its existing texconv and 7-Zip without copying them: `forge tool-reuse-reverse --approve`. The owner's receipt supplies bounded paths; Forge pins actual executable bytes. Subsequent runs refresh only Forge's recorded automatic bindings, preserving personal paths and pins.

## MCP availability

Installed and enabled are different states. If the current host has the toolbox, discover the requested Skyrim capability with the project path, describe its live schema and call it. Otherwise use the installed Forge CLI while checking provider scope/trust and the real MCP handshake. Do not recommend reinstalling a binary merely because deferred tool search returned no matches.

houseCARL is the primary builder for load-order work and Forge is its independent fallback: `docs/HOUSECARL-PARITY.md` lists every houseCARL tool against Forge's equivalent with its covered/partial/missing status and the roadmap. Use houseCARL first; when it is down, say so, use the Forge column, and name what that route cannot prove. Forge's public release never contains imported third-party tools, game/compiler files, saves, personal profiles or credentials. Game Data, mod-manager staging and saves are read-only unless an explicit scoped deployment was authorized.
