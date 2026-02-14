"""Extract tile data from Content Map for markdown generation.

Outputs JSON with each tile's recipe, combinations, generation, and tags.
Usage: python scripts/extractTileData.py > tile_data.json
"""

from __future__ import annotations
import json, sys
from pathlib import Path

_SCRIPTS_DIR = str(Path(__file__).parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from analyzeTree import load_content_map, calc_depths
from utils import name_to_id

graph = load_content_map()
depths = calc_depths(graph)

# Build combination lookup: for each tile, what does it combine with to produce?
tile_combos: dict[str, list[dict]] = {tid: [] for tid in graph.tiles}
for (a, b), out in graph.combos.items():
    tile_combos.setdefault(a, []).append({"with": b, "produces": out})
    tile_combos.setdefault(b, []).append({"with": a, "produces": out})

# Deduplicate
for tid in tile_combos:
    seen = set()
    unique = []
    for c in tile_combos[tid]:
        key = (c["with"], c["produces"])
        if key not in seen:
            seen.add(key)
            unique.append(c)
    tile_combos[tid] = unique

result = []
for tid, tile in sorted(graph.tiles.items()):
    created_from = []
    if tile.created_from:
        created_from = list(tile.created_from)

    gen = depths.get(tid, -1)

    result.append(
        {
            "id": tid,
            "name": tile.name,
            "gen": gen,
            "createdFrom": created_from,
            "combinations": sorted(
                tile_combos.get(tid, []), key=lambda c: c["produces"]
            ),
            "isStarting": gen == 0,
        }
    )

# Sort by generation, then name
result.sort(key=lambda t: (t["gen"], t["name"]))

print(json.dumps(result, indent=2))
