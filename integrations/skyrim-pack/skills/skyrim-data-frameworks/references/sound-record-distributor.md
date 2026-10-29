# Sound Record Distributor (SRD, doodlum) — `_SRD` configs

Checked: Nexus 77815 description (plugin 1.5.3/1.5.4, 2026-08-24) and shipped configs from Audio Overhaul for
Skyrim 4.1.3 and an Immersive Sounds patch on the reference machine. The key list per record type is **not
published on the page**; the YAML below is what shipped configs actually use. Before using a slot name not shown
here, open a shipped `*_SRD.yaml` for that record type. SRD does nothing on its own (it patches records from configs).

## Files and load order

Placed in `Data` (the mod root). Names:

- tied to a plugin: `<PluginName>[ _<Name>]_SRD.<json|jsonc|yaml>` — e.g.
  `Audio Overhaul Skyrim.esp_Magic_Base_SRD.yaml`, `Immersive Sounds - Compendium.esp_Mysticism_SRD.jsonc`
- not tied: `<Name>_SRD.<json|jsonc|yaml>` — e.g. `MyCoolMod_SRD.jsonc`

The game loads forms normally; SRD then parses plugin-tied configs (for loaded plugins), then untied configs in
alphabetical order, patching records. Sound records effectively get their own load order. JSON and JSONC are
identical (JSONC allows comments); YAML is the most compact. MergeMapper is supported — do **not** merge a plugin
that has configs tied to its name.

## Forms and requirements

A form is `PluginName|LocalFormID` (as in the shipped YAML, `Skyrim.esm|013CA9`) or an EditorID. `NULL` is
reserved. EditorIDs outside Regions and Sound Descriptors need powerofthree's Tweaks. A trailing `!` on a plugin
in `Requirements` means "only if that plugin is **not** present":

```yaml
Requirements:
  - Audio Overhaul Skyrim.esp
  - Immersive Sounds - Compendium.esp!
```
The last line means "only if Immersive Sounds is not present".

## Record sections (YAML) seen in shipped configs

```yaml
Requirements:
  - Audio Overhaul Skyrim.esp
Magic Effects:
  - Form: Skyrim.esm|07F82E
    Release: Audio Overhaul Skyrim.esp|01DC97
    On Hit: Audio Overhaul Skyrim.esp|01D1D1
Projectiles:
  - Form: Skyrim.esm|012E84
    Active Loop: Audio Overhaul Skyrim.esp|000846
Weapons:
  - Form: PrvtI_SaintsSeducersArmory.esp|802
    Attack Fail: Immersive Sounds - Compendium.esp|1E6B31
```

Replaceable slots per the Nexus page (outside Regions): Weapons — Pick Up, Put Down, Impact Data Set, Attack,
Attack 2D, Attack Loop, Attack Fail, Idle, Equip, Unequip · Magic Effects — Draw/Sheathe, Charge, Ready, Release,
Cast Loop, On Hit · Armor Addons — Footstep · Armors, Misc Items, Soul Gems — Pick Up, Put Down · Projectiles —
Active, Countdown, Deactivate · Explosions — Interior, Exterior · Effect Shaders — Ambient · Ingestibles — Consume.

Regions are different: referencing a sound already in the Region replaces it, otherwise a new one is added; a
sound is effectively disabled with `Chance` 0.00; later configs can reference sounds added by earlier ones; an
RDSA entry must already exist in the Region. `Chance` defaults to 0.05, `Flags` to all enabled.
