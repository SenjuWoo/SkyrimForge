<p align="center">
  <img src="assets/mark.svg" width="72" height="72" alt="Skyrim Forge">
</p>

<div align="center">

# Skyrim Forge 6.11.3

**Typed, safety-first Skyrim SE/AE mod engineering for AI agents — offline, free, MCP-ready.**

<p>
  <a href="https://github.com/SenjuWoo/SkyrimForge/actions/workflows/ci.yml"><img src="https://github.com/SenjuWoo/SkyrimForge/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-8EC8E8?labelColor=0d1117" alt="MIT License"></a>
  <a href="https://github.com/SenjuWoo/SkyrimForge/releases/latest"><img src="https://img.shields.io/github/v/release/SenjuWoo/SkyrimForge?label=release&color=8EC8E8&labelColor=0d1117" alt="latest release"></a>
  <img src="https://img.shields.io/badge/python-%3E%3D3.11-8EC8E8?labelColor=0d1117" alt="Python 3.11+">
</p>

<p>
  <a href="#install">Install</a>
  ·
  <a href="#what-it-does">Capabilities</a>
  ·
  <a href="#free-assets">Free assets</a>
  ·
  <a href="#skill-pack">Skill pack</a>
  ·
  <a href="#maintenance">Maintenance</a>
  ·
  <a href="CHANGELOG.md">Changelog</a>
</p>

</div>

<p align="center">
  <img src="assets/hero.svg" alt="Skyrim Forge workbench" width="100%">
</p>

Skyrim Forge is a local workbench and MCP server that lets an AI build Skyrim mods without clicking through SSEEdit, Creation Kit, Wrye Bash, LOOT or Mod Organizer 2. A job is typed JSON: Forge validates it, runs only hash-pinned adapters, reopens what it can verify, and reports exactly what was and was not proven.

It runs **outside** the game and never installs into `Data`. Live game files, saves, MO2/Vortex staging and profiles are read-only inputs; every write lands in a Forge workspace behind an explicit approval. It is not the in-game SKSE C# framework at [docs.skyrimforge.net](https://docs.skyrimforge.net/).

## Install

| Path | What happens |
|---|---|
| **Standalone** | Download `Skyrim-Forge-<version>.zip` from [Releases](https://github.com/SenjuWoo/SkyrimForge/releases/latest), check it against `SHA256SUMS.txt`, extract it, rename the folder to something stable such as `SkyrimForge`, then run `START-HERE.bat` inside it. That folder **is** the install root. |
| **With the bundle** | The [Ultimate AI Starter Bundle](https://github.com/SenjuWoo/Ultimate-AI-Starter-Bundle) extracts the latest digest-verified release to `%LOCALAPPDATA%\Skyrim-Tools\Skyrim-Forge` and never downgrades a newer local install. |

Setup bootstraps a durable Python runtime, installs the Forge skill and the 50-skill Skyrim pack into every detected AI app, and registers the MCP server. It needs no admin rights. Re-running `START-HERE.bat`, `Update Forge.bat` or `Install-or-Update.ps1` updates that same folder in place, so a version-stamped extraction folder is safe as long as you keep its name: every AI client stores the MCP command as an absolute path. `SKYRIM_FORGE_ROOT` records the folder for other processes.

```powershell
.\forge doctor            # core health, venv durability, tool readiness
.\forge capabilities      # direct / profiled / adapter / worker / human gate
```

`forge.cmd` beside the install runs the bundled interpreter, so no PATH edit or venv activation is needed. `Forge Doctor.bat` opens the same report.

## What it does

| Capability | Command surface | Evidence |
|---|---|---|
| Plugin headers, records, FormIDs, load order, conflicts | `plugin-info`, `record-query`, `load-order`, `record-conflicts` | Forge parser; not xEdit |
| Typed plugin output (KYWD/GLOB/FLST/OTFT) | `plugin-plan-validate`, `plugin-build` | Transactional workspace writes |
| Papyrus analysis and compile | `papyrus-analyze`, `papyrus-compile` | Official compiler; fresh PEX verified, not runtime |
| SPID / KID / BOS / SkyPatcher / CDF lint and build | `lint`, `framework-plan-validate`, `framework-build` | Source-locked grammar; unknown tokens stay unverified |
| Static findings vs framework logs | `framework-correlate-logs` | `RUNTIME_VERIFIED_PASS` only for a named file and row |
| FOMOD 5.0 generation and simulation | `fomod-*` | Every `SelectExactlyOne`/`SelectAtMostOne` branch extracted into an MO2/Vortex-shaped sandbox; other group types are reported as uncovered, never claimed as tested |
| Archives, release trees, deterministic ZIPs | `bsarch-*`, `release-*` | Payload hashes and manifest |
| Nexus publication gate | `nexus-*` | File-level rights, credits, licences, AI disclosure; the uploader signs |
| Voice containers (FUZ/XWM/WAV/LIP) | `audio-*`, `voice-path-validate` | Container bytes; codec and lip-sync stay external |
| SKSE DLL inspection | `skse-inspect-pe`, `skse-audit-imports`, `skse-verify-reproducible` | PE32+ bytes; never loaded |
| Native CommonLibSSE-NG projects | `native-scaffold`, `native-build`, `native-audit` | Source-locked scaffold, pinned tools |
| xEdit fixed scripts, LOOT, Wrye Bash, Creation Kit | `automation-*` | Allowlisted scripts or pinned workers; completion markers required |
| Procedural textures | `texture-generate`, `texture-inspect` | DDS bytes and a PNG preview |
| Cleanup and drift detection | `maintain` | Forge-owned paths only; dry-run by default |

`forge doctor` reports separate readiness levels: `read_only_ready`, `plugin_write_ready`, `xedit_automation_ready`, `mo2_automation_ready`. A missing external tool does not make the core install broken.

## Free assets

`texture-generate` writes deterministic DDS files — BC1, BC3 or A8R8G8B8, full mip chains — from solid, checker, gradient, seeded-noise, brick and tangent-space-normal patterns, with an optional PNG preview. No paid tool, no network, no new dependency.

```powershell
.\forge texture-generate bricks mod/Textures/Stone.dds --size 512 --preview mod/Stone.png --approve
.\forge texture-generate normal mod/Textures/Stone_n.dds --strength 0.12 --flip-green --approve
```

Meshes stay with Blender, hand art with GIMP or Krita, BC7 with `texconv`. [docs/ASSET-GENERATION.md](docs/ASSET-GENERATION.md) maps every remaining gap to a free tool and its licence.

## Skill pack

Forge owns the **50-skill Skyrim SE/AE pack** (`integrations/skyrim-pack/`): router, memory, versioned workspace, SPID/KID/SkyPatcher/OAR/CDF grammar, Papyrus, NIF/DDS, FOMOD, Nexus publishing, diagnostics and houseCARL. It ships **inside this repository**, so a standalone Forge install gets the whole pack without the bundle.

```powershell
.\Install-Skyrim-Pack.ps1 -Provider All -WithHouseCarl
```

The pack's `skyrim-tooling-stack` decides between Forge, houseCARL and external tools. `houseCARL 2.1.2` setup and the Vortex load-order shim live at `integrations/skyrim-pack/skills/housecarl/scripts/Setup-HouseCarl.ps1`.

## Maintenance and updates

```powershell
.\forge maintain                    # report stale Forge-owned files and moved roots
.\forge maintain --apply --approve  # delete the reported leftovers
.\forge maintain --fix-roots --approve  # write a discovered Skyrim/Vortex path into config
```

`maintain` removes only paths Forge can prove it owns: spill files and sandbox runs older than a week under `<workspace>\.forge`, and provider skill backups beyond the newest two. It reports the self-test, flags configured roots that moved with the discovered replacement, and never touches a mod, a tool install or a user file. See [docs/MAINTENANCE.md](docs/MAINTENANCE.md).

Updates are explicit: `Update Forge.bat` or `Update-Forge.ps1 -CheckOnly`. The updater verifies the release digest, keeps the newest two backups and rolls back on any failure. A weekly **Ecosystem contract check** verifies the bundle's `skyrim-forge` catalog entry, this repository's release assets and Reverse THIS!'s receipt shape without copying either project's version.

## MCP

Forge serves the current **MCP `2026-07-28`** revision and the `initialize` handshake older clients still use, from one process. The full surface exposes 68 tools with annotations; `--surface compact` exposes four orthogonal tools for hosts with a server-slot or token ceiling. Oversized results spill to a workspace artifact instead of being truncated, and Grok's 8-server limit is handled by skipping registration rather than taking the last slot. See [docs/MCP.md](docs/MCP.md).

## Safety and evidence

- Live `Data`, saves, profiles, archives and manager staging are read-only; outputs stay in the workspace.
- Writes require explicit approval; subprocesses use argument arrays and `shell=False`.
- External tools are selected by exact capability and a SHA-256 pin; nothing third-party ships in this repository or a release.
- Static checks, compiler acceptance, PE parsing and xEdit output are labelled separately from Skyrim runtime evidence.
- No check in this repository claims that a mod works in game.

[docs/SAFETY.md](docs/SAFETY.md) · [docs/LIMITATIONS.md](docs/LIMITATIONS.md) · [docs/CAPABILITY-MATRIX.md](docs/CAPABILITY-MATRIX.md)

## Docs

| Doc | Contents |
|---|---|
| [INSTALLATION](docs/INSTALLATION.md) | install roots, venv durability, provider registration |
| [MCP](docs/MCP.md) | surfaces, protocol eras, bounded output, registration |
| [MAINTENANCE](docs/MAINTENANCE.md) | cleanup rules, root drift, weekly upkeep |
| [AGENTS](AGENTS.md) | preflight, edit/test loop, release runbook for AI agents |
| [TOOLCHAIN-BROKER](docs/TOOLCHAIN-BROKER.md) | hash-pinned tools, vault, capability matching |
| [ASSET-GENERATION](docs/ASSET-GENERATION.md) | procedural DDS and the free-tool map |
| [AUDIO-ENGINEERING](docs/AUDIO-ENGINEERING.md) | FUZ/XWM/WAV/LIP, voice layout |
| [PAPYRUS-ENGINEERING](docs/PAPYRUS-ENGINEERING.md) | analysis and compile evidence |
| [NEXUS-PUBLICATION](docs/NEXUS-PUBLICATION.md) | the rights and publication gate |
| [WHICH-AI-SHOULD-I-USE](docs/WHICH-AI-SHOULD-I-USE.md) | task-to-assistant routing |
| [prompts](docs/prompts/README.md) | copy-paste Skyrim prompt packs |

## Status

CI runs Python 3.11/3.13/3.14 on Windows and Ubuntu, the native writer on both, a reproducible repository gate, CodeQL and the Windows installer/legacy-migration path. Releases are built from the exact commit whose checks passed and carry `MANIFEST.json`, `SBOM.spdx.json`, `BUILD-RECEIPT.json`, `VALIDATION.json` and `SHA256SUMS.txt`.

Not claimed: gameplay results, in-game visuals, or that any static check replaces a real Skyrim session. The [CHANGELOG](CHANGELOG.md) and [STATE](STATE.md) record what each release actually verified.

Forge is MIT licensed. The bundled houseCARL-derived skills keep their own GPL-3.0 licence and notices (`integrations/skyrim-pack/skills/housecarl/LICENSE`, `THIRD-PARTY-NOTICES.txt`). Ownership across Forge, the bundle and Reverse THIS! is stated once in the [bundle README](https://github.com/SenjuWoo/Ultimate-AI-Starter-Bundle#ownership).
