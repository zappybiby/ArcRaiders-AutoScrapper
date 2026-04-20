# MetaForge Arc Raiders API - Field Schemas

## Item

Returned by `GET /items`.

`id`, Type=string, Notes=Slug, e.g. `acoustic-guitar`
`name`, Type=string, Notes=Display name
`description`, Type=string, Notes=
`item_type`, Type=string, Notes=`Weapon`, `Quick Use`, `Topside Material`, `Basic Material`, `Armor`, etc.
`rarity`, Type=string, Notes=`Common`, `Uncommon`, `Rare`, `Epic`, `Legendary`
`value`, Type=int, Notes=Base loot value in credits
`workbench`, Type=string\, Notes=null, Crafting bench name, e.g. `Weapon Bench 2`
`loadout_slots`, Type=string[], Notes=e.g. `["weapon"]`, `["armor"]`, `[]` for non-equippable
`icon`, Type=string, Notes=CDN URL to `.webp` icon
`flavor_text`, Type=string, Notes=
`subcategory`, Type=string, Notes=
`shield_type`, Type=string, Notes=
`loot_area`, Type=string, Notes=
`ammo_type`, Type=string, Notes=e.g. `heavy`, `light`, `shotgun`
`sources`, Type=null\, Notes=any, Loot sources (sparse)
`locations`, Type=array, Notes=Map locations
`guide_links`, Type=`{url, label}[]`, Notes=Links to MetaForge guides
`game_asset_id`, Type=int, Notes=Internal ID; `-9999` = no asset ID
`created_at`, Type=ISO8601, Notes=
`updated_at`, Type=ISO8601, Notes=
`stat_block`, Type=object, Notes=See below

### stat_block fields

All numeric; `0` means not applicable for this item type.

**Universal:** `value`, `weight`, `stackSize`

**Combat:** `damage`, `health`, `radius`, `shield`, `arcStun`, `raiderStun`, `damageMult`, `damagePerSecond`, `damageMitigation`

**Weapon-specific:** `range`, `fireRate`, `stability`, `magazineSize`, `firingMode` (string), `reducedReloadTime`, `reducedVerticalRecoil`, `increasedVerticalRecoil`, `increasedBulletVelocity`, `reducedMaxShotDispersion`, `reducedPerShotDispersion`, `reducedDispersionRecoveryTime`, `reducedRecoilRecoveryTime`, `increasedRecoilRecoveryTime`, `reducedDurabilityBurnRate`, `reducedNoise`, `ammo` (string, weapon only), `increasedFireRate`, `increasedADSSpeed`

**Mobility/equip:** `agility`, `movementPenalty`, `reducedEquipTime`, `increasedEquipTime`, `reducedUnequipTime`, `increasedUnequipTime`

**Survival:** `healing`, `healingPerSecond`, `healingSlots`, `stamina`, `staminaPerSecond`, `stealth`, `useTime`, `duration`

**Loadout/storage:** `augmentSlots`, `backpackSlots`, `quickUseSlots`, `safePocketSlots`, `weightLimit`, `shieldCharge`, `shieldCompatibility` (string), `illuminationRadius`

---

## Arc

Returned by `GET /arcs`.

| `id` | string | Slug, e.g. `bastion` |
| `name` | string | |
| `icon` | string | CDN URL |
| `image` | string | CDN URL (larger image) |
| `loot` | array | Only present when `includeLoot=true`; may be empty `[]` |

## Quest

Returned by `GET /quests`.

| `id` | string | Slug, e.g. `a-bad-feeling` |
| `objectives` | string[] | Step-by-step objective text |
| `xp` | int | XP reward (0 if none) |
| `granted_items` | array | Items granted on unlock |
| `trader_name` | string | Quest giver, e.g. `Celeste`, `Apollo` |
| `sort_order` | int | Quest chain order within trader |
| `position` | `{x, y}` | Map quest board position |
| `marker_category` | string\|null | |
| `image` | string | CDN URL |
| `locations` | array | |
| `guide_links` | `{url, label}[]` | |
| `required_items` | RequiredItem[] | Items to turn in (see below) |
| `rewards` | Reward[] | Items awarded on completion (see below) |

### RequiredItem

```json
{
 "item": { "id": "...", "icon": "...", "name": "...", "rarity": "...", "item_type": "..." },
 "item_id": "string",
 "quantity": "string"
}
```

### Reward

"id": "uuid",

## Trader Item

Returned by `GET /traders` - each trader key maps to an array of these.

| `id` | string | Item slug |
| `rarity` | string | |
| `item_type` | string | |
| `value` | int | Base loot value |
| `trader_price` | int | Buy price from trader (typically 3× `value`) |

**Known traders:** `Apollo`, `Celeste` (others may exist - iterate `data` keys at runtime).

## Event

Returned by `GET /events-schedule`.

| `name` | string | Event name, e.g. `Matriarch`, `Night Raid`, `Bird City` |
| `map` | string | Map name, e.g. `Spaceport`, `Dam`, `Buried City`, `Blue Gate`, `Stella Montis` |
| `startTime` | int | Unix timestamp **milliseconds** |
| `endTime` | int | Unix timestamp **milliseconds** |

Convert to JS Date: `new Date(startTime)`. Convert to Python: `datetime.fromtimestamp(startTime / 1000)`.
