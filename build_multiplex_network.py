"""
Build a multiplex character relationship network for One Piece.

Edge layers:
1. Co-appearance (Jaccard + PMI)
2. Affiliation / faction similarity
3. Explicit relationships (from wiki Relationships sections)
4. Hierarchy / command edges
5. Conflict / hostility edges

Composite score:
  w_ij = α·coapp + β·affiliation + γ·relationship + δ·hierarchy + ε·conflict

All weights are configurable in the frontend. This script pre-computes
each layer separately so the frontend can blend them dynamically.

Output: web/data/multiplex_network.json
"""

import json
import math
import numpy as np
from collections import defaultdict, Counter
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
OUTPUT_DIR = Path(__file__).parent / "web" / "data"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

MIN_APPEARANCES = 3

# Arc definitions for One Piece (episode ranges)
ARCS = {
    "Romance Dawn": (1, 3), "Orange Town": (4, 8), "Syrup Village": (9, 18),
    "Baratie": (19, 30), "Arlong Park": (31, 44), "Loguetown": (45, 53),
    "Reverse Mountain": (62, 63), "Whisky Peak": (64, 67),
    "Little Garden": (70, 77), "Drum Island": (78, 91),
    "Arabasta": (92, 130), "Jaya": (144, 152),
    "Skypiea": (153, 195), "Long Ring Long Land": (207, 219),
    "Water 7": (229, 263), "Enies Lobby": (264, 312),
    "Post-Enies Lobby": (313, 325), "Thriller Bark": (337, 381),
    "Sabaody Archipelago": (382, 405), "Amazon Lily": (408, 417),
    "Impel Down": (422, 452), "Marineford": (457, 489),
    "Post-War": (490, 516), "Return to Sabaody": (517, 522),
    "Fish-Man Island": (523, 574), "Punk Hazard": (579, 625),
    "Dressrosa": (629, 746), "Zou": (751, 779),
    "Whole Cake Island": (783, 877), "Reverie": (878, 889),
    "Wano Country": (890, 1085), "Egghead": (1086, 1122),
}


def load_all_data():
    """Load all data files."""
    with open(DATA_DIR / "episode_characters.json") as f:
        episode_data = {int(k): v for k, v in json.load(f).items()}
    with open(DATA_DIR / "character_factions.json") as f:
        faction_data = json.load(f)

    # Optional files - may not exist yet
    relationship_data = {}
    rel_file = DATA_DIR / "character_relationships.json"
    if rel_file.exists():
        with open(rel_file) as f:
            relationship_data = json.load(f)

    org_data = {}
    org_file = DATA_DIR / "organization_data.json"
    if org_file.exists():
        with open(org_file) as f:
            org_data = json.load(f)

    # Hardcoded factions for major characters whose wiki pages use tabbed templates
    MAJOR_FACTIONS = {
        "Monkey D. Luffy": "Straw Hat Pirates", "Roronoa Zoro": "Straw Hat Pirates",
        "Nami": "Straw Hat Pirates", "Usopp": "Straw Hat Pirates",
        "Sanji": "Straw Hat Pirates", "Tony Tony Chopper": "Straw Hat Pirates",
        "Nico Robin": "Straw Hat Pirates", "Franky": "Straw Hat Pirates",
        "Brook": "Straw Hat Pirates", "Jinbe": "Straw Hat Pirates",
        "Shanks": "Red Hair Pirates", "Buggy": "Cross Guild",
        "Kaido": "Beasts Pirates", "Charlotte Linlin": "Big Mom Pirates",
        "Marshall D. Teach": "Blackbeard Pirates",
        "Edward Newgate": "Whitebeard Pirates", "Gol D. Roger": "Roger Pirates",
        "Monkey D. Garp": "Marines", "Sengoku": "Marines",
        "Akainu": "Marines", "Aokiji": "Marines", "Kizaru": "Marines",
        "Fujitora": "Marines", "Smoker": "Marines", "Koby": "Marines",
        "Monkey D. Dragon": "Revolutionary Army", "Sabo": "Revolutionary Army",
        "Portgas D. Ace": "Whitebeard Pirates",
        "Trafalgar D. Water Law": "Heart Pirates",
        "Eustass Kid": "Kid Pirates",
        "Donquixote Doflamingo": "Donquixote Pirates",
        "Boa Hancock": "Kuja Pirates", "Silvers Rayleigh": "Roger Pirates",
        "Dracule Mihawk": "Cross Guild", "Crocodile": "Cross Guild",
        "Gecko Moria": "Thriller Bark Pirates",
        "Bartholomew Kuma": "Revolutionary Army",
        "Oden": "Roger Pirates", "Kozuki Oden": "Kozuki Family",
        "Yamato": "Beasts Pirates", "Carrot": "Mink Tribe",
        "Vivi": "Arabasta Kingdom", "Nefertari Vivi": "Arabasta Kingdom",
        "Tama": "Wano Country",
    }
    for char, faction in MAJOR_FACTIONS.items():
        if not faction_data.get(char):
            faction_data[char] = faction

    # Patch remaining missing factions using org data (prefer crews over locations)
    CREW_KEYWORDS = {"pirates", "family", "army", "marines", "guild", "tribe", "kingdom", "cp0", "cp9"}
    patched = 0
    for org_name, org_info in org_data.items():
        org_lower = org_name.lower()
        is_crew = any(kw in org_lower for kw in CREW_KEYWORDS)
        for member in org_info.get("members", []):
            page = member["page"]
            if not faction_data.get(page):
                faction_data[page] = org_name
                patched += 1
            elif not is_crew:
                continue  # Don't overwrite with location-type orgs
            elif faction_data.get(page) and is_crew and member.get("rank_level", 0) >= 6:
                # High-ranking crew member — prefer crew over location
                existing = faction_data[page]
                if not any(kw in existing.lower() for kw in CREW_KEYWORDS):
                    faction_data[page] = org_name
                    patched += 1
    if patched:
        print(f"  Patched {patched} missing factions from org data")

    return episode_data, faction_data, relationship_data, org_data


def get_qualified_characters(episode_data, min_appearances=MIN_APPEARANCES):
    """Get characters with enough appearances."""
    char_episodes = defaultdict(set)
    display_names = {}

    for ep_num, chars in episode_data.items():
        for char in chars:
            page = char["page"]
            char_episodes[page].add(ep_num)
            if page not in display_names:
                display_names[page] = char["display_name"]

    qualified = {p for p, eps in char_episodes.items() if len(eps) >= min_appearances}
    return qualified, char_episodes, display_names


def get_character_arcs(char_episodes):
    """Map each character to the set of arcs they appear in."""
    char_arcs = defaultdict(set)
    for char, episodes in char_episodes.items():
        for arc_name, (start, end) in ARCS.items():
            if any(start <= ep <= end for ep in episodes):
                char_arcs[char].add(arc_name)
    return char_arcs


# ---- Layer 1: Co-appearance ----

def compute_coappearance_layer(episode_data, qualified, char_episodes):
    """
    Compute Jaccard co-appearance and PMI scores.

    Jaccard: |Ei ∩ Ej| / |Ei ∪ Ej|
    PMI: log(P(i,j) / (P(i) * P(j)))
    """
    total_episodes = len(episode_data)

    # Count co-appearances
    co_counts = Counter()
    for ep_num, chars in episode_data.items():
        pages = sorted(set(c["page"] for c in chars if c["page"] in qualified))
        for i in range(len(pages)):
            for j in range(i + 1, len(pages)):
                co_counts[(pages[i], pages[j])] += 1

    edges = {}
    for (a, b), n_ij in co_counts.items():
        eps_a = char_episodes[a]
        eps_b = char_episodes[b]

        # Jaccard
        intersection = len(eps_a & eps_b)
        union = len(eps_a | eps_b)
        jaccard = intersection / union if union > 0 else 0

        # PMI (normalized to [0, 1] range roughly)
        p_a = len(eps_a) / total_episodes
        p_b = len(eps_b) / total_episodes
        p_ab = n_ij / total_episodes
        if p_a > 0 and p_b > 0 and p_ab > 0:
            pmi = math.log2(p_ab / (p_a * p_b))
            # Normalize PMI by its maximum (-log2(p_ab))
            max_pmi = -math.log2(p_ab) if p_ab > 0 else 1
            npmi = pmi / max_pmi if max_pmi > 0 else 0
            npmi = max(0, min(1, npmi))  # clamp to [0, 1]
        else:
            npmi = 0

        # Blend Jaccard and NPMI (equal weight)
        score = 0.5 * jaccard + 0.5 * npmi

        if score > 0.001:
            edges[(a, b)] = {
                "score": round(score, 4),
                "jaccard": round(jaccard, 4),
                "npmi": round(npmi, 4),
                "co_episodes": n_ij,
            }

    return edges


# ---- Layer 2: Arc overlap ----

def compute_arc_overlap_layer(qualified, char_arcs):
    """
    Jaccard index on arc sets: |Ai ∩ Aj| / |Ai ∪ Aj|
    """
    chars = sorted(qualified)
    edges = {}

    for i in range(len(chars)):
        arcs_i = char_arcs[chars[i]]
        if not arcs_i:
            continue
        for j in range(i + 1, len(chars)):
            arcs_j = char_arcs[chars[j]]
            if not arcs_j:
                continue
            intersection = len(arcs_i & arcs_j)
            if intersection == 0:
                continue
            union = len(arcs_i | arcs_j)
            score = intersection / union if union > 0 else 0
            if score > 0.01:
                edges[(chars[i], chars[j])] = {
                    "score": round(score, 4),
                    "shared_arcs": intersection,
                }

    return edges


# ---- Layer 3: Affiliation / faction ----

def compute_affiliation_layer(qualified, faction_data, org_data):
    """
    Score based on shared faction membership.

    same exact crew/unit = 1.0
    same umbrella faction = 0.6
    allied factions = 0.4
    former same faction only = 0.3
    institutional enemies = -0.7
    """
    # Build org membership map: character -> set of orgs
    char_orgs = defaultdict(set)
    for char in qualified:
        faction = faction_data.get(char)
        if faction:
            char_orgs[char].add(faction)

    # Also add from org_data members
    for org_name, org_info in org_data.items():
        for member in org_info.get("members", []):
            if member["page"] in qualified:
                char_orgs[member["page"]].add(org_name)

    # Build alliance/enemy maps between orgs
    org_allies = defaultdict(set)
    org_enemies = defaultdict(set)
    for org_name, org_info in org_data.items():
        for ally in org_info.get("allies", []):
            org_allies[org_name].add(ally)
            org_allies[ally].add(org_name)
        for enemy in org_info.get("enemies", []):
            org_enemies[org_name].add(enemy)
            org_enemies[enemy].add(org_name)

    # Compute pairwise affiliation scores
    chars = sorted(qualified)
    edges = {}

    for i in range(len(chars)):
        orgs_i = char_orgs[chars[i]]
        if not orgs_i:
            continue
        for j in range(i + 1, len(chars)):
            orgs_j = char_orgs[chars[j]]
            if not orgs_j:
                continue

            # Check relationships between their orgs
            shared = orgs_i & orgs_j
            if shared:
                # Same org
                score = 1.0
            else:
                # Check if any of their orgs are allied
                allied = False
                enemy = False
                for oi in orgs_i:
                    for oj in orgs_j:
                        if oj in org_allies.get(oi, set()):
                            allied = True
                        if oj in org_enemies.get(oi, set()):
                            enemy = True

                if allied and not enemy:
                    score = 0.4
                elif enemy and not allied:
                    score = -0.7
                elif allied and enemy:
                    score = -0.1  # ambiguous
                else:
                    continue  # no relationship

            edges[(chars[i], chars[j])] = {
                "score": round(score, 4),
                "shared_orgs": list(shared) if shared else [],
                "type": "same_org" if shared else ("allied" if score > 0 else "enemy"),
            }

    return edges


# ---- Layer 4: Explicit relationships ----

def compute_relationship_layer(qualified, relationship_data):
    """
    Use wiki Relationships section data.

    family/sworn = +1.0
    crew = +0.9
    mentor = +0.8
    ally = +0.6
    rival = -0.2
    enemy = -1.0
    """
    SENTIMENT_MAP = {
        "family": 1.0,
        "sworn_bond": 1.0,
        "crew": 0.9,
        "mentor": 0.8,
        "ally": 0.6,
        "rival": -0.2,
        "enemy": -1.0,
        "subordinate": 0.3,
        "unknown": 0.0,
    }

    edges = {}

    for char_a, rels in relationship_data.items():
        if char_a not in qualified:
            continue
        for char_b, rel_info in rels.items():
            if char_b not in qualified:
                continue

            # Create canonical edge key
            key = (min(char_a, char_b), max(char_a, char_b))
            rel_type = rel_info.get("type", "unknown")
            sentiment = SENTIMENT_MAP.get(rel_type, rel_info.get("sentiment", 0))

            # If edge already exists (from the other direction), average/max
            if key in edges:
                existing = edges[key]
                # Keep the more extreme sentiment
                if abs(sentiment) > abs(existing["score"]):
                    edges[key] = {
                        "score": round(sentiment, 4),
                        "type": rel_type,
                        "bidirectional": True,
                    }
                else:
                    existing["bidirectional"] = True
            else:
                edges[key] = {
                    "score": round(sentiment, 4),
                    "type": rel_type,
                    "bidirectional": False,
                }

    return edges


# ---- Layer 5: Hierarchy ----

def compute_hierarchy_layer(qualified, org_data):
    """
    Hierarchy edges based on shared org membership with rank differences.
    Score = 1.0 / (1 + |rank_a - rank_b|) for same-org members.
    """
    # Build character -> [(org, rank_level)] map
    char_ranks = defaultdict(list)
    for org_name, org_info in org_data.items():
        for member in org_info.get("members", []):
            if member["page"] in qualified:
                char_ranks[member["page"]].append((org_name, member.get("rank_level", 2)))

    chars = sorted(qualified)
    edges = {}

    for i in range(len(chars)):
        ranks_i = char_ranks[chars[i]]
        if not ranks_i:
            continue
        for j in range(i + 1, len(chars)):
            ranks_j = char_ranks[chars[j]]
            if not ranks_j:
                continue

            # Find shared orgs
            best_score = 0
            best_info = {}
            for org_a, rank_a in ranks_i:
                for org_b, rank_b in ranks_j:
                    if org_a == org_b:
                        rank_diff = abs(rank_a - rank_b)
                        score = 1.0 / (1.0 + rank_diff * 0.3)
                        if score > best_score:
                            best_score = score
                            best_info = {
                                "org": org_a,
                                "rank_a": rank_a,
                                "rank_b": rank_b,
                            }

            if best_score > 0:
                edges[(chars[i], chars[j])] = {
                    "score": round(best_score, 4),
                    **best_info,
                }

    return edges


# ---- Layer 6: Conflict / hostility ----

def compute_conflict_layer(qualified, relationship_data, affiliation_edges):
    """
    Conflict edges derived from:
    - Negative relationship scores
    - Opposing factions
    """
    edges = {}

    # From explicit relationships
    for char_a, rels in relationship_data.items():
        if char_a not in qualified:
            continue
        for char_b, rel_info in rels.items():
            if char_b not in qualified:
                continue

            sentiment = rel_info.get("sentiment", 0)
            if sentiment < 0:
                key = (min(char_a, char_b), max(char_a, char_b))
                conflict_score = abs(sentiment)

                if key in edges:
                    edges[key]["score"] = max(edges[key]["score"], round(conflict_score, 4))
                else:
                    edges[key] = {
                        "score": round(conflict_score, 4),
                        "type": rel_info.get("type", "enemy"),
                    }

    # From opposing factions
    for (a, b), info in affiliation_edges.items():
        if info["score"] < 0:
            key = (min(a, b), max(a, b))
            conflict_score = abs(info["score"])
            if key not in edges:
                edges[key] = {
                    "score": round(conflict_score, 4),
                    "type": "opposing_factions",
                }

    return edges


# ---- Build and export ----

def build_multiplex_network():
    """Build the complete multiplex network."""
    print("Loading data...")
    episode_data, faction_data, relationship_data, org_data = load_all_data()

    print("Getting qualified characters...")
    qualified, char_episodes, display_names = get_qualified_characters(episode_data)
    char_arcs = get_character_arcs(char_episodes)
    print(f"  {len(qualified)} qualified characters")

    print("\nComputing edge layers...")

    print("  Layer 1: Co-appearance (Jaccard + NPMI)...")
    coapp_edges = compute_coappearance_layer(episode_data, qualified, char_episodes)
    print(f"    {len(coapp_edges)} edges")

    print("  Layer 2: Arc overlap...")
    arc_edges = compute_arc_overlap_layer(qualified, char_arcs)
    print(f"    {len(arc_edges)} edges")

    print("  Layer 3: Affiliation / faction...")
    affil_edges = compute_affiliation_layer(qualified, faction_data, org_data)
    print(f"    {len(affil_edges)} edges")

    print("  Layer 4: Explicit relationships...")
    rel_edges = compute_relationship_layer(qualified, relationship_data)
    print(f"    {len(rel_edges)} edges")

    print("  Layer 5: Hierarchy...")
    hier_edges = compute_hierarchy_layer(qualified, org_data)
    print(f"    {len(hier_edges)} edges")

    print("  Layer 6: Conflict / hostility...")
    conflict_edges = compute_conflict_layer(qualified, relationship_data, affil_edges)
    print(f"    {len(conflict_edges)} edges")

    # Build node list with all metrics
    print("\nBuilding node data...")
    nodes = []
    for page in sorted(qualified):
        episodes = len(char_episodes[page])
        faction = faction_data.get(page, "Unknown") or "Unknown"
        arcs = list(char_arcs.get(page, set()))
        nodes.append({
            "id": page,
            "label": display_names.get(page, page),
            "episodes": episodes,
            "faction": faction,
            "arc_count": len(arcs),
        })
    nodes.sort(key=lambda x: -x["episodes"])

    # Serialize edge layers
    # For efficiency, only send edges above a minimum threshold
    def serialize_edges(edge_dict, min_abs_score=0.01):
        result = []
        for (a, b), info in edge_dict.items():
            score = info["score"]
            if abs(score) >= min_abs_score:
                entry = {"s": a, "t": b, "w": info["score"]}
                # Add extra info selectively
                if "type" in info:
                    entry["type"] = info["type"]
                if "co_episodes" in info:
                    entry["co"] = info["co_episodes"]
                result.append(entry)
        # Sort by absolute weight descending
        result.sort(key=lambda x: -abs(x["w"]))
        return result

    print("\nSerializing edge layers...")
    layers = {
        "coappearance": serialize_edges(coapp_edges, 0.05),
        "arc_overlap": serialize_edges(arc_edges, 0.35),
        "affiliation": serialize_edges(affil_edges, 0.1),
        "relationship": serialize_edges(rel_edges, 0.01),
        "hierarchy": serialize_edges(hier_edges, 0.1),
        "conflict": serialize_edges(conflict_edges, 0.05),
    }

    for name, edges in layers.items():
        print(f"  {name}: {len(edges)} edges")

    # Layer metadata for frontend
    layer_meta = {
        "coappearance": {
            "label": "Co-appearance",
            "description": "Jaccard + NPMI co-appearance across episodes",
            "default_weight": 0.25,
            "color": "#00bfff",
            "signed": False,
        },
        "arc_overlap": {
            "label": "Arc Overlap",
            "description": "Jaccard index on shared story arcs",
            "default_weight": 0.15,
            "color": "#ffd93d",
            "signed": False,
        },
        "affiliation": {
            "label": "Affiliation",
            "description": "Shared faction/crew membership and alliances",
            "default_weight": 0.20,
            "color": "#6bcb77",
            "signed": True,
        },
        "relationship": {
            "label": "Relationship",
            "description": "Explicit wiki relationships (family, ally, enemy...)",
            "default_weight": 0.20,
            "color": "#ff69b4",
            "signed": True,
        },
        "hierarchy": {
            "label": "Hierarchy",
            "description": "Organizational rank proximity within same group",
            "default_weight": 0.10,
            "color": "#a66cff",
            "signed": False,
        },
        "conflict": {
            "label": "Conflict",
            "description": "Hostility, opposition, and enmity",
            "default_weight": 0.10,
            "color": "#ff6b6b",
            "signed": False,
        },
    }

    # Skip pre-computed composite - frontend computes dynamically
    composite_edges = []

    # Stats
    all_chars_in_edges = set()
    for layer_edges in layers.values():
        for e in layer_edges:
            all_chars_in_edges.add(e["s"])
            all_chars_in_edges.add(e["t"])

    stats = {
        "total_characters": len(nodes),
        "characters_with_edges": len(all_chars_in_edges),
        "layer_edge_counts": {name: len(edges) for name, edges in layers.items()},
        "total_arcs": len(ARCS),
        "arc_names": list(ARCS.keys()),
    }

    # Final output
    output = {
        "nodes": nodes,
        "layers": layers,
        "layer_meta": layer_meta,
        "default_composite": composite_edges,
        "stats": stats,
    }

    output_file = OUTPUT_DIR / "multiplex_network.json"
    with open(output_file, "w") as f:
        json.dump(output, f)

    file_size = output_file.stat().st_size / (1024 * 1024)
    print(f"\nSaved {output_file} ({file_size:.1f} MB)")
    print("Done!")


def compute_default_composite(layers, weights):
    """Pre-compute composite edges with default weights for fast initial load."""
    edge_scores = defaultdict(float)

    for layer_name, layer_edges in layers.items():
        w = weights.get(layer_name, 0)
        if w == 0:
            continue
        for e in layer_edges:
            key = (e["s"], e["t"]) if e["s"] < e["t"] else (e["t"], e["s"])
            edge_scores[key] += w * e["w"]

    # Threshold and format
    composite = []
    for (a, b), score in edge_scores.items():
        if abs(score) > 0.05:
            composite.append({
                "s": a, "t": b,
                "w": round(score, 4),
            })
    composite.sort(key=lambda x: -abs(x["w"]))
    return composite


if __name__ == "__main__":
    build_multiplex_network()
