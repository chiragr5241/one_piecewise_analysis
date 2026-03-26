"""
Scrape One Piece character appearances from all episodes using the MediaWiki API.

Uses batch queries (50 episodes per request) for efficiency.
Output: JSON file mapping episode numbers to lists of character appearances.
"""

import json
import re
import time
import requests
from pathlib import Path

API_URL = "https://onepiece.fandom.com/api.php"
HEADERS = {"User-Agent": "OnePieceResearchBot/1.0 (character appearance analysis)"}
OUTPUT_FILE = Path(__file__).parent / "data" / "episode_characters.json"
BATCH_SIZE = 50

# Total episodes to scrape (One Piece has 1100+ episodes as of 2025)
MAX_EPISODE = 1200


def get_episode_count():
    """Find the highest episode number that exists."""
    # Binary search for the last valid episode
    low, high = 1100, 1300
    while low < high:
        mid = (low + high + 1) // 2
        resp = requests.get(API_URL, params={
            "action": "query",
            "titles": f"Episode {mid}",
            "format": "json",
        }, headers=HEADERS)
        pages = resp.json()["query"]["pages"]
        if "-1" in pages:
            high = mid - 1
        else:
            low = mid
    return low


def extract_characters_from_wikitext(wikitext):
    """Extract character names from the 'Characters in Order of Appearance' section."""
    # Find the section
    pattern = r"==\s*Characters in Order of Appearance\s*==\s*\n(.*?)(?=\n==|\Z)"
    match = re.search(pattern, wikitext, re.DOTALL)
    if not match:
        return []

    section = match.group(1)

    # Extract character links: *[[Page Name|Display Name]] or *[[Page Name]]
    characters = []
    for m in re.finditer(r'\[\[([^\]|]+?)(?:\|([^\]]+?))?\]\]', section):
        page_name = m.group(1).strip()
        display_name = m.group(2).strip() if m.group(2) else page_name

        # Skip non-character links (categories, files, etc.)
        if any(page_name.startswith(prefix) for prefix in ["Category:", "File:", "Image:"]):
            continue

        characters.append({
            "page": page_name,
            "display_name": display_name,
        })

    return characters


def fetch_batch(episode_numbers):
    """Fetch wikitext for a batch of episodes using the batch query API."""
    titles = "|".join(f"Episode {n}" for n in episode_numbers)
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
    for page_id, page_data in pages.items():
        if page_id == "-1" or "missing" in page_data:
            continue
        title = page_data.get("title", "")
        # Extract episode number from title
        ep_match = re.search(r"Episode\s+(\d+)", title)
        if not ep_match:
            continue
        ep_num = int(ep_match.group(1))

        revisions = page_data.get("revisions", [])
        if revisions:
            wikitext = revisions[0].get("slots", {}).get("main", {}).get("*", "")
            if not wikitext:
                # Older API format
                wikitext = revisions[0].get("*", "")
            characters = extract_characters_from_wikitext(wikitext)
            results[ep_num] = characters

    return results


def scrape_all_episodes(max_episode=None):
    """Scrape character appearances from all One Piece episodes."""
    if max_episode is None:
        print("Finding total episode count...")
        max_episode = get_episode_count()
        print(f"Found {max_episode} episodes")

    all_data = {}
    episode_numbers = list(range(1, max_episode + 1))

    for i in range(0, len(episode_numbers), BATCH_SIZE):
        batch = episode_numbers[i:i + BATCH_SIZE]
        batch_start, batch_end = batch[0], batch[-1]
        print(f"Fetching episodes {batch_start}-{batch_end}...")

        try:
            results = fetch_batch(batch)
            all_data.update(results)
            print(f"  Got data for {len(results)} episodes")
        except Exception as e:
            print(f"  Error: {e}")
            # Retry once after a delay
            time.sleep(5)
            try:
                results = fetch_batch(batch)
                all_data.update(results)
                print(f"  Retry succeeded: {len(results)} episodes")
            except Exception as e2:
                print(f"  Retry also failed: {e2}")

        # Be polite to the API
        time.sleep(2)

    return all_data


def build_character_matrix(episode_data):
    """Build the character appearance matrix from scraped data.

    Returns:
        character_names: list of unique character page names (sorted by first appearance)
        episode_numbers: sorted list of episode numbers
        matrix: dict mapping (char_page, ep_num) -> True
        char_display_names: dict mapping page_name -> display_name
    """
    # Collect all unique characters by page name, tracking first appearance
    first_appearance = {}
    char_display_names = {}

    for ep_num in sorted(episode_data.keys()):
        for char in episode_data[ep_num]:
            page = char["page"]
            if page not in first_appearance:
                first_appearance[page] = ep_num
                char_display_names[page] = char["display_name"]

    # Sort characters by first appearance
    character_names = sorted(first_appearance.keys(), key=lambda c: first_appearance[c])
    episode_numbers = sorted(episode_data.keys())

    # Build matrix
    matrix = {}
    for ep_num, chars in episode_data.items():
        for char in chars:
            matrix[(char["page"], ep_num)] = True

    return character_names, episode_numbers, matrix, char_display_names


def main():
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    # Check for cached data
    if OUTPUT_FILE.exists():
        print(f"Loading cached data from {OUTPUT_FILE}")
        with open(OUTPUT_FILE) as f:
            data = json.load(f)
        # Convert string keys back to int
        episode_data = {int(k): v for k, v in data.items()}
    else:
        episode_data = scrape_all_episodes()

        # Save raw data
        with open(OUTPUT_FILE, "w") as f:
            json.dump(episode_data, f, indent=2)
        print(f"\nSaved data to {OUTPUT_FILE}")

    # Print summary
    char_names, ep_nums, matrix, display_names = build_character_matrix(episode_data)
    total_appearances = len(matrix)
    print(f"\nSummary:")
    print(f"  Episodes: {len(ep_nums)}")
    print(f"  Unique characters: {len(char_names)}")
    print(f"  Total appearances: {total_appearances}")
    print(f"  First 10 characters: {[display_names[c] for c in char_names[:10]]}")


if __name__ == "__main__":
    main()
