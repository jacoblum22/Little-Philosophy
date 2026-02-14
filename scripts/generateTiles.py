#!/usr/bin/env python3
"""Generate placeholder tile markdown files from tile_data.json."""

import json
import os
import re

TILE_DIR = os.path.join("src", "data", "tiles")
DATA_FILE = "tile_data.json"


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def yaml_str(s: str) -> str:
    """Quote a string for YAML if it contains special chars."""
    if any(c in s for c in ":{}[]#&*!|>'\"%@`"):
        return f'"{s}"'
    return s


def generate_tile(tile: dict) -> str:
    lines = ["---"]
    lines.append(f"id: {tile['id']}")
    lines.append(f"name: {yaml_str(tile['name'])}")
    lines.append(f"type: {tile['type']}")

    # createdFrom
    if tile["createdFrom"]:
        lines.append("createdFrom:")
        for ing in tile["createdFrom"]:
            lines.append(f"- {ing}")

    # combinations
    if tile["combinations"]:
        lines.append("combinations:")
        for combo in tile["combinations"]:
            lines.append(f"- with: {combo['with']}")
            lines.append(f"  produces: {combo['produces']}")

    lines.append("---")
    lines.append("")
    lines.append("")

    # Placeholder body
    tile_type = tile["type"]
    name = tile["name"]

    if tile_type == "philosopher":
        lines.append(
            f"{name} is a philosopher whose ideas shaped the course of philosophical thought."
        )
        lines.append("")
        lines.append("*Content coming soon.*")
    elif tile_type == "writing":
        lines.append(
            f"{name} is a philosophical text that explores fundamental questions about reality, knowledge, or ethics."
        )
        lines.append("")
        lines.append("*Content coming soon.*")
    else:
        if tile["createdFrom"]:
            parents = " and ".join(
                p.replace("-", " ").title() for p in tile["createdFrom"]
            )
            lines.append(f"{name} emerges from the intersection of {parents}.")
        else:
            lines.append(f"{name} is a foundational concept in philosophy.")
        lines.append("")
        lines.append("*Content coming soon.*")

    # Add starting tag for tiles with no createdFrom
    if not tile["createdFrom"] and tile["type"] == "concept":
        lines.append("")
        lines.append("#starting")

    # Parents and Children wikilinks
    if tile["createdFrom"]:
        parents = " ".join(f"[[{p}]]" for p in tile["createdFrom"])
        lines.append(f"Parents: {parents}")
    
    children = sorted(set(c["produces"] for c in tile["combinations"]))
    if children:
        child_links = " ".join(f"[[{c}]]" for c in children)
        lines.append(f"Children: {child_links}")

    lines.append("")
    return "\n".join(lines)


def main():
    with open(DATA_FILE, encoding="utf-8-sig") as f:
        tiles = json.load(f)

    os.makedirs(TILE_DIR, exist_ok=True)

    written = 0
    skipped = 0

    for tile in tiles:
        filepath = os.path.join(TILE_DIR, f"{tile['id']}.md")
        if os.path.exists(filepath):
            skipped += 1
            continue

        content = generate_tile(tile)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        written += 1

    print(f"Written: {written}, Skipped (already exist): {skipped}")
    print(f"Total files: {written + skipped}")


if __name__ == "__main__":
    main()
