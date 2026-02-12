#!/usr/bin/env python3
"""
Combination Tree Health Check
==============================

Analyzes the Little Philosophy tile data and compares it against
Little Alchemy 2 benchmarks to ensure the combination tree is on track.

Run:  python scripts/analyzeTree.py
      python scripts/analyzeTree.py --verbose
      python scripts/analyzeTree.py --json          (machine-readable output)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
TILES_DIR = PROJECT_ROOT / "src" / "data" / "tiles"
CONTENT_MAP = PROJECT_ROOT / "Planning notes" / "Temporary" / "Prototype Content Map.md"

# ---------------------------------------------------------------------------
# Little Alchemy 2 Benchmarks  (from our Jupyter analysis)
# ---------------------------------------------------------------------------

LA2 = {
    "total_elements": 720,
    "total_combos": 3452,
    "combos_per_element": 4.8,
    "leaf_ratio": 0.26,
    "hub_ratio": 0.078,  # elements with degree >= 30
    "median_depth": 9,
    "max_depth": 16,  # excluding base-gated outliers
    "median_recipes": 4,
    "mean_recipes": 4.8,
    "gen0_hit_rate": 1.0,
    "gen1_hit_rate": 0.286,
    "steady_hit_rate": 0.03,  # gens 5-10
    "self_combo_ratio": 0.041,
    "multi_output_ratio": 0.041,
    "median_degree": 6,
    "mean_degree": 12.1,
    "max_degree": 180,
    "starting_elements": 4,
}

# ---------------------------------------------------------------------------
# Thresholds  (scaled for a ~40-100 tile game)
# ---------------------------------------------------------------------------


@dataclass
class Thresholds:
    """Configurable thresholds for health warnings."""

    combos_per_element_min: float = 2.0
    combos_per_element_ideal: float = 3.5
    combos_per_element_max: float = 6.0

    leaf_ratio_max: float = 0.40
    leaf_ratio_ideal: float = 0.30

    hub_degree_threshold: int = 7  # what counts as a "hub" at our scale
    hub_ratio_min: float = 0.05
    hub_ratio_ideal: float = 0.10

    gen0_hit_rate_min: float = 0.80  # starting combos should mostly work
    max_burst_ratio: float = 0.35  # no single gen should discover >35% of total

    median_depth_min: int = 4
    median_depth_max: int = 12

    min_recipes_ideal: float = 1.5  # median alternate recipes per element
    max_single_burst: int = 15  # max elements discovered in one BFS gen


# ---------------------------------------------------------------------------
# YAML Frontmatter Parser (no external deps)
# ---------------------------------------------------------------------------


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Parse YAML-ish frontmatter from a markdown file. Returns (metadata, body)."""
    if not text.startswith("---"):
        return {}, text

    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text

    fm_text = parts[1]
    body = parts[2].strip()

    meta: dict[str, Any] = {}
    current_key: str | None = None
    current_list: list[Any] | None = None
    current_obj_list: list[dict] | None = None
    current_obj: dict | None = None

    for line in fm_text.split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        # Top-level key: value
        top_match = re.match(r"^([a-zA-Z_][\w-]*):\s*(.*)", line)
        if top_match and not line.startswith(" ") and not line.startswith("\t"):
            # Save previous list/object
            if current_key and current_list is not None:
                meta[current_key] = current_list
            if current_key and current_obj_list is not None:
                meta[current_key] = current_obj_list

            key = top_match.group(1)
            val = top_match.group(2).strip()

            if val == "":
                # Could be a list or object, wait for next lines
                current_key = key
                current_list = None
                current_obj_list = None
                current_obj = None
            elif val == "[]":
                meta[key] = []
                current_key = None
                current_list = None
                current_obj_list = None
            else:
                # Strip quotes
                if (val.startswith('"') and val.endswith('"')) or (
                    val.startswith("'") and val.endswith("'")
                ):
                    val = val[1:-1]
                meta[key] = val
                current_key = None
                current_list = None
                current_obj_list = None
            continue

        # List item -- combo object (- with: / produces:)
        list_match = re.match(r"^\s*-\s+with:\s*(.*)", line)
        if list_match and current_key:
            # Start of a combo object
            if current_obj_list is None:
                current_obj_list = []
                current_list = None
            current_obj = {"with": list_match.group(1).strip()}
            continue

        prod_match = re.match(r"^\s*produces:\s*(.*)", line)
        if prod_match and current_obj is not None:
            current_obj["produces"] = prod_match.group(1).strip()
            if current_obj_list is not None:
                current_obj_list.append(current_obj)
            current_obj = None
            continue

        simple_list_match = re.match(r"^\s*-\s+(.+)", line)
        if simple_list_match and current_key:
            if current_list is None:
                current_list = []
                current_obj_list = None
            current_list.append(simple_list_match.group(1).strip())
            continue

    # Save last list
    if current_key and current_list is not None:
        meta[current_key] = current_list
    if current_key and current_obj_list is not None:
        meta[current_key] = current_obj_list

    return meta, body


# ---------------------------------------------------------------------------
# Tile Data Model
# ---------------------------------------------------------------------------


@dataclass
class Tile:
    id: str
    name: str
    tile_type: str
    combinations: list[dict[str, str]]
    created_from: list[str]
    recipe: list[str]
    is_starting: bool
    tags: list[str]


@dataclass
class GameGraph:
    tiles: dict[str, Tile]
    combos: dict[tuple[str, str], str]  # sorted (a,b) → output
    combo_partners: dict[str, set[str]]
    starting_tiles: set[str]


def load_tiles() -> GameGraph:
    """Load all tile markdown files and build the game graph."""
    tiles: dict[str, Tile] = {}
    combos: dict[tuple[str, str], str] = {}
    combo_partners: defaultdict[str, set[str]] = defaultdict(set)
    starting_tiles: set[str] = set()

    for f in sorted(TILES_DIR.glob("*.md")):
        content = f.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(content)

        tile_id = meta.get("id", f.stem)
        name = meta.get("name", tile_id)
        tile_type = meta.get("type", "concept")

        # Parse combinations
        raw_combos = meta.get("combinations", [])
        combinations = []
        if isinstance(raw_combos, list):
            for c in raw_combos:
                if isinstance(c, dict) and "with" in c and "produces" in c:
                    combinations.append(c)

        # Parse createdFrom
        created_from = meta.get("createdFrom", [])
        if isinstance(created_from, str):
            created_from = [created_from]

        # Parse recipe
        recipe = meta.get("recipe", [])
        if isinstance(recipe, str):
            recipe = [recipe]

        # Parse tags from body
        tags = re.findall(r"#([\w-]+)", body) if body else []

        # Check starting tag from parsed tags
        is_starting = "starting" in tags
        if is_starting:
            starting_tiles.add(tile_id)

        tile = Tile(
            id=tile_id,
            name=name,
            tile_type=tile_type,
            combinations=combinations,
            created_from=created_from,
            recipe=recipe,
            is_starting=is_starting,
            tags=tags,
        )
        tiles[tile_id] = tile

        # Build combo lookup
        for combo in combinations:
            key = tuple(sorted([tile_id, combo["with"]]))
            combos[key] = combo["produces"]
            combo_partners[tile_id].add(combo["with"])
            combo_partners[combo["with"]].add(tile_id)

    return GameGraph(
        tiles=tiles,
        combos=combos,
        combo_partners=dict(combo_partners),
        starting_tiles=starting_tiles,
    )


# ---------------------------------------------------------------------------
# Content Map Parser
# ---------------------------------------------------------------------------

def name_to_id(name: str) -> str:
    """Convert a tile name to a kebab-case ID. e.g. 'Allegory of the Cave' → 'allegory-of-the-cave'."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def load_content_map(path: Path | None = None) -> GameGraph:
    """Parse a Prototype Content Map markdown file into a GameGraph.

    Expected format
    ===============

    ## Starting Elements
    - Self
    - Other
    - World

    ## Combinations
    Self + World = Experience
    Self + Other = Empathy
    ...

    ## Philosopher: Socrates
    Recipe: Dialogue, Ethics, Questioning, Virtue
    Socrates + Knowledge = Socratic Method
    Socrates + Virtue = Eudaimonia

    ## Writing: The Republic
    Recipe: Plato, Philosopher King, Justice, Society
    The Republic + Ethics = Political Philosophy

    Lines that don't match any pattern are silently ignored, so you can
    freely add notes, blank lines, or markdown prose between the data.
    Section headings (## ...) are used to switch parsing context.
    """
    if path is None:
        path = CONTENT_MAP

    text = path.read_text(encoding="utf-8")
    lines = text.split("\n")

    tiles: dict[str, Tile] = {}
    combos: dict[tuple[str, str], str] = {}
    combo_partners: defaultdict[str, set[str]] = defaultdict(set)
    starting_tiles: set[str] = set()

    # Track which section we're in
    section: str | None = None          # "starting", "combinations", "philosopher", "writing"
    current_entity_id: str | None = None  # id of current philosopher/writing

    # Regex patterns
    combo_re = re.compile(r"^(.+?)\s*\+\s*(.+?)\s*=\s*(.+)$")
    recipe_re = re.compile(r"^Recipe:\s*(.+)$", re.IGNORECASE)
    starting_re = re.compile(r"^\s*[-*]\s+(.+)$")
    heading_re = re.compile(r"^##\s+(.+)$")

    def ensure_tile(name: str, tile_type: str = "concept",
                    is_starting: bool = False) -> str:
        """Create tile if it doesn't exist. Return its ID."""
        tid = name_to_id(name)
        if tid not in tiles:
            tiles[tid] = Tile(
                id=tid,
                name=name.strip(),
                tile_type=tile_type,
                combinations=[],
                created_from=[],
                recipe=[],
                is_starting=is_starting,
                tags=["starting"] if is_starting else [],
            )
        if is_starting:
            tiles[tid].is_starting = True
            if "starting" not in tiles[tid].tags:
                tiles[tid].tags.append("starting")
            starting_tiles.add(tid)
        return tid

    def register_combo(name_a: str, name_b: str, name_out: str,
                       source_type: str = "concept"):
        """Register a combination and ensure all tiles exist."""
        id_a = ensure_tile(name_a)
        id_b = ensure_tile(name_b)
        id_out = ensure_tile(name_out)

        key = tuple(sorted([id_a, id_b]))
        combos[key] = id_out

        # Add to source tile's combinations list
        tiles[id_a].combinations.append({"with": id_b, "produces": id_out})
        combo_partners[id_a].add(id_b)
        combo_partners[id_b].add(id_a)

        # Set createdFrom on the output tile
        if not tiles[id_out].created_from:
            tiles[id_out].created_from = list(key)

    for line in lines:
        stripped = line.strip()

        # Detect section headings
        heading_match = heading_re.match(stripped)
        if heading_match:
            heading_text = heading_match.group(1).strip()
            ht_lower = heading_text.lower()

            if "starting" in ht_lower:
                section = "starting"
                current_entity_id = None
            elif ht_lower == "combinations" or ht_lower.startswith("combination"):
                section = "combinations"
                current_entity_id = None
            elif ht_lower.startswith("philosopher:"):
                name = heading_text.split(":", 1)[1].strip()
                section = "philosopher"
                current_entity_id = ensure_tile(name, tile_type="philosopher")
            elif ht_lower.startswith("writing:"):
                name = heading_text.split(":", 1)[1].strip()
                section = "writing"
                current_entity_id = ensure_tile(name, tile_type="writing")
            else:
                # Sub-section heading (e.g. "### Epistemology Branch")
                # Stay in whatever section we're in — allows sub-grouping
                pass
            continue

        # Skip empty lines
        if not stripped:
            continue

        # --- Parse content based on current section ---

        # Starting elements: bullet items
        if section == "starting":
            m = starting_re.match(stripped)
            if m:
                ensure_tile(m.group(1).strip(), is_starting=True)
            continue

        # Combinations: "A + B = C" lines
        if section == "combinations":
            m = combo_re.match(stripped)
            if m:
                register_combo(m.group(1).strip(), m.group(2).strip(), m.group(3).strip())
            continue

        # Philosopher / Writing sections: Recipe line or combo lines
        if section in ("philosopher", "writing") and current_entity_id:
            # Recipe line
            m = recipe_re.match(stripped)
            if m:
                ingredients = [i.strip() for i in m.group(1).split(",") if i.strip()]
                tiles[current_entity_id].recipe = [name_to_id(i) for i in ingredients]
                # Ensure all recipe ingredients exist as tiles
                for ingredient in ingredients:
                    ensure_tile(ingredient)
                continue

            # Combo line
            m = combo_re.match(stripped)
            if m:
                register_combo(m.group(1).strip(), m.group(2).strip(), m.group(3).strip())
                continue

    return GameGraph(
        tiles=tiles,
        combos=combos,
        combo_partners=dict(combo_partners),
        starting_tiles=starting_tiles,
    )


# ---------------------------------------------------------------------------
# Analysis Functions
# ---------------------------------------------------------------------------


def run_bfs(graph: GameGraph) -> list[dict[str, Any]]:
    """Simulate discovery from starting tiles, generation by generation."""
    discovered = set(graph.starting_tiles)
    generations = [{"gen": 0, "total": len(discovered), "new": sorted(discovered)}]

    for gen in range(1, 50):
        new_this_gen: set[str] = set()

        disc_list = list(discovered)
        for i, a in enumerate(disc_list):
            for b in disc_list[i:]:
                key = tuple(sorted([a, b]))
                if key in graph.combos:
                    output = graph.combos[key]
                    if output not in discovered:
                        new_this_gen.add(output)

        # Check recipe unlocks
        for tid, tile in graph.tiles.items():
            if tile.recipe and tid not in discovered and tid not in new_this_gen:
                if all(r in (discovered | new_this_gen) for r in tile.recipe):
                    new_this_gen.add(tid)

        if not new_this_gen:
            break

        discovered |= new_this_gen
        generations.append(
            {
                "gen": gen,
                "total": len(discovered),
                "new": sorted(new_this_gen),
            }
        )

    return generations


def calc_hit_rates(graph: GameGraph, generations: list[dict]) -> list[dict[str, Any]]:
    """Calculate combo hit rates at each BFS generation."""
    discovered = set(graph.starting_tiles)
    rates = []

    for g in generations:
        disc_list = list(discovered)
        total_possible = len(disc_list) * (len(disc_list) + 1) // 2
        valid = 0
        productive = 0

        for i, a in enumerate(disc_list):
            for b in disc_list[i:]:
                key = tuple(sorted([a, b]))
                if key in graph.combos:
                    valid += 1
                    if graph.combos[key] not in discovered:
                        productive += 1

        rates.append(
            {
                "gen": g["gen"],
                "elements": len(discovered),
                "total_possible": total_possible,
                "valid": valid,
                "productive": productive,
                "hit_rate": valid / total_possible if total_possible > 0 else 0,
            }
        )

        if g["gen"] > 0:
            discovered |= set(g["new"])

    return rates


def calc_depths(graph: GameGraph) -> dict[str, int]:
    """Calculate minimum combo depth for each tile."""
    depths: dict[str, int] = {}
    for tid in graph.starting_tiles:
        depths[tid] = 0

    changed = True
    iterations = 0
    while changed and iterations < 100:
        changed = False
        iterations += 1
        for tid, tile in graph.tiles.items():
            if tid in depths and depths[tid] == 0 and tile.is_starting:
                continue

            # Check createdFrom (combo result)
            if len(tile.created_from) == 2:
                a, b = tile.created_from
                if a in depths and b in depths:
                    depth = max(depths[a], depths[b]) + 1
                    if tid not in depths or depth < depths[tid]:
                        depths[tid] = depth
                        changed = True

            # Check recipe
            if tile.recipe:
                if all(r in depths for r in tile.recipe):
                    depth = max(depths[r] for r in tile.recipe) + 1
                    if tid not in depths or depth < depths[tid]:
                        depths[tid] = depth
                        changed = True

    return depths


def count_recipes(graph: GameGraph) -> dict[str, int]:
    """Count how many different ways each element can be created."""
    recipes: defaultdict[str, int] = defaultdict(int)

    # From combinations
    for (a, b), output in graph.combos.items():
        recipes[output] += 1

    # From createdFrom (each element is created by its parents combo)
    # This is already counted above since createdFrom maps to a combo

    return dict(recipes)


# ---------------------------------------------------------------------------
# Report Rendering
# ---------------------------------------------------------------------------

STATUS_OK = "[OK]"
STATUS_WARN = "[!!]"
STATUS_BAD = "[XX]"
STATUS_INFO = "[ii]"


@dataclass
class Finding:
    status: str
    metric: str
    value: str
    benchmark: str
    suggestion: str = ""


def analyze(graph: GameGraph, thresholds: Thresholds) -> tuple[list[Finding], dict]:
    """Run all analyses and produce findings."""
    findings: list[Finding] = []
    raw: dict[str, Any] = {}

    n_tiles = len(graph.tiles)
    n_combos = len(graph.combos)
    n_starting = len(graph.starting_tiles)

    # --- Basic counts ---
    raw["total_tiles"] = n_tiles
    raw["total_combos"] = n_combos
    raw["starting_tiles"] = n_starting
    raw["tile_types"] = dict(Counter(t.tile_type for t in graph.tiles.values()))

    # --- Combos per element ---
    cpe = n_combos / n_tiles if n_tiles > 0 else 0
    raw["combos_per_element"] = round(cpe, 2)

    if cpe < thresholds.combos_per_element_min:
        findings.append(
            Finding(
                STATUS_BAD,
                "Combos/element",
                f"{cpe:.2f}",
                f"target >= {thresholds.combos_per_element_min} (LA2: {LA2['combos_per_element']})",
                "Add more combinations to existing tiles. Most tiles should combine with 2-4 others.",
            )
        )
    elif cpe < thresholds.combos_per_element_ideal:
        findings.append(
            Finding(
                STATUS_WARN,
                "Combos/element",
                f"{cpe:.2f}",
                f"ideal >= {thresholds.combos_per_element_ideal} (LA2: {LA2['combos_per_element']})",
                "Getting closer! Add combinations to tiles with 0-1 combo partners.",
            )
        )
    else:
        findings.append(
            Finding(
                STATUS_OK,
                "Combos/element",
                f"{cpe:.2f}",
                f"target: {thresholds.combos_per_element_min}-{thresholds.combos_per_element_max}",
            )
        )

    # --- Leaf ratio ---
    # "Leaf" = tiles with no outgoing combos (no children)
    tiles_with_children = set()
    for tid, t in graph.tiles.items():
        if t.combinations:
            tiles_with_children.add(tid)
    leaf_count = n_tiles - len(tiles_with_children)
    leaf_ratio = leaf_count / n_tiles if n_tiles > 0 else 0
    raw["leaf_count"] = leaf_count
    raw["leaf_ratio"] = round(leaf_ratio, 3)
    raw["leaf_tiles"] = sorted(
        [graph.tiles[tid].name for tid in graph.tiles if tid not in tiles_with_children]
    )

    if leaf_ratio > thresholds.leaf_ratio_max:
        findings.append(
            Finding(
                STATUS_BAD,
                "Leaf ratio",
                f"{leaf_ratio:.0%} ({leaf_count}/{n_tiles})",
                f"target <= {thresholds.leaf_ratio_max:.0%} (LA2: {LA2['leaf_ratio']:.0%})",
                f"Too many dead ends. Give combos to: {', '.join(raw['leaf_tiles'][:5])}...",
            )
        )
    elif leaf_ratio > thresholds.leaf_ratio_ideal:
        findings.append(
            Finding(
                STATUS_WARN,
                "Leaf ratio",
                f"{leaf_ratio:.0%} ({leaf_count}/{n_tiles})",
                f"ideal <= {thresholds.leaf_ratio_ideal:.0%} (LA2: {LA2['leaf_ratio']:.0%})",
                f"Consider adding combos to: {', '.join(raw['leaf_tiles'][:3])}",
            )
        )
    else:
        findings.append(
            Finding(
                STATUS_OK,
                "Leaf ratio",
                f"{leaf_ratio:.0%} ({leaf_count}/{n_tiles})",
                f"target <= {thresholds.leaf_ratio_max:.0%}",
            )
        )

    # --- Hub analysis ---
    degrees = {tid: len(partners) for tid, partners in graph.combo_partners.items()}
    hub_tiles = {
        tid: deg
        for tid, deg in degrees.items()
        if deg >= thresholds.hub_degree_threshold
    }
    hub_ratio = len(hub_tiles) / n_tiles if n_tiles > 0 else 0
    raw["hub_count"] = len(hub_tiles)
    raw["hub_ratio"] = round(hub_ratio, 3)
    raw["hub_tiles"] = {
        graph.tiles[tid].name: deg
        for tid, deg in sorted(hub_tiles.items(), key=lambda x: x[1], reverse=True)
    }

    if hub_ratio < thresholds.hub_ratio_min:
        findings.append(
            Finding(
                STATUS_WARN,
                "Hub ratio",
                f"{hub_ratio:.0%} ({len(hub_tiles)} hubs, deg >= {thresholds.hub_degree_threshold})",
                f"target >= {thresholds.hub_ratio_min:.0%} (LA2: {LA2['hub_ratio']:.0%})",
                "Add more combos to key connective concepts (Empathy, Wonder, Experience).",
            )
        )
    else:
        findings.append(
            Finding(
                STATUS_OK,
                "Hub ratio",
                f"{hub_ratio:.0%} ({len(hub_tiles)} hubs)",
                f"target >= {thresholds.hub_ratio_min:.0%}",
            )
        )

    # --- Degree distribution ---
    all_degrees = [degrees.get(tid, 0) for tid in graph.tiles]
    if all_degrees:
        mean_deg = sum(all_degrees) / len(all_degrees)
        sorted_degs = sorted(all_degrees)
        median_deg = sorted_degs[len(sorted_degs) // 2]
        max_deg = max(all_degrees)
    else:
        mean_deg = median_deg = max_deg = 0
    raw["degree_mean"] = round(mean_deg, 1)
    raw["degree_median"] = median_deg
    raw["degree_max"] = max_deg

    # --- BFS Analysis ---
    generations = run_bfs(graph)
    raw["bfs_generations"] = len(generations) - 1
    raw["bfs_total_discovered"] = generations[-1]["total"] if generations else 0

    # Reachability
    discovered_all = set()
    for g in generations:
        discovered_all |= set(g["new"])
    unreachable = set(graph.tiles.keys()) - discovered_all
    raw["unreachable_count"] = len(unreachable)
    raw["unreachable_tiles"] = sorted([graph.tiles[tid].name for tid in unreachable])

    if unreachable:
        findings.append(
            Finding(
                STATUS_BAD,
                "Unreachable tiles",
                f"{len(unreachable)} tiles",
                "0 (all tiles should be reachable)",
                f"Cannot reach: {', '.join(raw['unreachable_tiles'])}",
            )
        )
    else:
        findings.append(
            Finding(STATUS_OK, "Reachability", f"All {n_tiles} tiles reachable", "100%")
        )

    # --- Hit rates ---
    hit_rates = calc_hit_rates(graph, generations)
    raw["hit_rates"] = hit_rates

    if hit_rates:
        gen0_hr = hit_rates[0]["hit_rate"]
        if gen0_hr < thresholds.gen0_hit_rate_min:
            findings.append(
                Finding(
                    STATUS_WARN,
                    "Gen 0 hit rate",
                    f"{gen0_hr:.0%}",
                    f"target >= {thresholds.gen0_hit_rate_min:.0%} (LA2: 100%)",
                    "Most starting element combos should produce something.",
                )
            )
        else:
            findings.append(
                Finding(
                    STATUS_OK,
                    "Gen 0 hit rate",
                    f"{gen0_hr:.0%}",
                    f"target >= {thresholds.gen0_hit_rate_min:.0%}",
                )
            )

    # --- Burst analysis ---
    if len(generations) > 1:
        biggest_burst = max(generations[1:], key=lambda g: len(g["new"]))
        burst_size = len(biggest_burst["new"])
        burst_ratio = burst_size / n_tiles if n_tiles > 0 else 0
        raw["biggest_burst_gen"] = biggest_burst["gen"]
        raw["biggest_burst_size"] = burst_size
        raw["biggest_burst_ratio"] = round(burst_ratio, 3)

        if burst_ratio > thresholds.max_burst_ratio:
            findings.append(
                Finding(
                    STATUS_WARN,
                    "Biggest burst",
                    f"Gen {biggest_burst['gen']}: {burst_size} tiles ({burst_ratio:.0%})",
                    f"target < {thresholds.max_burst_ratio:.0%} of total",
                    f"Gen {biggest_burst['gen']} discovers too many at once. Split some combos to spread discovery.",
                )
            )
        elif burst_size > thresholds.max_single_burst:
            findings.append(
                Finding(
                    STATUS_WARN,
                    "Biggest burst",
                    f"Gen {biggest_burst['gen']}: {burst_size} tiles",
                    f"target < {thresholds.max_single_burst}",
                    "Large burst may overwhelm players. Consider adding intermediate steps.",
                )
            )
        else:
            findings.append(
                Finding(
                    STATUS_OK,
                    "Biggest burst",
                    f"Gen {biggest_burst['gen']}: {burst_size} tiles",
                    f"< {thresholds.max_burst_ratio:.0%} of total",
                )
            )

    # --- Depth analysis ---
    depths = calc_depths(graph)
    raw["depths"] = {graph.tiles[tid].name: d for tid, d in depths.items()}

    depth_vals = [d for d in depths.values() if d > 0]
    if depth_vals:
        sorted_dv = sorted(depth_vals)
        median_depth = sorted_dv[len(sorted_dv) // 2]
        max_depth = max(depth_vals)
        raw["median_depth"] = median_depth
        raw["max_depth"] = max_depth

        if median_depth < thresholds.median_depth_min:
            findings.append(
                Finding(
                    STATUS_WARN,
                    "Median depth",
                    f"{median_depth}",
                    f"target {thresholds.median_depth_min}-{thresholds.median_depth_max} (LA2: {LA2['median_depth']})",
                    "Tree is too shallow. Add intermediate concepts to create deeper chains.",
                )
            )
        elif median_depth > thresholds.median_depth_max:
            findings.append(
                Finding(
                    STATUS_WARN,
                    "Median depth",
                    f"{median_depth}",
                    f"target {thresholds.median_depth_min}-{thresholds.median_depth_max} (LA2: {LA2['median_depth']})",
                    "Some paths are too deep. Add shortcuts or alternate paths.",
                )
            )
        else:
            findings.append(
                Finding(
                    STATUS_OK,
                    "Median depth",
                    f"{median_depth} (max: {max_depth})",
                    f"target: {thresholds.median_depth_min}-{thresholds.median_depth_max}",
                )
            )

    # --- Disconnected tiles (degree 0-1) ---
    low_degree = [
        (tid, degrees.get(tid, 0))
        for tid in graph.tiles
        if degrees.get(tid, 0) <= 1 and not graph.tiles[tid].is_starting
    ]
    raw["low_degree_tiles"] = [(graph.tiles[tid].name, d) for tid, d in low_degree]

    if low_degree:
        findings.append(
            Finding(
                STATUS_INFO,
                "Low-connectivity tiles",
                f"{len(low_degree)} tiles with <= 1 combo partner",
                "Most tiles should have 2+ combo partners",
                f"Candidates for more combos: {', '.join(graph.tiles[tid].name for tid, _ in low_degree[:5])}",
            )
        )

    # --- Recipe redundancy ---
    recipe_counts = count_recipes(graph)
    recipe_vals = [v for v in recipe_counts.values()]
    if recipe_vals:
        mean_recipes = sum(recipe_vals) / len(recipe_vals)
        sorted_rv = sorted(recipe_vals)
        median_recipes = sorted_rv[len(sorted_rv) // 2]
        raw["mean_recipes"] = round(mean_recipes, 2)
        raw["median_recipes"] = median_recipes
        single_recipe = sum(1 for v in recipe_vals if v <= 1)
        raw["single_recipe_count"] = single_recipe

        if median_recipes < thresholds.min_recipes_ideal:
            findings.append(
                Finding(
                    STATUS_INFO,
                    "Recipe redundancy",
                    f"median {median_recipes} (mean {mean_recipes:.1f})",
                    f"ideal >= {thresholds.min_recipes_ideal} (LA2: median {LA2['median_recipes']})",
                    f"{single_recipe} tiles have only 1 recipe. Add alternate paths to key concepts.",
                )
            )
        else:
            findings.append(
                Finding(
                    STATUS_OK,
                    "Recipe redundancy",
                    f"median {median_recipes}",
                    f"target >= {thresholds.min_recipes_ideal}",
                )
            )

    raw["generations"] = [
        {
            "gen": g["gen"],
            "new_count": len(g["new"]),
            "total": g["total"],
            "tiles": [graph.tiles[t].name for t in g["new"] if t in graph.tiles],
        }
        for g in generations
    ]

    return findings, raw


def print_report(
    findings: list[Finding],
    raw: dict,
    graph: GameGraph | None = None,
    verbose: bool = False,
):
    """Print a formatted CLI report."""
    print()
    print("=" * 68)
    print("  LITTLE PHILOSOPHY -- Combination Tree Health Check")
    print("=" * 68)
    print()

    # Summary bar
    ok = sum(1 for f in findings if f.status == STATUS_OK)
    warn = sum(1 for f in findings if f.status == STATUS_WARN)
    bad = sum(1 for f in findings if f.status == STATUS_BAD)
    info = sum(1 for f in findings if f.status == STATUS_INFO)
    print(
        f"  {STATUS_OK} {ok} passing   {STATUS_WARN} {warn} warnings   {STATUS_BAD} {bad} problems   {STATUS_INFO} {info} info"
    )
    print()

    # Overview
    print("  OVERVIEW")
    print("  " + "-" * 50)
    types = raw.get("tile_types", {})
    type_str = ", ".join(f"{v} {k}s" for k, v in types.items())
    print(f"  Tiles:       {raw['total_tiles']} ({type_str})")
    print(f"  Combos:      {raw['total_combos']}")
    print(f"  Starting:    {raw['starting_tiles']}")
    print(f"  BFS gens:    {raw['bfs_generations']}")
    print(
        f"  Degree:      median {raw['degree_median']}, mean {raw['degree_mean']}, max {raw['degree_max']}"
    )
    print()

    # Findings
    print("  FINDINGS")
    print("  " + "-" * 50)
    for f in findings:
        print(f"  {f.status} {f.metric}: {f.value}")
        if verbose:
            print(f"       benchmark: {f.benchmark}")
            if f.suggestion:
                print(f"       → {f.suggestion}")
    print()

    # Suggestions (only if there are warnings/problems)
    suggestions = [
        f for f in findings if f.suggestion and f.status in (STATUS_BAD, STATUS_WARN)
    ]
    if suggestions:
        print("  SUGGESTIONS")
        print("  " + "-" * 50)
        for i, f in enumerate(suggestions, 1):
            print(f"  {i}. [{f.metric}] {f.suggestion}")
        print()

    # BFS Progression
    print("  DISCOVERY PROGRESSION (BFS)")
    print("  " + "-" * 50)
    print(f"  {'Gen':<5} {'New':<6} {'Total':<7} {'Tiles'}")
    for g in raw.get("generations", []):
        names = ", ".join(g["tiles"][:6])
        if len(g["tiles"]) > 6:
            names += f"... (+{len(g['tiles'])-6})"
        print(f"  {g['gen']:<5} {g['new_count']:<6} {g['total']:<7} {names}")
    print()

    # Degree ranking
    if verbose and graph:
        print("  DEGREE RANKING (combo partners per tile)")
        print("  " + "-" * 50)
        print(f"  {'Tile':<30} {'Degree':<8} {'Type'}")
        for tid in sorted(
            graph.combo_partners,
            key=lambda t: len(graph.combo_partners[t]),
            reverse=True,
        ):
            deg = len(graph.combo_partners[tid])
            tile = graph.tiles[tid]
            marker = " *" if deg >= 7 else ""
            print(f"  {tile.name:<30} {deg:<8} {tile.tile_type}{marker}")
        # Also show tiles with 0 combo partners
        for tid in sorted(graph.tiles):
            if tid not in graph.combo_partners:
                tile = graph.tiles[tid]
                print(f"  {tile.name:<30} {'0':<8} {tile.tile_type}")
        print()

    # Leaf tiles
    if verbose and raw.get("leaf_tiles"):
        print("  LEAF TILES (no outgoing combos)")
        print("  " + "-" * 50)
        for name in raw["leaf_tiles"]:
            print(f"  * {name}")
        print()

    # Unreachable
    if raw.get("unreachable_tiles"):
        print("  ⚠ UNREACHABLE TILES")
        print("  " + "-" * 50)
        for name in raw["unreachable_tiles"]:
            print(f"  * {name}")
        print()

    # LA2 comparison table
    print("  LA2 COMPARISON")
    print("  " + "-" * 50)
    print(f"  {'Metric':<30} {'LP':<12} {'LA2':<12} {'Target'}")
    print(
        f"  {'Combos/element':<30} {raw['combos_per_element']:<12} {LA2['combos_per_element']:<12} {'3-5'}"
    )
    print(
        f"  {'Leaf ratio':<30} {raw['leaf_ratio']:<12.0%} {LA2['leaf_ratio']:<12.0%} {'25-35%'}"
    )
    print(
        f"  {'Hub ratio':<30} {raw['hub_ratio']:<12.0%} {LA2['hub_ratio']:<12.0%} {'5-10%'}"
    )
    print(
        f"  {'Median depth':<30} {raw.get('median_depth', '?'):<12} {LA2['median_depth']:<12} {'4-12'}"
    )
    print(f"  {'Max degree':<30} {raw['degree_max']:<12} {LA2['max_degree']:<12} {'--'}")
    print(
        f"  {'Median degree':<30} {raw['degree_median']:<12} {LA2['median_degree']:<12} {'--'}"
    )
    print()

    # Score
    score = ok * 10 - warn * 3 - bad * 8
    max_score = len(findings) * 10
    pct = max(0, score / max_score * 100) if max_score > 0 else 0
    bar_len = 30
    filled = int(pct / 100 * bar_len)
    bar = "█" * filled + "░" * (bar_len - filled)
    print(f"  HEALTH SCORE: [{bar}] {pct:.0f}%")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Little Philosophy Tree Health Check")
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show detailed output"
    )
    parser.add_argument("--json", action="store_true", help="Output raw JSON data")
    parser.add_argument(
        "--from-map",
        nargs="?",
        const=str(CONTENT_MAP),
        metavar="PATH",
        help="Parse a Content Map markdown file instead of tile files. "
             "Defaults to 'Planning notes/Temporary/Prototype Content Map.md'.",
    )
    args = parser.parse_args()

    if args.from_map:
        map_path = Path(args.from_map)
        if not map_path.exists():
            print(f"Error: Content Map not found: {map_path}", file=sys.stderr)
            sys.exit(1)
        print(f"  (reading from Content Map: {map_path.name})")
        graph = load_content_map(map_path)
    else:
        if not TILES_DIR.exists():
            print(f"Error: Tiles directory not found: {TILES_DIR}", file=sys.stderr)
            sys.exit(1)
        graph = load_tiles()

    thresholds = Thresholds()
    findings, raw = analyze(graph, thresholds)

    if args.json:
        # Convert findings to serializable format
        raw["findings"] = [
            {
                "status": f.status,
                "metric": f.metric,
                "value": f.value,
                "benchmark": f.benchmark,
                "suggestion": f.suggestion,
            }
            for f in findings
        ]
        print(json.dumps(raw, indent=2, default=str))
    else:
        print_report(findings, raw, graph=graph, verbose=args.verbose)


if __name__ == "__main__":
    main()
