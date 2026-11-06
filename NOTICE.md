# Notices

Skyrim Forge does not bundle Bethesda game files, Creation Kit files, xEdit binaries, LOOT binaries, Wrye Bash files, Mod Organizer 2, Vortex, SKSE, CKPE, or third-party mod assets.

The bundled xEdit Pascal scripts are original Forge integration scripts written against the public xEdit scripting API. External applications retain their own licenses and distribution terms.

## SPDX schema

`references/spdx-2.3.schema.json` is the unmodified SPDX 2.3 JSON schema from the SPDX specification (CC-BY-3.0). See `references/SPDX-SCHEMA-PROVENANCE.md`. It is used only by tests to validate the generated SBOM.

## Skills derived from houseCARL

These Skyrim pack skills started from the skills that ship with houseCARL by Avick3110 (<https://github.com/Avick3110/houseCARL>), which is licensed GPL-3.0-only, and have since been edited or extended for Forge: `housecarl`, `kid-authoring`, `spid-authoring`, `skypatcher-authoring`, `papyrus-reference`, `mutagen-reference`, `skse-plugin-authoring` and `oar-authoring` (upstream `open-animation-replacer`). Those directories remain under GPL-3.0-only; the full text is `integrations/skyrim-pack/skills/housecarl/LICENSE`. The MIT licence of the rest of Forge does not apply to them. The generated half of `papyrus-reference/references/` comes from BellCube's papyrus-index (<https://github.com/BellCubeDev/papyrus-index>), and `mutagen-reference/references/` is generated from Mutagen.Bethesda.Skyrim 0.54.4 (GPL-3.0-only).
