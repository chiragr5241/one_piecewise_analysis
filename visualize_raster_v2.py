"""
One Piece Character Raster — improved version using imshow for crisp pixels.
"""

import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, BoundaryNorm
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

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

STRAW_HATS = [
    "Monkey D. Luffy", "Roronoa Zoro", "Nami", "Usopp", "Sanji",
    "Tony Tony Chopper", "Nico Robin", "Franky", "Brook", "Jinbe",
]

FACTION_COLORS = {
    "Straw Hat Pirates": [0, 191, 255],
    "Marines": [41, 128, 185],
    "Beasts Pirates": [192, 57, 43],
    "Charlotte Family": [255, 105, 180],
    "Whitebeard Pirates": [243, 156, 18],
    "World Government": [142, 68, 173],
    "Revolutionary Army": [39, 174, 96],
    "Baroque Works": [212, 172, 13],
    "Blackbeard Pirates": [100, 100, 100],
    "Donquixote Pirates": [231, 76, 60],
    "Roger Pirates": [212, 160, 23],
    "Kid Pirates": [203, 67, 53],
    "Shandia": [160, 64, 0],
    "Tontatta Kingdom": [118, 215, 196],
    "Big Mom Pirates": [255, 105, 180],
    "Thriller Bark Pirates": [108, 52, 131],
    "Foxy Pirates": [203, 67, 53],
    "Kouzuki Family": [241, 196, 15],
    "Mokomo Dukedom": [69, 179, 157],
    "Levely": [133, 146, 158],
    "Spade Pirates": [230, 126, 34],
    "Heart Pirates": [241, 196, 15],
    "Sun Pirates": [46, 134, 193],
    "Arlong Pirates": [22, 160, 133],
    "Cross Guild": [185, 119, 14],
    "Straw Hat Grand Fleet": [52, 152, 219],
    "Germa Kingdom": [93, 173, 226],
    "Wano Country": [183, 149, 11],
}
DEFAULT_COLOR = [60, 60, 60]


def load_data():
    with open(DATA_DIR / "episode_characters.json") as f:
        episode_data = {int(k): v for k, v in json.load(f).items()}
    with open(DATA_DIR / "character_factions.json") as f:
        faction_data = json.load(f)
    return episode_data, faction_data


def build_matrix(episode_data):
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

    return char_names, ep_numbers, matrix, display_names, char_idx, ep_idx


def add_arc_annotations(ax, ep_numbers, ep_idx, n_chars, at_top=True):
    """Add arc boundary lines and labels."""
    for i, (name, start_ep, end_ep) in enumerate(ARCS):
        s = ep_idx.get(start_ep)
        if s is None:
            s = min(range(len(ep_numbers)), key=lambda j: abs(ep_numbers[j] - start_ep))
        e = ep_idx.get(end_ep)
        if e is None:
            e = min(range(len(ep_numbers)), key=lambda j: abs(ep_numbers[j] - end_ep))

        ax.axvline(x=s - 0.5, color='#ffffff', alpha=0.2, linewidth=0.4)
        mid = (s + e) / 2
        if at_top:
            y_pos = -2
            ax.text(mid, y_pos, name, color='#aaaaaa', fontsize=4.5,
                    ha='center', va='bottom', rotation=90, clip_on=False)


def plot_basic(char_names, ep_numbers, matrix, char_idx):
    """White-on-black raster."""
    print("Generating basic raster...")
    # Create RGB image
    h, w = matrix.shape
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[matrix] = [255, 255, 255]

    # Highlight straw hats in cyan
    for sh in STRAW_HATS:
        if sh in char_idx:
            row = char_idx[sh]
            img[row, matrix[row]] = [0, 191, 255]

    fig, ax = plt.subplots(figsize=(20, 28))
    fig.patch.set_facecolor('#080808')
    ax.set_facecolor('#080808')

    ax.imshow(img, aspect='auto', interpolation='nearest')

    ax.set_xlabel("Episode", color='white', fontsize=12)
    ax.set_ylabel("Character (by first appearance)", color='white', fontsize=12)
    ax.set_title(f"One Piece Character Appearance Raster\n{len(char_names):,} Characters × {len(ep_numbers):,} Episodes",
                 color='white', fontsize=16, fontweight='bold', pad=15)

    # Ticks
    xt = list(range(0, w, 100))
    ax.set_xticks(xt)
    ax.set_xticklabels([str(ep_numbers[i]) for i in xt], color='white', fontsize=8)
    yt = list(range(0, h, 200))
    ax.set_yticks(yt)
    ax.set_yticklabels([str(y) for y in yt], color='white', fontsize=8)
    ax.tick_params(colors='white', length=3)

    for spine in ax.spines.values():
        spine.set_color('#333')

    plt.tight_layout()
    fig.savefig(OUTPUT_DIR / "raster_basic.png", dpi=250, facecolor=fig.get_facecolor(),
                bbox_inches='tight')
    plt.close(fig)
    print("  Saved: output/raster_basic.png")


def plot_with_arcs(char_names, ep_numbers, matrix, char_idx, ep_idx):
    """Raster with arc annotations."""
    print("Generating raster with arcs...")
    h, w = matrix.shape
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[matrix] = [255, 255, 255]
    for sh in STRAW_HATS:
        if sh in char_idx:
            row = char_idx[sh]
            img[row, matrix[row]] = [0, 191, 255]

    fig, ax = plt.subplots(figsize=(20, 28))
    fig.patch.set_facecolor('#080808')
    ax.set_facecolor('#080808')
    ax.imshow(img, aspect='auto', interpolation='nearest')

    add_arc_annotations(ax, ep_numbers, ep_idx, h)

    ax.set_xlabel("Episode", color='white', fontsize=12)
    ax.set_ylabel("Character (by first appearance)", color='white', fontsize=12)
    ax.set_title("One Piece Character Raster with Story Arcs",
                 color='white', fontsize=16, fontweight='bold', pad=15)

    xt = list(range(0, w, 100))
    ax.set_xticks(xt)
    ax.set_xticklabels([str(ep_numbers[i]) for i in xt], color='white', fontsize=8)
    yt = list(range(0, h, 200))
    ax.set_yticks(yt)
    ax.set_yticklabels([str(y) for y in yt], color='white', fontsize=8)
    ax.tick_params(colors='white', length=3)
    for spine in ax.spines.values():
        spine.set_color('#333')

    plt.tight_layout()
    fig.savefig(OUTPUT_DIR / "raster_arcs.png", dpi=250, facecolor=fig.get_facecolor(),
                bbox_inches='tight')
    plt.close(fig)
    print("  Saved: output/raster_arcs.png")


def plot_factions(char_names, ep_numbers, matrix, char_idx, ep_idx, faction_data):
    """Faction-colored raster."""
    print("Generating faction-colored raster...")
    h, w = matrix.shape
    img = np.zeros((h, w, 3), dtype=np.uint8)

    for i, name in enumerate(char_names):
        faction = faction_data.get(name)
        if name in STRAW_HATS:
            color = FACTION_COLORS["Straw Hat Pirates"]
        elif faction and faction in FACTION_COLORS:
            color = FACTION_COLORS[faction]
        else:
            color = DEFAULT_COLOR
        img[i, matrix[i]] = color

    fig, ax = plt.subplots(figsize=(20, 28))
    fig.patch.set_facecolor('#080808')
    ax.set_facecolor('#080808')
    ax.imshow(img, aspect='auto', interpolation='nearest')

    ax.set_xlabel("Episode", color='white', fontsize=12)
    ax.set_ylabel("Character (by first appearance)", color='white', fontsize=12)
    ax.set_title("One Piece Character Raster — Colored by Faction",
                 color='white', fontsize=16, fontweight='bold', pad=15)

    xt = list(range(0, w, 100))
    ax.set_xticks(xt)
    ax.set_xticklabels([str(ep_numbers[i]) for i in xt], color='white', fontsize=8)
    yt = list(range(0, h, 200))
    ax.set_yticks(yt)
    ax.set_yticklabels([str(y) for y in yt], color='white', fontsize=8)
    ax.tick_params(colors='white', length=3)
    for spine in ax.spines.values():
        spine.set_color('#333')

    # Legend
    legend_items = [
        ("Straw Hat Pirates", '#00bfff'), ("Marines", '#2980b3'),
        ("Beasts Pirates", '#c0392b'), ("Charlotte Family", '#ff69b4'),
        ("Whitebeard Pirates", '#f39c12'), ("World Government", '#8e44ad'),
        ("Revolutionary Army", '#27ae60'), ("Baroque Works", '#d4ac0d'),
        ("Blackbeard Pirates", '#646464'), ("Donquixote Pirates", '#e74c3c'),
        ("Roger Pirates", '#d4a017'), ("Other", '#3c3c3c'),
    ]
    handles = [plt.Line2D([0], [0], marker='s', color='w', label=n,
                          markerfacecolor=c, markersize=7, linewidth=0)
               for n, c in legend_items]
    ax.legend(handles=handles, loc='lower right', fontsize=7,
              facecolor='#151515', edgecolor='#333', labelcolor='white', framealpha=0.95)

    plt.tight_layout()
    fig.savefig(OUTPUT_DIR / "raster_factions.png", dpi=250, facecolor=fig.get_facecolor(),
                bbox_inches='tight')
    plt.close(fig)
    print("  Saved: output/raster_factions.png")


def plot_combined(char_names, ep_numbers, matrix, char_idx, ep_idx, faction_data):
    """Combined: factions + arcs."""
    print("Generating combined raster...")
    h, w = matrix.shape
    img = np.zeros((h, w, 3), dtype=np.uint8)

    for i, name in enumerate(char_names):
        faction = faction_data.get(name)
        if name in STRAW_HATS:
            color = FACTION_COLORS["Straw Hat Pirates"]
        elif faction and faction in FACTION_COLORS:
            color = FACTION_COLORS[faction]
        else:
            color = DEFAULT_COLOR
        img[i, matrix[i]] = color

    fig, ax = plt.subplots(figsize=(22, 30))
    fig.patch.set_facecolor('#080808')
    ax.set_facecolor('#080808')
    ax.imshow(img, aspect='auto', interpolation='nearest')

    add_arc_annotations(ax, ep_numbers, ep_idx, h)

    ax.set_xlabel("Episode", color='white', fontsize=12)
    ax.set_ylabel("Character (by first appearance)", color='white', fontsize=12)
    ax.set_title("One Piece Character Raster\nColored by Faction | Story Arcs Annotated",
                 color='white', fontsize=16, fontweight='bold', pad=15)

    xt = list(range(0, w, 100))
    ax.set_xticks(xt)
    ax.set_xticklabels([str(ep_numbers[i]) for i in xt], color='white', fontsize=8)
    yt = list(range(0, h, 200))
    ax.set_yticks(yt)
    ax.set_yticklabels([str(y) for y in yt], color='white', fontsize=8)
    ax.tick_params(colors='white', length=3)
    for spine in ax.spines.values():
        spine.set_color('#333')

    legend_items = [
        ("Straw Hat Pirates", '#00bfff'), ("Marines", '#2980b3'),
        ("Beasts Pirates", '#c0392b'), ("Charlotte Family", '#ff69b4'),
        ("Whitebeard Pirates", '#f39c12'), ("World Government", '#8e44ad'),
        ("Revolutionary Army", '#27ae60'), ("Baroque Works", '#d4ac0d'),
        ("Blackbeard Pirates", '#646464'), ("Donquixote Pirates", '#e74c3c'),
        ("Roger Pirates", '#d4a017'), ("Other", '#3c3c3c'),
    ]
    handles = [plt.Line2D([0], [0], marker='s', color='w', label=n,
                          markerfacecolor=c, markersize=7, linewidth=0)
               for n, c in legend_items]
    ax.legend(handles=handles, loc='lower right', fontsize=7,
              facecolor='#151515', edgecolor='#333', labelcolor='white', framealpha=0.95)

    plt.tight_layout()
    fig.savefig(OUTPUT_DIR / "raster_combined.png", dpi=250, facecolor=fig.get_facecolor(),
                bbox_inches='tight')
    plt.close(fig)
    print("  Saved: output/raster_combined.png")


def main():
    episode_data, faction_data = load_data()
    char_names, ep_numbers, matrix, display_names, char_idx, ep_idx = build_matrix(episode_data)

    print(f"Matrix: {len(char_names):,} characters × {len(ep_numbers):,} episodes")
    print(f"Total appearances: {matrix.sum():,}\n")

    plot_basic(char_names, ep_numbers, matrix, char_idx)
    plot_with_arcs(char_names, ep_numbers, matrix, char_idx, ep_idx)
    plot_factions(char_names, ep_numbers, matrix, char_idx, ep_idx, faction_data)
    plot_combined(char_names, ep_numbers, matrix, char_idx, ep_idx, faction_data)

    print("\nAll visualizations saved to output/")


if __name__ == "__main__":
    main()
