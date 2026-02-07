"""
Odds lookup module for Glory kickboxing matches.

Attempts to find decimal betting odds for fighters from public sources.
Falls back gracefully — the app works fine without auto-fetched odds.

Strategy:
1. Try The Odds API (free tier, 500 requests/month) if API key is set
2. Fallback: return None (manual entry in settings page)
"""

import os
import json
import urllib.request
import urllib.parse
import urllib.error
import re
from datetime import datetime


# The Odds API — free tier gives 500 requests/month
# Sign up at https://the-odds-api.com/ and set ODDS_API_KEY env var
ODDS_API_KEY = os.environ.get('ODDS_API_KEY', '')

# Sport key for kickboxing/MMA — The Odds API uses these identifiers
# Glory falls under MMA category when available
SPORT_KEYS = [
    'mma_mixed_martial_arts',  # general MMA/combat sports
]


def _fetch_url(url, timeout=10):
    """Fetch a URL and return the response body as string."""
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (compatible; PredictionPool/1.0)',
        'Accept': 'application/json',
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode('utf-8')
    except (urllib.error.URLError, urllib.error.HTTPError, Exception):
        return None


def _normalize_name(name):
    """Normalize a fighter name for fuzzy matching."""
    name = name.lower().strip()
    # Remove common prefixes/suffixes
    name = re.sub(r'\b(jr|sr|iii|ii|iv)\b', '', name)
    # Remove non-alphanumeric except spaces
    name = re.sub(r'[^a-z\s]', '', name)
    # Collapse whitespace
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def _names_match(name1, name2):
    """Check if two fighter names likely refer to the same person."""
    n1 = _normalize_name(name1)
    n2 = _normalize_name(name2)

    if n1 == n2:
        return True

    # Check if one contains the other (handles "Rico" vs "Rico Verhoeven")
    if n1 in n2 or n2 in n1:
        return True

    # Check last name match
    parts1 = n1.split()
    parts2 = n2.split()
    if parts1 and parts2 and parts1[-1] == parts2[-1]:
        return True

    return False


def lookup_odds_api(fighter_a, fighter_b):
    """
    Try to find odds via The Odds API (https://the-odds-api.com/).

    Returns dict with odds_a, odds_b, source or None if not found.
    Requires ODDS_API_KEY environment variable.
    """
    if not ODDS_API_KEY:
        return None

    for sport_key in SPORT_KEYS:
        url = (
            f'https://api.the-odds-api.com/v4/sports/{sport_key}/odds/'
            f'?apiKey={ODDS_API_KEY}'
            f'&regions=eu'
            f'&markets=h2h'
            f'&oddsFormat=decimal'
        )

        body = _fetch_url(url)
        if not body:
            continue

        try:
            events = json.loads(body)
        except (json.JSONDecodeError, ValueError):
            continue

        for event in events:
            home = event.get('home_team', '')
            away = event.get('away_team', '')

            # Check if this event matches our fighters
            a_is_home = _names_match(fighter_a, home)
            a_is_away = _names_match(fighter_a, away)
            b_is_home = _names_match(fighter_b, home)
            b_is_away = _names_match(fighter_b, away)

            if (a_is_home and b_is_away) or (a_is_away and b_is_home):
                # Found the match! Extract best odds
                odds_a = None
                odds_b = None

                for bookmaker in event.get('bookmakers', []):
                    for market in bookmaker.get('markets', []):
                        if market.get('key') == 'h2h':
                            for outcome in market.get('outcomes', []):
                                outcome_name = outcome.get('name', '')
                                price = outcome.get('price', 0)

                                if _names_match(fighter_a, outcome_name):
                                    if odds_a is None or price > odds_a:
                                        odds_a = price  # best odds
                                elif _names_match(fighter_b, outcome_name):
                                    if odds_b is None or price > odds_b:
                                        odds_b = price

                if odds_a and odds_b:
                    return {
                        'odds_a': round(odds_a, 2),
                        'odds_b': round(odds_b, 2),
                        'source': 'The Odds API',
                    }

    return None


def lookup_odds(fighter_a, fighter_b):
    """
    Look up decimal betting odds for a fight.

    Args:
        fighter_a: Name of fighter A
        fighter_b: Name of fighter B

    Returns:
        dict with keys: odds_a, odds_b, source
        or None if no odds found

    Example return:
        {"odds_a": 1.50, "odds_b": 2.80, "source": "The Odds API"}
    """
    # Try The Odds API first
    result = lookup_odds_api(fighter_a, fighter_b)
    if result:
        return result

    # No odds found — manual entry will be needed
    return None


# Quick test
if __name__ == '__main__':
    print("Testing odds lookup...")
    print(f"ODDS_API_KEY set: {'Yes' if ODDS_API_KEY else 'No (set ODDS_API_KEY for auto-fetch)'}")

    result = lookup_odds("Rico Verhoeven", "Jamal Ben Saddik")
    if result:
        print(f"Found odds: {result}")
    else:
        print("No odds found (expected without API key — use manual entry in settings)")
