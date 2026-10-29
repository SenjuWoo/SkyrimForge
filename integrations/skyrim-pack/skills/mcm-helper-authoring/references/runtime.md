# Runtime, Papyrus, hotkeys, localization, packaging

Sources: MCM-Helper wiki (`5bb0f61`, 2022-10-08), repo `a303348` (v1.6.3, version code 15): `scripts/public/*.psc`,
`src/ConfigStore.cpp`, `src/SettingStore.cpp`, `src/FormUtil.cpp`, `src/Json/ReaderHandler.cpp`.

## 1. Quest, script, alias (required)

1. Create the quest form in the CK (**OK the dialog first**, then attach scripts — attaching on the
   unsaved quest dialog crashes the CK, per the wiki).
2. Script:
   ```papyrus
   Scriptname MyMod_Config extends MCM_ConfigBase
   ```
3. Quest Aliases → new Reference Alias named `PlayerAlias`, Fill Type *Specific Reference* → `PlayerRef`
   (cell *any*) → script **`SKI_PlayerLoadGameAlias`**. It runs the per-load maintenance SkyUI needs;
   without it the menu never registers after a load.
4. Compile against SDK sources for `MCM_ConfigBase`, `SKI_ConfigBase`, `SKI_QuestBase`, `SKI_ConfigMenu`
   and `MCM`: repo `scripts/public/*.psc` (MCM-Helper) or the `MCM.SDK.7z` asset of release v1.5.0 (later
   releases ship only the runtime archive). The installed 1.6.3 mod ships only
   `Source\Scripts\SKI_ConfigMenu.psc` plus the `.pex` files, so put the SDK `.psc` on the compiler import
   path (Forge `papyrus.imports`).

## 2. How MCM Helper finds your menu (derived from source)

- Reads SkyUI's `SKI_ConfigManager._modConfigs`; every registered script that **is an `MCM_ConfigBase`**
  gets a `Data/MCM/Config/<name>/config.json` lookup. SkyUI-resort layouts (`_modConfigsP1..9`,
  `_MainMenu`) are handled too.
- `<name>` = stem of the **first source file of the quest form** (its originating plugin), mapped through
  MergeMapper if installed. So `modName`, the folder and the quest's plugin must all be the same name.
  Do not merge a plugin that carries a menu quest unless the merge map covers it.
- A parse failure builds a one-control **error page** showing RapidJSON's message and sets the menu's
  `ModName` display; the script's `Pages` property is overwritten from `config.json`'s `pages`.
- Keybinds are read for the same name from `keybinds.json`.
- Settings: defaults from every `Data/MCM/Config/<Mod>/settings.ini`, then user overrides from every
  `Data/MCM/Settings/*.ini`. The id `key:Section` is split at the first `:`.

## 3. Papyrus API (installed reference: `papyrus-reference/references/mcmhelper.md`)

`MCM_ConfigBase` events: `OnConfigInit()`, `OnConfigOpen()`, `OnConfigClose()`,
`OnPageSelect(string a_page)` (since code 11), `OnSettingChange(string a_ID)` (control must have `id`).
Functions: `RefreshMenu()`, `SetMenuOptions(string a_ID, string[] a_options, string[] a_shortNames = None)`,
`Get/SetModSetting{Int,Bool,Float,String}(string a_settingName[, value])`.
Inherited from `SKI_ConfigBase`: `ForcePageReset()`, `SetTitleText(string)`,
`ShowMessage(string, bool withCancel = true, string accept = "Accept", string cancel = "Cancel") → bool`,
`GetVersion()`, `OnVersionUpdate(int)`, properties `ModName`, `Pages`, `CurrentPage`.
Global `MCM` script (usable from any mod): `IsInstalled()`, `GetVersionCode()`,
`Get/SetModSetting*(string a_modName, string a_settingName[, value])`.

```papyrus
Event OnConfigInit()
    ; mirror settings into game state once
    MyGlobal.SetValue(GetModSettingFloat("fIntensity:Main"))
EndEvent

Event OnSettingChange(string a_ID)
    if a_ID == "fIntensity:Main"
        MyGlobal.SetValue(GetModSettingFloat(a_ID))
    endif
    RefreshMenu()          ; only if the script changed displayed values
EndEvent
```
Soft dependency from another mod: check `MCM.IsInstalled()` / `Game.GetModByName("MCMHelper.esp")` before
calling the global API; the function list is the only contract.

Version discipline: override `int Function GetVersion()` and handle `Event OnVersionUpdate(int aVersion)`
when script variables are added or renamed, so existing saves migrate.

## 4. Hotkeys — `MCM\Config\<Mod>\keybinds.json`

```json
{
  "$schema": "https://raw.githubusercontent.com/Exit-9B/MCM-Helper/main/docs/keybinds.schema.json",
  "modName": "MyMod",
  "keybinds": [
    { "id": "toggleThing", "desc": "$MyMod_ToggleThing",
      "action": { "type": "CallFunction", "form": "MyMod.esp|800", "scriptName": "MyMod_Config",
                  "function": "ToggleThing", "params": [] } },
    { "id": "globalMsg", "desc": "Msg",
      "action": { "type": "CallGlobalFunction", "script": "Debug", "function": "MessageBox", "params": ["Hi"] } },
    { "id": "consoleCmd", "desc": "Menus",
      "action": { "type": "RunConsoleCommand", "command": "ToggleMenus" } },
    { "id": "holdKey", "desc": "Hold",
      "action": { "type": "SendEvent", "form": "MyMod.esp|800", "scriptName": "MyMod_Config" } }
  ]
}
```
- Required: `modName`, `keybinds[]`, each with `id` and `action`. Unknown keys are errors.
- `CallFunction` and `SendEvent` **require** `form`; `CallGlobalFunction` requires `script`;
  `CallFunction`/`CallGlobalFunction` require `function`; `RunConsoleCommand` requires `command`.
- `SendEvent` raises `OnControlDown(string)` / `OnControlUp(string)` (the keybind `id`) on the form —
  use it to detect a held key.
- A `keymap` control with the same `id` (`"type":"keymap","id":"toggleThing"`) lets the user pick the key.
  Conflicts with game controls or other mods warn the user; `ignoreConflicts: true` suppresses the warning.
- Alternative without keybinds.json: a `keymap` backed by an int Property + `RegisterForKey`.

## 5. Localization

- All user text as `$Key`: control `text`, `help`, `displayName`, `pageDisplayName`, option lists,
  keybind `desc`. Non-`$` strings are legal but not translatable (schema warns).
- File: `Data\Interface\Translations\<PluginName>_<LANGUAGE>.txt` for each active plugin
  (e.g. `MyMod_ENGLISH.txt`). **UTF-16 LE with BOM.** Lines `$Key<TAB>Value`; `\n` for line breaks.
- Languages: CZECH ENGLISH FRENCH GERMAN ITALIAN POLISH RUSSIAN SPANISH JAPANESE. Only the current
  language file loads — **no fallback to ENGLISH**; ship every language you list, or copy ENGLISH into them.
- A whole string must equal a key: `"$Hello"` ✓, `"$Hello World"` ✗. Prefix long keys with your mod
  (`$MYMOD_Question1`); `{}` tokens nest runtime text (`$SKI_MSG2{}` pattern).
- Works from a BSA.

## 6. Packaging

```
Data/
  MyMod.esp                         (owns the config quest; name == modName)
  Scripts/MyMod_Config.pex
  Source/Scripts/MyMod_Config.psc   (optional)
  MCM/Config/MyMod/config.json
  MCM/Config/MyMod/settings.ini     (defaults)
  MCM/Config/MyMod/keybinds.json    (optional)
  Interface/Translations/MyMod_ENGLISH.txt  (+ other languages)
```
- Never ship `Data\MCM\Settings\*.ini` (user data) in a release; it overrides the player's choices.
- Requirements to list: SKSE, Address Library, SkyUI, **MCM Helper** (optionally with `pluginRequirements`).
  Version-gate with `minMcmVersion` only for features you use (`$schema`/hotkeys need ≥13).
- Patches for another mod's settings = `settings.ini` + translation files only; do not duplicate its
  `config.json` (a second config for the same `modName` conflicts by file override).

## 7. Failure modes → first check

| Symptom | Likely cause |
|---|---|
| Menu absent | quest/script missing, `PlayerAlias`/`SKI_PlayerLoadGameAlias` missing, MCM Helper/SkyUI not loaded, folder != quest plugin stem |
| Menu present, page shows an error string | JSON syntax (comment, trailing comma, BOM, `//`) — read the message |
| Control missing | `groupBehavior: hide/skip` with false condition; wrong `type` spelling |
| Value never saved | id has no `:Section`; sourceType mismatches control; Property not `Auto` |
| Change not seen by gameplay | script reads the property but control stores a ModSetting (or vice versa) |
| Strings show as `$Key` | translation file missing for the *current* language, wrong encoding (not UTF-16 LE+BOM), or key not an exact whole-string match |
| Hotkey silent | `keymap` `id` not in `keybinds.json`; `SendEvent` handler named wrong; form id wrong |
| Ported menu loses values | renamed `id` / section — old saved value orphaned |

Log: `…\Documents\My Games\Skyrim Special Edition\SKSE\MCMHelper.log` (also the Papyrus log for
script errors). Structural validation is not runtime proof — open the menu in game.
