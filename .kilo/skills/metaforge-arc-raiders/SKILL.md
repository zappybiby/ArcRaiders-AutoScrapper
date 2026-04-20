---
name: metaforge-arc-raiders
description: |
 Fetch Arc Raiders game data from the MetaForge community API - items, quests,
 ARCs (enemies), traders, and event timers. Use when you need to: look up item
 stats/rarity/value/workbench by type or rarity; find quest requirements and
 rewards by trader; check trader buy prices; or get upcoming in-game event
 schedules. Base URL: https://metaforge.app/api/arc-raiders. No auth required.
 Attribution to metaforge.app/arc-raiders required in public projects.
 Commercial use requires contacting MetaForge via Discord first.
---

# MetaForge Arc Raiders API

**Base URL:** `https://metaforge.app/api/arc-raiders`
No authentication required. Data is community-maintained, not from Embark directly.

**Terms:** Public projects must include attribution + link to `metaforge.app/arc-raiders`.
Commercial/monetized use → contact via [Discord](https://discord.gg/8UEK9TrQDs) first.

**Caching:** Endpoints may throttle. Cache responses on your end; avoid repeated calls for the same data.

**Endpoint instability:** Endpoints may change or break without warning. Treat responses defensively.

## Endpoints

### GET /items

Retrieve items with filtering and pagination.

```text
GET https://metaforge.app/api/arc-raiders/items

`page`, Type=int, Notes=Default 1
`limit`, Type=int, Notes=Items per page
`item_type`, Type=string, Notes=e.g. `Weapon`, `Quick Use`, `Topside Material`, `Basic Material`
`rarity`, Type=string, Notes=`Common`, `Uncommon`, `Rare`, `Epic`, `Legendary`
`includeComponents`, Type=bool, Notes=Include component/crafting relationships

**Note:** `name` param exists but does **not** filter by substring - it does not reliably narrow results. Filter client-side by `name` after fetching.

Response envelope: `{data: [Item], pagination: {...}}`
Full field reference: [references/schemas.md](references/schemas.md#item)

### GET /arcs
Retrieve ARC enemies/units with optional loot tables.

GET https://metaforge.app/api/arc-raiders/arcs

| `includeLoot` | bool | Adds `loot: []` array to each ARC |

~21 total ARCs. Response envelope: `{data: [Arc], pagination: {...}}`
Full field reference: [references/schemas.md](references/schemas.md#arc)

### GET /quests
Retrieve quests with required items and rewards.

GET https://metaforge.app/api/arc-raiders/quests

| `trader_name` | string | Filter by trader: `Celeste`, `Apollo`, etc. |

~94 total quests. Response envelope: `{data: [Quest], pagination: {...}}`
Full field reference: [references/schemas.md](references/schemas.md#quest)

### GET /traders
Get all trader inventories in a single call. No pagination.

GET https://metaforge.app/api/arc-raiders/traders

Response: `{success: true, data: {"Apollo": [TraderItem], "Celeste": [TraderItem], ...}}`
Full field reference: [references/schemas.md](references/schemas.md#trader-item)

### GET /events-schedule
Retrieve upcoming in-game event timers.

GET https://metaforge.app/api/arc-raiders/events-schedule

Response: `{data: [Event]}`
`startTime` and `endTime` are Unix timestamps in **milliseconds**.
Full field reference: [references/schemas.md](references/schemas.md#event)

### GET /game-map-data *(partially documented)*
Retrieve map marker data. Requires a `tableID` param - exact values undocumented.
Returns `{"error": "tableID: null does not exist"}` if param is missing or wrong.
Known maps: Dam, Spaceport, Buried City, Blue Gate, Stella Montis. Try slug forms (`dam`, `spaceport`, `buried-city`).

### GET /event-timers *(DEPRECATED)*
Use `/events-schedule` instead.

## Pagination Envelope
All paginated endpoints return:

```json
{
 "data": [...],
 "pagination": {
 "page": 1,
 "limit": 25,
 "total": 94,
 "totalPages": 4,
 "hasNextPage": true,
 "hasPrevPage": false
 }

## Error Responses
- 400: Invalid parameters or request format
- 404: Resource not found
- 413: Request body too large
- 500: Server-side error

## Common Patterns
**Fetch all quests for a specific trader:**
GET /quests?trader_name=Celeste&limit=100

**Fetch all weapons:**
GET /items?item_type=Weapon&limit=100

**Fetch all trader prices (best for price comparison):**
GET /traders → iterate data["Apollo"], data["Celeste"], etc.
`trader_price` is the buy price; `value` is the base loot value.

**Check upcoming events:**
GET /events-schedule → filter by startTime > Date.now()

**Fetch all ARCs with loot info:**
GET /arcs?includeLoot=true&limit=50
```
