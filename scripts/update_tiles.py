"""
Script to update tile Markdown files:
1. Strip [[]] brackets from YAML frontmatter values
2. Add Parents: and Children: wikilink lines at the bottom of the body

Parents = createdFrom entries + recipe entries (for philosophers/writings)
Children = all 'produces' values from combinations
"""

import os
import re
import yaml

TILES_DIR = r"c:\Users\jacob\OneDrive - UBC\Desktop\Personal Projects\Little Philosophy\src\data\tiles"


def strip_wikilinks(value):
    """Remove [[ and ]] from a string."""
    if isinstance(value, str):
        return re.sub(r"\[\[([^\]]+)\]\]", r"\1", value)
    elif isinstance(value, list):
        return [strip_wikilinks(v) for v in value]
    elif isinstance(value, dict):
        return {k: strip_wikilinks(v) for k, v in value.items()}
    return value


def extract_parents(frontmatter):
    """Extract parent tile IDs from frontmatter."""
    parents = []
    if "createdFrom" in frontmatter:
        for item in frontmatter["createdFrom"]:
            parents.append(strip_wikilinks(item))
    if "recipe" in frontmatter:
        for item in frontmatter["recipe"]:
            parents.append(strip_wikilinks(item))
    if "author" in frontmatter:
        author = strip_wikilinks(frontmatter["author"])
        if author not in parents:
            parents.append(author)
    return parents


def extract_children(frontmatter):
    """Extract child tile IDs from combinations."""
    children = []
    if "combinations" in frontmatter:
        for combo in frontmatter["combinations"]:
            if "produces" in combo:
                children.append(strip_wikilinks(combo["produces"]))
    return children


def process_tile(filepath):
    """Process a single tile file."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # Split frontmatter from body
    if not content.startswith("---"):
        print(f"  Skipping {filepath} - no frontmatter")
        return

    parts = content.split("---", 2)
    if len(parts) < 3:
        print(f"  Skipping {filepath} - malformed frontmatter")
        return

    frontmatter_str = parts[1]
    body = parts[2]

    # Parse frontmatter
    frontmatter = yaml.safe_load(frontmatter_str)
    if not frontmatter:
        print(f"  Skipping {filepath} - empty frontmatter")
        return

    # Extract parents and children BEFORE stripping wikilinks
    parents = extract_parents(frontmatter)
    children = extract_children(frontmatter)

    # Strip [[ ]] from all frontmatter values
    cleaned_frontmatter = strip_wikilinks(frontmatter)

    # Rebuild frontmatter string
    new_frontmatter_str = yaml.dump(
        cleaned_frontmatter,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    )

    # Remove any existing Parents:/Children: lines from body
    body = re.sub(r"\nParents:.*", "", body)
    body = re.sub(r"\nChildren:.*", "", body)

    # Build the parents/children lines
    footer_lines = []
    if parents:
        parent_links = " ".join(f"[[{p}]]" for p in parents)
        footer_lines.append(f"Parents: {parent_links}")
    if children:
        child_links = " ".join(f"[[{c}]]" for c in children)
        footer_lines.append(f"Children: {child_links}")

    # Rebuild body: trim trailing whitespace, add footer
    body = body.rstrip()
    if footer_lines:
        body = body + "\n" + "\n".join(footer_lines) + "\n"
    else:
        body = body + "\n"

    # Write back
    new_content = f"---\n{new_frontmatter_str}---\n{body}"
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(new_content)

    tile_name = os.path.basename(filepath)
    print(f"  ✓ {tile_name}: {len(parents)} parents, {len(children)} children")


def main():
    print(f"Processing tiles in {TILES_DIR}\n")

    files = sorted([f for f in os.listdir(TILES_DIR) if f.endswith(".md")])
    print(f"Found {len(files)} tile files\n")

    for filename in files:
        filepath = os.path.join(TILES_DIR, filename)
        process_tile(filepath)

    print(f"\nDone! Processed {len(files)} files.")


if __name__ == "__main__":
    main()
