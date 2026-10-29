# MCM Helper — provenance and version facts

Verified 2026-10-29 against primary sources; re-derive when the installed version differs.

| Source | Revision |
|---|---|
| github.com/Exit-9B/MCM-Helper (code, schemas, `scripts/public/*.psc`) | `a303348` 2026-08-26 — `CMakeLists.txt`: **VERSION 1.6.3, PLUGIN_VERSION 15** (= `MCM.GetVersionCode()`) |
| GitHub releases | latest tagged **v1.6.2** (2026-04-26); 1.6.3 is on Nexus (file 53000) and in the repo |
| Wiki (`MCM-Helper.wiki.git`) | `5bb0f61` 2022-10-08 — older than the code; trust schema/source where they differ |
| Nexus "MCM Helper" (mod 53000) | 1.6.3, 2026-08-26 (installed on the reference machine) |

Release notes: 1.4.0 (code 13) `$schema` support, ShowMessage/ForcePageReset fixes, mod name taken from the
form's origin file (not the last overriding file), `scriptName` optional on single-script forms ·
1.5.0 (code 14) SkyrimSE 1.6.1130, MergeMapper, SkyrimVR ESL, FOMOD installer (ESP/ESL choice) ·
1.6.0 SkyUI v6 MCM, faster settings load, static VC++ runtime, crash fix on 0-item menus · 1.6.1 SkyUI
Equip Mode key · 1.6.2 first-init Papyrus error · 1.6.3 (code 15) SE 1.7.99 update. Wiki version tags:
`GlobalValue` 1.1.0/code 6, `SetMenuOptions` on enum 1.2.0/code 7, `minMcmVersion` code 9, `OnPageSelect`
1.3.0/code 11, `$schema` code 13.

## Source facts the docs do not state

- `ReaderHandler::ReadFile` → `rapidjson::Reader::Parse` with default flags over a `FileReadStream`:
  **no comments, no trailing commas, no BOM skipping**. Errors become an in-menu error page.
- Mod name = stem of `quest->sourceFiles.array->front()` (origin plugin), via MergeMapper's
  `GetOriginalFormID` when installed (`FormUtil::GetModName`).
- Only `MCM_ConfigBase` scripts registered in SkyUI's `ConfigManager._modConfigs` (plus resort
  `_modConfigsP1..9` / `_MainMenu`) are read.
- Settings: `key:Section` split at the first `:` (`find_first_of(':')`); no colon → "Section could not be
  resolved", not saved. `CommitModSetting` rewrites `Data/MCM/Settings/<Mod>.ini` on every change using
  `std::to_string` (floats `0.500000`, bools `1`/`0`).
- `ResetToDefault` restores the `settings.ini` value; `Property`/`GlobalValue` sources use `defaultValue`.
- Form strings: `plugin|hex` → `TESDataHandler::LookupForm(relativeID, plugin)`; light plugins mask the
  local id to 12 bits when generating identifiers.
- Group controls: `ContentHandler.cpp` assigns `GroupControl` only for `toggle` and `hiddenToggle` and
  registers them per page layout (`PageLayout::GroupControls`). The condition parser stores a single
  conjunction per object, so extra operator keys overwrite it.

## Schema vs. shipped reality (50 configs from the reference machine's `Data\MCM\Config`, 2026-10-29)

`scripts/validate_mcm.py` was tuned until it stopped rejecting working menus. Deviations seen in shipped,
working configs, therefore **tolerated** (INFO/WARNING, not errors):

- `"content": []` together with a `customContent` splash (also `"customContent": {}`) — the documented
  "mutually exclusive" rule is not enforced for an empty `content`.
- Top-level with neither `content` nor `customContent` (pages-only menus).
- Per-page `cursorFillMode` (the shipped SkyUI_SE config uses it; the schema omits it).
- `minMcmVersion` below the schema's minimum of 13 (support began at 9).
- `sourceType` on `text`/`menu`/`input` controls (deprecated/ignored).
- A `hiddenToggle` re-using a visible control's `id` to drive a group.
- `groupControl` on `enum`/`keymap` (parsed but ignored at runtime — a latent bug in those mods).
- Two operators in one `groupCondition` object (parser keeps the last conjunction).
- `settings.ini` booleans written `True`/`False`; unset key codes as `-1` in `u*` settings.
- `help`/`text` using nested translation templates (`$SKI_INFO1{$Medium}`), which are not whole-string keys.
- Text controls with non-`$` labels (most shipped menus are English-only).

Upstream schema quirks: `ignoreConflicts` is typed `"bool"` (should be `boolean`); `scriptName`/`propertyName`
are only allowed when `sourceType` is `PropertyValue*`; `sourceType` on string controls is `deprecated`.

## Related installed pieces (reference machine)

`MCMHelper.dll` (SKSE), `MCM-Unlocked.dll` (separate plugin), SkyUI, `SKSEMenuFramework` (separate ImGui menu
route, not MCM — see `skyrim-data-frameworks`). Detect the installed MCM Helper version from the Nexus/Vortex
staging name or `MCM.GetVersionCode()`; never assume.
