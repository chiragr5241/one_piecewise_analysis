"""
Create the One Piece Character Raster visualization.

Generates three versions:
1. Basic raster (white dots on black) - shows character appearances
2. Raster with arc annotations
3. Raster colored by faction/affiliation
"""

import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from matplotlib.patches import Rectangle
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

# One Piece anime arcs (episode ranges) - canon arcs
# Source: https://onepiece.fandom.com/wiki/Story_Arcs
ARCS = [
    ("Romance Dawn", 1, 3),
    ("Orange Town", 4, 8),
    ("Syrup Village", 9, 18),
    ("Baratie", 19, 30),
    ("Arlong Park", 31, 44),
    ("Loguetown", 45, 53),
    ("Reverse Mountain", 62, 63),
    ("Whisky Peak", 64, 67),
    ("Little Garden", 70, 77),
    ("Drum Island", 78, 91),
    ("Alabasta", 92, 130),
    ("Jaya", 144, 152),
    ("Skypiea", 153, 195),
    ("Long Ring Long Land", 207, 219),
    ("Water 7", 229, 263),
    ("Enies Lobby", 264, 312),
    ("Post-Enies Lobby", 313, 325),
    ("Thriller Bark", 337, 381),
    ("Sabaody Archipelago", 382, 405),
    ("Amazon Lily", 408, 417),
    ("Impel Down", 422, 452),
    ("Marineford", 457, 489),
    ("Post-War", 490, 516),
    ("Return to Sabaody", 517, 522),
    ("Fish-Man Island", 523, 574),
    ("Punk Hazard", 579, 625),
    ("Dressrosa", 629, 746),
    ("Zou", 751, 779),
    ("Whole Cake Island", 783, 877),
    ("Reverie", 878, 889),
    ("Wano Country", 890, 1085),
    ("Egghead", 1086, 1156),
]

# Straw Hat crew members (page names)
STRAW_HATS = [
    "Monkey D. Luffy",
    "Roronoa Zoro",
    "Nami",
    "Usopp",
    "Sanji",
    "Tony Tony Chopper",
    "Nico Robin",
    "Franky",
    "Brook",
    "Jinbe",
]


def load_data():
    """Load episode and faction data."""
    with open(DATA_DIR / "episode_characters.json") as f:
        episode_data = {int(k): v for k, v in json.load(f).items()}

    faction_data = {}
    faction_file = DATA_DIR / "character_factions.json"
    if faction_file.exists():
        with open(faction_file) as f:
            faction_data = json.load(f)

    return episode_data, faction_data


def build_matrix(episode_data):
    """Build the character appearance matrix.

    Returns:
        char_names: list of character page names sorted by first appearance
        ep_numbers: sorted list of episode numbers
        matrix: numpy boolean array (chars x episodes)
        display_names: dict page_name -> display_name
    """
    first_appearance = {}
    display_names = {}

    for ep_num in sorted(episode_data.keys()):
        for char in episode_data[ep_num]:
            page = char["page"]
            if page not in first_appearance:
                first_appearance[page] = ep_num
                display_names[page] = char["display_name"]

    char_names = sorted(first_appearance.keys(), key=lambda c: first_appearance[c])
    ep_numbers = sorted(episode_data.keys())

    char_idx = {name: i for i, name in enumerate(char_names)}
    ep_idx = {ep: i for i, ep in enumerate(ep_numbers)}

    matrix = np.zeros((len(char_names), len(ep_numbers)), dtype=bool)
    for ep_num, chars in episode_data.items():
        if ep_num not in ep_idx:
            continue
        for char in chars:
            if char["page"] in char_idx:
                matrix[char_idx[char["page"]], ep_idx[ep_num]] = True

    return char_names, ep_numbers, matrix, display_names, char_idx


def plot_basic_raster(char_names, ep_numbers, matrix, display_names, char_idx):
    """Plot the basic character raster (white on black)."""
    print("Generating basic raster...")

    fig, ax = plt.subplots(figsize=(24, 32))
    fig.patch.set_facecolor('#0a0a0a')
    ax.set_facecolor('#0a0a0a')

    # Plot appearances as small dots
    ys, xs = np.where(matrix)
    # Make straw hats slightly larger
    straw_hat_indices = set()
    for sh in STRAW_HATS:
        if sh in char_idx:
            straw_hat_indices.add(char_idx[sh])

    # Regular characters
    regular_mask = np.array([y not in straw_hat_indices for y in ys])
    ax.scatter(xs[regular_mask], ys[regular_mask], s=0.3, c='white', marker='s',
               linewidths=0, alpha=0.8, rasterized=True)

    # Straw hats
    sh_mask = ~regular_mask
    ax.scatter(xs[sh_mask], ys[sh_mask], s=0.8, c='#00bfff', marker='s',
               linewidths=0, alpha=1.0, rasterized=True)

    ax.set_xlim(-5, len(ep_numbers) + 5)
    ax.set_ylim(-5, len(char_names) + 5)
    ax.invert_yaxis()
    ax.set_xlabel("Episode", color='white', fontsize=14)
    ax.set_ylabel("Character (sorted by first appearance)", color='white', fontsize=14)
    ax.set_title("One Piece Character Appearance Raster\n1,653 Characters × 1,156 Episodes",
                 color='white', fontsize=18, fontweight='bold', pad=20)
    ax.tick_params(colors='white', labelsize=10)
    ax.spines['bottom'].set_color('#333')
    ax.spines['left'].set_color('#333')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    # Add episode number ticks
    tick_positions = list(range(0, len(ep_numbers), 100))
    tick_labels = [str(ep_numbers[i]) for i in tick_positions]
    ax.set_xticks(tick_positions)
    ax.set_xticklabels(tick_labels)

    plt.tight_layout()
    out = OUTPUT_DIR / "raster_basic.png"
    fig.savefig(out, dpi=200, facecolor=fig.get_facecolor(), bbox_inches='tight')
    plt.close(fig)
    print(f"  Saved: {out}")


def plot_raster_with_arcs(char_names, ep_numbers, matrix, display_names, char_idx):
    """Plot raster with arc annotations."""
    print("Generating raster with arcs...")

    fig, ax = plt.subplots(figsize=(24, 32))
    fig.patch.set_facecolor('#0a0a0a')
    ax.set_facecolor('#0a0a0a')

    # Plot appearances
    ys, xs = np.where(matrix)
    straw_hat_indices = set()
    for sh in STRAW_HATS:
        if sh in char_idx:
            straw_hat_indices.add(char_idx[sh])

    regular_mask = np.array([y not in straw_hat_indices for y in ys])
    ax.scatter(xs[regular_mask], ys[regular_mask], s=0.3, c='white', marker='s',
               linewidths=0, alpha=0.7, rasterized=True)
    sh_mask = ~regular_mask
    ax.scatter(xs[sh_mask], ys[sh_mask], s=0.8, c='#00bfff', marker='s',
               linewidths=0, alpha=1.0, rasterized=True)

    # Build episode index lookup
    ep_to_idx = {ep: i for i, ep in enumerate(ep_numbers)}

    # Draw arc boundaries and labels
    arc_colors = plt.cm.Set3(np.linspace(0, 1, len(ARCS)))
    for i, (arc_name, start_ep, end_ep) in enumerate(ARCS):
        if start_ep not in ep_to_idx:
            # Find closest
            start_idx = min(range(len(ep_numbers)), key=lambda j: abs(ep_numbers[j] - start_ep))
        else:
            start_idx = ep_to_idx[start_ep]

        if end_ep not in ep_to_idx:
            end_idx = min(range(len(ep_numbers)), key=lambda j: abs(ep_numbers[j] - end_ep))
        else:
            end_idx = ep_to_idx[end_ep]

        # Vertical line at arc start
        ax.axvline(x=start_idx, color=arc_colors[i], alpha=0.3, linewidth=0.5, linestyle='--')

        # Arc label at top
        mid_idx = (start_idx + end_idx) / 2
        ax.text(mid_idx, -15, arc_name, color=arc_colors[i], fontsize=5,
                ha='center', va='bottom', rotation=90, alpha=0.9)

    ax.set_xlim(-5, len(ep_numbers) + 5)
    ax.set_ylim(-25, len(char_names) + 5)
    ax.invert_yaxis()
    ax.set_xlabel("Episode", color='white', fontsize=14)
    ax.set_ylabel("Character (sorted by first appearance)", color='white', fontsize=14)
    ax.set_title("One Piece Character Raster with Story Arcs",
                 color='white', fontsize=18, fontweight='bold', pad=20)
    ax.tick_params(colors='white', labelsize=10)
    ax.spines['bottom'].set_color('#333')
    ax.spines['left'].set_color('#333')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    tick_positions = list(range(0, len(ep_numbers), 100))
    tick_labels = [str(ep_numbers[i]) for i in tick_positions]
    ax.set_xticks(tick_positions)
    ax.set_xticklabels(tick_labels)

    plt.tight_layout()
    out = OUTPUT_DIR / "raster_arcs.png"
    fig.savefig(out, dpi=200, facecolor=fig.get_facecolor(), bbox_inches='tight')
    plt.close(fig)
    print(f"  Saved: {out}")


def plot_raster_factions(char_names, ep_numbers, matrix, display_names, char_idx, faction_data):
    """Plot raster colored by faction."""
    print("Generating faction-colored raster...")

    # Assign colors to top factions, rest get gray
    faction_counts = {}
    for name in char_names:
        f = faction_data.get(name)
        if f:
            faction_counts[f] = faction_counts.get(f, 0) + 1

    top_factions = sorted(faction_counts.keys(), key=lambda f: -faction_counts[f])[:30]

    # Color palette for top factions
    palette = [
        '#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7',
        '#DDA0DD', '#98D8C8', '#F7DC6F', '#BB8FCE', '#85C1E9',
        '#F8C471', '#82E0AA', '#F1948A', '#AED6F1', '#D7BDE2',
        '#A3E4D7', '#FAD7A0', '#A9CCE3', '#D5DBDB', '#EDBB99',
        '#ABB2B9', '#F9E79F', '#A9DFBF', '#F5B7B1', '#D2B4DE',
        '#AEB6BF', '#FADBD8', '#D4EFDF', '#FCF3CF', '#D6EAF8',
    ]

    # Special colors for key factions
    faction_color_map = {}
    # Straw Hats get a special blue
    faction_color_map["Straw Hat Pirates"] = '#00bfff'
    faction_color_map["Marines"] = '#1a5276'
    faction_color_map["Beasts Pirates"] = '#922b21'
    faction_color_map["Charlotte Family"] = '#ff69b4'
    faction_color_map["Whitebeard Pirates"] = '#f39c12'
    faction_color_map["World Government"] = '#7d3c98'
    faction_color_map["Revolutionary Army"] = '#27ae60'
    faction_color_map["Baroque Works"] = '#d4ac0d'
    faction_color_map["Blackbeard Pirates"] = '#1c1c1c'
    faction_color_map["Donquixote Pirates"] = '#e74c3c'
    faction_color_map["Roger Pirates"] = '#d4a017'

    color_idx = 0
    for f in top_factions:
        if f not in faction_color_map:
            faction_color_map[f] = palette[color_idx % len(palette)]
            color_idx += 1

    default_color = '#444444'

    fig, ax = plt.subplots(figsize=(24, 32))
    fig.patch.set_facecolor('#0a0a0a')
    ax.set_facecolor('#0a0a0a')

    # Plot each faction group
    ys, xs = np.where(matrix)

    # Assign color to each point
    colors = []
    for y in ys:
        char_name = char_names[y]
        faction = faction_data.get(char_name)
        if faction and faction in faction_color_map:
            colors.append(faction_color_map[faction])
        else:
            colors.append(default_color)

    ax.scatter(xs, ys, s=0.4, c=colors, marker='s', linewidths=0, alpha=0.85, rasterized=True)

    ax.set_xlim(-5, len(ep_numbers) + 5)
    ax.set_ylim(-5, len(char_names) + 5)
    ax.invert_yaxis()
    ax.set_xlabel("Episode", color='white', fontsize=14)
    ax.set_ylabel("Character (sorted by first appearance)", color='white', fontsize=14)
    ax.set_title("One Piece Character Raster — Colored by Faction",
                 color='white', fontsize=18, fontweight='bold', pad=20)
    ax.tick_params(colors='white', labelsize=10)
    ax.spines['bottom'].set_color('#333')
    ax.spines['left'].set_color('#333')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    tick_positions = list(range(0, len(ep_numbers), 100))
    tick_labels = [str(ep_numbers[i]) for i in tick_positions]
    ax.set_xticks(tick_positions)
    ax.set_xticklabels(tick_labels)

    # Legend for key factions
    legend_factions = [
        "Straw Hat Pirates", "Marines", "Beasts Pirates", "Charlotte Family",
        "Whitebeard Pirates", "World Government", "Revolutionary Army",
        "Baroque Works", "Blackbeard Pirates", "Donquixote Pirates", "Roger Pirates"
    ]
    legend_handles = []
    for f in legend_factions:
        if f in faction_color_map:
            legend_handles.append(plt.Line2D([0], [0], marker='s', color='w', label=f,
                                             markerfacecolor=faction_color_map[f],
                                             markersize=8, linewidth=0))
    legend_handles.append(plt.Line2D([0], [0], marker='s', color='w', label='Other',
                                     markerfacecolor=default_color, markersize=8, linewidth=0))

    legend = ax.legend(handles=legend_handles, loc='lower right', fontsize=9,
                       facecolor='#1a1a1a', edgecolor='#333', labelcolor='white',
                       framealpha=0.9)

    plt.tight_layout()
    out = OUTPUT_DIR / "raster_factions.png"
    fig.savefig(out, dpi=200, facecolor=fig.get_facecolor(), bbox_inches='tight')
    plt.close(fig)
    print(f"  Saved: {out}")


def plot_combined(char_names, ep_numbers, matrix, display_names, char_idx, faction_data):
    """Plot combined raster with arcs and factions."""
    print("Generating combined raster (arcs + factions)...")

    # Faction color setup (same as above)
    faction_counts = {}
    for name in char_names:
        f = faction_data.get(name)
        if f:
            faction_counts[f] = faction_counts.get(f, 0) + 1

    faction_color_map = {
        "Straw Hat Pirates": '#00bfff',
        "Marines": '#1a5276',
        "Beasts Pirates": '#922b21',
        "Charlotte Family": '#ff69b4',
        "Whitebeard Pirates": '#f39c12',
        "World Government": '#7d3c98',
        "Revolutionary Army": '#27ae60',
        "Baroque Works": '#d4ac0d',
        "Blackbeard Pirates": '#2c3e50',
        "Donquixote Pirates": '#e74c3c',
        "Roger Pirates": '#d4a017',
        "Kid Pirates": '#c0392b',
        "Shandia": '#a04000',
        "Tontatta Kingdom": '#76d7c4',
        "Big Mom Pirates": '#ff69b4',
        "Thriller Bark Pirates": '#6c3483',
        "Foxy Pirates": '#cb4335',
        "Kouzuki Family": '#f1c40f',
        "Mokomo Dukedom": '#45b39d',
        "Levely": '#85929e',
    }
    default_color = '#444444'

    fig, ax = plt.subplots(figsize=(28, 36))
    fig.patch.set_facecolor('#0a0a0a')
    ax.set_facecolor('#0a0a0a')

    ys, xs = np.where(matrix)

    # Straw hat indices for bigger markers
    straw_hat_indices = set()
    for sh in STRAW_HATS:
        if sh in char_idx:
            straw_hat_indices.add(char_idx[sh])

    colors = []
    sizes = []
    for y in ys:
        char_name = char_names[y]
        faction = faction_data.get(char_name)

        if char_name in STRAW_HATS:
            colors.append('#00bfff')
            sizes.append(1.2)
        elif faction and faction in faction_color_map:
            colors.append(faction_color_map[faction])
            sizes.append(0.4)
        else:
            colors.append(default_color)
            sizes.append(0.3)

    ax.scatter(xs, ys, s=sizes, c=colors, marker='s', linewidths=0, alpha=0.85, rasterized=True)

    # Arc boundaries
    ep_to_idx = {ep: i for i, ep in enumerate(ep_numbers)}
    for i, (arc_name, start_ep, end_ep) in enumerate(ARCS):
        start_idx = ep_to_idx.get(start_ep,
                                   min(range(len(ep_numbers)), key=lambda j: abs(ep_numbers[j] - start_ep)))
        end_idx = ep_to_idx.get(end_ep,
                                 min(range(len(ep_numbers)), key=lambda j: abs(ep_numbers[j] - end_ep)))
        ax.axvline(x=start_idx, color='#ffffff', alpha=0.15, linewidth=0.5, linestyle='-')
        mid_idx = (start_idx + end_idx) / 2
        ax.text(mid_idx, -20, arc_name, color='#cccccc', fontsize=5.5,
                ha='center', va='bottom', rotation=90, alpha=0.9, fontweight='bold')

    ax.set_xlim(-5, len(ep_numbers) + 5)
    ax.set_ylim(-30, len(char_names) + 5)
    ax.invert_yaxis()
    ax.set_xlabel("Episode", color='white', fontsize=14)
    ax.set_ylabel("Character (sorted by first appearance)", color='white', fontsize=14)
    ax.set_title("One Piece Character Raster — 1,653 Characters × 1,156 Episodes\nColored by Faction | Story Arcs Annotated",
                 color='white', fontsize=18, fontweight='bold', pad=20)
    ax.tick_params(colors='white', labelsize=10)
    ax.spines['bottom'].set_color('#333')
    ax.spines['left'].set_color('#333')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    tick_positions = list(range(0, len(ep_numbers), 100))
    tick_labels = [str(ep_numbers[i]) for i in tick_positions]
    ax.set_xticks(tick_positions)
    ax.set_xticklabels(tick_labels)

    # Legend
    legend_factions = [
        ("Straw Hat Pirates", '#00bfff'),
        ("Marines", '#1a5276'),
        ("Beasts Pirates", '#922b21'),
        ("Charlotte Family", '#ff69b4'),
        ("Whitebeard Pirates", '#f39c12'),
        ("World Government", '#7d3c98'),
        ("Revolutionary Army", '#27ae60'),
        ("Baroque Works", '#d4ac0d'),
        ("Blackbeard Pirates", '#2c3e50'),
        ("Donquixote Pirates", '#e74c3c'),
        ("Roger Pirates", '#d4a017'),
        ("Other", '#444444'),
    ]
    handles = [plt.Line2D([0], [0], marker='s', color='w', label=name,
                          markerfacecolor=color, markersize=8, linewidth=0)
               for name, color in legend_factions]
    ax.legend(handles=handles, loc='lower right', fontsize=9,
              facecolor='#1a1a1a', edgecolor='#333', labelcolor='white', framealpha=0.9)

    plt.tight_layout()
    out = OUTPUT_DIR / "raster_combined.png"
    fig.savefig(out, dpi=200, facecolor=fig.get_facecolor(), bbox_inches='tight')
    plt.close(fig)
    print(f"  Saved: {out}")


def main():
    episode_data, faction_data = load_data()
    char_names, ep_numbers, matrix, display_names, char_idx = build_matrix(episode_data)

    print(f"Matrix shape: {matrix.shape} (characters × episodes)")
    print(f"Total appearances: {matrix.sum()}")
    print()

    plot_basic_raster(char_names, ep_numbers, matrix, display_names, char_idx)
    plot_raster_with_arcs(char_names, ep_numbers, matrix, display_names, char_idx)
    plot_raster_factions(char_names, ep_numbers, matrix, display_names, char_idx, faction_data)
    plot_combined(char_names, ep_numbers, matrix, display_names, char_idx, faction_data)

    print("\nDone! All visualizations saved to output/")


if __name__ == "__main__":
    main()
