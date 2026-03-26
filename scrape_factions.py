"""
Scrape character faction/affiliation data from the One Piece wiki.
For each unique character found in episode data, fetch their wiki page
and extract their affiliation.
"""

import json
import re
import time
import requests
from pathlib import Path

API_URL = "https://onepiece.fandom.com/api.php"
HEADERS = {"User-Agent": "OnePieceResearchBot/1.0 (character appearance analysis)"}
DATA_DIR = Path(__file__).parent / "data"
EPISODE_FILE = DATA_DIR / "episode_characters.json"
FACTION_FILE = DATA_DIR / "character_factions.json"
BATCH_SIZE = 50


def get_unique_characters():
    """Get all unique character page names from episode data."""
    with open(EPISODE_FILE) as f:
        data = json.load(f)

    chars = set()
    for ep_num, char_list in data.items():
        for char in char_list:
            chars.add(char["page"])
    return sorted(chars)


def extract_affiliation(wikitext):
    """Extract affiliation from character infobox wikitext."""
    # Look for affiliation in the infobox
    # Common patterns: | affiliation = ..., |affiliation=...
    aff_match = re.search(
        r'\|\s*affiliation\s*=\s*(.+?)(?:\n\||\n\}\}|\n\n)',
        wikitext, re.IGNORECASE | re.DOTALL
    )
    if not aff_match:
        return None

    aff_text = aff_match.group(1).strip()

    # Extract the first linked affiliation
    # Pattern: [[Straw Hat Pirates]] or [[Straw Hat Pirates|Straw Hats]]
    links = re.findall(r'\[\[([^\]|]+?)(?:\|[^\]]+?)?\]\]', aff_text)
    if links:
        return links[0].strip()

    # If no links, return cleaned text
    # Remove wiki markup
    clean = re.sub(r'\[\[([^\]|]+?\|)?', '', aff_text)
    clean = re.sub(r'\]\]', '', clean)
    clean = re.sub(r"'{2,}", '', clean)
    clean = re.sub(r'<[^>]+>', '', clean)
    clean = clean.strip()
    return clean if clean else None


def fetch_faction_batch(page_names):
    """Fetch wikitext for a batch of character pages."""
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

    # Build normalized title map for matching
    normalized = data.get("query", {}).get("normalized", [])
    norm_map = {n["to"]: n["from"] for n in normalized} if normalized else {}

    for page_id, page_data in pages.items():
        if page_id == "-1" or "missing" in page_data:
            continue

        title = page_data.get("title", "")
        # Map back to original requested name
        original = norm_map.get(title, title)

        revisions = page_data.get("revisions", [])
        if revisions:
            wikitext = revisions[0].get("slots", {}).get("main", {}).get("*", "")
            if not wikitext:
                wikitext = revisions[0].get("*", "")
            affiliation = extract_affiliation(wikitext)
            results[original] = affiliation

    return results


def main():
    characters = get_unique_characters()
    print(f"Total unique characters: {len(characters)}")

    # Load existing data if any
    if FACTION_FILE.exists():
        with open(FACTION_FILE) as f:
            factions = json.load(f)
        print(f"Loaded {len(factions)} cached factions")
    else:
        factions = {}

    # Find characters we still need to scrape
    remaining = [c for c in characters if c not in factions]
    print(f"Characters remaining to scrape: {len(remaining)}")

    for i in range(0, len(remaining), BATCH_SIZE):
        batch = remaining[i:i + BATCH_SIZE]
        print(f"Fetching factions {i+1}-{i+len(batch)} of {len(remaining)}...")

        try:
            results = fetch_faction_batch(batch)
            factions.update(results)
            # Mark missing pages as None
            for name in batch:
                if name not in factions:
                    factions[name] = None
            print(f"  Got {len(results)} affiliations")
        except Exception as e:
            print(f"  Error: {e}")
            time.sleep(5)
            try:
                results = fetch_faction_batch(batch)
                factions.update(results)
                for name in batch:
                    if name not in factions:
                        factions[name] = None
            except Exception as e2:
                print(f"  Retry failed: {e2}")

        # Save incrementally
        with open(FACTION_FILE, "w") as f:
            json.dump(factions, f, indent=2)

        time.sleep(2)

    # Summary
    faction_counts = {}
    for char, faction in factions.items():
        if faction:
            faction_counts[faction] = faction_counts.get(faction, 0) + 1

    print(f"\nTotal characters with factions: {sum(1 for v in factions.values() if v)}")
    print(f"Total unique factions: {len(faction_counts)}")
    print("\nTop 20 factions:")
    for faction, count in sorted(faction_counts.items(), key=lambda x: -x[1])[:20]:
        print(f"  {faction}: {count}")


if __name__ == "__main__":
    main()
