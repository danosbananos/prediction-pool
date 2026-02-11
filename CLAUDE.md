# Prediction Pool — Project Instructions

## Project Overview

A kickboxing fight prediction game built for Glory Kickboxing events. Friends join a pool, predict winners for each match, and compete on a leaderboard. Scoring uses real betting odds: **score = odds x multiplier**.

Built as a server-rendered Flask app — no SPA, no frontend framework, no JavaScript build step. Designed to be simple, mobile-first, and fun.

## Tech Stack

- **Backend:** Flask + SQLAlchemy (single file: `app.py`, ~950 lines)
- **Database:** PostgreSQL in production (Railway), SQLite locally (auto-fallback via `DATABASE_URL` env var)
- **Templates:** Jinja2 (6 templates in `templates/`)
- **Styling:** Custom CSS in `base.html` — fight-night theme (dark background, Oswald/Barlow fonts, crimson/gold palette)
- **Fighter data:** Local Fighter database (synced from Glory API via `sync_fighters.py`), updated per-fighter when selected. Fallback: `fighter_lookup.py` (Glory API -> Wikipedia/Wikidata)
- **Odds data:** The Odds API (optional, needs `ODDS_API_KEY`) + manual entry — see `odds_lookup.py`
- **Deployment:** Railway via GitHub integration (Nixpacks, gunicorn)
- **Dependencies:** stdlib only for HTTP calls (no requests/beautifulsoup), just Flask + SQLAlchemy + gunicorn + psycopg2-binary

## Key Architecture Decisions

- **Single-file app (`app.py`):** Models, routes, helpers all in one file. Keeps things simple for a small app. Split into sections with comment banners.
- **No migrations (yet):** Uses `db.create_all()` on startup. Works for new deployments but can't add columns to existing tables. Flask-Migrate may be needed as the schema evolves.
- **PIN-based auth:** Participants join with a display name + 4-digit PIN. No accounts, no email. Session-based via Flask's `session`. The `SECRET_KEY` is persisted to `instance/.secret_key` to survive server restarts.
- **Fighter database:** All ~650 Glory fighters are stored locally in the `Fighter` table. Initial bulk load is done via `sync_fighters.py` (run locally against the production DB). Individual fighters are updated from the Glory API when selected for a match. Wikipedia/Wikidata is the fallback for fighters not in the Glory database.
- **PostgreSQL for production:** Railway's ephemeral containers wiped SQLite on every deploy. Switched to Railway PostgreSQL addon. Migration script (`migrate_to_pg.py`) handles one-time data transfer.

## File Structure

| File | Purpose |
|------|---------|
| `app.py` | Main app: models (Pool, Match, Participant, Prediction, Fighter), all routes, helpers |
| `fighter_lookup.py` | Fighter data lookup: Glory API -> Wikidata -> Wikipedia fallback chain |
| `odds_lookup.py` | Odds auto-fetch via The Odds API (free tier, 500 req/month) |
| `sync_fighters.py` | Standalone script: bulk-sync all Glory fighters into the database (run locally with `DATABASE_URL`) |
| `migrate_to_pg.py` | One-time SQLite -> PostgreSQL migration script |
| `templates/base.html` | Layout + all CSS + toast notification system |
| `templates/pool.html` | Main pool view: match cards, predictions, leaderboard |
| `templates/settings.html` | Pool admin: add/edit/delete matches, CSV upload, odds, fighter data |
| `templates/fighters_settings.html` | Global settings: fighter database browser, search, add/edit fighters |
| `templates/fighter_edit.html` | Add/edit individual fighter |
| `templates/home.html` | Homepage: create pool |
| `templates/join.html` | Join pool form |
| `templates/signin.html` | Sign back in form |
| `product-backlog.md` | Roadmap, backlog, and known bugs |
| `ux-overhaul-plan.md` | Technical spec for the UX overhaul (temporary — delete after implementation) |
| `CLAUDE.md` | This file — project instructions for Claude |

## Git Workflow

- New features / feature bundles go on a `feature/<name>` branch.
- Bugfixes go on a `bugfix/<name>` branch.
- Always ask before committing and before pushing.
- After pushing, automatically create a PR. Always ask before merging to main.
- Note: this repo uses a git worktree. `git checkout main` fails because main is checked out in the primary worktree. PR merges succeed on GitHub but the local checkout step errors — this is expected, verify with `gh api`.

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Production | PostgreSQL connection string. Omit for local SQLite. Railway sets this automatically. |
| `SECRET_KEY` | Production | Flask session signing key. If unset, auto-generated and persisted to `instance/.secret_key`. **Must be set explicitly in Railway** since the filesystem is ephemeral — without it, user sessions are lost on every deploy. Set to any long random string (e.g. `python3 -c "import secrets; print(secrets.token_hex(32))"`). |
| `ODDS_API_KEY` | Optional | API key for The Odds API (auto-fetch betting odds). Free tier: 500 requests/month. |
| `PORT` | Optional | Server port. Defaults to 5000. Use `PORT=5050` locally to avoid macOS AirPlay conflict. |

## Getting Up to Speed

When resuming work on this project:
1. Check `git status` and `git log --oneline -5` to see where things left off
2. Check `product-backlog.md` for the backlog and known bugs
3. Run `PORT=5050 python3 app.py` to start locally
4. The GitHub repo is `danosbananos/prediction-pool` — use `gh` CLI for PRs

## Style & Preferences

- **Language:** The developer communicates in English and occasionally Dutch. UI is English.
- **Approach:** Pragmatic, ship fast, iterate. No over-engineering. Prefer fixing bugs and adding features over refactoring.
- **Testing:** Manual testing via browser. No test suite. Run locally with `PORT=5050 python3 app.py`.
- **Tone of flash messages:** Short, friendly. Success auto-dismisses (4s), errors persist until dismissed.
- **Design:** Dark, fight-night aesthetic. Mobile-first. No frameworks — all custom CSS.

## Running Locally

```bash
PORT=5050 python3 app.py
# Opens at http://localhost:5050
# Uses SQLite by default (instance/pool.db)
# Set DATABASE_URL for PostgreSQL
```

## Roadmap

See `product-backlog.md` for the full backlog. Priority items:
1. Settings UX overhaul (two-tab layout, unified match editor) — see `ux-overhaul-plan.md`
2. Odds auto-fetch investigation
4. Hide predictions from others until pool is locked
5. Accept commas as decimal separators in odds fields
6. Add favicon
