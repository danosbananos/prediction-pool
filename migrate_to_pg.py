#!/usr/bin/env python3
"""
One-time migration script: SQLite → PostgreSQL

Usage:
    DATABASE_URL=postgresql://user:pass@host:port/dbname python3 migrate_to_pg.py

Reads from local SQLite (instance/pool.db) and writes to the PostgreSQL
database specified in DATABASE_URL. Preserves all IDs and relationships.
"""

import os
import sys
import sqlite3
from datetime import datetime

# Ensure DATABASE_URL is set to a PostgreSQL URL
pg_url = os.environ.get('DATABASE_URL')
if not pg_url:
    print("Error: Set DATABASE_URL to your PostgreSQL connection string.")
    print("Example: DATABASE_URL=postgresql://localhost/prediction_pool_test python3 migrate_to_pg.py")
    sys.exit(1)

if pg_url.startswith('postgres://'):
    pg_url = pg_url.replace('postgres://', 'postgresql://', 1)

if 'sqlite' in pg_url:
    print("Error: DATABASE_URL points to SQLite. It must be a PostgreSQL URL.")
    sys.exit(1)

# Set DATABASE_URL before importing app (which reads it on import)
os.environ['DATABASE_URL'] = pg_url

from app import app, db, Pool, Match, Participant, Prediction

SQLITE_PATH = os.path.join(os.path.dirname(__file__), 'instance', 'pool.db')


def migrate():
    if not os.path.exists(SQLITE_PATH):
        print(f"Error: SQLite database not found at {SQLITE_PATH}")
        sys.exit(1)

    # Connect to SQLite source
    sqlite_conn = sqlite3.connect(SQLITE_PATH)
    sqlite_conn.row_factory = sqlite3.Row

    print(f"Source:  {SQLITE_PATH}")
    print(f"Target:  {pg_url}")
    print()

    with app.app_context():
        # Create all tables in PostgreSQL
        db.create_all()

        # --- Migrate Pools ---
        rows = sqlite_conn.execute("SELECT * FROM pool").fetchall()
        for row in rows:
            pool = Pool(
                id=row['id'],
                name=row['name'],
                description=row['description'] or '',
                status=row['status'] or 'open',
                created_at=_parse_dt(row['created_at']),
            )
            db.session.merge(pool)  # merge = insert or update
        db.session.commit()
        print(f"Pools:        {len(rows)} migrated")

        # --- Migrate Matches ---
        rows = sqlite_conn.execute("SELECT * FROM match").fetchall()
        for row in rows:
            match = Match(
                id=row['id'],
                pool_id=row['pool_id'],
                participant_a=row['participant_a'],
                participant_b=row['participant_b'],
                multiplier=row['multiplier'] or 1,
                result=row['result'],
                order=row['order'] or 0,
                odds_a=row['odds_a'],
                odds_b=row['odds_b'],
                odds_source=row['odds_source'],
                odds_fetched_at=_parse_dt(row['odds_fetched_at']),
                fighter_a_image=row['fighter_a_image'],
                fighter_a_record=row['fighter_a_record'],
                fighter_a_nationality=row['fighter_a_nationality'],
                fighter_a_flag=row['fighter_a_flag'],
                fighter_b_image=row['fighter_b_image'],
                fighter_b_record=row['fighter_b_record'],
                fighter_b_nationality=row['fighter_b_nationality'],
                fighter_b_flag=row['fighter_b_flag'],
                data_fetched=bool(row['data_fetched']),
            )
            db.session.merge(match)
        db.session.commit()
        print(f"Matches:      {len(rows)} migrated")

        # --- Migrate Participants ---
        rows = sqlite_conn.execute("SELECT * FROM participant").fetchall()
        for row in rows:
            participant = Participant(
                id=row['id'],
                pool_id=row['pool_id'],
                display_name=row['display_name'],
                pin_hash=row['pin_hash'],
                joined_at=_parse_dt(row['joined_at']),
            )
            db.session.merge(participant)
        db.session.commit()
        print(f"Participants: {len(rows)} migrated")

        # --- Migrate Predictions ---
        rows = sqlite_conn.execute("SELECT * FROM prediction").fetchall()
        for row in rows:
            prediction = Prediction(
                id=row['id'],
                participant_id=row['participant_id'],
                match_id=row['match_id'],
                pick=row['pick'],
            )
            db.session.merge(prediction)
        db.session.commit()
        print(f"Predictions:  {len(rows)} migrated")

        # Reset PostgreSQL auto-increment sequences to avoid ID conflicts
        _reset_sequences(db)

    sqlite_conn.close()
    print()
    print("Migration complete!")


def _parse_dt(value):
    """Parse a datetime string from SQLite, or return None."""
    if not value:
        return None
    for fmt in ('%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S.%f', '%Y-%m-%dT%H:%M:%S'):
        try:
            return datetime.strptime(value, fmt)
        except (ValueError, TypeError):
            continue
    return None


def _reset_sequences(db):
    """Reset PostgreSQL sequences so new inserts get IDs after the migrated ones."""
    tables = ['match', 'participant', 'prediction']
    for table in tables:
        try:
            db.session.execute(
                db.text(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                        f"COALESCE((SELECT MAX(id) FROM {table}), 1))")
            )
        except Exception as e:
            print(f"  Warning: could not reset sequence for {table}: {e}")
    db.session.commit()


if __name__ == '__main__':
    migrate()
