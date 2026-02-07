# Glory Prediction Pool — Project Plan

## Overview

A lightweight, mobile-friendly web app where a small group of friends (2–5 people) can predict the outcomes of kickboxing matches in a tournament, earn points for correct predictions, and see who comes out on top. No mention of betting or monetary amounts — this is purely a prediction game for bragging rights.

---

## 1. Core Features (MVP — Today)

### Pool Management
- **Create a pool**: Give it a name (e.g., "Glory Heavyweight Finals 2026"), optionally a description
- **Edit / delete a pool**: Change name, description, or remove entirely
- **Pool states**: Open (accepting predictions) → Locked (no more changes to predictions) → Finished (results entered, winner declared)
- **Share link**: Each pool gets a unique URL that you can send to friends

### Match Management
- **Add matches to a pool**: Each match has two participant names and a point value (set by whoever adds it)
- **Edit / delete matches**: Update names, points, or remove a match
- **Enter results**: After a fight, anyone can mark which participant won (or mark a draw)

### Predictions
- **Join a pool**: Enter your display name + a 4-digit PIN → you're a participant
- **Make predictions**: For each match, pick who you think will win
- **Edit predictions**: Change your mind anytime while the pool is still open (requires your PIN)
- **Lock**: Once the pool is locked, no more prediction changes

### Scoring & Results
- **Point values**: Each match has a point value assigned by whoever created/edited it
- **Correct prediction** = you earn those points
- **Final standings**: When the pool is marked finished and all results are entered, display a leaderboard ranked by total points
- **Winner declaration**: The person at the top of the leaderboard is declared the winner

### User Identity
- **Display name + 4-digit PIN**: Simple, no email, no password
- **PIN is only needed to edit your own predictions** — viewing the pool, standings, and other people's picks is open
- **Future upgrade path**: Avatar picker, pattern lock, or OAuth can replace this later

---

## 2. Tech Stack

| Layer | Choice | Rationale |
|-------|--------|-----------|
| **Backend** | Python + Flask | Daniël knows Python; Flask is minimal and fast to build with |
| **Database** | SQLite | Zero config, single file, more than enough for 5 users |
| **Frontend** | Server-rendered HTML + minimal JS (HTMX or vanilla) | No build step, no React overhead, works perfectly on phones |
| **CSS** | Pico CSS or Simple.css | Classless or minimal CSS framework — looks good with zero effort, mobile-responsive out of the box |
| **Hosting** | Railway.app | Fastest deploy path, auto-detects Python, ~$0–2/month after trial |
| **Domain** | GoDaddy domain → CNAME to Railway | Or: point GoDaddy nameservers to Cloudflare (free) for easier DNS management |

### Why this stack?
- **No build tools**: No npm, no webpack, no compilation step. Write Python + HTML, push to git, it's live.
- **SQLite is fine**: With 5 concurrent users and read-heavy workload, SQLite handles this trivially. No database server to manage.
- **Server-rendered HTML**: The app is simple enough that a Single Page App framework adds complexity without benefit. HTMX can add interactivity (live updates, inline editing) without JavaScript overhead.
- **Mobile-first by default**: Pico CSS / Simple.css are responsive out of the box. No media queries needed.

---

## 3. Data Model

```
Pool
├── id (UUID, used in share URL)
├── name
├── description (optional)
├── status: open | locked | finished
├── created_at
│
├── Matches[]
│   ├── id
│   ├── participant_a (name)
│   ├── participant_b (name)
│   ├── points (integer)
│   ├── result: null | "a" | "b" | "draw"
│   └── order (display order)
│
└── Participants[]
    ├── id
    ├── display_name
    ├── pin_hash (hashed 4-digit PIN)
    │
    └── Predictions[]
        ├── match_id
        └── pick: "a" | "b"
```

Key design decisions:
- Pool ID is a UUID (or short random string) so URLs aren't guessable/sequential
- PIN is hashed (even though it's just 4 digits, it's good practice)
- Draw is supported but optional — most kickboxing tournaments don't end in draws
- No separate "admin" role — anyone can edit pool settings and enter results (as specified)

---

## 4. Page Structure

| Page | URL | Purpose |
|------|-----|---------|
| Home | `/` | Create a new pool or enter a pool code |
| Pool view | `/pool/<id>` | See matches, standings, make/edit predictions |
| Pool settings | `/pool/<id>/settings` | Edit pool name, status, manage matches |
| Join pool | `/pool/<id>/join` | Enter display name + PIN to participate |
| Results | `/pool/<id>/results` | Enter fight outcomes (when pool is locked/finished) |

Everything is optimized for mobile: big tap targets, readable text, no horizontal scrolling.

---

## 5. Hosting & Deployment Plan

### Step 1: Create a GitHub/GitLab repository
Push the app code to a repo.

### Step 2: Connect to Railway
1. Sign up at railway.app (GitHub login)
2. "New Project" → "Deploy from GitHub Repo"
3. Railway auto-detects Python, installs dependencies from `requirements.txt`
4. App is live on a `*.railway.app` subdomain within minutes

### Step 3: Connect your domain
**Option A (simpler):** In GoDaddy, add a CNAME record pointing your domain (or a subdomain like `pool.yourdomain.com`) to Railway's provided hostname.

**Option B (recommended long-term):** Transfer DNS management to Cloudflare (free), then add CNAME there. Cloudflare gives you free SSL, caching, and easier DNS management. GoDaddy's DNS panel is functional but clunky.

### Step 4: Environment
- Set `SECRET_KEY` as a Railway environment variable
- SQLite file lives on Railway's persistent volume (or we use Railway's PostgreSQL if SQLite persistence is unreliable on the platform)

**Estimated deployment time: 15–25 minutes** (assuming the app code is ready)

---

## 6. Red Team Review

Here's where I poke holes in the plan and address them:

### Risk 1: SQLite on Railway might not persist
**Problem:** Railway uses ephemeral containers. If the container restarts, an SQLite file could be lost.
**Mitigation:** Railway supports persistent volumes. Attach one and store the DB there. **Backup plan:** Switch to Railway's PostgreSQL add-on (free tier, zero config). The code change is ~5 lines with SQLAlchemy.
**Severity:** High if unaddressed, trivial to fix.

### Risk 2: No authentication = anyone with the URL can vandalize the pool
**Problem:** Since anyone can edit pool settings and enter results, a random person (or a mischievous friend) could mess things up.
**Mitigation:** The pool URL uses a random UUID — it's not guessable. For today's MVP, this is acceptable for a trusted friend group. Future enhancement: add a pool-level passcode.
**Severity:** Low for 5 friends. Medium if the link leaks.

### Risk 3: PIN is only 4 digits — brute-forceable
**Problem:** 10,000 combinations. A determined person could try them all.
**Mitigation:** Add rate limiting (max 5 PIN attempts per minute per IP). For 5 friends, nobody's going to brute-force a PIN — but rate limiting is 3 lines of code.
**Severity:** Very low for this audience. Include rate limiting anyway.

### Risk 4: "Anyone can enter results" could cause conflicts
**Problem:** Two people enter different results for the same fight at the same time.
**Mitigation:** Last write wins, but show who entered the result and when. If there's a dispute, anyone can correct it. For 5 friends watching together, this is a non-issue.
**Severity:** Very low.

### Risk 5: No data backup
**Problem:** If the database is corrupted or the hosting goes down, everything is lost.
**Mitigation:** For today, acceptable. For future: daily SQLite backup to a file, or use PostgreSQL with Railway's automatic backups.
**Severity:** Low (it's a fun pool, not financial records).

### Risk 6: Mobile UX could be poor if not tested
**Problem:** We're building fast — mobile responsiveness might have issues.
**Mitigation:** Using Pico CSS / Simple.css ensures baseline mobile support. Test on phone immediately after deploy.
**Severity:** Medium. Mitigated by framework choice.

### Risk 7: Time pressure — the tournament is TODAY
**Problem:** Rushing leads to bugs. Features might not work correctly.
**Mitigation:** Ruthlessly scope down. The MVP is: create pool → add matches → share link → friends join → make picks → enter results → see winner. That's it. No edit/delete for v1 if it saves time. No fancy CSS. Function over form.
**Severity:** High. Addressed by aggressive scoping below.

---

## 7. MVP Scope (Aggressive — for today)

**Absolutely must have:**
1. Create a pool with a name
2. Add matches (two names + point value) to the pool
3. Share pool link
4. Join pool (name + PIN)
5. Pick a winner for each match
6. Lock the pool (no more prediction changes)
7. Enter results for each match
8. See leaderboard / declare winner

**Cut for today, add later:**
- Edit/delete pools (just create a new one if you mess up)
- Edit/delete matches (get it right the first time, or we add a quick "delete" button if time permits)
- Pool description field
- Pretty styling (functional but not beautiful is fine)
- Draws (declare one participant as winner in a draw scenario, or skip)

---

## 8. Time Estimate

| Task | Estimated Time |
|------|---------------|
| Project setup (Flask, SQLite, folder structure) | 15 min |
| Data models + database | 20 min |
| Pool creation page | 15 min |
| Match management (add matches to pool) | 20 min |
| Join pool + PIN system | 15 min |
| Prediction interface (pick winners) | 25 min |
| Results entry | 15 min |
| Leaderboard / scoring | 20 min |
| Mobile-friendly CSS (Pico/Simple.css) | 10 min |
| Testing + bug fixes | 20 min |
| Deploy to Railway | 15 min |
| Connect domain (GoDaddy → Railway) | 15 min |
| **Total** | **~3–3.5 hours** |

### Realistic expectation
With back-and-forth, debugging, and "oh wait, that doesn't work on mobile" moments: **4–5 hours from start to live**. If we start now and focus, the app could be live and usable by mid-afternoon.

### What we'll build together vs. what I'll generate
I'll generate the bulk of the code (Flask app, templates, CSS, database setup) and walk you through deployment step by step. Your main tasks will be:
1. Creating the Railway account
2. Running a few terminal commands to deploy
3. Configuring DNS in GoDaddy
4. Testing on your phone and telling me what's broken

---

## 9. Future Ideas (Separate Document)

See `future-ideas.md` for post-MVP features including:
- Fight data + images from external sources
- Automatic result collection
- AI-generated avatars from user photos
- Native mobile apps (iOS/Android)
- Avatar-based authentication
- Pool passcodes
- Match draw support
- Pool history and stats
