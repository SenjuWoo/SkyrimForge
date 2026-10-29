---
name: skyrim-data-frameworks
description: Use when writing or auditing the config files of installed SKSE data frameworks not owned by SPID, KID, SkyPatcher, BOS, CDF or OAR skills - Light Placer, Anim Object Swapper, Enchantment Art Extender, Dynamic String Distributor, Sound Record Distributor, SKSE HTTP - or when locating the grammar authority for another installed framework.
---

# Skyrim data frameworks

## Overview

Many SKSE plugins are driven by small JSON/INI/YAML files that mod authors drop into `Data`. A wrong key fails
silently (the plugin logs and skips), so each framework here has a reference built from its **primary source**
(author wiki, shipped docs or Nexus description, plus shipped example files), with the version it was checked
against. Nothing is invented: where a grammar is not published, `references/authority-map.md` says where to read it.

Scope boundary: SPID/KID/SkyPatcher/BOS/CDF/OAR/FLM grammars live in their own skills
(`skyrim-frameworks-index` picks the owner). MCM menus: `mcm-helper-authoring`. Papyrus library APIs
(PapyrusUtil, JContainers, po3 extender, ConsoleUtil, Custom Skills...): `papyrus-reference`.

## First step — open the one reference you need

| Task | Reference |
|---|---|
| Attach real lights to meshes, actors, armor, spell FX; disable vanilla lights | `references/light-placer.md` |
| Swap AnimObjects (bread, tankard, sword on grindstone) per actor/inventory | `references/anim-object-swapper.md` |
| Different enchantment glow art per weapon type/enchantment | `references/enchantment-art-extender.md` |
| Replace or add game text without touching plugins (translations, rewrites) | `references/dynamic-string-distributor.md` |
| Swap sounds on weapons, spells, footsteps, regions, projectiles | `references/sound-record-distributor.md` |
| Call a local HTTP server from Papyrus (AI/NPC bridges) | `references/skse-http.md` |
| Another installed framework (Prisma UI, SKSE Menu Framework, DAV, OIF, CIF, DEF, MTD, Inventory Injector...) | `references/authority-map.md` |

Read only that file. Each starts with the checked version and the log file to read when something does not work.

## Workflow

1. **Confirm installed reality.** The DLL is present in `Data\SKSE\Plugins`, note its version (Vortex staging name,
   DLL properties or log header). Grammar below is dated; if the installed version is newer, re-check the source
   named in the reference before using a new feature.
2. **Resolve forms from the plugins, not memory.** Use houseCARL (`housecarl_records`) for the live load order;
   without it, `forge load-order` + `forge record-conflicts --editor-id X --signature SIG` (see
   `docs/HOUSECARL-PARITY.md`). EditorID references in several of these frameworks need powerofthree's Tweaks.
3. **Write the file** to the exact folder and filename pattern in the reference (pattern mistakes are the most
   common silent failure).
4. **Validate what can be validated** (strict JSON parse; the framework's own log after a launch). Structural
   checks are not runtime proof: load the game or save and read the framework's log in
   `Documents\My Games\Skyrim Special Edition\SKSE\`.
5. **Package** the files as runtime product files only, with the required masters/frameworks listed as
   requirements.

## Rules that apply to all of them

- Config files are consumed once at startup (Light Placer also supports `ReloadLP`); plan a restart per test.
- Last loaded wins is not universal: check each reference's conflict rule.
- Use plugin-qualified forms (`0x800~Mod.esp`, `Mod.esp|800`) for forms you do not own; EditorIDs only where the
  reference says they work and the dependency is listed.
- Do not edit a framework's own shipped example/default files; add your own file.
- Keep explicit adult content and identifiers intact where a config references them.
