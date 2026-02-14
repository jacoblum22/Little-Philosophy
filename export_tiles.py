#!/usr/bin/env python3
"""Export all tiles from the Content Map as JSON for tile generation."""

import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "scripts"))
from pathlib import Path
from analyzeTree import load_content_map

CONTENT_MAP = Path("Planning notes") / "Temporary" / "Prototype Content Map.md"


def main():
    graph = load_content_map(CONTENT_MAP)

    tiles_out = []
    for tid, tile in sorted(graph.tiles.items()):
        # Build combinations list
        combos = []
        seen = set()
        for combo in tile.combinations:
            other = combo["with"]
            product = combo["produces"]
            key = (other, product)
            if key not in seen:
                seen.add(key)
                combos.append({"with": other, "produces": product})

        tiles_out.append(
            {
                "id": tid,
                "name": tile.name,
                "type": tile.tile_type,
                "createdFrom": list(tile.created_from) if tile.created_from else [],
                "combinations": combos,
            }
        )

    with open("tile_data.json", "w", encoding="utf-8") as f:
        json.dump(tiles_out, f, indent=2, ensure_ascii=False)

    print(f"Exported {len(tiles_out)} tiles to tile_data.json")


if __name__ == "__main__":
    main()
