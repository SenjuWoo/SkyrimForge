# Enchantment Art Extender (EAE, SeaSparrow) — rules JSON

Checked: wiki `4c037f6` (2026-06-14) against installed plugin 3.0.2 (Nexus 105492, 2026-06-16). EditorIDs need
powerofthree's Tweaks; plugin-qualified forms do not. Installed `EnchantmentArtExtender.ini`: `[General]
bOnlyPlayer = 0` (not described in the wiki; leave it alone unless the author documents it).

The framework attaches an art object to an enchantment *per weapon*, so one enchantment can look different on a
sword and a bow, and modded enchantments get art without editing records.

## Files

Every `.json` under `Data\SKSE\Plugins\EnchantmentArtExtender\` is a config: an **array of rules**.

```json
[
  { "WeaponArt": "MyCoolMod.esp|0x800",
    "WeaponKeywords": ["WeapTypeSword", "MaterialTypeIron"],
    "EnchantmentKeywords": "MagicDamageFire" },
  { "WeaponArt": "BlackfireNettlebane",
    "EnchantmentKeywords": "MagicDamageFire",
    "Weapons": "My Awesome Mod.esm|0x78D3A" }
]
```

## Rule keys

| Key | Meaning |
|---|---|
| `WeaponArt` | **mandatory**; an Art Object (`AOBJ`) as `"Plugin.esp\|0xID"` or EditorID. Must resolve or the rule is ignored |
| `WeaponKeywords` | string or array; the weapon must have **all** of them |
| `EnchantmentKeywords` | string or array; the enchantment must have **all** of them |
| `Weapons` | specific weapon(s) (string or array); templates count (an Iron Sword entry also covers "Iron Sword of Embers"); **`WeaponKeywords` is ignored** when present |
| `Enchantments` | same as `Weapons`, for enchantments |

## Which rule wins

Four tiers, most restrictive first, search stops at the first tier with a match:
1. specific enchantment + specific weapon
2. specific enchantment + weapon keywords
3. enchantment keywords + specific weapon
4. enchantment keywords + weapon keywords

Within a tier, the rule matching more keywords is preferred (a Fire+Frost rule beats a Fire rule on a
double-enchanted weapon). A specific-weapon rule always beats keyword rules for that weapon.

## Notes

- Commas between array elements, none after the last (strict JSON).
- Ship the art object (AOBJ) in your own plugin; EAE only chooses which one attaches.
- Papyrus helper shipped by the mod: script `EAE_ModObjectsScript` (properties on a quest; not an authoring API).
