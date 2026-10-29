# Authority map — frameworks without a vendored grammar

For each framework: what was seen installed on the reference machine (2026-10-29), and where its grammar is
published. **Nothing here is a grammar.** Read the named source and an installed example before writing a file;
if neither exists, say the syntax is unverified instead of guessing. Papyrus-facing APIs are in
`papyrus-reference/references/*.md` when a file exists there.

| Framework | Seen installed | Grammar / API authority |
|---|---|---|
| Light Placer, Anim Object Swapper, Enchantment Art Extender, Dynamic String Distributor, Sound Record Distributor, SKSE HTTP | DLLs + configs | this skill's references |
| MCM Helper | `MCMHelper.dll`, 50 `MCM\Config` menus | `mcm-helper-authoring` |
| SPID, KID, SkyPatcher, BOS, CDF/CID, FLM, OAR | DLLs + INI/JSON | their own skills (`skyrim-frameworks-index`) |
| Dynamic Spell Description (SeaSparrow) | `DynamicSpellDescription.dll`, `SKSE\Plugins\DynamicSpellDescription\*.json` (8 shipped sets: Fire/Frost/Shock effects, atronachs, bound weapons...), `DynamicSpellDescription.ini` | Nexus 136026; README has build notes only. Copy the structure of a shipped JSON; unknown keys unverified |
| Description Framework (DEF) | `DescriptionFramework.dll`, `Scripts\Source\DescriptionFramework.psc` | Nexus 105799; Papyrus API in the shipped `.psc`; INI keys on the Nexus page |
| Music Type Distributor | `MusicTypeDistributor.dll/.ini` | Nexus 119571 |
| Object Impact Framework, Core Impact Framework, Mu Impact Framework | `ObjectImpactFramework\`, `CoreImpactFramework\` (`CIF_BipedMapping\BM_*.json`), `MuImpactFramework\` folders | Nexus 149484 (OIF), 146873 (CIF); shipped JSON/INI are the grammar of record |
| Dynamic Armor Variants (Exit-9B) | `DynamicArmorVariants.dll`, `SKSE\Plugins\DynamicArmorVariants\`; sample mod ships `MCM\Config\DynamicArmorMenu` | Nexus 65963; repo `Exit-9B/DynamicArmorVariants` has build notes only |
| Keyword Equip Framework | `KeywordEquipFramework.dll`, folder | repo `Teijirr/SkyrimKeywordEquipFramework` (README is a one-liner); verify from shipped files |
| Inventory Injector (+ Improved) | `InventoryInjector.dll`, `InventoryInjectorImproved.dll`, `SKSE\Plugins\InventoryInjector\` | Nexus page of the installed build; sample sets in other mods' `InventoryInjector` folders |
| Prisma UI | `PrismaUI.dll`; web inspector under `PrismaUI\` | Nexus 148718; the installed mod ships its web inspector files, not a grammar |
| SKSE Menu Framework (ImGui menus for plugins) | `SKSEMenuFramework.dll`, `SKSEMenuFramework.ini`, `...MenuConfig.json`, `...Strings*.json`, `SKSEMenuFrameworkThemes\{classic,modern,skyrimDefault}.json`, bundled fonts | C++ API header `include/SKSEMenuFramework.h` in `QTR-Modding/SKSE-Menu-Framework-3` (read it; do not assume ImGui calls beyond it); Nexus 120352 |
| MenuStudio, InfinityUI | DLLs, `MenuStudio\` folder | Nexus pages; Scaleform/SWF work is separate (`skyrim-assets-pbr`) |
| SkyPrompt | `SkyPrompt\` folder | `papyrus-reference/references/skyprompt.md` |
| Custom Skills Framework | `CustomSkills.dll`, `CustomSkills\` folder | `papyrus-reference/references/custom-skills.md` |
| TrueHUD, True Directional Movement, Precision | DLLs + MCM menus | their public C++/Papyrus APIs live in the authors' repos (APIs header files); verify before use |
| Payload Interpreter | `PayloadInterpreter.dll`; Nemesis mod files | animation-event payloads: `skyrim-animation-behaviors` |
| Scaleform Translation++ | `ScaleformTranslationPP.dll` | translation files for UI text; MCM localization is in `mcm-helper-authoring` |
| Perk Entry Point Extender, ConsoleUtilSSE, PapyrusUtil, JContainers, PO3 extender | DLLs | `papyrus-reference/references/{perkentrypoint,consoleutil,papyrusutil,jcontainers,po3}.md` |

## How to settle an unknown grammar

1. Read the author's published doc: GitHub wiki (`git clone <repo>.wiki.git` works for repos that have one), the
   repo `docs/`, or the Nexus description (the built-in browser can read it).
2. Read shipped example files in the installed mods (staging folders); they are working grammar.
3. Read the plugin's log after one launch; a parse error names the line.
4. If still unknown, state the gap. A guessed token in these frameworks fails silently.
