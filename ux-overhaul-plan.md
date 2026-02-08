# UX Overhaul — Technical Plan

Working document. Delete after implementation.

---

## Goals (from product plan)

1. **Separate admin actions from personal actions** — users should never confuse "Lock pool" with a personal setting
2. **Declutter the prediction view** — the default experience is clean and focused
3. **Fast admin experience on mobile** — adding matches and updating odds during a fight night must be frictionless

## Phasing

### Phase 1+2: Two-tab layout + match editor + quick wins (do together)
### Phase 3: Inline JS saving (no page reloads for match edits)

---

## Phase 1+2: Two-tab layout + match editor

### Architecture: client-side tabs, no page reload

The two tabs ("My Predictions" and "Pool") live on `pool.html` as a **client-side tab switch** using CSS classes toggled by vanilla JS. No extra routes, no extra templates, no page reloads when switching tabs. Both tabs' HTML is rendered server-side and present in the DOM — JS just shows/hides.

```
pool.html structure:
├── Header (pool name, status badge, share link)
├── Tab bar: [My Predictions] [Pool]
├── Tab content: My Predictions (default)
│   ├── Action bar (signed in as / join / sign in)
│   ├── Match cards (prediction interface — existing)
│   ├── Save My Predictions button
│   ├── Everyone's Picks table (when locked/finished)
│   └── Leaderboard
└── Tab content: Pool
    ├── Pool status controls (Lock Pool / Reopen / Finish)
    ├── Match cards (admin editor — compact, expandable)
    ├── Add Match form
    └── Link to settings page (for CSV, bulk actions, danger zone)
```

### The duplicate match card problem

Both tabs show match cards, but with different content:
- **Predictions tab:** Fighter buttons (tap to pick), odds badges, potential scores, result display
- **Pool tab:** Compact summary showing fighter names + odds, expandable to edit form

These are different enough that they should be **two separate Jinja2 blocks**, not one shared component. The predictions tab keeps the existing match card markup almost unchanged. The Pool tab gets new, simpler admin cards.

### Tab bar implementation

```html
<div class="tab-bar">
    <button class="tab active" data-tab="predictions">My Predictions</button>
    <button class="tab" data-tab="pool">Pool</button>
</div>
<div class="tab-content active" id="tab-predictions">
    <!-- existing prediction content -->
</div>
<div class="tab-content" id="tab-pool">
    <!-- admin content -->
</div>
```

```js
document.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', () => {
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
        tab.classList.add('active');
        document.getElementById('tab-' + tab.dataset.tab).classList.add('active');
    });
});
```

```css
.tab-content { display: none; }
.tab-content.active { display: block; }
```

### Admin match card (Pool tab)

Each match is a compact card. Tapping expands it (one at a time) to show the unified edit form.

**Collapsed state:**
```
Match 1                              x2
🇳🇱 Rico Verhoeven (1.40) vs Jamal Ben Saddik 🇲🇦 (3.10)
```

**Expanded state (single unified form):**
```
Fighter A:  [Rico Verhoeven    ] Odds A: [1.40]
Fighter B:  [Jamal Ben Saddik  ] Odds B: [3.10]
Multiplier: [2]
[Re-fetch Odds]  [Save]  [Delete]
```

All fields save in one POST. This replaces the three separate `<details>` sections (Edit Match, Odds, Fighter Data).

### Backend route changes

**Routes that currently redirect to `pool_settings`** — change redirect target:
- `edit_match` → redirect to `pool_view` (with `#tab-pool` anchor to stay on Pool tab)
- `delete_match` → redirect to `pool_view#tab-pool`
- `update_odds` → redirect to `pool_view#tab-pool` (but this route may be merged into edit_match)
- `add_match` → redirect to `pool_view#tab-pool`

**Merge `update_odds` into `edit_match`:**
The unified save button saves fighter names, multiplier, AND odds in one request. The `edit_match` route needs to accept `odds_a` and `odds_b` fields in addition to the existing fields. The separate `update_odds` route can be kept for backward compatibility but is no longer called from the main UI.

**`refetch_odds`** — keep as a separate POST route, redirect to `pool_view#tab-pool`.

**Fighter data fields** — include `fighter_a_image`, `fighter_a_record`, `fighter_a_nationality` (and b equivalents) in the unified edit form as hidden/collapsed fields. These are auto-populated by the Glory API and rarely need manual editing. If needed, they can be in an "Advanced" toggle within the expanded card.

### Quick wins (included in this phase)

1. Rename "Lock Predictions" to **"Lock Pool"** in pool.html
2. Add subtitle: **"No one can change predictions after locking"**
3. Move pool status controls (Lock/Reopen/Finish) from the top of the predictions area to the **Pool tab**

### What stays on settings.html

- Pool info editing (name, description)
- CSV upload (bulk import)
- "Fetch Missing Fighter Data" bulk action
- Danger zone (delete pool)
- Link: "← Back to pool"

### What moves from settings.html to pool.html (Pool tab)

- Individual match editing (unified form: names + odds + multiplier)
- Add Match form
- Pool status controls (lock/reopen/finish)

### Template changes summary

| File | Changes |
|------|---------|
| `pool.html` | Add tab bar + tab content wrappers. Move match admin cards and add-match form here. Move pool status controls to Pool tab. Keep predictions + leaderboard in Predictions tab. |
| `settings.html` | Remove per-match editing sections. Keep pool info, CSV, bulk fetch, danger zone. Update heading to reflect reduced scope. |
| `base.html` | Add CSS for tab bar, tab content, admin match cards, expanded/collapsed states. |

### CSS additions needed

- `.tab-bar` — horizontal bar, two buttons, sticky or near top
- `.tab` / `.tab.active` — styling consistent with fight-night theme (crimson underline for active)
- `.tab-content` / `.tab-content.active` — show/hide
- `.admin-match-card` — compact card style
- `.admin-match-card.expanded` — expanded state showing form
- Responsive: tabs should be full-width on mobile

### Navigation update

The "Settings" button in the actions bar currently links to the settings page. Options:
- **Keep it**, but it now leads to a slimmer settings page (CSV, pool info, danger zone)
- **Rename** to something like "Pool Settings" or "Import & Settings" to clarify scope
- Move it to the Pool tab instead of the top actions bar

Recommendation: Move the Settings link to the **bottom of the Pool tab**, since that's where admin features live. Remove it from the top actions bar to declutter the predictions view.

---

## Phase 3: Inline JS saving

**Goal:** Editing a match (save names, odds, multiplier) should not cause a page reload. The admin can edit multiple matches in sequence without waiting.

### Implementation

Replace form `action` POSTs with `fetch()` calls:

```js
async function saveMatch(matchId, formData) {
    const response = await fetch(`/pool/${poolId}/match/${matchId}/edit`, {
        method: 'POST',
        body: formData
    });
    if (response.ok) {
        // Update card summary in-place
        // Show success toast
        // Collapse card
    }
}
```

### Backend changes for Phase 3

The `edit_match` route needs to detect if the request is an AJAX call (check `Accept` header or a query param) and return JSON instead of redirecting:

```python
@app.route('/pool/<pool_id>/match/<int:match_id>/edit', methods=['POST'])
def edit_match(pool_id, match_id):
    # ... existing logic ...
    if request.headers.get('Accept') == 'application/json':
        return jsonify({'status': 'ok', 'match': { ... }})
    return redirect(url_for('pool_view', pool_id=pool_id))
```

Same pattern for `add_match`, `delete_match`, `refetch_odds`.

### Scope of Phase 3

- Inline save for match editing (names, odds, multiplier)
- Inline delete (with confirm dialog)
- Inline add match
- Inline re-fetch odds
- Toast notifications for success/error (reuse existing flash system, but triggered from JS)
- Result entry (already on pool.html) can also become inline

Phase 3 can be done incrementally — start with edit, then add, then delete.

---

## Execution order

1. Add tab bar + tab content wrappers to `pool.html` (structural change, no new features)
2. Move pool status controls (lock/reopen/finish) to Pool tab
3. Rename "Lock Predictions" → "Lock Pool" + add subtitle
4. Build admin match cards in Pool tab (unified edit form)
5. Add "Add Match" form to Pool tab
6. Update admin routes to redirect to `pool_view#tab-pool`
7. Slim down `settings.html` (remove per-match editing)
8. Move Settings link to Pool tab
9. Add CSS for all new components
10. Test on mobile
11. **Phase 3:** Add inline JS saving (fetch-based, no reloads)

## Risk / considerations

- **No migration needed** — no database changes in this phase
- **All changes are in templates + CSS + routes** — low risk to data
- **The pool.html template will get larger** — currently 294 lines, will roughly double. Consider extracting Jinja2 `{% include %}` partials for predictions vs admin cards if it gets unwieldy.
- **Tab state on redirect** — when an admin action redirects back to pool_view, we need to land on the Pool tab, not Predictions. Use URL fragment (`#tab-pool`) and JS to check `location.hash` on load.
- **Non-signed-in users** — the Pool tab should still be visible (read-only match list) but admin controls (edit, add, delete, lock) should only render for signed-in users. Currently there's no admin role — anyone signed in can admin. This is unchanged.
