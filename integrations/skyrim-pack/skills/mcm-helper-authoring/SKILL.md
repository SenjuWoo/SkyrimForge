---
name: mcm-helper-authoring
description: Use when creating, editing, fixing, or auditing an MCM Helper in-game menu (MCM\Config\<Mod>\config.json, keybinds.json, settings.ini, MCM_ConfigBase quest script, translations) for Skyrim SE/AE.
---

# MCM Helper Authoring

## Overview

MCM Helper (Exit-9B) is an SKSE plugin that builds SkyUI Mod Configuration Menus from JSON instead of
hand-written Papyrus `AddToggleOption`/`OnOptionSelect` code. A menu is: **a quest carrying a script that
extends `MCM_ConfigBase`** (registers with SkyUI) + **`Data\MCM\Config\<ModName>\config.json`** (layout) +
optional **`settings.ini`** (defaults) + optional **`keybinds.json`**. User values live in
`Data\MCM\Settings\<ModName>.ini`. This is the default for every new menu; `SKI_ConfigBase` stays legacy
maintenance (see `skyrim-papyrus-modding`).

It is a **reference-lookup skill with a deterministic validator**: every key, enum and rule here is taken
from the schema, wiki and parser source listed in `references/MCM-HELPER-AUTHORITY.md`. Do not invent keys.

## First step — pick the references you need

1. `references/config-json.md` — file layout, top-level keys, all 12 control types, `valueOptions` per
   type, value sources, group conditions, actions. Read for any layout work.
2. `references/runtime.md` — quest/script/alias setup, how the mod name is derived, ModSettings vs
   Property vs GlobalValue, the Papyrus API and events, hotkeys, localization, packaging, failure modes.
3. `references/templates.md` — a complete minimal menu (script + config + settings + keybinds +
   translations) to copy and adapt.
4. `references/MCM-HELPER-AUTHORITY.md` — provenance, version facts, upstream quirks. Read when a
   behaviour is disputed or the installed version differs.
5. Exact Papyrus signatures: `papyrus-reference` → `references/mcmhelper.md` (generated from the
   installed scripts).

Grep `references/index.jsonl` to jump straight to a topic.

## Workflow — new menu

1. **Verify installed reality.** MCM Helper and SkyUI present (`MCMHelper.dll`, `MCMHelper.esp`,
   `Scripts\MCM_ConfigBase.pex`); note the version. Use houseCARL/Forge to read the plugin's quest and
   masters; never guess FormIDs.
2. **Decide storage per setting** (`runtime.md` §Storage): ModSetting (`settings.ini`, survives
   characters, shareable) vs Property (save-bound script variable) vs GlobalValue (save-bound, readable
   by conditions/scripts). One setting, one source.
3. **Write the quest + script.** `Scriptname <X> extends MCM_ConfigBase`; quest has a reference alias named
   `PlayerAlias` filling the player with `SKI_PlayerLoadGameAlias` attached. Create the quest form first
   (OK the dialog) *then* attach scripts — attaching earlier crashes the CK.
4. **Write `config.json`** with `$schema`, `modName` (= the plugin that **owns the quest**, no extension;
   must equal the folder name), `displayName`, and `content` or `pages`. Give every control that must
   store a value or raise `OnSettingChange` an `id`.
5. **Write `settings.ini`** for every ModSetting id: `[Section]` + `key=value`, id is `key:Section`; the
   first letter of the key is the type (`b f i r s u`).
6. **Hook Papyrus.** React in `OnSettingChange(string a_ID)` (needs the control `id`) or give the control
   an `action`. Mirror ModSettings into your gameplay script on `OnConfigInit` and on change.
7. **Localize.** Every user-facing string is a `$Key`; add `Interface\Translations\<Plugin>_<LANGUAGE>.txt`
   (UTF-16 LE with BOM) for every language you ship — there is no fallback to ENGLISH.
8. **Validate** (below), compile the script against the installed `Source\Scripts`, then runtime-test:
   open the menu, change each control, reload a save, and read `MCMHelper.log` in the SKSE log folder
   (`…\My Games\Skyrim Special Edition\SKSE\`).

## Workflow — edit or repair an existing menu

Read the quest script, `config.json`, `settings.ini` and `Settings\<Mod>.ini` together. Preserve every
`id` (renaming one orphans the player's saved value and any script that reads it). Keep the SKI version
number discipline: bump `GetVersion()` and handle `OnVersionUpdate` when script variables change. Do not
migrate a legacy `SKI_ConfigBase` menu to MCM Helper without a save/configuration migration plan.

## Hard rules (each one is a silent-failure trap)

- **`config.json` is strict JSON.** The parser is RapidJSON with default flags: **no comments, no trailing
  commas, no BOM**. The wiki's `jsonc` blocks are documentation only. A parse error does not crash — the
  menu shows an *error page* containing the parse message.
- **`modName` = plugin file name without extension, of the plugin that defines the quest** (the quest's
  origin file, resolved through MergeMapper if present). Folder `MCM\Config\<modName>\` must match exactly.
  Moving the quest into another plugin silently detaches the menu.
- **Form references are `Plugin.ext|HEXID`** (e.g. `MyMod.esp|800`), the *local* ID without load-order
  byte; for ESL-flagged plugins the ID is the 12-bit local ID. `sourceForm`/`form` default to the config
  quest when omitted.
- **Only Auto properties are reachable** by `PropertyValue*` sources.
- **`id` format for ModSettings is `key:Section`**; no colon = "Section could not be resolved" warning and
  the value is never saved.
- **Translations only match whole strings**: `"$Hello"` translates, `"$Hello World"` does not.
- **Group condition ids are integers ≥ 1**; `groupControl` exists only on `toggle`/`hiddenToggle`.
- **Menu controls hold ≤128 options** and store a string; `enum`/`stepper` store an int index.
- Keep explicit adult content and identifiers intact where a menu exposes them; do not sanitize labels.

## Validation

```
python scripts/validate_mcm.py <mod-root-or-config-folder> [--strict]
```

Checks `config.json` (schema rules above), `keybinds.json`, `settings.ini` types/ids, id uniqueness, group
references, `$Key` coverage in every shipped translation file and translation encoding. Exit 0 = no
errors. Structural validity is **not** runtime proof: confirm in game (menu renders, values persist, hotkeys
fire, no `MCMHelper.log` errors).

## Notes

- MCM Helper is SE/AE/VR; VR needs the VR build. The FOMOD of MCM Helper chooses ESP vs ESL.
- `SetMenuOptions` works only on `menu` and `enum` controls; call `RefreshMenu()` after changing values
  inside `OnSettingChange`.
- `ShowMessage` and `ForcePageReset` are inherited from SkyUI `SKI_ConfigBase`; release 1.4.0 fixed them
  inside MCM Helper menus.
- A menu for a mod that has none needs its own plugin with its own config quest; because the name comes
  from the quest's plugin, the folder is named after that plugin, not after the mod being patched.
