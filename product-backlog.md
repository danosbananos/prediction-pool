# Prediction Pool — Backlog

---

## What to tackle next

Pick a lane — items within each group are independent and can be done in any order.

### Bugs

| Item | Description |
|------|-------------|
| **Sign-in toast hard to read** | The "Sign in or join the pool" toast (shown when unauthenticated user taps a fighter card) has a transparent background — text is difficult to read. Should use the same opaque reddish style as other flash notifications. |

### UX & gameplay improvements (medium effort)

| Item | Description |
|------|-------------|
| **Hide predictions until locked** | Other participants' predictions should be hidden until the pool is locked — prevents copying and adds suspense |
| **Clean up settings page** | `settings.html` still exists with pool info + delete pool. Fold these into the Pool tab and remove the separate page, or keep it as a minimal "danger zone" |

### Features (larger effort)

| Item | Description |
|------|-------------|
| **Fighter database + autocomplete** | Persistent `Fighter` table cached from Glory API. Dropdown on the add-match form auto-fills fighter data. See detailed spec below. |
| **Competition framework (v1)** | Generalizable competition system — pools are linked to a competition (Glory event, Olympics, etc.) with start/end dates, theming, and optional Wikidata-powered event import. v1 covers 1v1 events only. See detailed spec below. |
| **Multi-participant predictions (v2)** | Extend the prediction model to support events with many participants (ski jump, 100m sprint, etc.). Dropdown to pick the winner from a list. Depends on competition framework v1. See detailed spec below. |
| **Pool auto-close on event end** | Pools linked to a competition should automatically close for joining when the competition end date has passed. Applies to all competition types (Glory, Olympics, etc.). |
| **Browse & join pools** | A view of all pools where users can browse and click to join |
| **Progressive Web App (PWA)** | Manifest + service worker → installable on mobile home screen |
| **Pool image/banner** | Let pool creators add a banner image (event poster, etc.) |

### Investigation / infrastructure

| Item | Description |
|------|-------------|
| **Odds auto-fetch** | The Odds API has never returned results for Glory events. Investigate viability, alternatives, or drop the feature. See detailed spec below. |

---

## Detailed specs

### Fighter database + autocomplete

User-requested feature (multiple users):

> "When adding fights to a pool, the input field should let you pick from existing fighters in the same pool — or maybe from all pools."

> "A base table of fighters you can select from. Probably handy since it's often the same ones."

**Refined plan (after PM discussion):**

The core insight: this is a **persistent fighter cache with auto-fill**, not a complex autocomplete system. The happy path requires no UI interaction — it just works.

1. Add a `Fighter` table (name, image, record, nationality, flag, glory_api_id)
2. Save/update fighters automatically whenever Glory API data is fetched — the DB is a cache, Glory API stays the source of truth (records etc. stay current)
3. On the "add match" form, add a dropdown of known fighters (populated from the Fighter table)
4. Selecting from the dropdown auto-fills all fighter data fields (image, record, nationality, flag)
5. Typing a new name still works — if Glory finds them, they get added to the table for next time
6. Fighter data is shared across all pools and all users

**Design notes:**
- Dropdown should show "Name (nationality)" or similar to handle name conflicts
- Always update saved data when Glory API is re-fetched (cache, not snapshot)
- The dropdown goes into the match editor in the Pool tab

**Future freebie (not in scope now):** fighter cards showing cross-pool history ("appeared in 3 pools, predicted correctly 67% of the time")

### Odds auto-fetch: investigation needed

The odds retrieval feature has never successfully returned results. Analysis of `odds_lookup.py` reveals the likely cause: it only queries `mma_mixed_martial_arts` on The Odds API. Glory Kickboxing events are niche and probably not listed under that sport key.

**Questions to answer:**
- Does The Odds API carry Glory Kickboxing events at all? (Check their sports list)
- If not, are there alternative APIs that cover kickboxing odds?
- Is manual entry sufficient, making auto-fetch not worth the complexity?
- Should the re-fetch button be removed or replaced with a "paste odds" shortcut?

**Last resort: screenshot-based odds extraction.**
If no API covers Glory events and bookmaker sites are too JS-heavy to scrape, an alternative is to navigate to a betting site (Unibet, Toto, bet365, etc.), take a screenshot of the odds page, and use Claude's vision to read and parse the odds from the image. Complicated and brittle, but worth trying if all other automated options fail.

**Decision:** Investigate first, then either fix the integration, switch providers, try screenshot extraction, or remove the feature and streamline manual entry.

### PostgreSQL production database access

Currently there's no practical way to inspect or fix production data. Options to explore (least coding required):

- **Railway CLI:** `railway connect` gives a psql shell directly to the production database
- **Railway dashboard:** Has a built-in data browser for PostgreSQL
- **pgAdmin / TablePlus:** Connect with the `DATABASE_URL` credentials from Railway
- **Admin route in app:** A lightweight `/admin/db` page showing table contents (auth-protected) — but this requires coding

Pick the simplest option and document how to use it.

### Competition framework — detailed spec

**Vision:** Transform Prediction Pool from a kickboxing-only app into a general-purpose sports prediction platform. Pools are linked to a *competition* (a Glory event, the Winter Olympics, a World Cup, etc.) which determines theming, available data sources, and pool lifecycle.

**Phasing:**
- **v1:** Competition table, Wikidata event import, lightweight theming, 1v1 match support only (covers Olympic boxing, judo, hockey, curling, etc. + Glory)
- **v2:** Multi-participant prediction model (dropdown to pick winner from a list — covers skiing, skating, sprints, etc.)

---

#### Data model (new tables)

**`Competition`**
| Column | Type | Description |
|--------|------|-------------|
| `id` | int PK | |
| `name` | string | e.g. "Winter Olympics 2026", "Glory 94" |
| `type` | string | e.g. "olympics", "glory", "custom" |
| `start_date` | date | First day of competition |
| `end_date` | date | Last day of competition |
| `wikidata_id` | string nullable | e.g. "Q115755642" for 2026 Winter Olympics |
| `theme` | string nullable | Theme identifier, e.g. "olympics", "glory" (default) |

**`Sport`** (cached from Wikidata/API)
| Column | Type | Description |
|--------|------|-------------|
| `id` | int PK | |
| `name` | string | e.g. "Ice Hockey", "Kickboxing" |
| `competition_id` | int FK | |
| `wikidata_id` | string nullable | |

**`SubEvent`** (e.g. "Men's Singles", "Women's Team")
| Column | Type | Description |
|--------|------|-------------|
| `id` | int PK | |
| `name` | string | e.g. "Men's Super-G", "Women's 70kg" |
| `sport_id` | int FK | |
| `scheduled_date` | date nullable | |
| `wikidata_id` | string nullable | |

**`Participant`** (athletes/teams — cached)
| Column | Type | Description |
|--------|------|-------------|
| `id` | int PK | |
| `name` | string | e.g. "Netherlands", "Mikaela Shiffrin" |
| `nationality` | string nullable | |
| `flag` | string nullable | |
| `image_url` | string nullable | |
| `wikidata_id` | string nullable | |

**Changes to existing `Pool` table:**
- Add `competition_id` (FK, nullable) — links pool to a competition
- Pools without a competition continue to work as today (backward compatible)

**Changes to existing `Match` table:**
- Add `sub_event_id` (FK, nullable) — links match to a sub-event
- Add `scheduled_date` (date, nullable) — when the match/event takes place
- Existing matches without sub_event_id continue to work

---

#### Pool creation flow

1. Admin clicks "Create Pool"
2. **New step:** "Link to a competition?" with options:
   - **Pick a known competition** — dropdown of existing competitions in the `Competition` table, or "Add new competition" (name, type, start/end date, optional Wikidata ID)
   - **No competition** — works exactly like today (manual Glory-style pool)
3. If competition selected → pool gets `competition_id`, theming applies, event import becomes available

#### Event import flow (in Pool tab)

1. Admin clicks "Import Events" (only visible if pool has a competition)
2. System queries Wikidata for sports within that competition
3. Admin picks a **sport** (filter dropdown)
4. System queries Wikidata for sub-events within that sport
5. Admin picks a **sub-event** (filter dropdown) and optionally filters by **date**
6. System shows matching fixtures/events:
   - If ≤10 results: all are added as matches
   - If >10 results: admin chooses "Add all" or "Add first 10" (can repeat to paginate)
7. **Fallback:** If Wikidata returns nothing (or competition has no Wikidata ID), admin enters matches manually (same as current flow)

#### Data source: Wikidata SPARQL

**Why Wikidata:**
- Free, no API key needed, no rate limits beyond 100 req/min
- We already use Wikidata as a fallback for fighter data (pattern exists in `fighter_lookup.py`)
- Has structured data for 2026 Winter Olympics (entity Q115755642) including sports, events, athletes, flags, nationalities
- Community-maintained — coverage improves as the event approaches

**Limitations:**
- Requires SPARQL queries (learning curve, but one-time)
- Data may be incomplete for future events — hence manual fallback is first-class
- No real-time scores during events (results still entered manually or via a future auto-results feature)
- Better for pre-event schedule data than live data

**Implementation:** Add a `wikidata_lookup.py` module (similar to `fighter_lookup.py`) with SPARQL queries for:
- Sports within a competition
- Sub-events within a sport
- Participants/fixtures within a sub-event

#### Theming (lightweight)

Each competition type gets a visual override, applied via a CSS class on `<body>`:

| Element | Glory (default) | Olympics |
|---------|-----------------|----------|
| Accent color | Crimson (`#E3263A`) | Olympic blue (`#0085C7`) |
| Banner/header | None (just pool name) | Olympic rings or "Winter Olympics 2026" banner image |
| Favicon | Boxing glove | Olympic rings or snowflake |
| Fonts | Same (Oswald/Barlow) | Same (Oswald/Barlow) |
| Background | Same dark theme | Same dark theme |

Implementation: `body.theme-olympics`, `body.theme-glory` CSS classes with CSS variable overrides. ~20 lines of CSS per theme. Pool template reads `pool.competition.theme` and sets the class.

#### Scoring

- If odds are available (manual entry or future API): **score = odds × multiplier** (same as today)
- If no odds: **flat scoring** — 1 point × multiplier per correct prediction
- Determined per-match: if a match has odds, odds-based scoring; if not, flat scoring
- This requires no code change to the scoring engine — just treat missing odds as 1.0

#### Auto-close on event end

- When a pool has a `competition_id` and `competition.end_date < today`:
  - Pool automatically closes for new joins (but existing participants can still view)
  - Admin can still manage the pool (enter results, finish pool, etc.)
- Check happens on pool load (no background job needed)
- Also applicable to Glory events if admin sets dates

---

#### v2: Multi-participant predictions

*Not in scope for v1 — documented here for future reference.*

- New match type: "multi-participant" (vs current "1v1")
- Match card shows a **dropdown** to pick the winner from a list of participants
- Participants are stored in a join table (`match_participants`) linking `Match` to `Participant`
- Scoring: same as 1v1 — odds × multiplier if odds exist, flat if not
- UI: match card shows event name (e.g. "Men's Super-G") with a dropdown instead of two fighter buttons
- Data model: `Match.match_type` enum ("1v1", "multi") determines which UI to render

---

#### API investigation results (February 2026)

**Free APIs for Olympics schedule data:**
| Source | Coverage | Viability |
|--------|----------|-----------|
| Wikidata SPARQL | 2026 entity exists, structured data, community-maintained | **Best free option** — use this |
| Codante.io | 2024 Paris only | Not viable for 2026 |
| joelschutz/olympics-api | Historical (1896-2014) | Not viable for 2026 |
| Olympics.com scraping | Full official schedule | Brittle, no public API, will break |

**Paid APIs (enterprise, not viable):** SportsDataIO, SportRadar, Data Sports Group

**Odds for Olympics:**
| Source | Coverage | Viability |
|--------|----------|-----------|
| The Odds API | Does not list Olympics | Not viable |
| Polymarket | 76+ Olympics markets, has API | Possible future exploration |
| Sportsbooks (FanDuel, Betfair) | Full Olympics betting | No public API, manual entry only |

**Decision:** Use Wikidata SPARQL for event data, manual entry as fallback. Manual odds entry (flat scoring if no odds). Polymarket worth investigating in future.

---

## Completed

### Settings UX overhaul ✅ DONE (76798aa)
- Two-tab layout on pool page (My Predictions + Pool)
- Compact match editor cards with expand/collapse in Pool tab
- Lock Pool button with subtitle text
- Separate settings page reduced to pool info + delete (still exists)

### Sign out ✅ DONE
- Sign out button in pool header (top-right)
- Clears session for that pool only

### Quick wins ✅ DONE (b4a7e96)
- Favicon (boxing glove emoji)
- Comma decimal separators accepted in all odds fields
- 1Password/autofill suppression on name and PIN inputs
- Abbreviated fighter names updated to full names from Glory API
- Sticky toast notifications (fixed position, opaque, auto-dismiss)

### Enhanced Match Data ✅ DONE
- Auto-fetched from Glory API (primary) + Wikipedia/Wikidata (fallback)
- Manual override available in settings

### Odds & Scoring ✅ DONE
- Decimal (European) odds on each match card
- Scoring: **score = odds x multiplier**
- Auto-fetch via The Odds API (set `ODDS_API_KEY`), manual entry fallback
- CSV upload for bulk-importing matches with odds and fighter data

### Bugfixes (resolved)
- Fix "None" appearing before fighter names (ca659fe)
- Fix flags not displaying at fighter names (ca659fe)
- Fix fetch fighter data feature (Glory API — aeee255)
- Fix deployment without re-creating database (PostgreSQL migration — aad3a52)
- Fix: cannot save predictions on matches added to a re-opened pool

---

## Backlog (lower priority)

### Automatic Result Collection
- After each fight is over, automatically fetch and enter the result
- Sources: official Glory results page, sports APIs, or web scraping
- Push notification or live update when a result comes in

### AI-Generated Avatars
- Allow users to upload a photo of themselves
- Use Claude's image capabilities to generate a fun, kickboxing-themed avatar
- Display avatars on the leaderboard and throughout the app

### Native Mobile Apps
- Wrap the web app in a native shell (React Native, Flutter, or PWA)
- Push notifications for pool updates, fight results, standings changes

### User Management
- Sign in with identity providers (Google, Apple) via OAuth/OpenID Connect
- Password-based accounts with password reset/retrieval flow (email-based)
- Migrate existing PIN-based users to full accounts (optional, backward-compatible)
- User profile page (display name, email, linked identity providers)
- "Remember me" on device
- Avatar-picker auth (choose your icon from a grid)

### Pool Features
- Pool-level passcode for access control
- Draw/no-contest support with configurable point rules
- Multiple pools per tournament
- Pool templates (pre-fill common match formats)
- Pool chat / trash talk section

### Social Features
- Historical leaderboard across multiple tournaments
- "Win streak" badges and achievements
- Share results to social media
- Invite friends via WhatsApp/iMessage deep links

### Data & Analytics
- Prediction accuracy stats per user over time
- Most/least predictable fighters
- Upset tracker (when underdogs win)
- Head-to-head record between friends across pools
