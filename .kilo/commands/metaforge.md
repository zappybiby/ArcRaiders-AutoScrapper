# MetaForge Lookup

Fetch Arc Raiders game data from MetaForge API.

**Base URL:** `https://metaforge.app/api/arc-raiders`
No auth required. Attribution required in public projects. Commercial use → contact Discord first.

**Endpoints:**

| Endpoint | Description |
|----------|-------------|
| `/items` | Items - filter by `item_type`, `rarity` |
| `/arcs` | ARC enemies with optional loot tables |
| `/quests` | Quests - filter by `trader_name` |
| `/traders` | Trader inventories (no pagination) |
| `/events-schedule` | Upcoming event timers |

**Fetch all quests for a trader:**
```bash
curl "https://metaforge.app/api/arc-raiders/quests?trader_name=Celeste&limit=100"
```

**Fetch all weapons:**
```bash
curl "https://metaforge.app/api/arc-raiders/items?item_type=Weapon&limit=100"
```

**Fetch trader prices:**
```bash
curl "https://metaforge.app/api/arc-raiders/traders"
```
`trader_price` = buy price; `value` = base loot value.

**Check upcoming events:**
```bash
curl "https://metaforge.app/api/arc-raiders/events-schedule"
```
`startTime`/`endTime` are Unix timestamps in **milliseconds**.

**Note:** Cache responses - endpoints may throttle. Treat responses defensively (may change without warning).
