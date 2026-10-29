# config.json — layout grammar

Source of truth: `docs/config.schema.json` (MCM-Helper `a303348`, v1.6.3), wiki pages *Menu Layout*,
*Control Types*, *Setting Types*, *Group Conditions*, *Papyrus Integration*. Where schema and wiki
disagree it is stated. File: `Data\MCM\Config\<ModName>\config.json`.

**Strict JSON.** No comments, no trailing commas, UTF-8 **without BOM** (RapidJSON default flags over a
plain file stream). The `//` comments below are documentation — strip them.

## Top level

```jsonc
{
  "$schema": "https://raw.githubusercontent.com/Exit-9B/MCM-Helper/main/docs/config.schema.json",
  "modName": "MyAwesomeMod",        // required. Plugin name without extension; == folder name
  "displayName": "My Awesome Mod",  // required. Left-panel label (may be "$Key")
  "minMcmVersion": 13,              // optional. integer, schema minimum 13; user must update below this
  "pluginRequirements": ["A.esp"],  // optional. user is told which are missing/disabled
  "cursorFillMode": "topToBottom",  // optional. "leftToRight" (default) | "topToBottom"
  "content": [ ],                   // content XOR customContent (and per page)
  "customContent": { "source": "modname/splash.dds", "x": 258, "y": 95 },
  "pages": [ { "pageDisplayName": "$General", "content": [ ] } ]
}
```

- `content` and `customContent` are mutually exclusive (schema `oneOf`), at top level and per page.
- `customContent.source` is relative to `Data\Interface\`; SWF or DDS (other formats import poorly).
  `x` < 770, `y` < 446 (exclusive); config area is 770x446, horizontal centre ≈ 376 (scroll bar on the
  right), vertical 223: `x = 376 - w/2`, `y = 223 - h/2`.
- With `pages`, make the main page blank or `customContent`: it is not selectable once another page is
  opened. `pageDisplayName` is required.
- `$schema` is ignored by MCM Helper; editors use it. `minMcmVersion` support began at version code 9;
  `$schema` support at 13. Code is `MCM.GetVersionCode()` (v1.5.0 = 14, repo v1.6.3 = 15).

## Common control keys

| Key | Meaning |
|---|---|
| `type` | **required**: `empty header text toggle hiddenToggle slider stepper menu enum color keymap input` |
| `text` | label (`$Key` to localize; a non-`$` string is flagged "will not be localized") |
| `id` | needed to receive `OnSettingChange`, to be a ModSetting, and for `keymap` hotkeys |
| `help` | hover text; supports `{value}` replacement; may be `$Key` |
| `position` | integer slot override; `1` = top of right column; later controls fill after it |
| `groupCondition` | when the control is active (see Groups) |
| `groupBehavior` | `disable` (default) \| `hide` \| `skip` |
| `groupControl` | integer ≥ 1; **only** `toggle` / `hiddenToggle` |
| `action` | Papyrus call on edit (see Actions) |
| `valueOptions` | per-type object; unknown keys are errors (`unevaluatedProperties: false`) |

Unknown control keys are errors in the schema (`unevaluatedProperties: false`); write to the schema, not
to what the runtime happens to tolerate.

## Control types

| type | Stores | Interaction / notes |
|---|---|---|
| `empty` | — | spacer (advances cursor) |
| `header` | — | decorated title; `text` |
| `text` | String | text/value pair; `valueOptions.value`; becomes a button with `action` |
| `toggle` | Bool/Int | checkbox; may carry `groupControl` |
| `hiddenToggle` | Bool/Int | **not drawn, does not advance cursor**; exists to drive `groupControl` from a script property/global |
| `slider` | Float/Int | dialog; `min max step formatString` (`"{2}"` = 2 decimals, `"Every {0} hours"`) |
| `stepper` | Int index | cycles `options` on each click |
| `menu` | **String** | dialog, ≤128 `options`, optional `shortNames`; script `SetMenuOptions` |
| `enum` | **Int index** | like menu but stores the index; `options`, `shortNames`; `SetMenuOptions` since 1.2.0 |
| `color` | Int | 0xRRGGBB swatch dialog (`ColorComponent` helps) |
| `keymap` | Int keycode | press-a-key; either a hotkey (`id` ↔ `keybinds.json`) or an int property + SKSE `RegisterForKey`; `ignoreConflicts` (boolean; schema file mistakenly types it `"bool"`) |
| `input` | String | text-entry dialog |

`options` and `shortNames` must have equal length (a mismatch makes the menu fall back to the full
names). Value sources per control family:

| Control | Value type |
|---|---|
| toggle | Bool, Int |
| slider | Float, Int |
| enum / color / keymap / stepper | Int |
| text / menu / input | String |

## valueOptions per type (schema)

- `toggle hiddenToggle stepper enum color keymap` → value-source keys.
- `slider` → value-source keys + `min max step formatString`.
- `stepper` → + `options`. `enum` → + `options shortNames`.
- `text` → `value` + text-source keys. `menu` → text-source + `options shortNames`. `input` → text-source.
- **value-source keys**: `sourceType`, `sourceForm`, `defaultValue`, and — when `sourceType` is a
  `PropertyValue*` — `scriptName` and `propertyName` (**required**).
- **text-source keys**: `sourceForm`, `scriptName`, `propertyName`, `defaultValue`; `sourceType` is
  *deprecated/unused* for strings (strings are decided by `id` vs `propertyName`).

`sourceType` ∈ `PropertyValueBool PropertyValueInt PropertyValueFloat ModSettingBool ModSettingInt
ModSettingFloat GlobalValue` (`GlobalValue` since 1.1.0 / code 6).

### Storage in one table

| Source | Where it lives | Pick when |
|---|---|---|
| `ModSetting*` | `settings.ini` default → `Data\MCM\Settings\<Mod>.ini` | persists for the install, shareable, survives updates |
| `PropertyValue*` | Auto property on `sourceForm`'s script (default: the config quest) | save-bound, script-owned |
| `GlobalValue` | a GLOB record via `sourceForm` (`Skyrim.esm|38` = GameHour); stored as float | save-bound and needed by conditions/other plugins; large ints lose precision |

`defaultValue` is what "reset to default" restores for Property/Global sources; ModSettings reset to the
`settings.ini` value.

## ModSettings (`settings.ini`)

```ini
[Main]
bEnabled=1
fIntensity=0.5
iMode=0
sLabel=Hello
rTint=255,128,0
uFlags=3
```
- id of a control is `<key>:<Section>`, e.g. `fIntensity:Main`. Key's first letter is the type:
  `b` Bool, `f` Float, `i` Int, `r` Color (comma-separated R,G,B), `s` String, `u` Unsigned Int.
- A control referencing a ModSetting not present in `settings.ini` has no default — always define it.
- User file `Data\MCM\Settings\<Mod>.ini` is written on **every** change and overrides defaults; never
  ship it (ship `settings.ini` under `MCM\Config\<Mod>\`). Values are written as C++ `to_string` text
  (e.g. floats as `0.500000`, bool as `1`/`0`).

## Groups

```jsonc
{ "id": "bAdv:Main", "type": "toggle", "text": "Show Advanced", "groupControl": 1 },
{ "id": "fX:Adv", "type": "slider", "text": "X", "groupCondition": 1, "groupBehavior": "hide",
  "valueOptions": { "min": 0, "max": 1, "step": 0.1, "sourceType": "ModSettingFloat" } }
```
`groupCondition` forms (integers ≥ 1, one key per object):
`1` ≡ `[1]` ≡ `{"OR":[1]}` · `{"NOT":1}` · `[1,2]` ≡ `{"OR":[1,2]}` · `{"AND":[1,2]}` ·
`{"ONLY":[1,2]}` (1 and 2 true **and every other groupControl on the page false**). Nesting allowed.
`skip` removes the control from layout; after a script changes a driving value call `ForcePageReset()`.

## Actions

```jsonc
"action": { "type": "CallFunction", "form": "MyMod.esp|800", "scriptName": "MyScript",
            "function": "OnChanged", "params": ["{value}", "{i}42", "{b}true", "{f}1.5", "{s}x"] }
"action": { "type": "CallGlobalFunction", "script": "Debug", "function": "MessageBox",
            "params": ["Hello"] }
```
- `type` ∈ `CallFunction | CallGlobalFunction`; `function` required.
- `form`/`scriptName` optional for `CallFunction` (defaults: config quest; since 1.4.0 `scriptName` may be
  omitted when the form has one script). `script` names the global script for `CallGlobalFunction`.
- `{value}` is replaced by the control's value (type follows the control). Constants take a prefix cast
  `{i} {b} {f} {s}`. `params` items are boolean, number or string.

## Form string

`^[^\\/:*?"<>|]+\.es[lmp]\|(0[Xx])?[\dA-Fa-f]{1,8}$` — e.g. `MCM_Demo.esp|800`, `Skyrim.esm|38`.
Local ID only. Applies to `sourceForm` and `form`.
