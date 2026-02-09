# Prediction Pool — Backlog

---

## What to tackle next

Pick a lane — items within each group are independent and can be done in any order.

### Quick wins (small, ship in a session)

| Item | Description |
|------|-------------|
| **Favicon** | Add a favicon so the browser tab isn't blank |
| **Comma decimals** | Accept commas as decimal separators in odds fields (iPhone NL keyboard shows comma, field only accepts periods) |
| **Autofill suppression** | Prevent 1Password/autofill popups on Pool Name, Your Name, and PIN fields — blocks the submit button on mobile. Use `autocomplete="off"` or similar attributes |
| **Abbreviated names → full names** | When fighters have abbreviated first names (e.g. "A. Bouzid") and are successfully fetched from the Glory API, update the match to use the full first name |
| **Sticky toasts** | Toast notifications should be fixed/sticky so they're always visible, not scrolled off the top of the page |

### UX & gameplay improvements (medium effort)

| Item | Description |
|------|-------------|
| **Hide predictions until locked** | Other participants' predictions should be hidden until the pool is locked — prevents copying and adds suspense |
| **Clean up settings page** | `settings.html` still exists with pool info + delete pool. Fold these into the Pool tab and remove the separate page, or keep it as a minimal "danger zone" |

### Features (larger effort)

| Item | Description |
|------|-------------|
| **Fighter database + autocomplete** | Persistent `Fighter` table cached from Glory API. Dropdown on the add-match form auto-fills fighter data. See detailed spec below. |
| **Browse & join pools** | A view of all pools where users can browse and click to join |
| **Progressive Web App (PWA)** | Manifest + service worker → installable on mobile home screen |
| **Pool image/banner** | Let pool creators add a banner image (event poster, etc.) |

### Investigation / infrastructure

| Item | Description |
|------|-------------|
| **Odds auto-fetch** | The Odds API has never returned results for Glory events. Investigate viability, alternatives, or drop the feature. See detailed spec below. |
| **Production DB access** | Set up a practical way to inspect/fix production data (Railway CLI, TablePlus, or admin route). See detailed spec below. |

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
