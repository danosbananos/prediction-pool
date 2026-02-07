import os
import uuid
import secrets
from datetime import datetime
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, session, abort, jsonify
)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', secrets.token_hex(32))
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    'DATABASE_URL', 'sqlite:///pool.db'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)


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
    points = db.Column(db.Integer, default=1)
    result = db.Column(db.String(10), nullable=True)  # 'a', 'b', 'draw', or None
    order = db.Column(db.Integer, default=0)
    predictions = db.relationship('Prediction', backref='match', cascade='all, delete-orphan')


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
        total = 0
        for pred in self.predictions:
            if pred.match.result and pred.pick == pred.match.result:
                total += pred.match.points
        return total


class Prediction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    participant_id = db.Column(db.Integer, db.ForeignKey('participant.id'), nullable=False)
    match_id = db.Column(db.Integer, db.ForeignKey('match.id'), nullable=False)
    pick = db.Column(db.String(10), nullable=False)  # 'a' or 'b'

    __table_args__ = (
        db.UniqueConstraint('participant_id', 'match_id', name='uq_participant_match'),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_pool_or_404(pool_id):
    pool = db.session.get(Pool, pool_id)
    if not pool:
        abort(404)
    return pool


def current_participant(pool_id):
    """Return the Participant object for the currently logged-in user in this pool, or None."""
    pid = session.get(f'participant_{pool_id}')
    if pid:
        return db.session.get(Participant, pid)
    return None


# ---------------------------------------------------------------------------
# Routes — Home
# ---------------------------------------------------------------------------

@app.route('/')
def home():
    return render_template('home.html')


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
    return redirect(url_for('pool_settings', pool_id=pool.id))


# ---------------------------------------------------------------------------
# Routes — Pool View (main page: predictions + leaderboard)
# ---------------------------------------------------------------------------

@app.route('/pool/<pool_id>')
def pool_view(pool_id):
    pool = get_pool_or_404(pool_id)
    me = current_participant(pool_id)

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
    points = request.form.get('points', '1').strip()

    if not a or not b:
        flash('Both participant names are required.', 'error')
        return redirect(url_for('pool_settings', pool_id=pool_id))

    try:
        points = max(1, int(points))
    except ValueError:
        points = 1

    order = len(pool.matches)
    match = Match(pool_id=pool_id, participant_a=a, participant_b=b,
                  points=points, order=order)
    db.session.add(match)
    db.session.commit()
    flash(f'Match added: {a} vs {b} ({points} pts)', 'success')
    return redirect(url_for('pool_settings', pool_id=pool_id))


@app.route('/pool/<pool_id>/match/<int:match_id>/delete', methods=['POST'])
def delete_match(pool_id, match_id):
    pool = get_pool_or_404(pool_id)
    match = db.session.get(Match, match_id)
    if match and match.pool_id == pool_id:
        db.session.delete(match)
        db.session.commit()
        flash('Match removed.', 'success')
    return redirect(url_for('pool_settings', pool_id=pool_id))


@app.route('/pool/<pool_id>/match/<int:match_id>/edit', methods=['POST'])
def edit_match(pool_id, match_id):
    pool = get_pool_or_404(pool_id)
    match = db.session.get(Match, match_id)
    if not match or match.pool_id != pool_id:
        abort(404)

    a = request.form.get('participant_a', '').strip()
    b = request.form.get('participant_b', '').strip()
    points = request.form.get('points', '1').strip()

    if a:
        match.participant_a = a
    if b:
        match.participant_b = b
    try:
        match.points = max(1, int(points))
    except ValueError:
        pass

    db.session.commit()
    flash('Match updated.', 'success')
    return redirect(url_for('pool_settings', pool_id=pool_id))


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

    return redirect(url_for('pool_view', pool_id=pool_id))


@app.route('/pool/<pool_id>/result/<int:match_id>/clear', methods=['POST'])
def clear_result(pool_id, match_id):
    pool = get_pool_or_404(pool_id)
    match = db.session.get(Match, match_id)
    if match and match.pool_id == pool_id:
        match.result = None
        db.session.commit()
        flash('Result cleared.', 'success')
    return redirect(url_for('pool_view', pool_id=pool_id))


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
# Init DB
# ---------------------------------------------------------------------------

with app.app_context():
    db.create_all()


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
