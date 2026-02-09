"""
Fighter data lookup module.

Fetches fighter info (image, record, nationality) from Wikipedia/Wikidata.
Falls back gracefully if nothing is found.
"""

import re
import json
import logging
import unicodedata
import urllib.request
import urllib.parse
from urllib.error import URLError

logger = logging.getLogger(__name__)

USER_AGENT = "PredictionPool/1.0 (https://github.com/prediction-pool)"
REQUEST_TIMEOUT = 10


def _api_get(url, timeout=None):
    """Make a GET request with proper User-Agent, return parsed JSON or None."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        resp = urllib.request.urlopen(req, timeout=timeout or REQUEST_TIMEOUT)
        return json.loads(resp.read())
    except (URLError, json.JSONDecodeError, OSError) as e:
        logger.warning("API request failed for %s: %s", url, e)
        return None


def _search_wikidata(name):
    """Search Wikidata for a kickboxer by name. Returns entity ID or None."""
    encoded = urllib.parse.quote(name)
    url = (
        f"https://www.wikidata.org/w/api.php?action=wbsearchentities"
        f"&search={encoded}&language=en&format=json&limit=5"
    )
    data = _api_get(url)
    if not data or not data.get("search"):
        return None

    # Prefer results that mention kickbox in the description
    for result in data["search"]:
        desc = (result.get("description") or "").lower()
        if "kickbox" in desc:
            return result["id"]

    # Fall back to first result if description mentions fighting/martial arts
    for result in data["search"]:
        desc = (result.get("description") or "").lower()
        if any(k in desc for k in ["fighter", "martial", "boxer", "combat", "athlete"]):
            return result["id"]

    return None


def _get_wikidata_claims(entity_id):
    """Get Wikidata claims for an entity. Returns claims dict or None."""
    url = (
        f"https://www.wikidata.org/w/api.php?action=wbgetentities"
        f"&ids={entity_id}&props=claims&format=json"
    )
    data = _api_get(url)
    if not data or "entities" not in data:
        return None
    entity = data["entities"].get(entity_id)
    return entity.get("claims") if entity else None


def _get_image_url(claims):
    """Extract image URL from Wikidata P18 claim."""
    if "P18" not in claims:
        return None
    try:
        filename = claims["P18"][0]["mainsnak"]["datavalue"]["value"]
        safe_name = filename.replace(" ", "_")
        return f"https://commons.wikimedia.org/wiki/Special:FilePath/{urllib.parse.quote(safe_name)}?width=200"
    except (KeyError, IndexError):
        return None


def _resolve_entity_label(entity_id):
    """Resolve a Wikidata entity ID to its English label."""
    url = (
        f"https://www.wikidata.org/w/api.php?action=wbgetentities"
        f"&ids={entity_id}&props=labels&languages=en&format=json"
    )
    data = _api_get(url)
    if not data or "entities" not in data:
        return None
    entity = data["entities"].get(entity_id)
    if entity and "labels" in entity and "en" in entity["labels"]:
        return entity["labels"]["en"]["value"]
    return None


def _get_nationality(claims):
    """Extract nationality from Wikidata P27 (country of citizenship)."""
    if "P27" not in claims:
        return None
    try:
        country_id = claims["P27"][0]["mainsnak"]["datavalue"]["value"]["id"]
        country = _resolve_entity_label(country_id)
        if country:
            # Simplify common long names
            simplifications = {
                "Kingdom of the Netherlands": "Netherlands",
                "United States of America": "USA",
                "United Kingdom of Great Britain and Northern Ireland": "UK",
            }
            return simplifications.get(country, country)
        return None
    except (KeyError, IndexError):
        return None


# ISO country name -> 2-letter code (common combat sports countries)
_COUNTRY_CODES = {
    "Netherlands": "NL", "Morocco": "MA", "Suriname": "SR", "Turkey": "TR",
    "Belgium": "BE", "France": "FR", "Germany": "DE", "Japan": "JP",
    "Brazil": "BR", "USA": "US", "UK": "GB", "Romania": "RO",
    "Ghana": "GH", "Cameroon": "CM", "New Zealand": "NZ", "Australia": "AU",
    "Russia": "RU", "China": "CN", "South Korea": "KR", "Thailand": "TH",
    "Italy": "IT", "Spain": "ES", "Poland": "PL", "Czech Republic": "CZ",
    "Croatia": "HR", "Serbia": "RS", "Georgia": "GE", "Armenia": "AM",
    "Iran": "IR", "Israel": "IL", "South Africa": "ZA", "Canada": "CA",
    "Mexico": "MX", "Colombia": "CO", "Argentina": "AR", "Cuba": "CU",
    "Portugal": "PT", "Sweden": "SE", "Denmark": "DK", "Norway": "NO",
    "Finland": "FI", "Ireland": "IE", "Switzerland": "CH", "Austria": "AT",
    "Ukraine": "UA", "Belarus": "BY", "Moldova": "MD", "Bulgaria": "BG",
    "Greece": "GR", "Albania": "AL", "Bosnia and Herzegovina": "BA",
    "North Macedonia": "MK", "Montenegro": "ME", "Kosovo": "XK",
    "Lithuania": "LT", "Latvia": "LV", "Estonia": "EE", "Hungary": "HU",
    "Slovakia": "SK", "Slovenia": "SI",
}


def _country_to_flag(country_name):
    """Convert country name to flag emoji using regional indicator symbols."""
    code = _COUNTRY_CODES.get(country_name)
    if not code:
        return ""
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in code.upper())


def _get_record_from_wikipedia(fighter_name):
    """Try to extract kickboxing record from Wikipedia infobox."""
    title = urllib.parse.quote(fighter_name.replace(" ", "_"))
    url = (
        f"https://en.wikipedia.org/w/api.php?action=parse"
        f"&page={title}&prop=wikitext&section=0&format=json"
    )
    data = _api_get(url)
    if not data or "parse" not in data:
        return None

    text = data["parse"]["wikitext"].get("*", "")

    # Try to extract kickboxing win/loss from infobox
    wins = _extract_infobox_value(text, "kickbox_win")
    losses = _extract_infobox_value(text, "kickbox_loss")

    if wins is not None:
        losses = losses or 0
        draws = _extract_infobox_value(text, "kickbox_draw") or 0
        return f"{wins}-{losses}-{draws}"

    # Fallback: try generic total fields
    wins = _extract_infobox_value(text, "total_win")
    losses = _extract_infobox_value(text, "total_loss")
    if wins is not None:
        losses = losses or 0
        draws = _extract_infobox_value(text, "total_draw") or 0
        return f"{wins}-{losses}-{draws}"

    return None


def _extract_infobox_value(wikitext, field_name):
    """Extract a numeric value from a Wikipedia infobox field."""
    pattern = rf"\|\s*{re.escape(field_name)}\s*=\s*(\d+)"
    match = re.search(pattern, wikitext)
    if match:
        return int(match.group(1))
    return None


def _name_to_slug(name):
    """Convert a fighter name to a URL slug (e.g. 'Miloš Cvjetićanin' -> 'milos-cvjeticanin')."""
    # Normalize unicode: ć->c, š->s, etc.
    normalized = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode()
    slug = normalized.lower().strip().replace(' ', '-')
    slug = re.sub(r'[^a-z0-9-]', '', slug)
    return slug


def _has_abbreviated_first_name(name):
    """Check if a name has an abbreviated first name like 'A. Bouzid' or 'A Bouzid'."""
    return bool(re.match(r'^[A-Z]\.?\s+\S', name.strip()))


def _lookup_glory(name):
    """
    Look up fighter data from the Glory Kickboxing API.

    Returns dict with image_url, record, nationality, nationality_flag
    or None if not found.
    """
    slug = _name_to_slug(name)
    if not slug:
        return None

    # Try exact slug match first
    url = (
        f"https://glory-api.pinkyellow.computer/api/collections/fighters/entries"
        f"?filter[slug]={urllib.parse.quote(slug)}"
    )
    data = _api_get(url, timeout=20)

    # If not found and name has an abbreviated first name, try last-name contains search
    if (not data or not data.get("data")) and _has_abbreviated_first_name(name):
        parts = name.strip().split()
        if len(parts) >= 2:
            last_name = _name_to_slug(parts[-1])
            initial = parts[0].rstrip('.').lower()
            if last_name:
                url = (
                    f"https://glory-api.pinkyellow.computer/api/collections/fighters/entries"
                    f"?filter[slug:contains]={urllib.parse.quote(last_name)}"
                )
                data = _api_get(url, timeout=20)
                # Filter results: slug must start with the initial
                if data and data.get("data"):
                    matches = [f for f in data["data"] if f.get("slug", "").startswith(initial)]
                    if matches:
                        data["data"] = matches
                    else:
                        data = None

    if not data or not data.get("data"):
        return None

    fighter = data["data"][0]
    result = {
        "image_url": None,
        "record": None,
        "nationality": None,
        "nationality_flag": "",
        "full_name": None,
    }

    # Full name from API title field
    title = fighter.get("title", "").strip()
    if title:
        result["full_name"] = title

    # Image: prefer passport_image (clean portrait), fall back to front_image
    for img_field in ("passport_image", "front_image"):
        img = fighter.get(img_field)
        if isinstance(img, dict) and img.get("url"):
            result["image_url"] = img["url"]
            break

    # Record
    wins = fighter.get("wins")
    losses = fighter.get("losses")
    if wins is not None:
        draws = fighter.get("draws") or 0
        losses = losses or 0
        result["record"] = f"{wins}-{losses}-{draws}"

    # Nationality
    nat_list = fighter.get("nationality")
    if nat_list and isinstance(nat_list, list) and len(nat_list) > 0:
        nat = nat_list[0]
        result["nationality"] = nat.get("label", "")
        country_code = nat.get("key", "")
        if country_code and len(country_code) == 2:
            result["nationality_flag"] = "".join(
                chr(0x1F1E6 + ord(c) - ord("A")) for c in country_code.upper()
            )

    logger.info("Glory API result for '%s' (slug=%s): found=%s",
                name, slug, any(v for k, v in result.items() if k != "nationality_flag"))
    return result


def lookup_fighter(name):
    """
    Look up fighter data by name.

    Tries Glory Kickboxing API first, then falls back to Wikipedia/Wikidata.
    Returns dict with keys: image_url, record, nationality, nationality_flag
    All values may be None if not found.
    """
    result = {
        "image_url": None,
        "record": None,
        "nationality": None,
        "nationality_flag": "",
        "full_name": None,
    }

    if not name or not name.strip():
        return result

    name = name.strip()
    logger.info("Looking up fighter: %s", name)

    # Step 1: Try Glory Kickboxing API (primary source for Glory fighters)
    glory_result = _lookup_glory(name)
    if glory_result:
        # Use Glory data as base
        for key in result:
            if glory_result.get(key):
                result[key] = glory_result[key]

    # Step 2: Fill gaps from Wikipedia/Wikidata
    if not result["record"] or not result["nationality"] or not result["image_url"]:
        entity_id = _search_wikidata(name)
        if entity_id:
            claims = _get_wikidata_claims(entity_id)
            if claims:
                if not result["image_url"]:
                    result["image_url"] = _get_image_url(claims)
                if not result["nationality"]:
                    result["nationality"] = _get_nationality(claims)
                    if result["nationality"]:
                        result["nationality_flag"] = _country_to_flag(result["nationality"])

    # Step 3: Try Wikipedia record if still missing
    if not result["record"]:
        record = _get_record_from_wikipedia(name)
        if record:
            result["record"] = record

    # Step 4: If still no image, try Wikipedia page image
    if not result["image_url"]:
        title = urllib.parse.quote(name.replace(" ", "_"))
        url = (
            f"https://en.wikipedia.org/w/api.php?action=query"
            f"&titles={title}&prop=pageimages&piprop=original&format=json"
        )
        data = _api_get(url)
        if data and "query" in data:
            pages = data["query"].get("pages", {})
            for page in pages.values():
                if "original" in page:
                    result["image_url"] = page["original"]["source"]
                    break

    found = any(v for k, v in result.items() if k != "nationality_flag")
    logger.info("Fighter lookup result for '%s': found=%s", name, found)
    return result
