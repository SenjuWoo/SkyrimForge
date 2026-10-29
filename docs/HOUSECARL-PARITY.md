# houseCARL parity and fallback

houseCARL (Avick3110, GPL-3.0-only, C#/.NET 10 + Mutagen, 31 `housecarl_*` MCP tools) is the primary builder for
load-order work. Forge must keep working if it breaks, is removed, or its host integration is stale. This page is the
honest map of what Forge can do on its own today, how to run each job without houseCARL, and what is still missing.
Forge's implementations are independent: written from the public plugin format and from observing plugin bytes, with
houseCARL used only as a behavioural cross-check. No houseCARL source is copied.

Routing rule for agents: **use houseCARL first** for anything on its read/write surface; switch to the Forge column
when its MCP is absent, erroring, or the task is outside what houseCARL exposes. Say which one produced the evidence.

| houseCARL tool | Forge equivalent | Status |
|---|---|---|
| `records` (select / project / tree) | `load-order`, `record-query` (one plugin), `record-conflicts` (EditorID or form key across the load order: every version, winner, changed subrecords, optional generic dump) | **partial**: no field schema (names/types/enums for 133 record types), no `where=` predicates, no reverse-reference index or link walks, no `info_order`, no SkyPatcher overlay |
| `check` (findings, facegen) | `record-query` + `record-conflicts` for evidence; procedure in `facegen-diagnostics` | **partial**: no packaged findings |
| `apply` `create` `remove` | `plugin-plan-validate` / `plugin-build` (new KYWD, GLOB, FLST, OTFT); xEdit automation adapter for anything else | **partial**: no generic typed edit |
| `forward` `copy` | none native; xEdit automation (copy as override into new file) | **missing** |
| `write_seq` | `seq-build` | **covered**: 229/257 shipped SEQ files byte-identical, 251/257 same set (rest differ in record order or are stale files) |
| `create_plugin` | `plugin-build` | **partial** (the four record types) |
| `compact_plugin` `merge_plugins` | xEdit / Synthesis adapters, Merge Plugins externally | **missing** (needs a record schema to remap FormIDs) |
| `asset_status` `place` | `mod-tree`, `archive-info`, `release-validate` | **partial**: no VFS winner view |
| `nif_inspect` `nif_set` | `deadmesh-scan` (collision report), `skyrim-nif` routing to NifSkope/Nifly/CAO/NIF Optimizer | **missing** native NIF read/write |
| `compile_script` `decompile_script` | `papyrus-compile`, `champollion-decompile`, `papyrus-analyze` | **covered** (needs pinned compiler/Champollion) |
| `bsa_list` `bsa_extract` `bsa_repack` | `bsarch-info` `bsarch-unpack` `bsarch-pack`, `archive-info` | **covered** (needs pinned BSArch) |
| `skypatcher_layer` | `framework-plan-validate` / `framework-build` / `lint` (SkyPatcher 6.4.2 core rules) | **partial**: no replay of the INI layer onto records |
| `skse` | `native-scaffold` `native-audit` `native-build` `native-binary-audit`, `sdk-status` | **partial**: authoring/building is covered, installed-plugin inventory is not |
| `nexus_search` `nexus_mod` `nexus_graphql` `nexus_check_updates` `nexus_identify` | `nexus-*` publication tooling only | **missing** (read-only API client would need the user's key) |
| `set_mo2_instance` `set_tool_path` `load_order_status` `update_status` | `config-set`, `tool-configure`, `load-order`, `doctor` | **covered** |

## Running without houseCARL

```
forge load-order --mo2-instance <MO2 folder>                       # ordered, indexed plugin list (headers only)
forge record-conflicts --mo2-instance <MO2 folder> --editor-id IronSword --signature WEAP
forge record-conflicts --mo2-instance <MO2 folder> --form-key 0x12EB7~Skyrim.esm --dump
forge record-query <plugin> --signature KYWD --editor-id Weap       # one plugin
forge seq-build <plugin> <workspace folder> --approve               # Seq/<plugin>.seq
```
No MO2: `--plugins-file <plugins.txt> --root <folder> [--root ...]` with roots highest priority first (Vortex:
the game `Data` folder plus staging).

- The MO2 instance and its `mods`, `overwrite` and game `Data` folders must be inside Forge's read roots
  (`extra_read_roots` in `config.toml`); Forge refuses otherwise. Nothing is written to them.
- `modlist.txt` is read highest priority first (MO2 writes it in reverse of the left pane); `+` entries only.
- Always pass `--signature` when you know the record type: without it every defined record's EditorID is read.
  Measured on a 2,957-plugin order: load-order resolution about 3 s, a signature-scoped EditorID query about 8 s.
- `changed_subrecords` is a raw byte comparison. Localized strings compare as string IDs, and subrecords holding
  FormIDs can differ only because the plugins' master lists differ, so treat a hit as "look closer", not as a
  semantic diff. houseCARL's field-level `delta`/`tree` is the precise view when it is available.

## Verification behind the "covered" rows

- `record-conflicts`: IronSword (`0x12EB7~Skyrim.esm`) on a 2,957-plugin order reports the same two providers and the
  same winner (Unofficial Skyrim Special Edition Patch) as houseCARL's `records project.form=tree`.
- `seq-build`: compared against the 257 `.seq` files in the installed game's `Data\SEQ` whose plugin sits in `Data`:
  229 byte-identical, 22 identical as a set with another record order, 6 differ (stale SEQ files made for an older
  plugin version). The rule is "quests the plugin defines with Start Game Enabled"; overrides of other plugins' quests
  are not listed.
- Both are structural evidence from plugin bytes. Neither replaces xEdit or an in-game check.

## Roadmap to closer parity (ordered by value / feasibility)

1. **Forward override**: byte-exact copy of a record into a new plugin whose masters are the source's master list plus
   the source plugin, so no FormID remapping is needed. Makes patch-by-forwarding possible without a schema.
2. **Curated typed edits** for the most requested records and fields (WEAP/ARMO/AMMO damage and value, NPC_ stats,
   keywords, names), each with a verified binary layout, not a guessed one.
3. **Reverse-reference scan** (what references this FormID) with an on-disk index.
4. **Read-only NIF inspection** (blocks, shader flags, texture paths) behind a parser with tests.
5. Anything needing the full record schema (compaction, merging, generic apply) stays on the xEdit/Synthesis adapters
   until a schema source with a compatible licence is chosen.
