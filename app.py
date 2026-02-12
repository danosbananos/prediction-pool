import os
import io
import csv
import uuid
import secrets
import logging
from datetime import datetime
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, session, abort, jsonify, Response
)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from fighter_lookup import lookup_fighter, _has_abbreviated_first_name
from odds_lookup import lookup_odds

logger = logging.getLogger(__name__)

app = Flask(__name__)
# Use a stable secret key: env var, or fall back to a file-based key so
# sessions survive server restarts during development.
def _get_or_create_secret_key():
    env_key = os.environ.get('SECRET_KEY')
    if env_key:
        return env_key
    key_file = os.path.join(os.path.dirname(__file__), 'instance', '.secret_key')
    os.makedirs(os.path.dirname(key_file), exist_ok=True)
    if os.path.exists(key_file):
        with open(key_file) as f:
            return f.read().strip()
    key = secrets.token_hex(32)
    with open(key_file, 'w') as f:
        f.write(key)
    return key

app.config['SECRET_KEY'] = _get_or_create_secret_key()
database_url = os.environ.get('DATABASE_URL', 'sqlite:///pool.db')
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)


@app.template_filter('country_flag')
def country_flag_filter(code):
    if not code or len(code) != 2:
        return ''
    return ''.join(chr(0x1F1E6 + ord(c) - ord('A')) for c in code.upper())


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class Pool(db.Model):
    id = db.Column(db.String(12), primary_key=True, default=lambda: uuid.uuid4().hex[:12])
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default='')
    status = db.Column(db.String(20), default='open')  # open, locked, finished
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    matches = db.relationship('Match', backref='pool', cascade='all, delete-orphan',
                              order_by='Match.order')
    participants = db.relationship('Participant', backref='pool', cascade='all, delete-orphan')

    @property
    def all_results_entered(self):
        return all(m.result is not None for m in self.matches)


class Match(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    pool_id = db.Column(db.String(12), db.ForeignKey('pool.id'), nullable=False)
    participant_a = db.Column(db.String(200), nullable=False)
    participant_b = db.Column(db.String(200), nullable=False)
    multiplier = db.Column(db.Integer, default=1)  # renamed from 'points'
    result = db.Column(db.String(10), nullable=True)  # 'a', 'b', 'draw', or None
    order = db.Column(db.Integer, default=0)
    predictions = db.relationship('Prediction', backref='match', cascade='all, delete-orphan')

    # Odds (decimal format, e.g. 1.50, 2.80)
    odds_a = db.Column(db.Float, nullable=True)   # odds for fighter A winning
    odds_b = db.Column(db.Float, nullable=True)   # odds for fighter B winning
    odds_source = db.Column(db.String(100), nullable=True)  # e.g. "The Odds API", "Manual", "CSV"
    odds_fetched_at = db.Column(db.DateTime, nullable=True)

    # Enhanced fighter data
    fighter_a_image = db.Column(db.String(500), nullable=True)
    fighter_a_record = db.Column(db.String(50), nullable=True)
    fighter_a_nationality = db.Column(db.String(100), nullable=True)
    fighter_a_flag = db.Column(db.String(10), nullable=True)

    fighter_b_image = db.Column(db.String(500), nullable=True)
    fighter_b_record = db.Column(db.String(50), nullable=True)
    fighter_b_nationality = db.Column(db.String(100), nullable=True)
    fighter_b_flag = db.Column(db.String(10), nullable=True)

    data_fetched = db.Column(db.Boolean, default=False)

    # Link to Fighter database
    fighter_a_id = db.Column(db.Integer, db.ForeignKey('fighter.id'), nullable=True)
    fighter_b_id = db.Column(db.Integer, db.ForeignKey('fighter.id'), nullable=True)
    fighter_a_ref = db.relationship('Fighter', foreign_keys='Match.fighter_a_id')
    fighter_b_ref = db.relationship('Fighter', foreign_keys='Match.fighter_b_id')

    def effective_odds_a(self):
        """Return odds for fighter A, defaulting to 1.0 if not set."""
        return self.odds_a if self.odds_a else 1.0

    def effective_odds_b(self):
        """Return odds for fighter B, defaulting to 1.0 if not set."""
        return self.odds_b if self.odds_b else 1.0

    def potential_score(self, pick):
        """Calculate potential score for a given pick."""
        odds = self.effective_odds_a() if pick == 'a' else self.effective_odds_b()
        return round(odds * self.multiplier, 1)


class Participant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    pool_id = db.Column(db.String(12), db.ForeignKey('pool.id'), nullable=False)
    display_name = db.Column(db.String(100), nullable=False)
    pin_hash = db.Column(db.String(256), nullable=False)
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)
    predictions = db.relationship('Prediction', backref='participant', cascade='all, delete-orphan')

    def check_pin(self, pin):
        return check_password_hash(self.pin_hash, pin)

    def score(self):
        total = 0.0
        for pred in self.predictions:
            if pred.match.result and pred.pick == pred.match.result:
                odds = 1.0  # default if no odds
                if pred.pick == 'a' and pred.match.odds_a:
                    odds = pred.match.odds_a
                elif pred.pick == 'b' and pred.match.odds_b:
                    odds = pred.match.odds_b
                total += odds * pred.match.multiplier
        return round(total, 1)


class Prediction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    participant_id = db.Column(db.Integer, db.ForeignKey('participant.id'), nullable=False)
    match_id = db.Column(db.Integer, db.ForeignKey('match.id'), nullable=False)
    pick = db.Column(db.String(10), nullable=False)  # 'a' or 'b'

    __table_args__ = (
        db.UniqueConstraint('participant_id', 'match_id', name='uq_participant_match'),
    )


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
# Helpers
# ---------------------------------------------------------------------------

def get_pool_or_404(pool_id):
    pool = db.session.get(Pool, pool_id)
    if not pool:
        abort(404)
    return pool


def fetch_fighter_data(match, skip_a=False, skip_b=False):
    """
    Fetch and store fighter data for fighters in a match.

    Args:
        skip_a: If True, don't fetch for fighter A (already has data)
        skip_b: If True, don't fetch for fighter B (already has data)

    Returns:
        dict with 'found_a' and 'found_b' booleans indicating whether
        data was found for each fighter.
    """
    found_a = False
    found_b = False

    if not skip_a:
        data_a = lookup_fighter(match.participant_a)
        logger.info("Lookup result for '%s': %s", match.participant_a, data_a)
        if any(v for k, v in data_a.items() if k not in ("nationality_flag", "full_name")):
            if data_a.get("image_url"):
                match.fighter_a_image = data_a["image_url"]
            if data_a.get("record"):
                match.fighter_a_record = data_a["record"]
            if data_a.get("nationality"):
                match.fighter_a_nationality = data_a["nationality"]
            # Flag can be empty string, so use explicit None check
            if data_a.get("nationality_flag") is not None:
                match.fighter_a_flag = data_a["nationality_flag"] or None
            # Update abbreviated name to full name (e.g. "A. Bouzid" -> "Ayoub Bouzid")
            if data_a.get("full_name") and _has_abbreviated_first_name(match.participant_a):
                match.participant_a = data_a["full_name"]
            found_a = True
    else:
        found_a = True  # already had data

    if not skip_b:
        data_b = lookup_fighter(match.participant_b)
        logger.info("Lookup result for '%s': %s", match.participant_b, data_b)
        if any(v for k, v in data_b.items() if k not in ("nationality_flag", "full_name")):
            if data_b.get("image_url"):
                match.fighter_b_image = data_b["image_url"]
            if data_b.get("record"):
                match.fighter_b_record = data_b["record"]
            if data_b.get("nationality"):
                match.fighter_b_nationality = data_b["nationality"]
            if data_b.get("nationality_flag") is not None:
                match.fighter_b_flag = data_b["nationality_flag"] or None
            if data_b.get("full_name") and _has_abbreviated_first_name(match.participant_b):
                match.participant_b = data_b["full_name"]
            found_b = True
    else:
        found_b = True  # already had data

    match.data_fetched = True
    return {'found_a': found_a, 'found_b': found_b}


def fetch_odds_data(match):
    """Try to auto-fetch odds for a match. Does not overwrite existing manual odds."""
    if match.odds_source == 'Manual' or match.odds_source == 'CSV':
        return  # don't overwrite manually entered or CSV-imported odds
    result = lookup_odds(match.participant_a, match.participant_b)
    if result:
        match.odds_a = result['odds_a']
        match.odds_b = result['odds_b']
        match.odds_source = result['source']
        match.odds_fetched_at = datetime.utcnow()


def parse_csv_matches(file_content):
    """
    Parse a CSV file with match data.

    Required columns: fighter_a, fighter_b
    Optional columns: multiplier, odds_a, odds_b,
                      fighter_a_record, fighter_a_nationality,
                      fighter_b_record, fighter_b_nationality,
                      fighter_a_image, fighter_b_image

    Returns a list of dicts, one per match.
    """
    # Try to detect encoding — handle BOM for Excel-generated CSVs
    if isinstance(file_content, bytes):
        for encoding in ('utf-8-sig', 'utf-8', 'latin-1'):
            try:
                file_content = file_content.decode(encoding)
                break
            except UnicodeDecodeError:
                continue

    reader = csv.DictReader(io.StringIO(file_content))

    # Normalize header names (strip whitespace, lowercase)
    if reader.fieldnames:
        reader.fieldnames = [f.strip().lower().replace(' ', '_') for f in reader.fieldnames]

    matches = []
    for row in reader:
        # Skip empty rows
        fighter_a = row.get('fighter_a', '').strip()
        fighter_b = row.get('fighter_b', '').strip()
        if not fighter_a or not fighter_b:
            continue

        match_data = {
            'fighter_a': fighter_a,
            'fighter_b': fighter_b,
        }

        # Optional: multiplier
        mult = row.get('multiplier', '').strip()
        if mult:
            try:
                match_data['multiplier'] = max(1, int(mult))
            except ValueError:
                match_data['multiplier'] = 1
        else:
            match_data['multiplier'] = 1

        # Optional: odds
        for key in ('odds_a', 'odds_b'):
            val = row.get(key, '').strip().replace(',', '.')
            if val:
                try:
                    match_data[key] = round(float(val), 2)
                except ValueError:
                    pass

        # Optional: fighter data
        for key in ('fighter_a_record', 'fighter_a_nationality',
                     'fighter_b_record', 'fighter_b_nationality',
                     'fighter_a_image', 'fighter_b_image'):
            val = row.get(key, '').strip()
            if val:
                match_data[key] = val

        matches.append(match_data)

    return matches


def current_participant(pool_id):
    """Return the Participant object for the currently logged-in user in this pool, or None."""
    pid = session.get(f'participant_{pool_id}')
    if pid:
        return db.session.get(Participant, pid)
    return None


def populate_match_from_fighter(match, side, fighter):
    """Copy Fighter DB data onto Match's denormalized fields for the given side ('a' or 'b')."""
    record = f"{fighter.wins}-{fighter.losses}-{fighter.draws}" if fighter.wins is not None else None
    flag = country_flag_filter(fighter.nationality_code) or None
    if side == 'a':
        match.participant_a = fighter.name
        match.fighter_a_image = fighter.image_url
        match.fighter_a_record = record
        match.fighter_a_nationality = fighter.nationality
        match.fighter_a_flag = flag
    else:
        match.participant_b = fighter.name
        match.fighter_b_image = fighter.image_url
        match.fighter_b_record = record
        match.fighter_b_nationality = fighter.nationality
        match.fighter_b_flag = flag


def refresh_fighter_from_glory(fighter):
    """For fighters with a glory_id, fetch latest data from the Glory API and update the record."""
    if not fighter or not fighter.glory_id:
        return
    import urllib.request
    import json as _json

    API_BASE = 'https://glory-api.pinkyellow.computer/api/collections/fighters/entries'
    url = f'{API_BASE}/{fighter.glory_id}'
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'PredictionPool/1.0'})
        resp = urllib.request.urlopen(req, timeout=20)
        entry = _json.loads(resp.read()).get('data', {})
    except Exception:
        return

    if not entry:
        return

    fighter.name = entry.get('title', fighter.name)
    fighter.first_name = entry.get('first_name') or fighter.first_name
    fighter.last_name = entry.get('last_name') or fighter.last_name
    fighter.wins = entry.get('wins') or fighter.wins or 0
    fighter.losses = entry.get('losses') or fighter.losses or 0
    fighter.draws = entry.get('draws') or fighter.draws or 0
    fighter.kos = entry.get('kos') or fighter.kos or 0

    nat = entry.get('nationality')
    if isinstance(nat, list) and nat:
        fighter.nationality = nat[0].get('label')
        fighter.nationality_code = nat[0].get('key')
    elif isinstance(nat, str):
        fighter.nationality = nat

    img = entry.get('front_image') or entry.get('passport_image')
    if isinstance(img, dict):
        fighter.image_url = img.get('url')
    elif isinstance(img, str):
        fighter.image_url = img

    fighter.last_synced = datetime.utcnow()


# ---------------------------------------------------------------------------
# Routes — Home
# ---------------------------------------------------------------------------

@app.route('/')
def home():
    recent_pools = session.get('recent_pools', [])
    # Validate pools still exist and refresh status
    if recent_pools:
        pool_ids = [r['id'] for r in recent_pools]
        existing = {p.id: p for p in Pool.query.filter(Pool.id.in_(pool_ids)).all()}
        recent_pools = [
            {'id': p.id, 'name': p.name, 'status': p.status}
            for r in recent_pools
            if (p := existing.get(r['id']))
        ]
        session['recent_pools'] = recent_pools
    return render_template('home.html', recent_pools=recent_pools)


@app.route('/create', methods=['POST'])
def create_pool():
    name = request.form.get('name', '').strip()
    if not name:
        flash('Please enter a pool name.', 'error')
        return redirect(url_for('home'))
    pool = Pool(name=name)
    db.session.add(pool)
    db.session.commit()
    flash(f'Pool "{pool.name}" created! Now add some matches.', 'success')
    return redirect(url_for('pool_view', pool_id=pool.id) + '#tab-pool')


# ---------------------------------------------------------------------------
# Routes — Pool View (main page: predictions + leaderboard)
# ---------------------------------------------------------------------------

@app.route('/pool/<pool_id>')
def pool_view(pool_id):
    pool = get_pool_or_404(pool_id)
    me = current_participant(pool_id)

    # Track this pool in the session for "recent pools" on home page
    recent = session.get('recent_pools', [])
    recent = [r for r in recent if r['id'] != pool.id]
    recent.insert(0, {'id': pool.id, 'name': pool.name, 'status': pool.status})
    session['recent_pools'] = recent[:5]

    # Build leaderboard
    leaderboard = sorted(pool.participants, key=lambda p: p.score(), reverse=True)

    # Build my predictions lookup
    my_predictions = {}
    if me:
        for pred in me.predictions:
            my_predictions[pred.match_id] = pred.pick

    # Build prediction summary (how many picked A vs B per match)
    pred_summary = {}
    for match in pool.matches:
        a_count = sum(1 for p in match.predictions if p.pick == 'a')
        b_count = sum(1 for p in match.predictions if p.pick == 'b')
        pred_summary[match.id] = {'a': a_count, 'b': b_count}

    # Build all predictions lookup for display after pool is locked/finished
    all_predictions = {}
    if pool.status in ('locked', 'finished'):
        for participant in pool.participants:
            all_predictions[participant.id] = {}
            for pred in participant.predictions:
                all_predictions[participant.id][pred.match_id] = pred.pick

    return render_template('pool.html',
                           pool=pool, me=me, leaderboard=leaderboard,
                           my_predictions=my_predictions,
                           pred_summary=pred_summary,
                           all_predictions=all_predictions)


# ---------------------------------------------------------------------------
# Routes — Join Pool
# ---------------------------------------------------------------------------

@app.route('/pool/<pool_id>/join', methods=['GET', 'POST'])
def join_pool(pool_id):
    pool = get_pool_or_404(pool_id)
    me = current_participant(pool_id)
    if me:
        return redirect(url_for('pool_view', pool_id=pool_id))

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        pin = request.form.get('pin', '').strip()

        if not name:
            flash('Please enter your name.', 'error')
            return render_template('join.html', pool=pool)
        if not pin or len(pin) != 4 or not pin.isdigit():
            flash('PIN must be exactly 4 digits.', 'error')
            return render_template('join.html', pool=pool)

        # Check for duplicate name in this pool
        existing = Participant.query.filter_by(pool_id=pool_id, display_name=name).first()
        if existing:
            flash('That name is already taken in this pool.', 'error')
            return render_template('join.html', pool=pool)

        participant = Participant(
            pool_id=pool_id,
            display_name=name,
            pin_hash=generate_password_hash(pin)
        )
        db.session.add(participant)
        db.session.commit()
        session[f'participant_{pool_id}'] = participant.id
        flash(f'Welcome, {name}! Make your predictions below.', 'success')
        return redirect(url_for('pool_view', pool_id=pool_id))

    return render_template('join.html', pool=pool)


# ---------------------------------------------------------------------------
# Routes — Sign back in (re-auth with PIN)
# ---------------------------------------------------------------------------

@app.route('/pool/<pool_id>/signin', methods=['GET', 'POST'])
def signin(pool_id):
    pool = get_pool_or_404(pool_id)

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        pin = request.form.get('pin', '').strip()

        participant = Participant.query.filter_by(pool_id=pool_id, display_name=name).first()
        if participant and participant.check_pin(pin):
            session[f'participant_{pool_id}'] = participant.id
            flash(f'Welcome back, {name}!', 'success')
            return redirect(url_for('pool_view', pool_id=pool_id))
        else:
            flash('Name or PIN incorrect.', 'error')

    return render_template('signin.html', pool=pool)


# ---------------------------------------------------------------------------
# Routes — Sign out
# ---------------------------------------------------------------------------

@app.route('/pool/<pool_id>/logout', methods=['POST'])
def logout(pool_id):
    pool = get_pool_or_404(pool_id)
    session.pop(f'participant_{pool_id}', None)
    flash('You have been signed out.', 'success')
    return redirect(url_for('pool_view', pool_id=pool_id))


# ---------------------------------------------------------------------------
# Routes — Save Predictions
# ---------------------------------------------------------------------------

@app.route('/pool/<pool_id>/predict', methods=['POST'])
def save_predictions(pool_id):
    pool = get_pool_or_404(pool_id)
    me = current_participant(pool_id)
    if not me:
        flash('Please join the pool first.', 'error')
        return redirect(url_for('join_pool', pool_id=pool_id))
    if pool.status != 'open':
        flash('This pool is no longer accepting predictions.', 'error')
        return redirect(url_for('pool_view', pool_id=pool_id))

    for match in pool.matches:
        pick = request.form.get(f'match_{match.id}')
        if pick in ('a', 'b'):
            existing = Prediction.query.filter_by(
                participant_id=me.id, match_id=match.id
            ).first()
            if existing:
                existing.pick = pick
            else:
                db.session.add(Prediction(
                    participant_id=me.id, match_id=match.id, pick=pick
                ))

    db.session.commit()
    flash('Predictions saved!', 'success')
    return redirect(url_for('pool_view', pool_id=pool_id))


# ---------------------------------------------------------------------------
# Routes — Pool Settings (manage matches, pool status)
# ---------------------------------------------------------------------------

@app.route('/pool/<pool_id>/settings')
def pool_settings(pool_id):
    pool = get_pool_or_404(pool_id)
    return render_template('settings.html', pool=pool)


@app.route('/pool/<pool_id>/match/add', methods=['POST'])
def add_match(pool_id):
    pool = get_pool_or_404(pool_id)
    a = request.form.get('participant_a', '').strip()
    b = request.form.get('participant_b', '').strip()
    multiplier = request.form.get('multiplier', '1').strip()

    if not a or not b:
        flash('Both participant names are required.', 'error')
        return redirect(url_for('pool_view', pool_id=pool_id) + '#tab-pool')

    try:
        multiplier = max(1, int(multiplier))
    except ValueError:
        multiplier = 1

    # Check for linked fighters from autocomplete
    fighter_a_id = request.form.get('fighter_a_id', '').strip()
    fighter_b_id = request.form.get('fighter_b_id', '').strip()
    fighter_a = db.session.get(Fighter, int(fighter_a_id)) if fighter_a_id else None
    fighter_b = db.session.get(Fighter, int(fighter_b_id)) if fighter_b_id else None

    order = len(pool.matches)
    match = Match(pool_id=pool_id, participant_a=a, participant_b=b,
                  multiplier=multiplier, order=order,
                  fighter_a_id=int(fighter_a_id) if fighter_a_id else None,
                  fighter_b_id=int(fighter_b_id) if fighter_b_id else None)
    db.session.add(match)
    db.session.flush()  # get match.id before fetching

    # Populate from Fighter DB if linked, else fetch externally
    skip_a = False
    skip_b = False
    if fighter_a:
        populate_match_from_fighter(match, 'a', fighter_a)
        skip_a = True
    if fighter_b:
        populate_match_from_fighter(match, 'b', fighter_b)
        skip_b = True

    not_found = []
    if not skip_a or not skip_b:
        try:
            result = fetch_fighter_data(match, skip_a=skip_a, skip_b=skip_b)
            if not skip_a and not result['found_a']:
                not_found.append(a)
            if not skip_b and not result['found_b']:
                not_found.append(b)
        except Exception:
            if not skip_a:
                not_found.append(a)
            if not skip_b:
                not_found.append(b)

    try:
        fetch_odds_data(match)
    except Exception:
        pass  # graceful fallback — match works without odds

    db.session.commit()

    # Refresh linked fighters from Glory API (background-safe, non-blocking)
    for fighter in (fighter_a, fighter_b):
        if fighter and fighter.glory_id:
            try:
                refresh_fighter_from_glory(fighter)
                db.session.commit()
            except Exception:
                db.session.rollback()

    flash(f'Match added: {match.participant_a} vs {match.participant_b} (×{multiplier})', 'success')
    if not_found:
        flash(f'Could not find data for: {", ".join(not_found)}. You can enter it manually in the Pool tab.', 'error')
    return redirect(url_for('pool_view', pool_id=pool_id) + '#tab-pool')


@app.route('/pool/<pool_id>/match/<int:match_id>/delete', methods=['POST'])
def delete_match(pool_id, match_id):
    pool = get_pool_or_404(pool_id)
    match = db.session.get(Match, match_id)
    if match and match.pool_id == pool_id:
        db.session.delete(match)
        db.session.commit()
        flash('Match removed.', 'success')
    return redirect(url_for('pool_view', pool_id=pool_id) + '#tab-pool')


@app.route('/pool/<pool_id>/match/<int:match_id>/edit', methods=['POST'])
def edit_match(pool_id, match_id):
    pool = get_pool_or_404(pool_id)
    match = db.session.get(Match, match_id)
    if not match or match.pool_id != pool_id:
        abort(404)

    a = request.form.get('participant_a', '').strip()
    b = request.form.get('participant_b', '').strip()
    multiplier = request.form.get('multiplier', '1').strip()

    # Handle linked fighters from autocomplete
    fighter_a_id = request.form.get('fighter_a_id', '').strip()
    fighter_b_id = request.form.get('fighter_b_id', '').strip()
    new_fighter_a_id = int(fighter_a_id) if fighter_a_id else None
    new_fighter_b_id = int(fighter_b_id) if fighter_b_id else None
    fighter_a_changed = new_fighter_a_id != match.fighter_a_id
    fighter_b_changed = new_fighter_b_id != match.fighter_b_id
    match.fighter_a_id = new_fighter_a_id
    match.fighter_b_id = new_fighter_b_id

    # Re-populate from Fighter DB if the linked fighter changed
    if fighter_a_changed and new_fighter_a_id:
        fighter_a_obj = db.session.get(Fighter, new_fighter_a_id)
        if fighter_a_obj:
            populate_match_from_fighter(match, 'a', fighter_a_obj)
    if fighter_b_changed and new_fighter_b_id:
        fighter_b_obj = db.session.get(Fighter, new_fighter_b_id)
        if fighter_b_obj:
            populate_match_from_fighter(match, 'b', fighter_b_obj)

    names_changed = False
    if a and a != match.participant_a:
        match.participant_a = a
        names_changed = True
    if b and b != match.participant_b:
        match.participant_b = b
        names_changed = True
    try:
        match.multiplier = max(1, int(multiplier))
    except ValueError:
        pass

    # Handle odds fields (inline editing from Pool tab)
    odds_a = request.form.get('odds_a', '').strip().replace(',', '.')
    odds_b = request.form.get('odds_b', '').strip().replace(',', '.')
    if odds_a is not None or odds_b is not None:
        try:
            match.odds_a = round(float(odds_a), 2) if odds_a else None
        except ValueError:
            match.odds_a = None
        try:
            match.odds_b = round(float(odds_b), 2) if odds_b else None
        except ValueError:
            match.odds_b = None
        if match.odds_a or match.odds_b:
            match.odds_source = 'Manual'
            match.odds_fetched_at = datetime.utcnow()
        else:
            match.odds_source = None
            match.odds_fetched_at = None

    # Handle fighter data fields (unified form)
    for field in ('fighter_a_image', 'fighter_a_record', 'fighter_a_nationality',
                  'fighter_b_image', 'fighter_b_record', 'fighter_b_nationality'):
        val = request.form.get(field)
        if val is not None:
            setattr(match, field, val.strip() or None)

    # Handle _action: re-fetch requests (save + fetch in one submit)
    action = request.form.get('_action', 'save')

    # Re-fetch fighter data + odds if names changed OR explicitly requested
    not_found = []
    if names_changed or action == 'refetch_fighter_data':
        try:
            result = fetch_fighter_data(match)
            if not result['found_a']:
                not_found.append(match.participant_a)
            if not result['found_b']:
                not_found.append(match.participant_b)
        except Exception:
            if action == 'refetch_fighter_data':
                flash('Could not fetch fighter data.', 'error')

    if names_changed or action == 'refetch_odds':
        old_source = match.odds_source
        old_odds_a = match.odds_a
        old_odds_b = match.odds_b
        if action == 'refetch_odds':
            match.odds_source = None  # clear so fetch_odds_data doesn't skip
        try:
            fetch_odds_data(match)
            if action == 'refetch_odds' and not (match.odds_a and match.odds_b):
                match.odds_source = old_source
                flash('No odds found for this matchup — try manual entry.', 'error')
            elif action == 'refetch_odds':
                if match.odds_a == old_odds_a and match.odds_b == old_odds_b:
                    flash('Odds unchanged — retrieved values are the same.', 'success')
                else:
                    old_a = f'{old_odds_a:.2f}' if old_odds_a else '—'
                    old_b = f'{old_odds_b:.2f}' if old_odds_b else '—'
                    new_a = f'{match.odds_a:.2f}' if match.odds_a else '—'
                    new_b = f'{match.odds_b:.2f}' if match.odds_b else '—'
                    flash(f'Odds refreshed: {old_a}/{old_b} → {new_a}/{new_b}', 'success')
        except Exception as e:
            if action == 'refetch_odds':
                match.odds_source = old_source
                flash(f'Could not fetch odds: {e}', 'error')

    db.session.commit()

    # Refresh linked fighters from Glory API
    for fid in (new_fighter_a_id, new_fighter_b_id):
        if fid:
            fighter_obj = db.session.get(Fighter, fid)
            if fighter_obj and fighter_obj.glory_id:
                try:
                    refresh_fighter_from_glory(fighter_obj)
                    db.session.commit()
                except Exception:
                    db.session.rollback()

    if action == 'save':
        flash('Match updated.', 'success')
    if not_found:
        flash(f'Could not find data for: {", ".join(not_found)}. You can enter it manually.', 'error')
    return redirect(url_for('pool_view', pool_id=pool_id) + '#tab-pool')


# ---------------------------------------------------------------------------
# Routes — Fighter Data (manual override + re-fetch)
# ---------------------------------------------------------------------------

@app.route('/pool/<pool_id>/match/<int:match_id>/fighter-data', methods=['POST'])
def update_fighter_data(pool_id, match_id):
    pool = get_pool_or_404(pool_id)
    match = db.session.get(Match, match_id)
    if not match or match.pool_id != pool_id:
        abort(404)

    match.fighter_a_image = request.form.get('fighter_a_image', '').strip() or None
    match.fighter_a_record = request.form.get('fighter_a_record', '').strip() or None
    match.fighter_a_nationality = request.form.get('fighter_a_nationality', '').strip() or None
    match.fighter_b_image = request.form.get('fighter_b_image', '').strip() or None
    match.fighter_b_record = request.form.get('fighter_b_record', '').strip() or None
    match.fighter_b_nationality = request.form.get('fighter_b_nationality', '').strip() or None

    db.session.commit()
    flash('Fighter data updated.', 'success')
    return redirect(url_for('pool_view', pool_id=pool_id) + '#tab-pool')


@app.route('/pool/<pool_id>/match/<int:match_id>/refetch', methods=['POST'])
def refetch_fighter_data_route(pool_id, match_id):
    pool = get_pool_or_404(pool_id)
    match = db.session.get(Match, match_id)
    if not match or match.pool_id != pool_id:
        abort(404)

    try:
        result = fetch_fighter_data(match)
        db.session.commit()

        not_found = []
        if not result['found_a']:
            not_found.append(match.participant_a)
        if not result['found_b']:
            not_found.append(match.participant_b)

        if not not_found:
            flash('Fighter data refreshed.', 'success')
        elif len(not_found) == 2:
            flash(f'No data found for {match.participant_a} or {match.participant_b}.', 'error')
        else:
            flash(f'Data refreshed, but nothing found for {not_found[0]}.', 'error')
    except Exception:
        flash('Could not fetch fighter data.', 'error')

    return redirect(url_for('pool_view', pool_id=pool_id) + '#tab-pool')


@app.route('/pool/<pool_id>/fetch-all-fighter-data', methods=['POST'])
def fetch_all_fighter_data(pool_id):
    pool = get_pool_or_404(pool_id)
    fetched = 0
    not_found = []

    for match in pool.matches:
        # Determine which fighters are missing data
        has_a = bool(match.fighter_a_record or match.fighter_a_image)
        has_b = bool(match.fighter_b_record or match.fighter_b_image)

        if has_a and has_b:
            continue  # both fighters already have data

        try:
            result = fetch_fighter_data(match, skip_a=has_a, skip_b=has_b)
            if not has_a and not result['found_a']:
                not_found.append(match.participant_a)
            if not has_b and not result['found_b']:
                not_found.append(match.participant_b)
            if (not has_a and result['found_a']) or (not has_b and result['found_b']):
                fetched += 1
        except Exception:
            not_found.append(f"{match.participant_a} / {match.participant_b}")

    db.session.commit()

    if fetched == 0 and not not_found:
        flash('All fighters already have data.', 'success')
    elif fetched > 0 and not not_found:
        flash(f'Fighter data fetched for {fetched} match(es).', 'success')
    elif fetched > 0 and not_found:
        flash(f'Data fetched for {fetched} match(es), but nothing found for: {", ".join(not_found)}.', 'error')
    else:
        flash(f'No data found for: {", ".join(not_found)}.', 'error')

    return redirect(url_for('pool_view', pool_id=pool_id) + '#tab-pool')


# ---------------------------------------------------------------------------
# Routes — Odds (manual entry + re-fetch)
# ---------------------------------------------------------------------------

@app.route('/pool/<pool_id>/match/<int:match_id>/odds', methods=['POST'])
def update_odds(pool_id, match_id):
    pool = get_pool_or_404(pool_id)
    match = db.session.get(Match, match_id)
    if not match or match.pool_id != pool_id:
        abort(404)

    odds_a = request.form.get('odds_a', '').strip().replace(',', '.')
    odds_b = request.form.get('odds_b', '').strip().replace(',', '.')

    try:
        match.odds_a = round(float(odds_a), 2) if odds_a else None
    except ValueError:
        match.odds_a = None
    try:
        match.odds_b = round(float(odds_b), 2) if odds_b else None
    except ValueError:
        match.odds_b = None

    if match.odds_a or match.odds_b:
        match.odds_source = 'Manual'
        match.odds_fetched_at = datetime.utcnow()
    else:
        match.odds_source = None
        match.odds_fetched_at = None

    db.session.commit()
    flash('Odds updated.', 'success')
    return redirect(url_for('pool_view', pool_id=pool_id) + '#tab-pool')


@app.route('/pool/<pool_id>/match/<int:match_id>/refetch-odds', methods=['POST'])
def refetch_odds(pool_id, match_id):
    pool = get_pool_or_404(pool_id)
    match = db.session.get(Match, match_id)
    if not match or match.pool_id != pool_id:
        abort(404)

    # Temporarily clear source so fetch_odds_data doesn't skip
    old_source = match.odds_source
    match.odds_source = None
    try:
        fetch_odds_data(match)
        if match.odds_a and match.odds_b:
            db.session.commit()
            flash('Odds refreshed.', 'success')
        else:
            match.odds_source = old_source  # restore
            db.session.commit()
            flash('No odds found — try manual entry.', 'error')
    except Exception:
        match.odds_source = old_source
        db.session.commit()
        flash('Could not fetch odds.', 'error')

    return redirect(url_for('pool_view', pool_id=pool_id) + '#tab-pool')


# ---------------------------------------------------------------------------
# Routes — CSV Upload (bulk import matches)
# ---------------------------------------------------------------------------

@app.route('/pool/<pool_id>/upload-csv', methods=['POST'])
def upload_csv(pool_id):
    pool = get_pool_or_404(pool_id)

    file = request.files.get('csv_file')
    if not file or not file.filename:
        flash('Please select a CSV file.', 'error')
        return redirect(url_for('pool_view', pool_id=pool_id) + '#tab-pool')

    if not file.filename.lower().endswith('.csv'):
        flash('File must be a .csv file.', 'error')
        return redirect(url_for('pool_view', pool_id=pool_id) + '#tab-pool')

    try:
        content = file.read()
        matches_data = parse_csv_matches(content)
    except Exception as e:
        flash(f'Error reading CSV: {e}', 'error')
        return redirect(url_for('pool_view', pool_id=pool_id) + '#tab-pool')

    if not matches_data:
        flash('No valid matches found in CSV. Required columns: fighter_a, fighter_b', 'error')
        return redirect(url_for('pool_view', pool_id=pool_id) + '#tab-pool')

    added = 0
    not_found_fighters = []
    base_order = len(pool.matches)
    for i, md in enumerate(matches_data):
        match = Match(
            pool_id=pool_id,
            participant_a=md['fighter_a'],
            participant_b=md['fighter_b'],
            multiplier=md.get('multiplier', 1),
            order=base_order + i,
        )

        # Set odds from CSV if provided
        if 'odds_a' in md:
            match.odds_a = md['odds_a']
        if 'odds_b' in md:
            match.odds_b = md['odds_b']
        if match.odds_a or match.odds_b:
            match.odds_source = 'CSV'
            match.odds_fetched_at = datetime.utcnow()

        # Set fighter data from CSV if provided
        for field in ('fighter_a_record', 'fighter_a_nationality',
                      'fighter_b_record', 'fighter_b_nationality',
                      'fighter_a_image', 'fighter_b_image'):
            if field in md:
                setattr(match, field, md[field])

        db.session.add(match)
        db.session.flush()

        # Auto-fetch fighter data per-fighter (skip if CSV already provided data)
        has_a_data = match.fighter_a_record or match.fighter_a_image
        has_b_data = match.fighter_b_record or match.fighter_b_image
        try:
            result = fetch_fighter_data(match, skip_a=has_a_data, skip_b=has_b_data)
            if not result['found_a']:
                not_found_fighters.append(md['fighter_a'])
            if not result['found_b']:
                not_found_fighters.append(md['fighter_b'])
        except Exception:
            if not has_a_data:
                not_found_fighters.append(md['fighter_a'])
            if not has_b_data:
                not_found_fighters.append(md['fighter_b'])

        # Auto-fetch odds if not provided in CSV
        if not match.odds_a and not match.odds_b:
            try:
                fetch_odds_data(match)
            except Exception:
                pass

        added += 1

    db.session.commit()
    flash(f'{added} match{"es" if added != 1 else ""} imported from CSV.', 'success')
    if not_found_fighters:
        flash(f'Could not find data for: {", ".join(not_found_fighters)}. You can enter it manually in the Pool tab.', 'error')
    return redirect(url_for('pool_view', pool_id=pool_id) + '#tab-pool')


@app.route('/pool/<pool_id>/csv-template')
def csv_template(pool_id):
    """Download an example CSV template."""
    pool = get_pool_or_404(pool_id)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'fighter_a', 'fighter_b', 'multiplier',
        'odds_a', 'odds_b',
        'fighter_a_record', 'fighter_a_nationality',
        'fighter_b_record', 'fighter_b_nationality',
    ])
    # Example row
    writer.writerow([
        'Rico Verhoeven', 'Jamal Ben Saddik', '2',
        '1.45', '2.90',
        '77-10-0', 'Netherlands',
        '38-11-0', 'Morocco',
    ])

    from flask import Response
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=matches_template.csv'}
    )


# ---------------------------------------------------------------------------
# Routes — Pool Status Changes
# ---------------------------------------------------------------------------

@app.route('/pool/<pool_id>/lock', methods=['POST'])
def lock_pool(pool_id):
    pool = get_pool_or_404(pool_id)
    pool.status = 'locked'
    db.session.commit()
    flash('Pool locked — no more predictions allowed.', 'success')
    return redirect(url_for('pool_view', pool_id=pool_id))


@app.route('/pool/<pool_id>/reopen', methods=['POST'])
def reopen_pool(pool_id):
    pool = get_pool_or_404(pool_id)
    pool.status = 'open'
    db.session.commit()
    flash('Pool reopened — predictions allowed again.', 'success')
    return redirect(url_for('pool_view', pool_id=pool_id))


@app.route('/pool/<pool_id>/finish', methods=['POST'])
def finish_pool(pool_id):
    pool = get_pool_or_404(pool_id)
    if not pool.all_results_entered:
        flash('Enter results for all matches before finishing.', 'error')
        return redirect(url_for('pool_view', pool_id=pool_id))
    pool.status = 'finished'
    db.session.commit()
    flash('Pool finished! Final standings are in.', 'success')
    return redirect(url_for('pool_view', pool_id=pool_id))


# ---------------------------------------------------------------------------
# Routes — Enter Results
# ---------------------------------------------------------------------------

@app.route('/pool/<pool_id>/result/<int:match_id>', methods=['POST'])
def enter_result(pool_id, match_id):
    pool = get_pool_or_404(pool_id)
    match = db.session.get(Match, match_id)
    if not match or match.pool_id != pool_id:
        abort(404)

    result = request.form.get('result')
    if result in ('a', 'b', 'draw'):
        match.result = result
        db.session.commit()
        winner_name = match.participant_a if result == 'a' else (
            match.participant_b if result == 'b' else 'Draw'
        )
        flash(f'Result recorded: {winner_name}', 'success')
    else:
        flash('Invalid result.', 'error')

    return redirect(url_for('pool_view', pool_id=pool_id) + '#tab-pool')


@app.route('/pool/<pool_id>/result/<int:match_id>/clear', methods=['POST'])
def clear_result(pool_id, match_id):
    pool = get_pool_or_404(pool_id)
    match = db.session.get(Match, match_id)
    if match and match.pool_id == pool_id:
        match.result = None
        db.session.commit()
        flash('Result cleared.', 'success')
    return redirect(url_for('pool_view', pool_id=pool_id) + '#tab-pool')


# ---------------------------------------------------------------------------
# Routes — Pool Delete
# ---------------------------------------------------------------------------

@app.route('/pool/<pool_id>/delete', methods=['POST'])
def delete_pool(pool_id):
    pool = get_pool_or_404(pool_id)
    db.session.delete(pool)
    db.session.commit()
    flash('Pool deleted.', 'success')
    return redirect(url_for('home'))


# ---------------------------------------------------------------------------
# Routes — Edit Pool Info
# ---------------------------------------------------------------------------

@app.route('/pool/<pool_id>/edit', methods=['POST'])
def edit_pool(pool_id):
    pool = get_pool_or_404(pool_id)
    name = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip()
    if name:
        pool.name = name
    pool.description = description
    db.session.commit()
    flash('Pool updated.', 'success')
    return redirect(url_for('pool_settings', pool_id=pool_id))


# ---------------------------------------------------------------------------
# Routes — Global Settings (Fighter Database)
# ---------------------------------------------------------------------------

@app.route('/settings')
def global_settings():
    fighter_count = Fighter.query.count()
    search_query = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = 25

    query = Fighter.query
    if search_query:
        like = f'%{search_query}%'
        query = query.filter(
            db.or_(
                Fighter.first_name.ilike(like),
                Fighter.last_name.ilike(like),
                Fighter.name.ilike(like),
            )
        )
    query = query.order_by(Fighter.last_name.asc(), Fighter.first_name.asc())
    total = query.count()
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    fighters = query.offset((page - 1) * per_page).limit(per_page).all()

    return render_template('fighters_settings.html',
                           fighter_count=fighter_count,
                           fighters=fighters,
                           page=page,
                           total_pages=total_pages,
                           search_query=search_query)


@app.route('/settings/fighter/new')
def fighter_new():
    return render_template('fighter_edit.html', fighter=None,
                           return_pool=request.args.get('return_pool', ''),
                           return_field=request.args.get('return_field', ''),
                           prefill_name=request.args.get('prefill_name', ''))


@app.route('/settings/fighter/<int:fighter_id>')
def fighter_edit(fighter_id):
    fighter = db.session.get(Fighter, fighter_id)
    if not fighter:
        abort(404)
    return render_template('fighter_edit.html', fighter=fighter,
                           return_pool='', return_field='', prefill_name='')


@app.route('/settings/fighter/save', methods=['POST'])
def fighter_save():
    fighter_id = request.form.get('fighter_id', '').strip()

    if fighter_id:
        fighter = db.session.get(Fighter, int(fighter_id))
        if not fighter:
            abort(404)
    else:
        fighter = Fighter()
        db.session.add(fighter)

    fighter.first_name = request.form.get('first_name', '').strip() or None
    fighter.last_name = request.form.get('last_name', '').strip() or None
    fighter.name = request.form.get('name', '').strip() or f"{fighter.first_name or ''} {fighter.last_name or ''}".strip()
    fighter.nickname = request.form.get('nickname', '').strip() or None
    fighter.nationality = request.form.get('nationality', '').strip() or None
    fighter.nationality_code = request.form.get('nationality_code', '').strip() or None

    for int_field in ('wins', 'losses', 'draws', 'kos'):
        val = request.form.get(int_field, '').strip()
        try:
            setattr(fighter, int_field, int(val) if val else 0)
        except ValueError:
            setattr(fighter, int_field, 0)

    fighter.weight_class = request.form.get('weight_class', '').strip() or None

    for float_field in ('height', 'weight'):
        val = request.form.get(float_field, '').strip().replace(',', '.')
        try:
            setattr(fighter, float_field, float(val) if val else None)
        except ValueError:
            setattr(fighter, float_field, None)

    fighter.image_url = request.form.get('image_url', '').strip() or None
    fighter.ranking = request.form.get('ranking', '').strip() or None
    fighter.retired = request.form.get('retired') == 'on'

    # Generate slug for new fighters
    if not fighter.slug:
        base_slug = fighter.name.lower().replace(' ', '-')
        base_slug = ''.join(c for c in base_slug if c.isalnum() or c == '-')
        slug = base_slug
        counter = 2
        with db.session.no_autoflush:
            while Fighter.query.filter_by(slug=slug).first():
                slug = f'{base_slug}-{counter}'
                counter += 1
        fighter.slug = slug

    db.session.commit()

    # Return-to-pool flow: redirect back to pool with prefill
    return_pool = request.form.get('return_pool', '').strip()
    return_field = request.form.get('return_field', '').strip()
    if return_pool:
        param = 'prefill_a_id' if return_field == 'a' else 'prefill_b_id'
        flash(f'Fighter "{fighter.name}" saved.', 'success')
        return redirect(url_for('pool_view', pool_id=return_pool, **{param: fighter.id}) + '#tab-pool')

    flash(f'Fighter "{fighter.name}" saved.', 'success')
    return redirect(url_for('global_settings'))


@app.route('/api/fighters/search')
def api_fighters_search():
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return jsonify([])
    like = f'%{q}%'
    fighters = Fighter.query.filter(
        db.or_(
            Fighter.name.ilike(like),
            Fighter.first_name.ilike(like),
            Fighter.last_name.ilike(like),
        )
    ).order_by(Fighter.name.asc()).limit(10).all()
    return jsonify([{
        'id': f.id,
        'name': f.name,
        'flag': f.nationality_code or '',
        'record': f"{f.wins}-{f.losses}-{f.draws}" if f.wins is not None else '',
        'image_url': f.image_url or '',
    } for f in fighters])


@app.route('/api/fighters/<int:fighter_id>')
def api_fighter_get(fighter_id):
    fighter = db.session.get(Fighter, fighter_id)
    if not fighter:
        return jsonify({'error': 'Not found'}), 404
    return jsonify({
        'id': fighter.id,
        'name': fighter.name,
        'flag': fighter.nationality_code or '',
        'record': f"{fighter.wins}-{fighter.losses}-{fighter.draws}" if fighter.wins is not None else '',
        'image_url': fighter.image_url or '',
    })


@app.route('/settings/fighter/<int:fighter_id>/delete', methods=['POST'])
def fighter_delete(fighter_id):
    fighter = db.session.get(Fighter, fighter_id)
    if not fighter:
        abort(404)
    name = fighter.name
    db.session.delete(fighter)
    db.session.commit()
    flash(f'Fighter "{name}" deleted.', 'success')
    return redirect(url_for('global_settings'))


# ---------------------------------------------------------------------------
# Init DB
# ---------------------------------------------------------------------------

with app.app_context():
    db.create_all()

    # Migrate: make fighter.glory_id nullable (existing SQLite tables keep old constraint)
    if database_url.startswith('sqlite'):
        try:
            db.session.execute(db.text(
                "CREATE TABLE IF NOT EXISTS fighter_tmp AS SELECT * FROM fighter WHERE 0"
            ))
            db.session.rollback()
        except Exception:
            pass
        # SQLite doesn't support ALTER COLUMN, so check via pragma
        try:
            result = db.session.execute(db.text("PRAGMA table_info(fighter)"))
            cols = {row[1]: row for row in result}
            if 'glory_id' in cols and cols['glory_id'][3] == 1:  # notnull=1
                # Recreate table with nullable glory_id
                db.session.execute(db.text("ALTER TABLE fighter RENAME TO fighter_old"))
                db.create_all()
                db.session.execute(db.text(
                    "INSERT INTO fighter SELECT * FROM fighter_old"
                ))
                db.session.execute(db.text("DROP TABLE fighter_old"))
                db.session.commit()
        except Exception:
            db.session.rollback()

    # Migrate: add fighter_a_id / fighter_b_id to match table
    if database_url.startswith('sqlite'):
        try:
            result = db.session.execute(db.text("PRAGMA table_info(match)"))
            cols = {row[1] for row in result}
            if 'fighter_a_id' not in cols:
                db.session.execute(db.text("ALTER TABLE match RENAME TO match_old"))
                db.create_all()
                # Copy data from old table (new FK columns default to NULL)
                old_cols = ', '.join(c for c in cols)
                db.session.execute(db.text(
                    f"INSERT INTO match ({old_cols}) SELECT {old_cols} FROM match_old"
                ))
                db.session.execute(db.text("DROP TABLE match_old"))
                db.session.commit()
        except Exception:
            db.session.rollback()
    else:
        # PostgreSQL: just add columns if missing
        for col in ('fighter_a_id', 'fighter_b_id'):
            try:
                db.session.execute(db.text(
                    f"ALTER TABLE match ADD COLUMN {col} INTEGER REFERENCES fighter(id)"
                ))
                db.session.commit()
            except Exception:
                db.session.rollback()


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
