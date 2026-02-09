# Prediction Pool — Future Ideas

Ideas for future versions. Prioritized — top sections are up next.

---

## Priority: What to tackle next

### 1. Settings UX overhaul (do together)
Combines: match editor redesign, odds integration, navigation restructure.
These are one project — reorganizing the settings/admin experience fixes multiple pain points at once.

### 2. Fighter database + autocomplete
The two user requests (autocomplete from pool, base fighter table) are the same feature at two levels. Build the database table first, then add autocomplete on top.

### 3. Odds auto-fetch investigation
Quick analysis — is The Odds API viable for Glory events at all? Determines whether to keep, replace, or drop the auto-fetch feature.

---

## Settings UX overhaul 🔥 UP NEXT

**Refined plan (after PM discussion):**

### Design principle
Everyone can be admin, but admin features should never be confused with personal features. The app is used on mobile during fight nights — admin actions (adding matches, updating odds) need to be fast and frictionless under time pressure.

### Two-tab layout on the pool page

Replace the current single-page layout + separate settings page with two tabs on the pool page:

**"My Predictions" tab (default view):**
- Personal prediction cards for each match
- Full leaderboard below
- This is the view 90% of the time — check picks, check standings

**"Pool" tab:**
- Match cards with inline admin edit controls (for admins)
- "Add match" button (prominent, fast access during fight night)
- "Lock pool" toggle (clearly a pool-wide action, not personal)
- Pool info / settings

The tab split solves the core confusion: "Lock pool" lives in the Pool tab, predictions live in My Predictions. No one will confuse a pool action with a personal action.

### Match editor redesign (within the Pool tab)

Each match is a **compact card** that expands in-place when tapped (one card open at a time):
- Fighter A name — Fighter A odds
- Fighter B name — Fighter B odds
- Multiplier field — Re-fetch odds button — Save button — Delete button
- Save button saves everything in one go (names, odds, fighter data, multiplier)
- Rename "Edit Match" → "Match", "Delete Match" → "Delete"

### Quick win (can ship independently)
- Rename "Lock" button to "Lock pool"
- Add subtitle text: "No one can change predictions after locking"

### What this replaces
- The separate `settings.html` page goes away (or is reduced to pool info/danger zone only)
- The nested `<details>` dropdowns ("Edit Match", "Odds", "Fighter Data") are replaced by the unified compact card editor
- Navigation confusion is resolved by the tab split

## Fighter database + autocomplete

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
- Build this *after* the settings UX overhaul — the dropdown goes into the new match editor, not the old one

**Future freebie (not in scope now):** fighter cards showing cross-pool history ("appeared in 3 pools, predicted correctly 67% of the time")

## Odds auto-fetch: investigation needed 🔍

The odds retrieval feature has never successfully returned results. Analysis of `odds_lookup.py` reveals the likely cause: it only queries `mma_mixed_martial_arts` on The Odds API. Glory Kickboxing events are niche and probably not listed under that sport key.

**Questions to answer:**
- Does The Odds API carry Glory Kickboxing events at all? (Check their sports list)
- If not, are there alternative APIs that cover kickboxing odds?
- Is manual entry sufficient, making auto-fetch not worth the complexity?
- Should the re-fetch button be removed or replaced with a "paste odds" shortcut?

**Last resort: screenshot-based odds extraction.**
If no API covers Glory events and bookmaker sites are too JS-heavy to scrape, an alternative is to navigate to a betting site (Unibet, Toto, bet365, etc.), take a screenshot of the odds page, and use Claude's vision to read and parse the odds from the image. Complicated and brittle, but worth trying if all other automated options fail.

**Decision:** Investigate first, then either fix the integration, switch providers, try screenshot extraction, or remove the feature and streamline manual entry.

## PostgreSQL production database access

Currently there's no practical way to inspect or fix production data. Options to explore (least coding required):

- **Railway CLI:** `railway connect` gives a psql shell directly to the production database
- **Railway dashboard:** Has a built-in data browser for PostgreSQL
- **pgAdmin / TablePlus:** Connect with the `DATABASE_URL` credentials from Railway
- **Read-only replica:** Railway supports read replicas for safe browsing
- **Admin route in app:** A lightweight `/admin/db` page showing table contents (auth-protected) — but this requires coding

Pick the simplest option and document how to use it.

---

## Bugfixes & Improvements

- Add a favicon
- ~~Fix "None" appearing before fighter names~~ ✅ Fixed in ca659fe
- ~~Fix flags not displaying at fighter names~~ ✅ Fixed in ca659fe
- ~~Review the fetch fighter data feature — currently not producing results~~ ✅ Fixed with Glory API (aeee255)
- ~~Investigate deployment without re-creating the database~~ ✅ Resolved with PostgreSQL migration (aad3a52)
- ~~Fix: cannot save predictions on matches added to a re-opened pool~~ ✅ Fixed
- Hide predictions from other participants until the pool is locked
- Accept commas as decimal separators in odds fields (iPhone NL keyboard shows comma, field only accepts periods)
- Toast notifications should be fixed/sticky so they're always visible, not at the top of the page requiring scroll
- Enable Progressive Web App (PWA) — manifest, service worker, installable on mobile

## New Features

- Add a view of all pools where a user can browse and click to join
- Add an image/banner to a pool

---

## Completed sections

### Enhanced Match Data ✅ DONE
- ~~Collect data and images on specific fights and participants~~
- ~~Pull fight history for each fighter (record, weight class, recent results)~~
- ~~Show fighter stats alongside prediction interface~~
- Auto-fetched from Glory API (primary) + Wikipedia/Wikidata (fallback)
- Manual override available in settings

### Odds & Scoring ✅ DONE
- ~~Fetch betting odds from external sources (hybrid: auto + manual fallback)~~
- ~~Display decimal (European) odds on each match card~~
- ~~New scoring: **score = odds x multiplier** (replaces old fixed-point system)~~
- ~~Rename "points" to "multiplier" throughout the app~~
- Auto-fetch via The Odds API (set `ODDS_API_KEY` env var), manual entry fallback
- CSV upload for bulk-importing matches with odds and fighter data

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

### Enhanced Authentication
- Avatar-picker auth (choose your icon from a grid)
- Optional OAuth (Google, Apple) for users who want it
- "Remember me" on device

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
