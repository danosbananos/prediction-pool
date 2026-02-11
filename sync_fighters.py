#!/usr/bin/env python3
"""
Standalone script to sync all Glory fighters into the production database.

Usage:
    DATABASE_URL="postgresql://..." python3 sync_fighters.py

Clears the fighter table first, then re-populates from the Glory API.
Matches that reference fighters will have their fighter links (fighter_a_id,
fighter_b_id) nullified — the denormalized data on the match is preserved.
"""

import os
import sys
import json
import urllib.request
from datetime import datetime

# ---------------------------------------------------------------------------
# Database setup (minimal Flask app just for SQLAlchemy)
# ---------------------------------------------------------------------------
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)

db_url = os.environ.get('DATABASE_URL')
if not db_url:
    print("ERROR: DATABASE_URL environment variable is required.")
    print("Set it to your Railway PostgreSQL connection string.")
    sys.exit(1)

# Railway uses postgres:// but SQLAlchemy needs postgresql://
if db_url.startswith('postgres://'):
    db_url = db_url.replace('postgres://', 'postgresql://', 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)


# ---------------------------------------------------------------------------
# Models (only what we need)
# ---------------------------------------------------------------------------
class Match(db.Model):
    id           = db.Column(db.Integer, primary_key=True)
    fighter_a_id = db.Column(db.Integer, db.ForeignKey('fighter.id'), nullable=True)
    fighter_b_id = db.Column(db.Integer, db.ForeignKey('fighter.id'), nullable=True)


class Fighter(db.Model):
    id               = db.Column(db.Integer, primary_key=True)
    glory_id         = db.Column(db.Integer, unique=True, nullable=True)
    slug             = db.Column(db.String(200), unique=True, nullable=False)
    name             = db.Column(db.String(200), nullable=False)
    first_name       = db.Column(db.String(100))
    last_name        = db.Column(db.String(100))
    wins             = db.Column(db.Integer, default=0)
    losses           = db.Column(db.Integer, default=0)
    draws            = db.Column(db.Integer, default=0)
    kos              = db.Column(db.Integer, default=0)
    nationality      = db.Column(db.String(100))
    nationality_code = db.Column(db.String(10))
    image_url        = db.Column(db.String(500))
    weight_class     = db.Column(db.String(100))
    height           = db.Column(db.Float)
    weight           = db.Column(db.Float)
    nickname         = db.Column(db.String(200))
    retired          = db.Column(db.Boolean, default=False)
    ranking          = db.Column(db.String(50))
    last_synced      = db.Column(db.DateTime)


# ---------------------------------------------------------------------------
# Glory API sync
# ---------------------------------------------------------------------------
API_BASE = 'https://glory-api.pinkyellow.computer/api/collections/fighters/entries'
LIMIT = 50
TIMEOUT = 30  # generous timeout per page


def fetch_page(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'PredictionPool/1.0'})
    resp = urllib.request.urlopen(req, timeout=TIMEOUT)
    return json.loads(resp.read())


def parse_fighter(entry):
    """Parse a Glory API entry into Fighter field kwargs."""
    fields = {
        'name': entry.get('title', entry.get('slug', '')),
        'first_name': entry.get('first_name'),
        'last_name': entry.get('last_name'),
        'wins': entry.get('wins') or 0,
        'losses': entry.get('losses') or 0,
        'draws': entry.get('draws') or 0,
        'kos': entry.get('kos') or 0,
        'nickname': entry.get('nickname'),
        'retired': bool(entry.get('retired')),
        'last_synced': datetime.utcnow(),
    }

    # nationality: list of dicts [{"key": "FR", "label": "France"}]
    nat = entry.get('nationality')
    if isinstance(nat, list) and nat:
        fields['nationality'] = nat[0].get('label')
        fields['nationality_code'] = nat[0].get('key')
    elif isinstance(nat, str):
        fields['nationality'] = nat

    # image_url
    img = entry.get('front_image') or entry.get('passport_image')
    if isinstance(img, dict):
        fields['image_url'] = img.get('url')
    elif isinstance(img, str):
        fields['image_url'] = img

    # weight_class: list of strings ["welterweight"]
    wc = entry.get('weight_class')
    if isinstance(wc, list) and wc:
        fields['weight_class'] = wc[0]
    elif isinstance(wc, str):
        fields['weight_class'] = wc

    # ranking: dict {"value": "unranked", "label": "Unranked"}
    rank = entry.get('ranking')
    if isinstance(rank, dict):
        fields['ranking'] = rank.get('label') or rank.get('value')
    elif isinstance(rank, str):
        fields['ranking'] = rank

    # height / weight
    for attr in ('height', 'weight'):
        val = entry.get(attr)
        if val:
            try:
                fields[attr] = float(val)
            except (ValueError, TypeError):
                pass

    return fields


def main():
    with app.app_context():
        # Step 1: Nullify fighter references on matches
        linked = Match.query.filter(
            (Match.fighter_a_id.isnot(None)) | (Match.fighter_b_id.isnot(None))
        ).count()
        if linked:
            print(f"Clearing fighter links on {linked} match(es)...")
            Match.query.filter(Match.fighter_a_id.isnot(None)).update(
                {'fighter_a_id': None}, synchronize_session=False
            )
            Match.query.filter(Match.fighter_b_id.isnot(None)).update(
                {'fighter_b_id': None}, synchronize_session=False
            )
            db.session.commit()

        # Step 2: Delete all fighters
        old_count = Fighter.query.count()
        print(f"Deleting {old_count} existing fighter(s)...")
        Fighter.query.delete()
        db.session.commit()

        # Step 3: Fetch all fighters from Glory API
        url = f'{API_BASE}?limit={LIMIT}'
        total_synced = 0
        skipped = 0
        page_num = 0
        seen_slugs = set()

        print(f"Fetching fighters from Glory API...")

        while url:
            page_num += 1
            try:
                page = fetch_page(url)
            except Exception as e:
                print(f"  ERROR on page {page_num}: {e}")
                print("  Retrying in 5 seconds...")
                import time
                time.sleep(5)
                try:
                    page = fetch_page(url)
                except Exception as e2:
                    print(f"  FAILED again: {e2}. Stopping.")
                    break

            total = page.get('meta', {}).get('total', '?')

            for entry in page.get('data', []):
                glory_id = entry.get('id')
                slug = entry.get('slug')
                if not glory_id or not slug:
                    continue

                if slug in seen_slugs:
                    skipped += 1
                    continue
                seen_slugs.add(slug)

                fields = parse_fighter(entry)
                fighter = Fighter(glory_id=glory_id, slug=slug, **fields)
                db.session.add(fighter)
                total_synced += 1

            db.session.commit()
            print(f"  Page {page_num}: {total_synced}/{total} fighters synced")

            # Follow pagination
            next_url = page.get('links', {}).get('next')
            if next_url and next_url != url:
                url = next_url
            else:
                break

        print(f"\nDone! {total_synced} fighters synced ({skipped} duplicates skipped).")
        if linked:
            print(f"Note: fighter links were cleared on {linked} match(es).")
            print("Re-link fighters to matches via the settings page.")


if __name__ == '__main__':
    main()
