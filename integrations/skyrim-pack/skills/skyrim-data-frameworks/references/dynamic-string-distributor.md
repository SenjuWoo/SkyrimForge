# Dynamic String Distributor (DSD, SkyHorizon) — JSON string replacement

Checked: repo docs `docs/modules/ROOT/pages/index.adoc` at `bf153cc` (2026-10-07) and tests/generalTestAll.json,
against installed 1.5.2 (Nexus 107676, 2026-09-30). Works on SE 1.5.97, AE (incl. GOG), VR with MergeMapper.

DSD replaces or adds in-game text (names, descriptions, dialogue lines, button text) at runtime from JSON, so a
translation or rewrite does not edit plugins and survives plugin updates. Parsed **once at startup**.

## Files

`Data\SKSE\Plugins\DynamicStringDistributor\<PluginName>\<Anything>.json`

- The folder is named after a plugin and is loaded only when that plugin is active (case-insensitive, e.g.
  `Skyrim.esm`). The strings inside may target records of any plugin.
- Conflicts resolve like plugin load order: a later plugin's folder overrides; inside one folder files override
  alphabetically. A folder named **`overwrite`** is processed last and wins.
- Content must be strict JSON (RFC 8259): escape quotes, backslashes and newlines (`\r\n`) inside strings.

## Entry

A file is an array of objects:

| Key | Required | Notes |
|---|---|---|
| `form_id` | yes | `"<FormID>\|<Plugin>"`, e.g. `"0x0176CD\|Skyrim.esm"`. Accepted ID spellings: `050176CD`, `0x0176CD`, `0X0176CD`, `176CD`; light: `FE0176CD`, `0x6CD`, `6CD` |
| `type` | yes | `"<RECORD> <SUBRECORD>"` from the lists below |
| `string` | yes | replacement text |
| `editor_id` | for `GMST DATA` | the setting's EditorID |
| `index` | for indexed types | exact entry index |
| `conditions` | no (since 1.5.0) | CK condition strings; only on the types listed below |
| `original` | no | deprecated since 1.4.0 |

## Types

- **EditorID required**: `GMST DATA`.
- **No index**: `XXXX FULL` (full name of any record type, e.g. `WEAP FULL`, `CELL FULL`, `REFR FULL`, `DIAL FULL`),
  `XXXX DESC` (description of any record, e.g. `BOOK DESC`), `NPC_ SHRT`, `WOOP TNAM`, `INFO RNAM`,
  `BOOK CNAM`, `MGEF DNAM`, `REGN RDMP`, `ACTI RNAM`, `FLOR RNAM`.
- **Index required**: `QUST CNAM` (INDX stage index + log entry index), `QUST NNAM` (QOBJ objective index),
  `INFO NAM1` (response number in TRDT), `MESG ITXT` (list index from 0, as xEdit shows), `PERK EPF2` (fragment
  index in EPF3), `PERK EPFD` (list index counting only PERK EPFD strings).
- **Conditions allowed on**: `ACTI FULL` `ACTI RNAM` `FLOR FULL` `FLOR RNAM` `NPC FULL` `NPC SHRT` `INFO NAM1`
  `INFO RNAM` `DIAL FULL`. `Self` is the reference holding the form (for `INFO NAM1`, the speaker).

```json
[
  { "form_id": "000D48B7|Skyrim.esm", "editor_id": "sCurrentLocation", "type": "GMST DATA", "string": "New string" },
  { "form_id": "000ACC37|Skyrim.esm", "type": "WEAP FULL", "string": "New full name" },
  { "form_id": "000E6C43|Skyrim.esm", "type": "INFO NAM1", "index": 2, "string": "new sentence",
    "conditions": ["Self IsOverEncumbered NONE NONE == 1"] }
]
```

## Settings — `Data\SKSE\Plugins\DynamicStringDistributor.ini`

`[General] bEnablePlayerRef = false` (also reload the player's NPC_ FULL/SHRT, which can overwrite the name the
player chose), `fUpdateInterval = 5.0` (seconds, scales with game time; 0 or negative = no refresh, which can leave
translations missing). `[Debug] bEnableDebugLog`, `bEnableDebugInfo` (prefixes every replaced string with
FormID and plugin, to see what DSD touched).

## Tooling and compatibility

xEdit exporter `DSD - Export plugins.pas` (Nexus file) turns existing plugin strings into DSD JSON; SSE Auto
Translator can translate a whole load order into DSD files. Compatibility (Nexus): `BOOK CNAM` conflicts with
Description Framework when both set the same book (the Description Framework INI text shows); full-name changes
conflict with SkyPatcher on the same item (the SkyPatcher INI wins); subtitles are compatible.
