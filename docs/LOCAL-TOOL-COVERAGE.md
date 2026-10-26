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
| Grass cache generator / personal output-rerun scripts | Document/discover at task time; not automatically imported. Such scripts may edit live GrassControl.ini, Data/Grass, manager enablement and game process state. They require a separate scoped deployment/runtime workflow. |

Version metadata, folder names and local README claims are evidence for discovery, not currency or runtime proof. Small open-source tools can be considered for a future explicitly licensed dependency package after exact upstream provenance/obligations are verified; this release retains the existing no-public-binary policy. Unknown/proprietary tools stay discover/configure-only or private local imports where supported.
