# Installation

Extract the entire release, run `START-HERE.bat`, install Forge, configure core paths, then configure installed automation tools.

The installer creates a local virtual environment and a `.pth` pointer to the extracted source. No package-index download is required.

The venv base must be durable. `Install-or-Update.ps1` reads `.venv\pyvenv.cfg` and rebuilds from the Windows Python Launcher when `home` points into a provider cache (`codex-runtimes`, `.cache`, `AppData\Local\Temp`, `pipx`, uv cache) or no longer exists. `forge doctor` reports the same check as `virtualenv`; a cached base fails with `VENV_EPHEMERAL_BASE_PYTHON`, because that interpreter disappears when the provider prunes its runtime and every registered MCP client then fails to start.

Weekly upkeep: `forge maintain` prunes Forge-owned leftovers and reports moved roots; see `docs/MAINTENANCE.md`.

Each successful update keeps the newest two Forge-owned backups beside the install root and prunes older `.forge-backup-*` copies it can prove it owns. `scripts/Prune-ForgeBackups.ps1 -Parent <dir> -WhatIf` prints the plan; the owner-update log records `pruned=<n>`. Legacy `Skyrim-Forge.backup-*` directories are never touched.

Replace the whole Forge directory when changing major versions. Do not copy isolated scripts between versions.

## One live install, under Skyrim tools

Forge is a Skyrim tool. The live product is a versioned folder next to xEdit
and the rest of your tools:

```text
<Skyrim Tools>\Skyrim-Forge\     live install, SKYRIM_FORGE_ROOT, MCP venv
<Skyrim Tools>\SkyrimForge\            optional git clone (source only)
<Skyrim Tools>\Skyrim-Forge\Workspaces\   job staging
```

Never:

```text
%USERPROFILE%\Documents\SkyrimForge      agents clone GitHub here by habit
%USERPROFILE%\Documents\Skyrim Forge     old default workspace (product name, not an install)
```

`Install-or-Update.ps1` registers `SKYRIM_FORGE_ROOT` **before** `config-show`,
so a fresh install stages jobs under the live folder. If you run the installer
from Documents it warns. MCP must point at
`<SKYRIM_FORGE_ROOT>\.venv\Scripts\python.exe -m skyrim_forge mcp`.

Keep the last known-good release ZIP as rollback. Do not edit an installed
output in place when a git clone exists; edit the clone, then install into that
same folder (or a second folder for side-by-side testing, remembering that MCP
registration points at one absolute path).

## Claude Code 2026-07-28

Forge 5.1.5+ always emits `resultType: "complete"` on `tools/call`,
`prompts/get`, and `ping`. 5.1.4 advertised the modern revision and then
omitted that field, so Claude rejected every tool call. Fresh installs must
not pin 5.1.4.

## Grok MCP cliff

Grok wedges at **8 running** MCP servers. `Register-MCP.ps1` skips Grok when
adding Forge would cross that cliff (7 configured, or 6 while claude-mem's
`mcp-search` plugin still loads). Replacing an existing Forge entry is allowed.
Disable `mcp-search` with `grok mcp disable mcp-search` to free a slot.

### Startup parser gate

`START-HERE.bat` invokes `PowerShell-Parse-Gate.ps1` without forwarding `%~dp0` as a separate argument. The gate resolves its repository root from `$PSScriptRoot`, avoiding Windows trailing-backslash quote ambiguity. `START-HERE.bat --validate-only` runs this exact startup gate noninteractively for CI and diagnostics.

Standalone prerequisites, safe owner updates and shared tool reuse are documented in [STANDALONE-TOOLCHAIN.md](STANDALONE-TOOLCHAIN.md).
