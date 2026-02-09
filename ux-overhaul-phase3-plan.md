# UX Overhaul — Phase 3: Pool Tab as Complete Management Hub

## Context

After Phase 1+2, match editing moved from Settings to the Pool tab, but several things were lost or misplaced:
- Fighter data editing fields (image URL, record, nationality) are gone entirely
- Re-fetch fighter data button is only on Settings, not next to the match it affects
- CSV import is still on Settings, but it belongs with match management
- CSV upload route still redirects to Settings and its flash message says "in settings"
- Save / Re-fetch / Delete buttons waste vertical space on separate lines

The goal: **Pool tab becomes the single place for all pool management**. Settings page shrinks to just pool info editing + danger zone.

---

## Step 1: Enrich admin match cards in `pool.html`

**In each admin match card's expanded body**, add a second form for fighter data (below the existing edit form):

```
[Fighter Data section]
  Fighter A — Image URL:  [___________]
  Record: [______]  Nationality: [______]
  Fighter B — Image URL:  [___________]
  Record: [______]  Nationality: [______]
  [Save Fighter Data]  [Re-fetch from Wikipedia]
```

This submits to the existing `update_fighter_data` route (separate form, no nesting issues).

**Compact the action buttons** — put Save, Re-fetch Odds, Re-fetch Fighter Data, Delete all in one `.admin-actions` row (flex-wrap handles overflow on small screens).

## Step 2: Move CSV import + bulk fetch to Pool tab in `pool.html`

Below the "Add Match" form, add:
- CSV Upload section (schema docs, template link, file input) — copied from current `settings.html`
- "Fetch Missing Fighter Data" bulk button — currently in `settings.html`

## Step 3: Slim down `settings.html`

Remove:
- CSV Upload section (moved to Pool tab)
- "Fetch Missing Fighter Data" section (moved to Pool tab)
- "Match editing has moved" note

Keep:
- Back to pool link
- Pool Info editing (name, description)
- Danger Zone (delete pool)

Update the footer link in pool.html from `"Pool Settings (CSV, Import, Danger Zone)"` to `"Pool Settings (Name, Danger Zone)"` or similar.

## Step 4: Fix redirects and flash messages in `app.py`

Change `pool_settings` → `pool_view` + `#tab-pool` in these routes:
- `upload_csv` — 5 redirects (lines 754, 758, 765, 769, 829)
- `update_fighter_data` (line ~610)
- `refetch_fighter_data_route` (line ~639)
- `fetch_all_fighter_data` (line ~678)

Fix flash message in `upload_csv` (line 828):
- "You can enter it manually in settings." → "You can enter it manually in the Pool tab."

---

## Files changed

| File | Change |
|------|--------|
| `templates/pool.html` | Add fighter data fields + re-fetch to admin cards, move CSV import + bulk fetch, compact buttons |
| `templates/settings.html` | Remove CSV and bulk fetch sections, remove "moved" note |
| `app.py` | Fix ~8 redirects + 1 flash message |

No CSS changes needed — existing `.admin-edit-grid`, `.admin-actions`, `.card` styles cover the new elements.

## Verification

1. `PORT=5050 python3 app.py`
2. Create new pool → lands on Pool tab → add match → see it appear in accordion
3. Expand admin card → edit fighter names + odds + multiplier (top form) + fighter data (bottom form)
4. Re-fetch fighter data and re-fetch odds buttons work, stay on Pool tab
5. Upload CSV on Pool tab → matches appear, flash messages reference "Pool tab"
6. "Fetch Missing Fighter Data" bulk button works from Pool tab
7. Settings page only shows pool info + danger zone
8. Test on mobile viewport — buttons wrap cleanly
