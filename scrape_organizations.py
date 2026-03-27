"""
Scrape organization/crew data from the One Piece wiki.

For each major organization, fetch its wiki page and extract:
1. Member lists with roles/ranks
2. Sub-organizations and alliances
3. Hierarchy relationships

Output: organization_data.json
  {org_page: {
    "members": [{page, role, rank_level}],
    "sub_orgs": [org_page],
    "allies": [org_page],
    "enemies": [org_page],
    "parent_org": org_page|null
  }}
"""

import json
import re
import time
import requests
from pathlib import Path
from collections import defaultdict

API_URL = "https://onepiece.fandom.com/api.php"
HEADERS = {"User-Agent": "OnePieceResearchBot/1.0 (organization analysis)"}
DATA_DIR = Path(__file__).parent / "data"
FACTION_FILE = DATA_DIR / "character_factions.json"
OUTPUT_FILE = DATA_DIR / "organization_data.json"
RAW_ORG_FILE = DATA_DIR / "organization_raw.json"
BATCH_SIZE = 50

# Major organizations to scrape (from wiki pages)
MAJOR_ORGS = [
    # Pirate crews
    "Straw Hat Pirates", "Whitebeard Pirates", "Beasts Pirates",
    "Big Mom Pirates", "Red Hair Pirates", "Blackbeard Pirates",
    "Roger Pirates", "Rocks Pirates", "Sun Pirates",
    "Heart Pirates", "Kid Pirates", "Donquixote Pirates",
    "Baroque Works", "Arlong Pirates", "Kuja Pirates",
    "Rumbar Pirates", "Thriller Bark Pirates",
    "New Fish-Man Pirates", "Flying Pirates",
    "Foxy Pirates", "Barto Club", "Beautiful Pirates",
    "Fire Tank Pirates", "Buggy Pirates",
    "Spade Pirates", "Cross Guild",
    # Marines & Government
    "Marines", "World Government", "Cipher Pol",
    "CP9", "CP0", "Impel Down", "Enies Lobby",
    "Marine Headquarters",
    # Revolutionary
    "Revolutionary Army",
    # Warlords
    "Seven Warlords of the Sea",
    # Yonko
    "Four Emperors",
    # Alliances
    "Straw Hat Grand Fleet", "Ninja-Pirate-Mink-Samurai Alliance",
    "Whitebeard Alliance",
    # Kingdoms & nations
    "Arabasta Kingdom", "Dressrosa", "Wano Country",
    "Ryugu Kingdom", "Germa Kingdom", "Tontatta Kingdom",
    "Mokomo Dukedom", "Elbaf",
    # Other groups
    "Mink Tribe", "Kozuki Family", "Vinsmoke Family",
    "Charlotte Family", "Donquixote Family",
    "World Nobles", "Celestial Dragons",
    "Worst Generation", "Eleven Supernovas",
    "SSG", "SWORD (Marines)",
]

# Rank levels for hierarchy (higher = more authority)
RANK_KEYWORDS = {
    10: ["king", "queen", "emperor", "yonko", "leader", "founder", "boss", "captain",
         "fleet admiral", "commander-in-chief", "chief", "don", "patriarch"],
    8: ["admiral", "commander", "vice captain", "first mate", "right hand",
        "sweet commander", "all-star", "lead performer", "general"],
    6: ["vice admiral", "officer", "executive", "minister", "headliner",
        "flying six", "tobi roppo", "number agent"],
    4: ["rear admiral", "lieutenant", "agent", "member", "subordinate",
        "gifter", "pleasure", "waiters"],
    2: ["recruit", "apprentice", "trainee", "cadet", "grunt", "fodder"],
}

# Known alliances between organizations
KNOWN_ALLIANCES = [
    ("Straw Hat Pirates", "Heart Pirates"),
    ("Straw Hat Pirates", "Kid Pirates"),
    ("Straw Hat Pirates", "Straw Hat Grand Fleet"),
    ("Marines", "World Government"),
    ("Marines", "Cipher Pol"),
    ("CP9", "Cipher Pol"),
    ("CP0", "Cipher Pol"),
    ("Whitebeard Pirates", "Whitebeard Alliance"),
    ("Big Mom Pirates", "Charlotte Family"),
    ("Beasts Pirates", "Big Mom Pirates"),  # temporary
    ("Baroque Works", "Crocodile"),
    ("Kozuki Family", "Mink Tribe"),
    ("Revolutionary Army", "Revolutionary Army"),
]

# Known adversary relationships
KNOWN_ENEMIES = [
    ("Straw Hat Pirates", "Marines"),
    ("Straw Hat Pirates", "Baroque Works"),
    ("Straw Hat Pirates", "CP9"),
    ("Straw Hat Pirates", "Donquixote Pirates"),
    ("Straw Hat Pirates", "Big Mom Pirates"),
    ("Straw Hat Pirates", "Beasts Pirates"),
    ("Straw Hat Pirates", "Blackbeard Pirates"),
    ("Revolutionary Army", "World Government"),
    ("Whitebeard Pirates", "Marines"),
    ("Whitebeard Pirates", "Blackbeard Pirates"),
]


def get_known_orgs():
    """Get all unique organizations from faction data."""
    if not FACTION_FILE.exists():
        return set()
    with open(FACTION_FILE) as f:
        factions = json.load(f)
    orgs = set()
    for faction in factions.values():
        if faction:
            orgs.add(faction)
    return orgs


def extract_members_from_wikitext(wikitext, all_characters):
    """Extract member names and roles from organization wikitext."""
    char_set = set(all_characters) if all_characters else set()
    members = []

    # Extract from structured member sections
    # Look for sections like "Crew Members", "Members", "Officers", etc.
    member_patterns = [
        r'={2,4}\s*(?:Crew\s+)?Members?\s*={2,4}\s*\n(.*?)(?=\n={2,4}\s*[^=]|\Z)',
        r'={2,4}\s*(?:Known\s+)?Members?\s*={2,4}\s*\n(.*?)(?=\n={2,4}\s*[^=]|\Z)',
        r'={2,4}\s*Crew\s+Strength\s*={2,4}\s*\n(.*?)(?=\n={2,4}\s*[^=]|\Z)',
        r'={2,4}\s*Organization\s*={2,4}\s*\n(.*?)(?=\n={2,4}\s*[^=]|\Z)',
    ]

    section_text = ""
    for pattern in member_patterns:
        match = re.search(pattern, wikitext, re.DOTALL | re.IGNORECASE)
        if match:
            section_text += match.group(1) + "\n"

    if not section_text:
        # Fall back to searching the entire page for character links
        section_text = wikitext

    # Extract links and try to determine roles
    seen = set()
    for m in re.finditer(r'\[\[([^\]|]+?)(?:\|([^\]]+?))?\]\]', section_text):
        page = m.group(1).strip()
        if any(page.startswith(p) for p in ["Category:", "File:", "Image:", "Template:"]):
            continue
        if page in seen:
            continue
        seen.add(page)

        # Only include known characters
        if char_set and page not in char_set:
            continue

        # Try to determine rank from surrounding context
        start = max(0, m.start() - 200)
        end = min(len(section_text), m.end() + 200)
        context = section_text[start:end].lower()

        rank_level = 2  # default
        role = "member"
        for level, keywords in sorted(RANK_KEYWORDS.items(), reverse=True):
            for kw in keywords:
                if kw in context:
                    rank_level = level
                    role = kw
                    break
            if rank_level > 2:
                break

        members.append({
            "page": page,
            "role": role,
            "rank_level": rank_level,
        })

    return members


def extract_alliances_and_enemies(wikitext):
    """Extract alliance and enemy relationships from org page."""
    allies = []
    enemies = []

    # Look for alliance/enemy sections
    ally_match = re.search(
        r'={2,4}\s*(?:Allies?|Alliance)\s*={2,4}\s*\n(.*?)(?=\n={2,4}\s*[^=]|\Z)',
        wikitext, re.DOTALL | re.IGNORECASE
    )
    enemy_match = re.search(
        r'={2,4}\s*(?:Enemies?|Rivals?|Adversar)\s*={2,4}\s*\n(.*?)(?=\n={2,4}\s*[^=]|\Z)',
        wikitext, re.DOTALL | re.IGNORECASE
    )

    if ally_match:
        for m in re.finditer(r'\[\[([^\]|]+?)(?:\|[^\]]+?)?\]\]', ally_match.group(1)):
            page = m.group(1).strip()
            if not any(page.startswith(p) for p in ["Category:", "File:", "Image:", "Template:"]):
                allies.append(page)

    if enemy_match:
        for m in re.finditer(r'\[\[([^\]|]+?)(?:\|[^\]]+?)?\]\]', enemy_match.group(1)):
            page = m.group(1).strip()
            if not any(page.startswith(p) for p in ["Category:", "File:", "Image:", "Template:"]):
                enemies.append(page)

    return allies, enemies


def fetch_org_batch(page_names):
    """Fetch wikitext for a batch of org pages."""
    titles = "|".join(page_names)
    params = {
        "action": "query",
        "titles": titles,
        "prop": "revisions",
        "rvprop": "content",
        "rvslots": "main",
        "format": "json",
    }

    resp = requests.get(API_URL, params=params, headers=HEADERS)
    resp.raise_for_status()
    data = resp.json()

    results = {}
    pages = data.get("query", {}).get("pages", {})
    normalized = data.get("query", {}).get("normalized", [])
    norm_map = {n["to"]: n["from"] for n in normalized} if normalized else {}

    for page_id, page_data in pages.items():
        if page_id == "-1" or "missing" in page_data:
            continue
        title = page_data.get("title", "")
        original = norm_map.get(title, title)
        revisions = page_data.get("revisions", [])
        if revisions:
            wikitext = revisions[0].get("slots", {}).get("main", {}).get("*", "")
            if not wikitext:
                wikitext = revisions[0].get("*", "")
            results[original] = wikitext

    return results


def get_all_characters():
    """Get all character page names from episode data."""
    episode_file = DATA_DIR / "episode_characters.json"
    if not episode_file.exists():
        return []
    with open(episode_file) as f:
        data = json.load(f)
    chars = set()
    for char_list in data.values():
        for char in char_list:
            chars.add(char["page"])
    return sorted(chars)


def main():
    all_characters = get_all_characters()
    print(f"Known characters: {len(all_characters)}")

    # Also get orgs from faction data
    known_orgs = get_known_orgs()
    print(f"Known orgs from factions: {len(known_orgs)}")

    # Combine org lists
    all_org_names = list(set(MAJOR_ORGS) | known_orgs)
    # Filter to reasonable page names (skip single words that are likely not org pages)
    all_org_names = [o for o in all_org_names if len(o) > 3]
    all_org_names.sort()
    print(f"Total org pages to scrape: {len(all_org_names)}")

    # Load cached raw data
    if RAW_ORG_FILE.exists():
        with open(RAW_ORG_FILE) as f:
            raw_orgs = json.load(f)
        print(f"Loaded {len(raw_orgs)} cached org pages")
    else:
        raw_orgs = {}

    # Scrape missing orgs
    remaining = [o for o in all_org_names if o not in raw_orgs]
    print(f"Orgs remaining to scrape: {len(remaining)}")

    for i in range(0, len(remaining), BATCH_SIZE):
        batch = remaining[i:i + BATCH_SIZE]
        print(f"Fetching orgs {i+1}-{i+len(batch)} of {len(remaining)}...")

        try:
            results = fetch_org_batch(batch)
            raw_orgs.update(results)
            for name in batch:
                if name not in raw_orgs:
                    raw_orgs[name] = None
            print(f"  Got {len(results)} pages")
        except Exception as e:
            print(f"  Error: {e}")
            time.sleep(5)
            try:
                results = fetch_org_batch(batch)
                raw_orgs.update(results)
                for name in batch:
                    if name not in raw_orgs:
                        raw_orgs[name] = None
            except Exception as e2:
                print(f"  Retry failed: {e2}")

        with open(RAW_ORG_FILE, "w") as f:
            json.dump(raw_orgs, f)
        time.sleep(2)

    # Process org data
    print("\nProcessing organization data...")
    org_data = {}

    for org_name, wikitext in raw_orgs.items():
        if not wikitext:
            continue

        members = extract_members_from_wikitext(wikitext, all_characters)
        allies, enemies = extract_alliances_and_enemies(wikitext)

        if members or allies or enemies:
            org_data[org_name] = {
                "members": members,
                "allies": allies,
                "enemies": enemies,
            }

    # Add known alliances and enemies
    for org1, org2 in KNOWN_ALLIANCES:
        if org1 in org_data:
            if org2 not in org_data[org1].get("allies", []):
                org_data.setdefault(org1, {"members": [], "allies": [], "enemies": []})
                org_data[org1]["allies"].append(org2)
        if org2 in org_data:
            if org1 not in org_data[org2].get("allies", []):
                org_data.setdefault(org2, {"members": [], "allies": [], "enemies": []})
                org_data[org2]["allies"].append(org1)

    for org1, org2 in KNOWN_ENEMIES:
        if org1 in org_data:
            if org2 not in org_data[org1].get("enemies", []):
                org_data.setdefault(org1, {"members": [], "allies": [], "enemies": []})
                org_data[org1]["enemies"].append(org2)

    # Save
    with open(OUTPUT_FILE, "w") as f:
        json.dump(org_data, f, indent=2)

    # Summary
    total_members = sum(len(o.get("members", [])) for o in org_data.values())
    print(f"\nOrgs with data: {len(org_data)}")
    print(f"Total member entries: {total_members}")
    print("\nTop orgs by member count:")
    for org, data in sorted(org_data.items(), key=lambda x: -len(x[1].get("members", [])))[:20]:
        print(f"  {org}: {len(data.get('members', []))} members")


if __name__ == "__main__":
    main()
