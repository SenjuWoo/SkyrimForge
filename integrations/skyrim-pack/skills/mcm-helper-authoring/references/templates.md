# Complete minimal MCM Helper menu

A working skeleton for a mod `MyMod` whose plugin `MyMod.esp` owns quest `MyMod_ConfigQuest`
(local id `0x800`). Replace names and ids; run `scripts/validate_mcm.py` on the result.

## Papyrus — `Scripts/Source/MyMod_Config.psc`

```papyrus
Scriptname MyMod_Config extends MCM_ConfigBase

GlobalVariable Property MyMod_Intensity Auto
Bool Property pBypass = False Auto            ; PropertyValueBool source
Int Property pMode = 0 Auto

Event OnConfigInit()
    SyncGlobals()
EndEvent

Event OnSettingChange(string a_ID)
    SyncGlobals()
EndEvent

Event OnConfigClose()
    SyncGlobals()
EndEvent

Function SyncGlobals()
    MyMod_Intensity.SetValue(GetModSettingFloat("fIntensity:Main"))
EndFunction

Function ResetAll()                           ; target of a button action
    SetModSettingFloat("fIntensity:Main", 0.5)
    SetModSettingBool("bEnabled:Main", True)
    RefreshMenu()
EndFunction

Function ToggleThing()                        ; target of keybinds.json
    Debug.Notification("MyMod toggled")
EndFunction

Int Function GetVersion()
    Return 1
EndFunction
```
Quest `MyMod_ConfigQuest`: script `MyMod_Config`; alias `PlayerAlias` (player ref) with
`SKI_PlayerLoadGameAlias`; property `MyMod_Intensity` filled with a GLOB.

## `Data/MCM/Config/MyMod/config.json`

```json
{
  "$schema": "https://raw.githubusercontent.com/Exit-9B/MCM-Helper/main/docs/config.schema.json",
  "modName": "MyMod",
  "displayName": "$MyMod",
  "minMcmVersion": 13,
  "content": [],
  "customContent": { "source": "MyMod/splash.dds", "x": 258, "y": 95 },
  "pages": [
    {
      "pageDisplayName": "$MyMod_General",
      "cursorFillMode": "topToBottom",
      "content": [
        { "type": "header", "text": "$MyMod_Core" },
        { "id": "bEnabled:Main", "type": "toggle", "text": "$MyMod_Enabled", "help": "$MyMod_EnabledHelp",
          "groupControl": 1, "valueOptions": { "sourceType": "ModSettingBool" } },
        { "id": "fIntensity:Main", "type": "slider", "text": "$MyMod_Intensity", "help": "$MyMod_IntensityHelp",
          "groupCondition": 1,
          "valueOptions": { "min": 0, "max": 1, "step": 0.05, "formatString": "{2}", "sourceType": "ModSettingFloat" },
          "action": { "type": "CallFunction", "function": "SyncGlobals", "params": [] } },
        { "id": "iMode:Main", "type": "enum", "text": "$MyMod_Mode", "groupCondition": 1, "groupBehavior": "hide",
          "valueOptions": { "options": ["$MyMod_ModeA", "$MyMod_ModeB"], "sourceType": "ModSettingInt" } },
        { "type": "empty" },
        { "type": "header", "text": "$MyMod_Advanced" },
        { "type": "text", "text": "$MyMod_Reset", "valueOptions": { "value": "$MyMod_ResetValue" },
          "action": { "type": "CallFunction", "function": "ResetAll", "params": [] } },
        { "id": "toggleThing", "type": "keymap", "text": "$MyMod_Hotkey", "help": "$MyMod_HotkeyHelp" },
        { "id": "pBypass", "type": "toggle", "text": "$MyMod_Bypass",
          "valueOptions": { "sourceType": "PropertyValueBool", "propertyName": "pBypass", "defaultValue": false } }
      ]
    }
  ]
}
```

## `Data/MCM/Config/MyMod/settings.ini`

```ini
[Main]
bEnabled=1
fIntensity=0.5
iMode=0
```

## `Data/MCM/Config/MyMod/keybinds.json`

```json
{
  "$schema": "https://raw.githubusercontent.com/Exit-9B/MCM-Helper/main/docs/keybinds.schema.json",
  "modName": "MyMod",
  "keybinds": [
    { "id": "toggleThing", "desc": "$MyMod_Hotkey",
      "action": { "type": "CallFunction", "form": "MyMod.esp|800", "scriptName": "MyMod_Config",
                  "function": "ToggleThing", "params": [] } }
  ]
}
```

## `Data/Interface/Translations/MyMod_ENGLISH.txt` (UTF-16 LE with BOM, TAB-separated)

```
$MyMod	My Mod
$MyMod_General	General
$MyMod_Core	Core
$MyMod_Enabled	Enabled
$MyMod_EnabledHelp	Turns the mod on or off.
$MyMod_Intensity	Intensity
$MyMod_IntensityHelp	Effect strength. Default: 0.5
$MyMod_Mode	Mode
$MyMod_ModeA	Mode A
$MyMod_ModeB	Mode B
$MyMod_Advanced	Advanced
$MyMod_Reset	Reset to defaults
$MyMod_ResetValue	Click
$MyMod_Hotkey	Toggle hotkey
$MyMod_HotkeyHelp	Key that toggles the effect.
$MyMod_Bypass	Bypass checks
```
Write the file from a script so the encoding is right, e.g. Python:
`Path(p).write_bytes(b"\xff\xfe" + text.encode("utf-16-le"))` with `\n` newlines in `text`.

## Patterns worth copying

- Toggle that reveals a block: toggle `groupControl: 1`, block controls `groupCondition: 1` (+ `hide`).
- Button: `text` control + `valueOptions.value` + `action`.
- Dynamic list: `menu`/`enum` with no `options`, call `SetMenuOptions("id", arr)` in `OnConfigOpen`.
- Mirror to gameplay: read ModSettings into GLOBs or script variables in `OnSettingChange`, not per frame.
- Cross-mod read: `MCM.GetModSettingBool("OtherMod", "bFlag:Main")` after `MCM.IsInstalled()`.
