# Local Skyrim tool coverage

The catalog identifies actual tool names and permitted local treatment. It does not assert the latest upstream version, grant redistribution rights, or turn a worker contract into a tested direct runner. Public Forge releases contain no third-party executables.

| Tool / actual identity | Forge treatment and evidence |
|---|---|
| xEdit / SSEEdit.exe | Existing scripted direct adapter; [upstream](https://github.com/TES5Edit/TES5Edit), MPL-2.0 in the inspected distribution. Completion markers remain required. |
| BSArch.exe | Existing archive adapter; [source](https://github.com/TES5Edit/TES5Edit/blob/dev/BSArch.dpr). Exact executable hash and local configuration required. |
| Champollion.exe | Existing decompile adapter; [upstream](https://github.com/Orvid/Champollion). Configure in place because legacy releases need DLL/runtime sidecars and their CLI flags differ. Verify help for the selected hash; empty PSC output fails. |
| dmscan.exe / DeadMesh.exe | Existing folder scan adapter. Inspected local documentation also describes JSON single-mesh analysis, comparison/scorecard, screenshots and MCP; those newer contracts are not claimed as Forge runners. Local LICENSE forbids redistribution/repackaging without written author permission. Configure/import locally only. |
| resaverpp-cli.exe / ReSaverPP.exe | Recognized separately from legacy ReSaver.exe. Local README describes analysis, compare, report and decompile CLI options; local LICENSE/NOTICE state Apache-2.0. The port's exact upstream release/source provenance is not yet established, so only existing-install configuration and a worker contract are exposed. [Original FallrimTools attribution](https://github.com/mdfairch/FallrimTools) is not proof of this port's binary provenance. No save is edited by discovery. |
| PGPatcher.exe / pgtools.exe | Both actual identities recognized; GUI and unverified CLI worker are distinct. No exact CLI source lock or redistribution permission established. |
| EasyNPC.exe | Existing-install GUI identity for NPC/FaceGen work. No fabricated headless runner; permissions must be checked upstream before redistribution. |
| TextureAnalyzer.exe | Existing-install GUI identity for VRAM/texture inspection; no verified CLI/version/license claim. |
| Bethini.exe | Existing-install GUI identity; [documented download](https://www.nexusmods.com/site/mods/631/). Inspected local license is CC-BY-NC-SA-4.0. Its documented option disabling backups is not a silent INI automation contract. |
| NIF Performance Analyzer MO2 plugin | Python `__init__.py` declares `mobase.IPluginTool` / `createPlugin`, imports PyQt6, and identifies the analyzer. Discovery reports the MO2 plugin directory separately. It is not NIFAnalyzer.exe and not a standalone CLI; license/upstream provenance unverified. |
| Cathedral Assets Optimizer / Sniff / ESLifier | Existing profiled or GUI catalog entries. Preserve actual runtime sidecars; profile/CLI and permission boundaries still apply. |
| Synthesis.exe / Synthesis.Bethesda.CLI.exe | GUI is never substituted for the dedicated pipeline CLI. A successful run requires a fresh parseable plugin. [Upstream](https://github.com/Mutagen-Modding/Synthesis). |
| xLODGen / TexGen / DynDOLOD | Existing configured/profiled or worker workflows; each stage requires its correct executable and workspace output. [DynDOLOD docs](https://dyndolod.info/). Static output inspection does not prove in-game LOD quality. |
| Wrye Bash / CK / Papyrus compiler | Existing worker/configure-only workflows. [Wrye source](https://github.com/wrye-bash/wrye-bash). Bethesda compiler/game files remain in the user's legal installation. |
| papyrus.exe (russo-2025 papyrus-compiler) | Catalog `papyrus_compiler_fast`, worker contract, MIT, [upstream](https://github.com/russo-2025/papyrus-compiler). Open-source V compiler: `papyrus compile -i <src> -o <out> -h <headers>`, `-check` for syntax only, `read`/`disassembly` for PEX. Useful for a quick syntax pass; `papyrus-compile` still uses the official Creation Kit compiler. Not auto-discovered (the file name is generic); configure it explicitly. |
| PCA SE.exe (Papyrus Compiler App SE) | Catalog `pca_se`, human gate. Electron GUI front end; Forge never drives it. |
| hkxcmd.exe | Catalog `hkxcmd`, worker contract. Havok convert/inspect CLI shipped in Cathedral Assets Optimizer's `bin` (Nemesis carries its own copy). No Forge runner. |
| Grass Cache Generator (NGIO-NG front end) / Output Rerun Wizard | Python/PowerShell personal workflows, not catalog executables. Grass Cache Generator launches the game repeatedly, edits `Data\SKSE\Plugins\GrassControl.ini` (one-time `.original-backup`), creates `PrecacheGrass.txt` and writes `Data\Grass\*.cgid`. Output Rerun Wizard walks the output run order (MisMatchR, ParallaxR, BENDr, PGPatcher, VRAMr, xLODGen, grass cache, TexGen, DynDOLOD) and toggles manager output mods. Both change live game state, so Forge only documents them; run them yourself. |

Version metadata, folder names and local README claims are evidence for discovery, not currency or runtime proof. Small open-source tools can be considered for a future explicitly licensed dependency package after exact upstream provenance/obligations are verified; this release retains the existing no-public-binary policy. Unknown/proprietary tools stay discover/configure-only or private local imports where supported.

## Native plugin development additions

- **CLibDT**: the supplied Windows executable has PE product/file version 6.0.0 and ships GPL-3.0-only plus third-party notices. It is a Skyrim project GUI, so Forge owns its discovery/configuration. The public [author toolkit](https://github.com/Supertron42/ClibDT_CommonLibSSE_NG_VR_Toolkit) describes an older Python implementation and links a Nexus download; it does not establish the supplied native binary's source revision. Configure the existing file with `forge tool-configure clibdt "<actual ClibDT.exe>" --approve`. No automatic source substitution, unknown CLI execution or public binary redistribution is performed.
- **Pinned CommonLib sources**: `forge sdk-install` fetches the maintained alandtse CommonLibSSE-NG, and with `--all` the libxse and powerof3 lineages, into the private SDK vault by commit SHA instead of relying on the incomplete archives below.
- **CommonLibSSE main**: the supplied source identifies [libxse/commonlibsse](https://github.com/libxse/commonlibsse), Xmake 3.0+ and C++23. Its `lib/commonlib-shared` submodule directory is empty in the downloaded archive. Use a recursive Git clone in the plugin's own workspace, pin the chosen commit and submodule revisions, then follow that revision's `xmake.lua`. An archive folder alone is not a complete SDK installation.
- **CommonLibSSE dev**: the supplied source identifies [powerof3/CommonLibSSE dev](https://github.com/powerof3/CommonLibSSE/tree/dev), a CMake build requiring `commonlib-shared` and `spdlog` (its README blob exactly matches that upstream; the inherited dann1 CI badge is stale); its AE option defaults off. Inspect the selected revision's actual presets, dependency manifest and runtime options. Do not replace it with the Xmake fork or assume equivalent SE/AE/VR coverage.
- Both supplied CommonLib trees carry GPL-3.0-or-later with their own modding/linking exceptions. Keep the exact selected license and exception texts with the project; older MIT examples do not describe these snapshots. The libraries are project dependencies, not globally auto-updated executables.
- **Xmake** is a general build system owned by the Starter Bundle's shared compiler suite, reused by Forge when a selected native project needs it. Forge remains standalone: install the official shared Xmake package and a compatible C++ toolchain without requiring the bundle. No downloaded library, game SDK or personal project is copied into Forge releases.

## Observed reference install (2026-11-03)

What one maintainer's tools root actually held, by folder, with PE version or the version the tool reports. Discovery uses executable names, not these folder names, and a version here is evidence, not a currency claim.

| Folder | Executables (version) | Kind | Forge catalog id |
|---|---|---|---|
| Bethini Pie | Bethini.exe | GUI | `bethini` |
| Cathedral Assets Optimizer | Cathedral_Assets_Optimizer.exe; bin\hkxcmd.exe (1.4) | GUI + CLI | `cathedral_assets_optimizer`, `hkxcmd` |
| CommonLibSSE-dev / CommonLibSSE-main | source trees (powerof3 dev CMake; libxse Xmake) | library source | SDK vault (`sdk-install`) |
| DeadMesh - MOPP Collision Validator | DeadMesh.exe (1.8.0), dmscan.exe | GUI + CLI | `deadmesh_gui`, `deadmesh_cli` |
| DynDOLOD | DynDOLODx64.exe, TexGenx64.exe (2.97), Edit Scripts\LODGenx64.exe (3.0) | profiled | `dyndolod` |
| EasyNPC's | EasyNPC.exe (0.9.6) | GUI | `easynpc` |
| ESLifier | ESLifier.exe, bsarch\BSArch.exe | GUI + CLI | `eslifier`, `bsarch` |
| Grass Cache Generator 1.0.0 | Generate Grass Cache.bat, grass_cache_generator.py | live-state workflow | none (documented above) |
| houseCARL | houseCARL-Setup.exe, housecarl\server\housecarl-mcp.exe (2.1.2 install pin, needs .NET 10 x64; bundled skill snapshot 2.1.1) | MCP server | `housecarl` skill; parity in `HOUSECARL-PARITY.md` |
| NIF Analyzer | MO2 Python plugin (`__init__.py`, mobase/PyQt6) | MO2 plugin | reported as `nif_analyzer_mo2_plugin` |
| Output Rerun Wizard | OutputRerunWizard.ps1, config.json, run order | live-state workflow | none (documented above) |
| Papy edits | Champollion-V1.0.1-x64\Champollion.exe (1.0.1); Papy compiler app\PCA SE.exe (5.8.0); papyrus-compiler\papyrus.exe (russo) with a copy of the CK compiler under `Original Compiler`; framework `.psc` sources (SKSE 2.2.8 / runtime 1.6.1170, po3 Papyrus Extender, PapyrusUtil, JContainers, Papyrus Tweaks, Andrealphus) | CLI + GUI + sources | `champollion`, `pca_se`, `papyrus_compiler_fast` |
| PGPatcher | PGPatcher.exe, pgtools.exe (2.3.1) | GUI + CLI | `pgpatcher`, `pgtools` |
| ReSaverPP | ReSaverPP.exe, resaverpp-cli.exe (19.6) | GUI + CLI | `resaverpp_gui`, `resaverpp_cli` |
| Sniff | Sniff.exe (1.9) | GUI | `sniff` |
| SSEEdit 4.1.5f | SSEEdit.exe, SSEEditQuickAutoClean.exe (4.1.5), Edit Scripts\Texconv | scripted CLI | `xedit`, `texconv` |
| Synthesis | Synthesis.exe (0.36.5) only; no `Synthesis.Bethesda.CLI.exe` | GUI | `synthesis_gui` (the CLI pipeline needs the separate CLI build) |
| Vram Texture Analyser | TextureAnalyzer.exe | GUI | `texture_analyzer` |
| Wyre Bash | Wrye Bash 316 installer only (not installed) | installer | `wrye_bash` after install |
| xLODGen | xLODGenx64.exe (4.1.5), Edit Scripts\LODGenx64.exe (3.0.36) | profiled | `xlodgen` |
| zOlder | SSE NIF Optimizer.exe (superseded by Cathedral Assets Optimizer) | legacy GUI | `nif_optimizer` |
| (root files) | `Exclusions.mod` (texture exclusion patterns), `PGgenmeshblacklist.txt` (PGPatcher mesh blacklist) | tool settings | none |

The official Papyrus compiler is the one beside the game (`<game>\Papyrus Compiler\PapyrusCompiler.exe`, installed with the Creation Kit); `discover-tools` now prefers it, together with `<game>\CreationKit.exe`, over copies elsewhere. Its imports are the Creation Kit's `Data\Scripts\Source` plus each framework's own `.psc` sources.
