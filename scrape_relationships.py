"""
Scrape character relationship data from the One Piece wiki.

For each character, fetch their wiki page and extract:
1. The "Relationships" section text with character mentions
2. Classify relationship types: family, crew, ally, enemy, rival, mentor, etc.

Output: character_relationships.json
  {character_page: {related_char_page: {"type": "family|crew|ally|enemy|rival|mentor|subordinate", "sentiment": float}}}
"""

import json
import re
import time
import requests
from pathlib import Path
from collections import defaultdict

API_URL = "https://onepiece.fandom.com/api.php"
HEADERS = {"User-Agent": "OnePieceResearchBot/1.0 (character relationship analysis)"}
DATA_DIR = Path(__file__).parent / "data"
EPISODE_FILE = DATA_DIR / "episode_characters.json"
OUTPUT_FILE = DATA_DIR / "character_relationships.json"
RAW_SECTIONS_FILE = DATA_DIR / "character_relationship_sections.json"
BATCH_SIZE = 50

# Keywords that signal relationship types
RELATIONSHIP_KEYWORDS = {
    "family": [
        "father", "mother", "son", "daughter", "brother", "sister",
        "parent", "child", "wife", "husband", "grandfather", "grandmother",
        "grandson", "granddaughter", "uncle", "aunt", "nephew", "niece",
        "cousin", "twin", "sibling", "adopted", "foster", "biological",
        "bloodline", "lineage", "heir", "born", "married",
    ],
    "sworn_bond": [
        "sworn brother", "oath", "blood brother", "sworn", "bond",
        "brotherhood", "sake cup", "sakazuki",
    ],
    "crew": [
        "crewmate", "crew member", "nakama", "shipmate", "captain",
        "first mate", "navigator", "cook", "doctor", "shipwright",
        "musician", "helmsman", "sniper", "archaeologist",
    ],
    "mentor": [
        "mentor", "teacher", "trained", "student", "apprentice",
        "taught", "master", "sensei", "learned from", "training",
        "disciple", "pupil",
    ],
    "ally": [
        "ally", "alliance", "allied", "friend", "comrade", "partner",
        "trusted", "respect", "admire", "grateful", "indebted",
        "cooperate", "helped", "saved", "rescued", "protect",
        "care", "fond", "friendship", "loyal", "loyalty",
    ],
    "rival": [
        "rival", "rivalry", "compete", "competition", "contest",
        "challenge", "match", "opposed",
    ],
    "enemy": [
        "enemy", "enemies", "hostile", "hatred", "hate", "despise",
        "kill", "killed", "murder", "murdered", "destroy", "defeated",
        "fought", "fight", "battle", "combat", "attacked", "villain",
        "antagonist", "oppose", "threat", "revenge", "vengeance",
        "captured", "imprisoned", "tortured", "betrayed", "betrayal",
        "conflict", "war", "anger", "furious", "enraged",
    ],
    "subordinate": [
        "subordinate", "officer", "commander", "lieutenant", "vice",
        "admiral", "captain", "leader", "boss", "underling",
        "serves", "serving", "under", "command", "orders",
        "reports to", "follows", "obey",
    ],
}

# Sentiment scores for relationship types
TYPE_SENTIMENTS = {
    "family": 0.8,
    "sworn_bond": 1.0,
    "crew": 0.9,
    "mentor": 0.7,
    "ally": 0.6,
    "rival": -0.1,
    "enemy": -0.8,
    "subordinate": 0.3,
}


def get_unique_characters():
    """Get all unique character page names from episode data."""
    with open(EPISODE_FILE) as f:
        data = json.load(f)
    chars = set()
    for ep_num, char_list in data.items():
        for char in char_list:
            chars.add(char["page"])
    return sorted(chars)


def extract_relationship_section(wikitext):
    """Extract the Relationships section from character wikitext."""
    # Match "== Relationships ==" or "===Relationships===" at various heading levels
    pattern = r'={2,3}\s*Relationships?\s*={2,3}\s*\n(.*?)(?=\n={2,3}\s*[^=]|\Z)'
    match = re.search(pattern, wikitext, re.DOTALL | re.IGNORECASE)
    if not match:
        return None
    return match.group(1).strip()


def extract_subsections(section_text):
    """Split relationship section into subsections by heading."""
    # Split by sub-headings (=== or ====)
    parts = re.split(r'={3,4}\s*(.+?)\s*={3,4}', section_text)
    subsections = {}
    for i in range(1, len(parts), 2):
        heading = parts[i].strip()
        body = parts[i + 1].strip() if i + 1 < len(parts) else ""
        subsections[heading] = body
    return subsections


def extract_character_links(text):
    """Extract character page names from wiki links in text."""
    links = []
    for m in re.finditer(r'\[\[([^\]|]+?)(?:\|([^\]]+?))?\]\]', text):
        page = m.group(1).strip()
        if any(page.startswith(p) for p in ["Category:", "File:", "Image:", "Template:"]):
            continue
        links.append(page)
    return links


def classify_relationship(text, subsection_heading=""):
    """Classify the relationship type based on text content."""
    text_lower = (text + " " + subsection_heading).lower()
    scores = {}

    for rel_type, keywords in RELATIONSHIP_KEYWORDS.items():
        score = 0
        for kw in keywords:
            count = text_lower.count(kw)
            if count > 0:
                score += count
        if score > 0:
            scores[rel_type] = score

    if not scores:
        return "unknown", 0.0

    # Pick the type with the highest keyword match count
    best_type = max(scores, key=scores.get)

    # Also check heading for strong signals
    heading_lower = subsection_heading.lower()
    if any(kw in heading_lower for kw in ["family", "relative"]):
        best_type = "family"
    elif any(kw in heading_lower for kw in ["enemy", "enemies", "antagonist"]):
        best_type = "enemy"
    elif any(kw in heading_lower for kw in ["ally", "allies", "friend"]):
        best_type = "ally"
    elif any(kw in heading_lower for kw in ["crew", "pirate"]):
        best_type = "crew"

    sentiment = TYPE_SENTIMENTS.get(best_type, 0.0)
    return best_type, sentiment


def fetch_relationship_batch(page_names):
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
            section = extract_relationship_section(wikitext)
            results[original] = section  # None if no section found

    return results


def process_relationship_sections(raw_sections, all_characters):
    """Process raw relationship sections into structured relationship data."""
    char_set = set(all_characters)
    relationships = {}

    for char_page, section_text in raw_sections.items():
        if not section_text:
            continue

        char_rels = {}
        subsections = extract_subsections(section_text)

        if subsections:
            for heading, body in subsections.items():
                # Extract character links in this subsection
                linked_chars = extract_character_links(body)
                # Also check if the heading itself is a character link
                heading_chars = extract_character_links(f"[[{heading}]]")

                rel_type, sentiment = classify_relationship(body, heading)

                # Add relationships for all mentioned characters
                all_mentioned = set(linked_chars + heading_chars)
                for mentioned_char in all_mentioned:
                    if mentioned_char in char_set and mentioned_char != char_page:
                        # Keep the strongest/most specific classification
                        if mentioned_char not in char_rels or abs(sentiment) > abs(char_rels[mentioned_char].get("sentiment", 0)):
                            char_rels[mentioned_char] = {
                                "type": rel_type,
                                "sentiment": sentiment,
                            }
        else:
            # No subsections - parse the whole section
            linked_chars = extract_character_links(section_text)
            rel_type, sentiment = classify_relationship(section_text)
            for mentioned_char in set(linked_chars):
                if mentioned_char in char_set and mentioned_char != char_page:
                    char_rels[mentioned_char] = {
                        "type": rel_type,
                        "sentiment": sentiment,
                    }

        if char_rels:
            relationships[char_page] = char_rels

    return relationships


def main():
    characters = get_unique_characters()
    print(f"Total unique characters: {len(characters)}")

    # Load existing raw sections if any
    if RAW_SECTIONS_FILE.exists():
        with open(RAW_SECTIONS_FILE) as f:
            raw_sections = json.load(f)
        print(f"Loaded {len(raw_sections)} cached relationship sections")
    else:
        raw_sections = {}

    # Find characters we still need to scrape
    remaining = [c for c in characters if c not in raw_sections]
    print(f"Characters remaining to scrape: {len(remaining)}")

    for i in range(0, len(remaining), BATCH_SIZE):
        batch = remaining[i:i + BATCH_SIZE]
        print(f"Fetching relationships {i+1}-{i+len(batch)} of {len(remaining)}...")

        try:
            results = fetch_relationship_batch(batch)
            raw_sections.update(results)
            # Mark missing pages
            for name in batch:
                if name not in raw_sections:
                    raw_sections[name] = None
            print(f"  Got {sum(1 for v in results.values() if v)} sections")
        except Exception as e:
            print(f"  Error: {e}")
            time.sleep(5)
            try:
                results = fetch_relationship_batch(batch)
                raw_sections.update(results)
                for name in batch:
                    if name not in raw_sections:
                        raw_sections[name] = None
            except Exception as e2:
                print(f"  Retry failed: {e2}")

        # Save incrementally
        with open(RAW_SECTIONS_FILE, "w") as f:
            json.dump(raw_sections, f, indent=2)

        time.sleep(2)

    # Process raw sections into structured relationships
    print("\nProcessing relationship sections...")
    relationships = process_relationship_sections(raw_sections, characters)

    # Save structured relationships
    with open(OUTPUT_FILE, "w") as f:
        json.dump(relationships, f, indent=2)

    # Summary
    total_rels = sum(len(v) for v in relationships.values())
    type_counts = defaultdict(int)
    for char_rels in relationships.values():
        for rel in char_rels.values():
            type_counts[rel["type"]] += 1

    print(f"\nCharacters with relationships: {len(relationships)}")
    print(f"Total relationship edges: {total_rels}")
    print("\nRelationship type distribution:")
    for rtype, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"  {rtype}: {count}")


if __name__ == "__main__":
    main()
