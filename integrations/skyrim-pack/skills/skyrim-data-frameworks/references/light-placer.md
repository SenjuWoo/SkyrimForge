# Light Placer (powerofthree) — JSON lights

Checked: wiki `58c9b71` (2025-10-11) against installed plugin 5.0.0 (Nexus 127557, 2026-09-25). Requirements per
Nexus: SKSE, Address Library, **powerofthree's Tweaks** (EditorIDs), Community Shaders / Light Limit Fix
recommended (real lights obey the engine light limit). Log: `po3_LightPlacer.log` in the SKSE log folder (JSON
errors). Settings: `Data\SKSE\Plugins\po3_LightPlacer.ini` `[Settings]`.

## Files

`Data\LightPlacer\<anything>.json` (subfolders fine: `Data\LightPlacer\YourMod\File1.json`). Strict JSON, a
top-level **array of entries**. One entry = *what to attach to* + *which lights*.

```json
[
  {
    "models": ["effects\\fxfirewithembers01_lite.nif"],
    "lights": [
      { "points": [[0, 0, 7.63]],
        "data": { "light": "LightCampFire01", "radius": 256.0, "fade": 1.2 } }
    ]
  }
]
```

## Attach target (use one per entry)

| Key | Meaning |
|---|---|
| `models` | full model paths (backslashes doubled). Works for objects, armor/weapons, hit shaders; **not** effect shaders |
| `formIDs` | FormID/EditorID of an object, worn item, effect shader or art object: `"EnchShockFXShader"`, `"0x1234~MyMod.esp"` (replaces `visualEffects`) |
| `addonNodes` | **deprecated**: AddOn Node indices, all matching nodes in the nif |
| `visualEffects` | **deprecated**: use `formIDs` |

Supported things: statics, movable statics, furniture, doors, containers, activators, flora; misc, soul gems,
books, potions, ingredients; armor, weapons; effect shaders and art objects (spell hit FX, enchantments, casting art).

## `lights[]` item

| Key | Notes |
|---|---|
| `points` **or** `nodes` | never both. `points`: `[[x,y,z],...]` in the nif's local space. `nodes`: nif node/shape names |
| `whiteList` / `blackList` | optional filters: model path (only for `addonNodes`/`visualEffects`), reference ID, base object ID, parent cell, worldspace, location |
| `data` | the light, below |

## `data`

| Key | Required | Meaning |
|---|---|---|
| `light` | yes | lightbulb EditorID/FormID; chain with `\|` — first valid form is used (`"DefaultGreen01NS\|WRCandleFlickerNS"`) |
| `color` | no | `[r,g,b]` 0-255 or normalized 0-1 |
| `radius`, `fade` | no | override the bulb |
| `fov` | no | shadow casters only |
| `shadowDepthBias` | shadow casters | prevents shadow striping |
| `offset` | no | `[x,y,z]` from the point/node |
| `rotation` | no | `[x,y,z]` degrees (spotlights) |
| `externalEmittance` | no | external emittance form; not on actors |
| `conditions` | no | CK condition strings; re-evaluated every second, e.g. `"Self IsSneaking NONE NONE == 1 AND"` |
| `conditionalNodes` | no | node/shape names shown only while the light is on |
| `flags` | no | `"A\|B"` from: `PortalStrict` `Simple` `Shadow` `UpdateOnWaiting` `UpdateOnCellTransition` `SyncAddonNodes` `IgnoreScale` `RandomAnimStart` `NoExternalEmittance` |
| `colorController` `radiusController` `fadeController` `positionController` `rotationController` | no | animation, below |

Shadow casters: bulb must be a shadow-casting light form + `"flags": "Shadow"` + `shadowDepthBias`; max **4
shadow casters per cell**, so scope them with `whiteList` to one reference or a unique model.

## Controllers

```json
"radiusController": { "interpolation": "Linear",
  "keys": [ {"time": 0.0, "value": 1.0, "forward": 0.0, "backward": 0.0}, {"time": 1.0, "value": 2.0, "forward": 0.0, "backward": 0.0} ] }
```
`interpolation` ∈ `Step` `Linear` `Cubic` (cubic uses `forward`/`backward`). Value field per controller: radius/fade
`value`, color `color: [r,g,b]`, position `translation: [x,y,z]`, rotation `rotation: [x,y,z]`. Keys cycle and loop.

## Disable vanilla/CK-placed lights

`Data\LightPlacer\<anything>.ini`:
```ini
[LightWhiteList]
0x801~Mod3.esl
MyLightingMod.esp
[LightBlackList]
Skyrim.esm
0x1235~Mod.esm
```
`bDisableAllGameLights = true` in `po3_LightPlacer.ini` disables everything except carryable lights and uses
`[LightWhiteList]` as exceptions; `[LightBlackList]` only works when `bDisableAllGameLights` is false. Other
ini settings: `bShowMarkers`, `fGlobalLightFadeMult`, `fGlobalLightRadiusMult`.

## Console and Papyrus

`logLP` (list lights on the selected ref), `tlp 0` (toggle lights) / `tlp 1` (debug markers, enable in the ini
first), `ReloadLP` (reload configs; new entries may need `disable`/`enable` on the object). Papyrus global script
`LightPlacer`: `TogglePlacedLight(ObjectReference akRef, bool abHide)`, `IsPlacedLightToggled(ObjectReference akRef)`.

## Doc inconsistency to know

One wiki example (Blue Palace) writes the light list as `lightData`; the format and properties pages use `lights`.
Use `lights`; if lights do not appear, read `po3_LightPlacer.log` before assuming a key rename.
