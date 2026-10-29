# Anim Object Swapper (AOS, powerofthree) — `_ANIO.ini`

Checked: Nexus 75167 description, plugin 2.0.0 (2026-09-20). Needs SKSE, Address Library, **powerofthree's Tweaks**
(EditorID support). Log: `po3_AnimObjectSwapper.log` in the SKSE log folder.

An AnimObject is the prop an idle animation attaches (the bread when eating, the tankard when drinking, the sword
on the grindstone). AOS swaps one for another at runtime, optionally by who is playing the animation.

## File

Any `.ini` in `Data` whose name contains **`_ANIO`** (e.g. `Data\MyMod_ANIO.ini`). Sections `[ANIO]` and
`[ANIO|<conditions>|<traits>]`; lines `origID|swapID|chance`.

Comments are `;` on their own line (the author's examples never trail a line).

```ini
[ANIO]
;random pick each time the idle plays
AnimObjectBread|AnimObjectBaguette,AnimObjectBagel,AnimObjectBiscuit
;location-fixed 50 %
AnimObjectBread|AnimObjectRye|chanceL(50)
;FormID~Plugin form
0x10FD02~Skyrim.esm|0x800~MyBreadMod.esp

[ANIO|Player]
AnimObjectBread|AnimObjectDragonBread

;OR: a steel sword, or any WeapTypeSteel item, in the inventory
[ANIO|SteelSword,WeapTypeSteel]
AnimObjectIronSword|AnimObjectSteelSword

;female AND has a steel sword
[ANIO|SteelSword|F]
AnimObjectIronSword|AnimObjectFlowerySteelSword

;AND with +
[ANIO|EbonySword+IngotEbony+Player]
AnimObjectIronSword|AnimObjectEbonySword

;negated wildcard EditorID
[ANIO|-*Bandit]
AnimObjectTankard|AnimObjectTankardClean
```

## IDs

`AnimObjectFormID~ModName.esp`, `AnimObjectFormID` (base game), or EditorID. `orig` = base AnimObject to replace,
`swap` = replacement.

## Multiples

- `orig|swapA,swapB` — one picked at random each time the idle plays.
- `origA,origB|swap` — every original gets the same swap.
- `origA,origB|swapA,swapB` — originals paired with swaps in order.

## Chance (third field, default 100)

`chance(50)` fixed per actor (persists across sessions) · `chanceL(50)` fixed per location/cell (everyone there
swaps the same) · `chanceR(50)` rerolled every play · optional seed `chance(50, 1234567)`.

## Conditions (section header, after `ANIO|`)

Same family as SPID/BOS/KID filters with pattern matching. Filters: keyword EditorIDs on the actor or on an
inventory item (`ActorTypeNPC`, `WeapTypeSteel`), actor-base EditorIDs (`BalgruufTheGreater`, `Player`), cell
EditorIDs (`WhiterunDragonsreach`), actor forms (faction, race, spell), formlists (any entry matches), object
EditorIDs present in the inventory (templated/enchanted variants match their base), nif paths found in inventory
item models. `,` = OR, `+` = AND, `-` = NOT, `*` wildcard. Traits (third header field): `M`, `F`, `C` (child),
combinable (`M,C`), negated (`-C`), `NONE` for no traits. **Do not target child actors with adult content.**

## Precedence

Conditional entries are tested before unconditional ones. Inside one file the first matching line wins (top to
bottom). Across files the last loaded config wins (like BOS).
