"""
Build One Piece character co-appearance network.

Friendship score: F_ij = N_ij / max(N_i, N_j)
where N_ij = episodes i and j appear together, N_i = total episodes for i.

Outputs JSON files for the interactive web frontend.
"""

import json
import math
import numpy as np
import networkx as nx
import community as community_louvain
from collections import defaultdict, Counter
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
OUTPUT_DIR = Path(__file__).parent / "web" / "data"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Minimum episode appearances to include a character in the network
MIN_APPEARANCES = 3


def load_data():
    with open(DATA_DIR / "episode_characters.json") as f:
        episode_data = {int(k): v for k, v in json.load(f).items()}
    with open(DATA_DIR / "character_factions.json") as f:
        faction_data = json.load(f)
    return episode_data, faction_data


def build_network(episode_data, faction_data, min_appearances=MIN_APPEARANCES):
    """Build co-appearance network with friendship scores."""
    # Count appearances per character (by page name)
    char_episodes = defaultdict(set)  # page -> set of episode numbers
    display_names = {}

    for ep_num, chars in episode_data.items():
        for char in chars:
            page = char["page"]
            char_episodes[page].add(ep_num)
            if page not in display_names:
                display_names[page] = char["display_name"]

    # Filter to characters with enough appearances
    qualified = {page for page, eps in char_episodes.items() if len(eps) >= min_appearances}
    print(f"Characters with >= {min_appearances} appearances: {len(qualified)}")

    # Count co-appearances (deduplicate within each episode)
    co_appearances = Counter()
    for ep_num, chars in episode_data.items():
        pages = sorted(set(c["page"] for c in chars if c["page"] in qualified))
        for i in range(len(pages)):
            for j in range(i + 1, len(pages)):
                co_appearances[(pages[i], pages[j])] += 1

    # Build NetworkX graph
    G = nx.Graph()

    for page in qualified:
        faction = faction_data.get(page)
        G.add_node(page, label=display_names.get(page, page),
                   episodes=len(char_episodes[page]),
                   faction=faction or "Unknown")

    # Add edges with friendship score
    for (a, b), n_ij in co_appearances.items():
        n_i = len(char_episodes[a])
        n_j = len(char_episodes[b])
        friendship = n_ij / max(n_i, n_j)
        if friendship > 0:
            G.add_edge(a, b, weight=friendship, co_appearances=n_ij)

    print(f"Nodes: {G.number_of_nodes()}, Edges: {G.number_of_edges()}")
    return G


def compute_metrics(G):
    """Compute network metrics."""
    print("Computing metrics...")

    # Degree centrality
    degree_cent = nx.degree_centrality(G)

    # Weighted degree (strength)
    strength = {n: sum(d['weight'] for _, _, d in G.edges(n, data=True)) for n in G.nodes()}

    # Betweenness centrality (on largest connected component, sampled for speed)
    if G.number_of_nodes() > 500:
        betweenness = nx.betweenness_centrality(G, k=200, weight='weight', seed=42)
    else:
        betweenness = nx.betweenness_centrality(G, weight='weight')

    # Eigenvector centrality
    try:
        eigenvector = nx.eigenvector_centrality(G, max_iter=1000, weight='weight')
    except nx.PowerIterationFailedConvergence:
        eigenvector = {n: 0 for n in G.nodes()}

    # Community detection (Louvain)
    print("Detecting communities...")
    partition = community_louvain.best_partition(G, weight='weight', random_state=42)
    modularity = community_louvain.modularity(partition, G, weight='weight')
    print(f"  Modularity: {modularity:.3f}")
    print(f"  Communities: {len(set(partition.values()))}")

    # Clustering coefficient
    clustering = nx.clustering(G, weight='weight')
    avg_clustering = np.mean(list(clustering.values()))
    print(f"  Avg clustering: {avg_clustering:.3f}")

    # Degree distribution stats
    degrees = [G.degree(n) for n in G.nodes()]
    print(f"  Mean degree: {np.mean(degrees):.1f}")
    print(f"  Max degree: {max(degrees)}")

    # Average path length (on largest connected component)
    components = list(nx.connected_components(G))
    largest_cc = max(components, key=len)
    G_cc = G.subgraph(largest_cc)
    print(f"  Largest component: {len(largest_cc)} nodes ({100*len(largest_cc)/G.number_of_nodes():.1f}%)")

    # Binary avg path length (faster)
    if len(largest_cc) <= 2000:
        avg_path = nx.average_shortest_path_length(G_cc)
        diameter = nx.diameter(G_cc)
    else:
        # Sample
        avg_path = nx.average_shortest_path_length(G_cc)
        diameter = nx.diameter(G_cc)
    print(f"  Avg path length: {avg_path:.2f}")
    print(f"  Diameter: {diameter}")

    # Store metrics on nodes
    for n in G.nodes():
        G.nodes[n]['degree_centrality'] = round(degree_cent[n], 4)
        G.nodes[n]['betweenness'] = round(betweenness.get(n, 0), 4)
        G.nodes[n]['eigenvector'] = round(eigenvector.get(n, 0), 4)
        G.nodes[n]['strength'] = round(strength[n], 4)
        G.nodes[n]['clustering'] = round(clustering[n], 4)
        G.nodes[n]['community'] = partition[n]
        G.nodes[n]['degree'] = G.degree(n)

    network_stats = {
        "num_characters": G.number_of_nodes(),
        "num_edges": G.number_of_edges(),
        "avg_path_length": round(avg_path, 2),
        "diameter": diameter,
        "mean_degree": round(np.mean(degrees), 2),
        "max_degree": int(max(degrees)),
        "avg_clustering": round(avg_clustering, 3),
        "modularity": round(modularity, 3),
        "num_communities": len(set(partition.values())),
        "largest_component_pct": round(100 * len(largest_cc) / G.number_of_nodes(), 1),
    }

    return network_stats, partition


def get_top_pairs(G, n=50):
    """Get top character pairs by friendship score."""
    edges = [(G.nodes[u]['label'], G.nodes[v]['label'], d['weight'], d['co_appearances'])
             for u, v, d in G.edges(data=True)]
    edges.sort(key=lambda x: -x[2])
    return [{"char1": a, "char2": b, "friendship": round(w, 4), "co_appearances": c}
            for a, b, w, c in edges[:n]]


def get_community_info(G, partition):
    """Get summary info about each community."""
    communities = defaultdict(list)
    for node, comm_id in partition.items():
        communities[comm_id].append(node)

    community_info = []
    for comm_id in sorted(communities.keys()):
        members = communities[comm_id]
        # Sort by episode count
        members.sort(key=lambda n: -G.nodes[n]['episodes'])

        # Most common faction
        faction_counts = Counter(G.nodes[n]['faction'] for n in members)
        top_faction = faction_counts.most_common(1)[0][0]

        # Top members
        top_members = [G.nodes[n]['label'] for n in members[:8]]

        community_info.append({
            "id": comm_id,
            "size": len(members),
            "top_faction": top_faction,
            "top_members": top_members,
            "avg_episodes": round(np.mean([G.nodes[n]['episodes'] for n in members]), 1),
        })

    community_info.sort(key=lambda x: -x['size'])
    return community_info


def export_for_web(G, network_stats, partition, episode_data, faction_data):
    """Export network data as JSON for the web frontend."""
    print("Exporting for web...")

    # Community colors (assign consistent colors to largest communities)
    comm_sizes = Counter(partition.values())
    sorted_comms = [c for c, _ in comm_sizes.most_common()]
    comm_color_map = {}
    palette = [
        "#00bfff", "#ff6b6b", "#ffd93d", "#6bcb77", "#4d96ff",
        "#ff69b4", "#a66cff", "#f39c12", "#1abc9c", "#e74c3c",
        "#9b59b6", "#2ecc71", "#e67e22", "#3498db", "#95a5a6",
        "#d35400", "#27ae60", "#8e44ad", "#c0392b", "#16a085",
        "#f1c40f", "#2980b9", "#7f8c8d", "#d4a017", "#45b39d",
    ]
    for i, comm_id in enumerate(sorted_comms):
        comm_color_map[comm_id] = palette[i % len(palette)]

    # Nodes
    nodes = []
    for n in G.nodes():
        d = G.nodes[n]
        nodes.append({
            "id": n,
            "label": d['label'],
            "episodes": d['episodes'],
            "faction": d['faction'],
            "community": d['community'],
            "community_color": comm_color_map[d['community']],
            "degree": d['degree'],
            "degree_centrality": d['degree_centrality'],
            "betweenness": d['betweenness'],
            "eigenvector": d['eigenvector'],
            "strength": d['strength'],
            "clustering": d['clustering'],
        })
    nodes.sort(key=lambda x: -x['episodes'])

    # Edges - only export significant ones (top edges + edges for important chars)
    # For the full graph view, we need to threshold
    edges_full = []
    for u, v, d in G.edges(data=True):
        edges_full.append({
            "source": u,
            "target": v,
            "weight": round(d['weight'], 4),
            "co_appearances": d['co_appearances'],
        })

    # For the force graph, only keep edges above a threshold
    # Find threshold where network stays connected
    thresholds = [0.01, 0.02, 0.03, 0.05, 0.08, 0.1, 0.15, 0.2, 0.3]
    connectivity_info = []
    for t in thresholds:
        filtered = [(u, v) for u, v, d in G.edges(data=True) if d['weight'] >= t]
        H = nx.Graph()
        H.add_nodes_from(G.nodes())
        H.add_edges_from(filtered)
        n_components = nx.number_connected_components(H)
        largest = len(max(nx.connected_components(H), key=len))
        connectivity_info.append({
            "threshold": t,
            "edges": len(filtered),
            "components": n_components,
            "largest_component": largest,
        })

    # Export multiple threshold versions for the frontend
    edge_sets = {}
    for t in [0.05, 0.1, 0.15, 0.2, 0.3]:
        filtered = [e for e in edges_full if e['weight'] >= t]
        edge_sets[str(t)] = filtered

    # Top characters data (for rankings table)
    top_by_episodes = sorted(nodes, key=lambda x: -x['episodes'])[:50]
    top_by_degree = sorted(nodes, key=lambda x: -x['degree'])[:50]
    top_by_betweenness = sorted(nodes, key=lambda x: -x['betweenness'])[:50]
    top_by_eigenvector = sorted(nodes, key=lambda x: -x['eigenvector'])[:50]

    # Character raster data (for the episode chart)
    # Build compact episode appearance data for top characters
    char_episodes_map = defaultdict(list)
    for ep_num, chars in episode_data.items():
        for char in chars:
            if char["page"] in {n["id"] for n in nodes}:
                char_episodes_map[char["page"]].append(int(ep_num))

    raster_data = {}
    for page, eps in char_episodes_map.items():
        raster_data[page] = sorted(eps)

    # Community info
    community_info = get_community_info(G, partition)

    # Top pairs
    top_pairs = get_top_pairs(G, 100)

    # Degree distribution
    degree_dist = Counter(d['degree'] for d in nodes)
    degree_histogram = [{"degree": k, "count": v} for k, v in sorted(degree_dist.items())]

    # Save all data
    main_data = {
        "stats": network_stats,
        "nodes": nodes,
        "edges": edge_sets,
        "all_edges_count": len(edges_full),
        "connectivity": connectivity_info,
        "communities": community_info,
        "top_pairs": top_pairs,
        "degree_distribution": degree_histogram,
        "rankings": {
            "by_episodes": [{"label": n["label"], "value": n["episodes"], "id": n["id"]} for n in top_by_episodes],
            "by_degree": [{"label": n["label"], "value": n["degree"], "id": n["id"]} for n in top_by_degree],
            "by_betweenness": [{"label": n["label"], "value": round(n["betweenness"], 4), "id": n["id"]} for n in top_by_betweenness],
            "by_eigenvector": [{"label": n["label"], "value": round(n["eigenvector"], 4), "id": n["id"]} for n in top_by_eigenvector],
        },
    }

    with open(OUTPUT_DIR / "network.json", "w") as f:
        json.dump(main_data, f)
    print(f"  Saved network.json ({len(nodes)} nodes)")

    # Save raster data separately (it's large)
    with open(OUTPUT_DIR / "raster.json", "w") as f:
        json.dump(raster_data, f)
    print(f"  Saved raster.json ({len(raster_data)} characters)")

    # Save full edge list for download
    with open(OUTPUT_DIR / "edges_full.json", "w") as f:
        json.dump(edges_full, f)
    print(f"  Saved edges_full.json ({len(edges_full)} edges)")

    return main_data


def main():
    episode_data, faction_data = load_data()
    G = build_network(episode_data, faction_data, min_appearances=MIN_APPEARANCES)
    network_stats, partition = compute_metrics(G)

    print("\n=== Network Statistics ===")
    for k, v in network_stats.items():
        print(f"  {k}: {v}")

    export_for_web(G, network_stats, partition, episode_data, faction_data)

    print("\nDone!")


if __name__ == "__main__":
    main()
