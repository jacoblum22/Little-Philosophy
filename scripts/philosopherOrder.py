"""
Philosopher ordering analyzer for Little Philosophy.

Reads philosopher recipes and ordering constraints from the Concept Brainstorm,
builds a dependency graph, and checks for contradictions or impossibilities.

Usage:
    python scripts/philosopherOrder.py
    python scripts/philosopherOrder.py --verbose
    python scripts/philosopherOrder.py --brainstorm "path/to/Concept Brainstorm.md"
"""

from __future__ import annotations

import re
import sys
import argparse
import statistics
from pathlib import Path
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass, field

from utils import name_to_id

# Ensure scripts directory is on sys.path for sibling imports
_SCRIPTS_DIR = str(Path(__file__).parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

# ── Data structures ──────────────────────────────────────────────────


@dataclass
class Philosopher:
    name: str
    era: str  # Ancient, Medieval, Modern, Contemporary
    recipe: list[str] = field(default_factory=list)
    produces: list[str] = field(default_factory=list)
    depends_on_output_of: list[str] = field(
        default_factory=list
    )  # philosophers whose outputs appear in recipe


@dataclass
class Writing:
    title: str
    author: str
    era: str  # Ancient, Medieval, Modern, Contemporary
    recipe: list[str] = field(default_factory=list)
    produces: list[str] = field(default_factory=list)
    depends_on_output_of: list[str] = field(default_factory=list)


@dataclass
class ReportOptions:
    """Configuration flags for print_report output sections."""

    verbose: bool = False
    prereqs: bool = False
    balance: bool = False
    effective: bool = False
    check_concepts: bool = False
    depth_check: bool = False
    content_map_path: Path | None = None
    brainstorm_path: Path | None = None


# ── Parser ───────────────────────────────────────────────────────────


def parse_brainstorm(
    path: Path,
) -> tuple[
    dict[str, Philosopher],
    dict[str, Writing],
    list[tuple[str, str]],
    list[tuple[str, str]],
]:
    """Parse the Concept Brainstorm markdown for philosopher data and ordering constraints."""
    text = path.read_text(encoding="utf-8")
    philosophers: dict[str, Philosopher] = {}

    # Build a lookup: concept -> which philosopher produces it
    concept_to_producer: dict[str, str] = {}

    current_era = None
    era_pattern = re.compile(
        r"^###\s+(Ancient|Medieval|Modern|Contemporary)", re.IGNORECASE
    )

    # First pass: extract all philosophers and their recipes/outputs
    lines = text.split("\n")
    in_philosopher_section = False

    for line in lines:
        # Detect philosopher section
        if line.strip().startswith("## Philosophers"):
            in_philosopher_section = True
            continue

        if (
            in_philosopher_section
            and line.strip().startswith("## ")
            and not line.strip().startswith("## Philosophers")
        ):
            # Any non-philosopher ## heading exits the philosopher section
            in_philosopher_section = False
            continue

        # Detect era subsections
        era_match = era_pattern.match(line.strip())
        if era_match:
            current_era = era_match.group(1)
            continue

        # Parse table rows (skip header and separator rows)
        if in_philosopher_section and current_era and line.strip().startswith("|"):
            parts = [p.strip() for p in line.split("|")]
            parts = [
                p for p in parts if p
            ]  # remove empty strings from leading/trailing |

            if len(parts) < 3:
                continue
            if parts[0] in ("Philosopher", "---", "") or parts[0].startswith("---"):
                continue
            if all(c in "-| " for c in line):
                continue

            name = parts[0].strip()
            recipe_str = parts[1].strip()
            produces_str = parts[2].strip()

            # Parse recipe: comma-separated, * marks philosopher-output dependency
            recipe_items = [
                r.strip().rstrip("*") for r in recipe_str.split(",") if r.strip()
            ]

            # Parse produces: comma-separated
            produces_items = [p.strip() for p in produces_str.split(",") if p.strip()]

            phil = Philosopher(
                name=name,
                era=current_era,
                recipe=recipe_items,
                produces=produces_items,
            )
            philosophers[name] = phil

            # Track what each philosopher produces
            for concept in produces_items:
                concept_to_producer[concept] = name

    # Second pass: resolve dependencies (which philosopher's output is in each recipe)
    for phil in philosophers.values():
        for ingredient in phil.recipe:
            if ingredient in concept_to_producer:
                producer = concept_to_producer[ingredient]
                if producer != phil.name and producer not in phil.depends_on_output_of:
                    phil.depends_on_output_of.append(producer)

    # Third pass: extract writings
    writings: dict[str, Writing] = {}
    in_writing_section = False
    current_era = None
    for line in lines:
        if line.strip().startswith("## Writings"):
            in_writing_section = True
            current_era = None
            continue
        if (
            in_writing_section
            and line.strip().startswith("## ")
            and not line.strip().startswith("## Writings")
        ):
            in_writing_section = False
            continue

        # Detect era subsections within writings
        era_match = era_pattern.match(line.strip())
        if in_writing_section and era_match:
            current_era = era_match.group(1)
            continue

        # Parse table rows
        if in_writing_section and current_era and line.strip().startswith("|"):
            parts = [p.strip() for p in line.split("|")]
            parts = [p for p in parts if p]
            if len(parts) < 4:
                continue
            if parts[0] in ("Writing", "---", "") or parts[0].startswith("---"):
                continue
            if all(c in "-| " for c in line):
                continue

            title = parts[0].strip()
            author = parts[1].strip()
            recipe_str = parts[2].strip()
            produces_str = parts[3].strip()

            recipe_items = [
                r.strip().rstrip("*") for r in recipe_str.split(",") if r.strip()
            ]
            produces_items = [p.strip() for p in produces_str.split(",") if p.strip()]

            # Determine writing's era from its author
            writing_era = current_era
            if author in philosophers:
                writing_era = philosophers[author].era

            writing = Writing(
                title=title,
                author=author,
                era=writing_era,
                recipe=recipe_items,
                produces=produces_items,
            )
            writings[title] = writing

            # Track writing productions in concept_to_producer
            for concept in produces_items:
                concept_to_producer[concept] = f"{title} (writing)"

            # Resolve dependencies: which philosophers' outputs are in the recipe
            for ingredient in recipe_items:
                if ingredient in concept_to_producer:
                    producer = concept_to_producer[ingredient]
                    if "(writing)" not in producer and producer != author:
                        writing.depends_on_output_of.append(producer)

    # Parse ordering constraints
    in_ordering = False
    ordering: list[tuple[str, str]] = []
    concept_depth_ordering: list[tuple[str, str]] = []
    for line in lines:
        if line.strip().startswith("## Philosopher Ordering"):
            in_ordering = True
            continue
        if in_ordering and line.strip().startswith("## "):
            break
        if in_ordering and line.strip().startswith("- "):
            # Parse chains like "Socrates < Plato ~ Aristotle"
            # Split on both < and ~, tracking which separator was used
            raw = line.lstrip("- ").strip()
            # Tokenize: split by < and ~, remembering separators
            tokens = re.split(r"\s*([<~])\s*", raw)
            # tokens = [name, sep, name, sep, name, ...]
            names = tokens[0::2]  # every other element starting at 0
            seps = tokens[1::2]  # every other element starting at 1
            names = [n.strip() for n in names if n.strip()]
            for i, sep in enumerate(seps):
                if i < len(names) - 1:
                    pair = (names[i], names[i + 1])
                    if sep == "<":
                        ordering.append(pair)
                    else:  # ~
                        concept_depth_ordering.append(pair)

    return philosophers, writings, ordering, concept_depth_ordering


# ── Analysis ─────────────────────────────────────────────────────────


def build_dependency_graph(
    philosophers: dict[str, Philosopher],
    ordering: list[tuple[str, str]],
) -> dict[str, set[str]]:
    """Build a graph of who must unlock before whom.

    Edge A -> B means A must unlock before B.
    Sources:
      1. Explicit output dependencies (B's recipe contains A's output)
      2. Ordering constraints (A < B)
    """
    graph: dict[str, set[str]] = defaultdict(set)
    for phil in philosophers:
        graph[phil]  # ensure every philosopher appears

    # Output dependencies
    for phil in philosophers.values():
        for dep in phil.depends_on_output_of:
            graph[dep].add(phil.name)

    # Ordering constraints
    for before, after in ordering:
        if before in philosophers and after in philosophers:
            graph[before].add(after)

    return graph


def detect_cycles(graph: dict[str, set[str]]) -> list[list[str]]:
    """Find all cycles in the dependency graph using DFS."""
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {node: WHITE for node in graph}
    path: list[str] = []
    cycles: list[list[str]] = []

    def dfs(node: str):
        color[node] = GRAY
        path.append(node)
        for neighbor in graph.get(node, set()):
            if neighbor not in color:
                continue
            if color[neighbor] == GRAY:
                # Found a cycle
                cycle_start = path.index(neighbor)
                cycles.append(path[cycle_start:] + [neighbor])
            elif color[neighbor] == WHITE:
                dfs(neighbor)
        path.pop()
        color[node] = BLACK

    for node in graph:
        if color[node] == WHITE:
            dfs(node)

    return cycles


def topological_sort(
    graph: dict[str, set[str]],
    sort_key: Callable[[str], tuple] | None = None,
) -> list[str] | None:
    """Return topological order, or None if cycles exist.

    Within each dependency tier, nodes are sorted by sort_key if provided,
    otherwise alphabetically.
    """
    in_degree: dict[str, int] = defaultdict(int)
    for node in graph:
        in_degree.setdefault(node, 0)
        for neighbor in graph[node]:
            in_degree[neighbor] = in_degree.get(neighbor, 0) + 1

    key_fn = sort_key or (lambda n: (n,))
    queue = deque(sorted((n for n in in_degree if in_degree[n] == 0), key=key_fn))
    order: list[str] = []

    while queue:
        node = queue.popleft()
        order.append(node)
        ready = []
        for neighbor in graph.get(node, set()):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                ready.append(neighbor)
        queue.extend(sorted(ready, key=key_fn))

    if len(order) != len(in_degree):
        return None  # cycle detected
    return order


def check_implicit_ordering(
    philosophers: dict[str, Philosopher],
    ordering: list[tuple[str, str]],
) -> list[str]:
    """Check if ordering constraints are already satisfied by output dependencies alone."""
    # Build graph from output dependencies only (no ordering constraints)
    output_graph: dict[str, set[str]] = defaultdict(set)
    for phil in philosophers.values():
        output_graph[phil.name]
        for dep in phil.depends_on_output_of:
            output_graph[dep].add(phil.name)

    # Check reachability for each ordering constraint
    warnings = []
    for before, after in ordering:
        if before not in philosophers or after not in philosophers:
            warnings.append(f"Unknown philosopher in ordering: {before} < {after}")
            continue

        # BFS: is 'after' reachable from 'before' via output dependencies alone?
        visited = set()
        queue = deque([before])
        reachable = False
        while queue:
            current = queue.popleft()
            if current == after:
                reachable = True
                break
            if current in visited:
                continue
            visited.add(current)
            queue.extend(output_graph.get(current, set()))

        if reachable:
            # Already guaranteed by output deps — constraint is redundant (which is fine)
            pass
        else:
            warnings.append(
                f"  {before} < {after}: NOT guaranteed by output dependencies alone. "
                f"Consider adding an explicit recipe dependency."
            )

    return warnings


# ── Recipe Balance ───────────────────────────────────────────────────


def get_concept_depths(content_map_path: Path | None = None) -> dict[str, int]:
    """Get depth of every concept from the Content Map using BFS.

    Returns a dict mapping concept name (lowered) -> BFS depth.
    Also returns depths by tile ID for cross-referencing.
    """
    from analyzeTree import load_content_map, calc_depths

    graph = load_content_map(content_map_path)
    depths = calc_depths(graph)

    # Build name-to-depth mapping
    name_depths: dict[str, int] = {}
    for tid, depth in depths.items():
        if tid in graph.tiles:
            name_depths[graph.tiles[tid].name.lower()] = depth
            name_depths[tid] = depth  # also index by ID

    return name_depths


def check_recipe_balance(
    philosophers: dict[str, Philosopher],
    concept_depths: dict[str, int],
    max_spread: int = 4,
    max_trivial_ratio: float = 0.75,
) -> list[dict]:
    """Check if philosopher recipes have well-balanced ingredient depths.

    Flags:
    - Recipes where the depth spread (max - min) is too wide
    - Recipes where most ingredients are trivially shallow
    - Recipes where one ingredient is doing all the gating work

    Args:
        philosophers: Philosopher data from brainstorm
        concept_depths: Concept name -> BFS depth mapping from Content Map
        max_spread: Max acceptable difference between deepest and shallowest
        max_trivial_ratio: Flag if this fraction of ingredients has depth <= 2
    """
    results = []

    for phil in sorted(philosophers.values(), key=lambda p: p.name):
        # Look up depth for each recipe ingredient
        ingredients = []
        for item in phil.recipe:
            clean = item.rstrip("*").strip()
            clean_lower = clean.lower()
            clean_id = name_to_id(clean)

            depth = None
            # Try exact name match
            if clean_lower in concept_depths:
                depth = concept_depths[clean_lower]
            # Try ID match
            elif clean_id in concept_depths:
                depth = concept_depths[clean_id]
            # If it's a philosopher output (*), estimate from producer's recipe depths
            elif item.strip().endswith("*"):
                for other_phil in philosophers.values():
                    if clean in other_phil.produces:
                        # Estimate producer's unlock depth as max of their recipe ingredient depths + 1
                        producer_depths = []
                        for ri in other_phil.recipe:
                            ri_clean = ri.rstrip("*").strip().lower()
                            ri_id = name_to_id(ri_clean)
                            if ri_clean in concept_depths:
                                producer_depths.append(concept_depths[ri_clean])
                            elif ri_id in concept_depths:
                                producer_depths.append(concept_depths[ri_id])
                        if producer_depths:
                            # Producer unlocks at max(recipe depths), output is +1
                            depth = max(producer_depths) + 1
                        break

            ingredients.append(
                {
                    "name": clean,
                    "depth": depth,
                    "is_output": item.strip().endswith("*"),
                    "source": (
                        "content-map"
                        if depth is not None
                        else (
                            "philosopher-output"
                            if item.strip().endswith("*")
                            else "unknown"
                        )
                    ),
                }
            )

        known_depths = [i["depth"] for i in ingredients if i["depth"] is not None]
        unknown = [i for i in ingredients if i["depth"] is None]

        issues = []

        if len(known_depths) >= 2:
            min_d = min(known_depths)
            max_d = max(known_depths)
            spread = max_d - min_d

            if spread > max_spread:
                # Find the bottleneck ingredient(s) — ones at max depth
                bottlenecks = [
                    i["name"]
                    for i in ingredients
                    if i["depth"] is not None and i["depth"] == max_d
                ]
                trivial = [
                    i["name"]
                    for i in ingredients
                    if i["depth"] is not None and i["depth"] <= min_d + 1
                ]
                issues.append(
                    f"Wide spread: depths span {min_d}–{max_d} (range {spread}). "
                    f"Bottleneck: {', '.join(bottlenecks)}. "
                    f"Trivially early: {', '.join(trivial)}"
                )

            # Check trivial ratio
            trivial_count = sum(1 for d in known_depths if d <= 2)
            if (
                len(known_depths) >= 3
                and trivial_count / len(known_depths) >= max_trivial_ratio
            ):
                issues.append(
                    f"High trivial ratio: {trivial_count}/{len(known_depths)} ingredients "
                    f"at depth <= 2"
                )

            # Check if single ingredient is doing all the gating
            if len(known_depths) >= 3 and max_d > 2:
                at_max = sum(1 for d in known_depths if d == max_d)
                at_low = sum(1 for d in known_depths if d < max_d - 1)
                if at_max == 1 and at_low >= 2:
                    gating_concept = [
                        i["name"]
                        for i in ingredients
                        if i["depth"] is not None and i["depth"] == max_d
                    ][0]
                    issues.append(
                        f"Single gatekeeper: '{gating_concept}' (depth {max_d}) "
                        f"while {at_low} others are <= depth {max_d - 2}"
                    )

        results.append(
            {
                "name": phil.name,
                "era": phil.era,
                "ingredients": ingredients,
                "known_depths": known_depths,
                "unknown_count": len(unknown),
                "issues": issues,
            }
        )

    return results


# ── Philosopher Depth Placement ───────────────────────────────────────


def check_philosopher_depth_placement(
    philosophers: dict[str, Philosopher],
    writings: dict[str, Writing],
    concept_depths: dict[str, int],
) -> list[dict]:
    """Check if each philosopher's pure-concept recipe ingredients align with their era.

    "Pure concepts" excludes:
    - Other philosopher tiles (e.g. "Marcus Aurelius")
    - Concepts produced by any philosopher (e.g. "Inner Citadel")
    - Writing tiles (e.g. "Meditations")
    - Concepts produced by any writing (e.g. "Eightfold Path")

    For each philosopher, keeps only the pure concept ingredients,
    looks up their BFS depths, and checks whether the philosopher's
    unlock point makes sense for their era.

    Era windows (max pure-concept depth expected):
      Ancient:       0-4
      Medieval:      0-6
      Modern:        0-8
      Contemporary:  0-∞  (no upper bound)

    Minimum pure-concept depth (ensures the philosopher isn't trivially early):
      Ancient:       1
      Medieval:      3
      Modern:        4
      Contemporary:  5
    """
    # Build exclusion sets
    philosopher_names = set(philosophers.keys())
    philosopher_outputs: set[str] = set()
    for phil in philosophers.values():
        for concept in phil.produces:
            philosopher_outputs.add(concept)

    writing_titles: set[str] = set()
    writing_outputs: set[str] = set()
    if writings:
        writing_titles = set(writings.keys())
        for w in writings.values():
            for concept in w.produces:
                writing_outputs.add(concept)

    excluded = (
        philosopher_names | philosopher_outputs | writing_titles | writing_outputs
    )

    # Era depth windows: (min_pure_depth, max_pure_depth)
    # 1-gen overlap between adjacent eras
    era_windows: dict[str, tuple[int, int]] = {
        "Ancient": (2, 4),
        "Medieval": (4, 6),
        "Modern": (6, 8),
        "Contemporary": (7, 999),
    }

    results = []

    for phil in sorted(philosophers.values(), key=lambda p: p.name):
        pure_ingredients: list[dict] = []
        excluded_ingredients: list[str] = []

        for item in phil.recipe:
            clean = item.rstrip("*").strip()
            if clean in excluded:
                excluded_ingredients.append(clean)
                continue

            # Look up depth
            clean_lower = clean.lower()
            clean_id = name_to_id(clean)
            depth = None
            if clean_lower in concept_depths:
                depth = concept_depths[clean_lower]
            elif clean_id in concept_depths:
                depth = concept_depths[clean_id]

            pure_ingredients.append(
                {
                    "name": clean,
                    "depth": depth,
                }
            )

        known_depths = [i["depth"] for i in pure_ingredients if i["depth"] is not None]
        unknown = [i for i in pure_ingredients if i["depth"] is None]
        max_depth = max(known_depths) if known_depths else None
        min_depth = min(known_depths) if known_depths else None

        issues: list[str] = []
        window = era_windows.get(phil.era)
        if window and max_depth is not None:
            if max_depth > window[1]:
                issues.append(
                    f"Too deep for {phil.era}: deepest pure concept at Gen {max_depth}, "
                    f"but {phil.era} window is Gen {window[0]}-{window[1]}"
                )
            if max_depth < window[0]:
                issues.append(
                    f"Too shallow for {phil.era}: deepest pure concept at Gen {max_depth}, "
                    f"but {phil.era} window is Gen {window[0]}-{window[1]}"
                )

        results.append(
            {
                "name": phil.name,
                "era": phil.era,
                "pure_ingredients": pure_ingredients,
                "excluded_ingredients": excluded_ingredients,
                "unknown_ingredients": [i["name"] for i in unknown],
                "known_depths": known_depths,
                "max_pure_depth": max_depth,
                "min_pure_depth": min_depth,
                "era_window": window,
                "issues": issues,
            }
        )

    return results


# ── Effective Recipe ──────────────────────────────────────────────────


def compute_effective_recipes(
    philosophers: dict[str, Philosopher],
    writings: dict[str, Writing] | None = None,
    min_philosopher_effective: int = 3,
    min_writing_effective: int = 2,
) -> list[dict]:
    """Compute the *effective recipe* for each philosopher and writing.

    The effective recipe is what remains after subtracting concepts that
    the player must have already acquired in order to unlock prerequisite
    philosophers.  If Philosopher B depends on Philosopher A's output,
    then every concept in A's recipe is already necessarily in the
    player's inventory when they unlock A.  Those concepts are
    "inherited" and don't represent new exploration work.

    We trace prerequisites transitively: if B depends on A which depends
    on root concepts, we collect all recipe ingredients from A (and
    recursively from A's prerequisites).

    For writings, the author name is always counted as inherited (it must
    be unlocked to produce the writing).

    Thresholds:
        min_philosopher_effective: flag philosophers with fewer new concepts (default 3)
        min_writing_effective: flag writings with fewer new concepts (default 2)

    Each result dict contains:
        name, era, type ("philosopher" | "writing"),
        recipe, inherited, effective, effective_size,
        prerequisite_chain, issues
    """
    if writings is None:
        writings = {}

    # Build concept -> producer lookup
    concept_to_producer: dict[str, str] = {}
    for phil in philosophers.values():
        for concept in phil.produces:
            concept_to_producer[concept] = phil.name

    def gather_inherited_concepts(
        phil_name: str, visited: set[str] | None = None
    ) -> set[str]:
        """Recursively collect all recipe concepts from prerequisite philosophers."""
        if visited is None:
            visited = set()
        if phil_name in visited:
            return set()
        visited.add(phil_name)

        phil = philosophers.get(phil_name)
        if not phil:
            return set()

        inherited = set()
        for dep_name in phil.depends_on_output_of:
            dep = philosophers.get(dep_name)
            if dep:
                # All of this prerequisite's recipe ingredients are inherited
                inherited.update(dep.recipe)
                # Also add concepts produced by this prerequisite (player has them)
                inherited.update(dep.produces)
                # And recurse: whatever THAT philosopher inherited, we inherit too
                inherited.update(gather_inherited_concepts(dep_name, visited))

        return inherited

    results: list[dict] = []

    # Philosophers
    for phil in sorted(philosophers.values(), key=lambda p: p.name):
        inherited = gather_inherited_concepts(phil.name)

        # Effective = recipe items NOT in the inherited set
        effective = []
        inherited_in_recipe = []
        for item in phil.recipe:
            clean = item.rstrip("*").strip()
            # Check if this concept (or the raw item) is inherited
            if clean in inherited or item in inherited:
                inherited_in_recipe.append(clean)
            else:
                effective.append(clean)

        issues = []
        if phil.depends_on_output_of and len(effective) < min_philosopher_effective:
            issues.append(
                f"Effective recipe has only {len(effective)} new concept(s) "
                f"beyond prerequisites (minimum {min_philosopher_effective}) — "
                f"may feel trivial after unlocking "
                f"{', '.join(phil.depends_on_output_of)}"
            )

        results.append(
            {
                "name": phil.name,
                "era": phil.era,
                "type": "philosopher",
                "recipe": phil.recipe,
                "inherited": inherited_in_recipe,
                "effective": effective,
                "effective_size": len(effective),
                "prerequisite_chain": phil.depends_on_output_of,
                "issues": issues,
            }
        )

    # Writings
    for w in sorted(writings.values(), key=lambda x: x.title):
        # Writings depend on their author (a philosopher).  Inheriting the
        # author's recipe concepts + outputs is the baseline.
        inherited = set()
        if w.author in philosophers:
            author = philosophers[w.author]
            inherited.update(author.recipe)
            inherited.update(author.produces)
            inherited.update(gather_inherited_concepts(w.author))

        # Also trace any other philosopher output dependencies
        for dep_name in w.depends_on_output_of:
            dep = philosophers.get(dep_name)
            if dep:
                inherited.update(dep.recipe)
                inherited.update(dep.produces)
                inherited.update(gather_inherited_concepts(dep_name))

        effective = []
        inherited_in_recipe = []
        for item in w.recipe:
            clean = item.rstrip("*").strip()
            # The author name itself is always in the recipe and always inherited
            if clean == w.author:
                inherited_in_recipe.append(clean)
            elif clean in inherited or item in inherited:
                inherited_in_recipe.append(clean)
            else:
                effective.append(clean)

        issues = []
        if len(effective) < min_writing_effective:
            issues.append(
                f"Effective recipe has only {len(effective)} new concept(s) "
                f"beyond what's needed for {w.author} (minimum {min_writing_effective}) — "
                f"may feel trivial"
            )

        results.append(
            {
                "name": w.title,
                "era": w.era,
                "type": "writing",
                "recipe": w.recipe,
                "inherited": inherited_in_recipe,
                "effective": effective,
                "effective_size": len(effective),
                "prerequisite_chain": [w.author] + w.depends_on_output_of,
                "issues": issues,
            }
        )

    return results


# ── Concept Coverage ─────────────────────────────────────────────────


def parse_branch_concepts(brainstorm_path: Path) -> dict[str, list[str]]:
    """Parse branch concept lists from the brainstorm.

    Returns a dict mapping branch name -> list of concept names.
    Also includes trunk concepts and cross-branch entries.
    """
    text = brainstorm_path.read_text(encoding="utf-8")
    lines = text.split("\n")

    branches: dict[str, list[str]] = {}
    current_branch = None

    # Known branch headings
    branch_headings = {
        "trunk": "Trunk",
        "epistemology": "Epistemology",
        "ethics": "Ethics",
        "metaphysics": "Metaphysics",
        "political philosophy": "Political Philosophy",
        "aesthetics": "Aesthetics",
        "philosophy of mind": "Philosophy of Mind",
        "philosophy of religion": "Philosophy of Religion",
    }

    for line in lines:
        stripped = line.strip()

        # Detect branch section headings
        if stripped.startswith("## "):
            heading = stripped[3:].strip()
            heading_lower = heading.lower()

            # Check if it matches a known branch
            matched = False
            for key, name in branch_headings.items():
                if heading_lower.startswith(key) or key in heading_lower:
                    current_branch = name
                    branches.setdefault(current_branch, [])
                    matched = True
                    break

            if not matched:
                # Non-branch heading (Philosophers, Writings, Ordering, etc.)
                current_branch = None
            continue

        # Parse trunk concepts (comma-separated on a line)
        if current_branch == "Trunk" and stripped and not stripped.startswith("#"):
            items = [c.strip() for c in stripped.split(",") if c.strip()]
            branches["Trunk"].extend(items)
            continue

        # Parse branch concepts (bullet list items)
        if current_branch and current_branch != "Trunk":
            m = re.match(r"^[-*]\s+(.+)$", stripped)
            if m:
                concept_text = m.group(1).strip()
                # Remove secondary branch annotations like "[also Ethics]"
                concept_text = re.sub(r"\s*\[.*?\]", "", concept_text).strip()
                if concept_text:
                    branches[current_branch].append(concept_text)

    return branches


def check_concept_coverage(
    philosophers: dict[str, Philosopher],
    writings: dict[str, Writing],
    brainstorm_path: Path,
    content_map_path: Path | None = None,
) -> dict:
    """Check that every recipe ingredient is defined somewhere.

    Builds a universe of known concepts from:
    1. Content Map trunk concepts (if available)
    2. Branch concept lists in the brainstorm
    3. Philosopher outputs (produces)
    4. Writing outputs (produces)
    5. Philosopher names (they are tiles too)
    6. Writing titles (they are tiles too)

    Then checks every recipe ingredient against this universe.
    Reports: undefined concepts, name mismatches, and orphan concepts.
    """
    # 1. Gather all defined concepts
    defined: dict[str, str] = {}  # concept -> source

    # Content Map trunk concepts
    if content_map_path and content_map_path.exists():
        _scripts_dir = str(Path(__file__).parent)
        if _scripts_dir not in sys.path:
            sys.path.insert(0, _scripts_dir)
        from analyzeTree import load_content_map

        graph = load_content_map(content_map_path)
        for tid, tile in graph.tiles.items():
            defined[tile.name] = "trunk"
    else:
        # Fall back to brainstorm trunk list
        pass

    # Branch concepts from brainstorm
    branches = parse_branch_concepts(brainstorm_path)
    for branch, concepts in branches.items():
        for concept in concepts:
            if concept not in defined:
                defined[concept] = f"branch:{branch}"

    # Philosopher names
    for name in philosophers:
        defined[name] = "philosopher"

    # Philosopher outputs
    for phil in philosophers.values():
        for concept in phil.produces:
            defined[concept] = f"output:{phil.name}"

    # Writing titles
    for title in writings:
        defined[title] = "writing"

    # Writing outputs
    for w in writings.values():
        for concept in w.produces:
            defined[concept] = f"output:{w.title}"

    # 2. Check every recipe ingredient
    undefined: list[dict] = []
    name_mismatches: list[dict] = []

    # Build a lowercase lookup for fuzzy matching
    lower_lookup: dict[str, str] = {}
    for name in defined:
        lower_lookup[name.lower()] = name

    def find_ingredient(ingredient: str) -> str | None:
        """Return the defined concept name if found, else None."""
        clean = ingredient.rstrip("*").strip()
        # Exact match
        if clean in defined:
            return clean
        # Case-insensitive match
        if clean.lower() in lower_lookup:
            return lower_lookup[clean.lower()]
        return None

    def find_near_match(ingredient: str) -> list[str]:
        """Find concepts that partially match the ingredient name."""
        clean = ingredient.rstrip("*").strip().lower()
        matches = []
        for name in defined:
            name_lower = name.lower()
            # Check if one is a substring of the other
            if clean in name_lower or name_lower in clean:
                matches.append(name)
            # Check if they share significant words
            clean_words = set(clean.split())
            name_words = set(name_lower.split())
            shared = clean_words & name_words
            if shared and len(shared) >= max(
                1, min(len(clean_words), len(name_words)) - 1
            ):
                if name not in matches:
                    matches.append(name)
        return matches[:5]  # limit suggestions

    # Check philosopher recipes
    for phil in philosophers.values():
        for ingredient in phil.recipe:
            clean = ingredient.rstrip("*").strip()
            match = find_ingredient(ingredient)
            if match is None:
                near = find_near_match(ingredient)
                undefined.append(
                    {
                        "ingredient": clean,
                        "used_by": phil.name,
                        "used_in": "philosopher recipe",
                        "near_matches": near,
                    }
                )
            elif match != clean:
                name_mismatches.append(
                    {
                        "recipe_name": clean,
                        "defined_name": match,
                        "used_by": phil.name,
                    }
                )

    # Check writing recipes (skip author name — that's a philosopher)
    for w in writings.values():
        for ingredient in w.recipe:
            clean = ingredient.rstrip("*").strip()
            # Skip the author (it's a philosopher name, already a tile)
            if clean == w.author:
                continue
            match = find_ingredient(ingredient)
            if match is None:
                near = find_near_match(ingredient)
                undefined.append(
                    {
                        "ingredient": clean,
                        "used_by": w.title,
                        "used_in": "writing recipe",
                        "near_matches": near,
                    }
                )
            elif match != clean:
                name_mismatches.append(
                    {
                        "recipe_name": clean,
                        "defined_name": match,
                        "used_by": w.title,
                    }
                )

    # 3. Find orphan concepts (defined but never used in any recipe)
    used_concepts: set[str] = set()
    for phil in philosophers.values():
        for item in phil.recipe:
            used_concepts.add(item.rstrip("*").strip())
    for w in writings.values():
        for item in w.recipe:
            used_concepts.add(item.rstrip("*").strip())
    # Also count outputs that are used somewhere
    for phil in philosophers.values():
        for item in phil.produces:
            used_concepts.add(item)
    for w in writings.values():
        for item in w.produces:
            used_concepts.add(item)

    return {
        "defined_count": len(defined),
        "undefined": undefined,
        "name_mismatches": name_mismatches,
        "branches": {k: len(v) for k, v in branches.items()},
    }


# ── Output ───────────────────────────────────────────────────────────


def print_report(
    philosophers: dict[str, Philosopher],
    ordering: list[tuple[str, str]],
    concept_depth_ordering: list[tuple[str, str]] | None = None,
    *,
    opts: ReportOptions | None = None,
    writings: dict[str, Writing] | None = None,
):
    """Print the full ordering analysis report to stdout.

    Includes dependency chains, era distribution, ordering constraint checks,
    balance analysis, prerequisite traces, depth placement, and writing summaries.
    """
    if concept_depth_ordering is None:
        concept_depth_ordering = []
    if writings is None:
        writings = {}
    if opts is None:
        opts = ReportOptions()

    verbose = opts.verbose
    prereqs = opts.prereqs
    balance = opts.balance
    effective = opts.effective
    check_concepts = opts.check_concepts
    depth_check = opts.depth_check
    content_map_path = opts.content_map_path
    brainstorm_path = opts.brainstorm_path

    w = 70

    # Shared era constants
    era_order: dict[str, int] = {
        "Ancient": 0,
        "Medieval": 1,
        "Modern": 2,
        "Contemporary": 3,
    }
    era_names: list[str] = list(era_order.keys())
    print()
    print("=" * w)
    print("  PHILOSOPHER ORDERING ANALYSIS")
    print("=" * w)
    print()

    # Build graph
    graph = build_dependency_graph(philosophers, ordering)

    # Check for cycles
    cycles = detect_cycles(graph)
    if cycles:
        print(f"  [XX] CONTRADICTIONS FOUND: {len(cycles)} cycle(s)")
        for i, cycle in enumerate(cycles):
            print(f"       Cycle {i+1}: {' -> '.join(cycle)}")
        print()
    else:
        print("  [OK] No contradictions found")
        print()

    # Compute effective depths for sorting (concept-depth-based unlock gen)
    eff_depths: dict[str, int] = {}
    if content_map_path:
        try:
            concept_depths = get_concept_depths(content_map_path)
            dp_results = check_philosopher_depth_placement(
                philosophers, writings or {}, concept_depths
            )
            depth_by_name = {r["name"]: r for r in dp_results}

            def _get_effective_depth(
                name: str, visited: set | None = None
            ) -> int | None:
                """Get effective unlock depth accounting for prerequisites."""
                if visited is None:
                    visited = set()
                if name in visited:
                    return None
                visited.add(name)
                r = depth_by_name.get(name)
                if r is None or r["max_pure_depth"] is None:
                    return None
                depth = r["max_pure_depth"]
                phil = philosophers.get(name)
                if phil:
                    for dep_name in phil.depends_on_output_of:
                        dep_depth = _get_effective_depth(dep_name, visited.copy())
                        if dep_depth is not None:
                            depth = max(depth, dep_depth + 1)
                return depth

            for r in dp_results:
                ed = _get_effective_depth(r["name"])
                if ed is not None:
                    eff_depths[r["name"]] = ed
        except (FileNotFoundError, ValueError, KeyError) as exc:
            print(f"  [ii] Could not compute effective depths: {exc}", file=sys.stderr)
            # Fall back to era-based sorting

    def sort_key(name: str) -> tuple:
        """Sort by effective depth, then by era, then alphabetically."""
        phil = philosophers[name]
        depth = eff_depths.get(name, 999)
        era = era_order.get(phil.era, 9)
        return (depth, era, name)

    # Topological sort
    topo = topological_sort(graph, sort_key=sort_key)
    if topo:
        print("  UNLOCK ORDER (by dependency, then effective depth)")
        print("  " + "-" * (w - 2))
        for i, name in enumerate(topo, 1):
            phil = philosophers[name]
            deps = phil.depends_on_output_of
            dep_str = f" (after {', '.join(deps)})" if deps else ""
            era_tag = f"[{phil.era[:3].upper()}]"
            depth = eff_depths.get(name)
            depth_str = f" ~Gen {depth}" if depth is not None else ""
            print(f"  {i:3d}. {era_tag} {name}{depth_str}{dep_str}")
        print()

        # Check for era violations using concept depths (not topological position)
        # A violation = later-era philosopher discoverable at a LOWER concept depth
        # than an earlier-era philosopher. We need depth_check results for this.
        if depth_check and content_map_path:
            # depth_results are computed later; defer era ordering to depth section
            pass
        else:
            # Fallback: topological-position-based check (less accurate)
            violations = []
            for i, name_a in enumerate(topo):
                for name_b in topo[i + 1 :]:
                    era_a = era_order.get(philosophers[name_a].era, -1)
                    era_b = era_order.get(philosophers[name_b].era, -1)
                    if era_a > era_b:
                        violations.append((name_a, name_b))

            if violations:
                print(
                    f"  [!!] ERA ORDERING WARNINGS (topological, not depth-based): {len(violations)} potential issue(s)"
                )
                print("  " + "-" * (w - 2))
                print(
                    "       Note: Run with --depth-check for accurate depth-based analysis"
                )
                for a, b in violations[:10]:
                    era_a = philosophers[a].era
                    era_b = philosophers[b].era
                    print(f"  {a} ({era_a}) unlocks before {b} ({era_b})")
                if len(violations) > 10:
                    print(f"  ... and {len(violations) - 10} more")
                print()

    # Dependency chains
    print("  DEPENDENCY CHAINS")
    print("  " + "-" * (w - 2))

    # Find chains: follow depends_on_output_of backwards to roots
    def get_chain(name: str, visited: set | None = None) -> list[str]:
        if visited is None:
            visited = set()
        if name in visited:
            return [name + " (CYCLE)"]
        visited.add(name)
        phil = philosophers.get(name)
        if not phil or not phil.depends_on_output_of:
            return [name]
        chains = []
        for dep in phil.depends_on_output_of:
            for ancestor in get_chain(dep, visited.copy()):
                chains.append(ancestor)
        chains.append(name)
        return chains

    # Find root philosophers (no dependencies)
    roots = [
        name for name, phil in philosophers.items() if not phil.depends_on_output_of
    ]
    # Trace chains from roots
    visited_chains: set[str] = set()
    for root in sorted(roots):
        chain = [root]
        current = root
        while True:
            # Find who depends on current
            followers = [
                name
                for name, phil in philosophers.items()
                if current in phil.depends_on_output_of and name not in visited_chains
            ]
            if not followers:
                break
            # Pick the longest chain follower
            current = sorted(followers)[0]
            chain.append(current)
            visited_chains.add(current)

        if len(chain) > 1:
            print(f"  {' -> '.join(chain)}")
        else:
            print(f"  {chain[0]} (independent)")
    print()

    # Check ordering constraints
    if ordering or concept_depth_ordering:
        print("  ORDERING CONSTRAINT CHECK")
        print("  " + "-" * (w - 2))

        # Check explicit constraints (must be guaranteed by output deps)
        explicit_warnings = check_implicit_ordering(philosophers, ordering)
        if not explicit_warnings:
            print(
                f"  [OK] All {len(ordering)} explicit constraints (<) satisfied by recipe dependencies"
            )
        else:
            for w_msg in explicit_warnings:
                print(w_msg)

        # Report concept-depth constraints (will be verified when tree is built)
        if concept_depth_ordering:
            verified = 0
            pending = []
            # Build output dependency graph once for all constraint checks
            output_graph: dict[str, set[str]] = defaultdict(set)
            for phil in philosophers.values():
                output_graph[phil.name]
                for dep in phil.depends_on_output_of:
                    output_graph[dep].add(phil.name)
            for before, after in concept_depth_ordering:
                if before not in philosophers or after not in philosophers:
                    pending.append(f"  {before} ~ {after}: unknown philosopher")
                    continue
                # Check if output deps happen to satisfy this anyway
                visited = set()
                queue = deque([before])
                reachable = False
                while queue:
                    current = queue.popleft()
                    if current == after:
                        reachable = True
                        break
                    if current in visited:
                        continue
                    visited.add(current)
                    queue.extend(output_graph.get(current, set()))
                if reachable:
                    verified += 1
                else:
                    pending.append(f"    {before} ~ {after}")
            if pending:
                print(
                    f"  [..] {len(concept_depth_ordering)} concept-depth constraints (~): "
                    f"{verified} already satisfied, {len(pending)} pending tree completion:"
                )
                for p in pending:
                    print(p)
            else:
                print(
                    f"  [OK] All {len(concept_depth_ordering)} concept-depth constraints (~) "
                    "happen to be satisfied by output deps"
                )

        print()

    # Concept-to-producer mapping
    if verbose:
        print("  CONCEPT PRODUCTION MAP")
        print("  " + "-" * (w - 2))
        concept_to_producer = {}
        for phil in philosophers.values():
            for concept in phil.produces:
                concept_to_producer[concept] = phil.name

        for concept in sorted(concept_to_producer.keys()):
            producer = concept_to_producer[concept]
            # Who consumes this concept?
            consumers = [
                p.name
                for p in philosophers.values()
                if concept in p.recipe and p.name != producer
            ]
            consumer_str = (
                f" -> used by {', '.join(consumers)}" if consumers else " (unused)"
            )
            print(f"  {concept} (from {producer}){consumer_str}")
        print()

    # Prerequisite trace
    if prereqs:
        print("  PREREQUISITE TRACE")
        print("  " + "-" * (w - 2))
        print("  Shows ALL concepts/philosophers that must exist before each")
        print("  philosopher can unlock, tracing through dependency chains.")
        print()

        # Build concept -> producer lookup
        concept_to_producer = {}
        for phil in philosophers.values():
            for concept in phil.produces:
                concept_to_producer[concept] = phil.name

        def trace_prereqs(
            p_name: str,
            visited_phils: set[str],
            all_concepts: list[str],
            all_philosophers: list[str],
        ) -> None:
            """Recursively gather all prerequisite concepts and philosophers."""
            if p_name in visited_phils:
                return
            visited_phils.add(p_name)
            p = philosophers[p_name]
            for concept in p.recipe:
                if concept not in all_concepts:
                    all_concepts.append(concept)
                # If this concept is produced by another philosopher, trace that too
                if concept in concept_to_producer:
                    producer = concept_to_producer[concept]
                    if producer != p_name and producer not in all_philosophers:
                        all_philosophers.append(producer)
                        trace_prereqs(
                            producer, visited_phils, all_concepts, all_philosophers
                        )

        # For each philosopher in topological order, show prerequisites
        if topo:
            for name in topo:
                phil = philosophers[name]
                # Gather all prerequisite concepts recursively
                all_concepts: list[str] = []  # own recipe
                all_philosophers: list[str] = []  # philosophers that must unlock first
                visited_phils: set[str] = set()

                trace_prereqs(name, visited_phils, all_concepts, all_philosophers)

                # Separate own recipe from inherited requirements
                own_recipe = phil.recipe
                inherited_concepts = [c for c in all_concepts if c not in own_recipe]
                prior_phils = [p for p in all_philosophers]

                era_tag = f"[{phil.era[:3].upper()}]"
                print(f"  {era_tag} {name}")
                print(f"    Recipe: {', '.join(own_recipe)}")

                if prior_phils:
                    print(f"    Requires philosophers: {', '.join(prior_phils)}")
                    print(f"    Inherited concepts: {', '.join(inherited_concepts)}")
                    total = len(set(all_concepts))
                    print(f"    Total unique concepts needed: {total}")
                else:
                    print("    No philosopher prerequisites (foundational)")
                print()

    # Stats
    total = len(philosophers)
    with_deps = sum(1 for p in philosophers.values() if p.depends_on_output_of)
    produces_used = sum(
        1
        for p in philosophers.values()
        if any(
            c in q.recipe
            for c in p.produces
            for q in philosophers.values()
            if q.name != p.name
        )
    )

    # ── Recipe Balance ───────────────────────────────────────────
    if balance:
        print()
        print("  RECIPE BALANCE ANALYSIS")
        print("  " + "-" * (w - 2))

        try:
            concept_depths = get_concept_depths(content_map_path)
            balance_results = check_recipe_balance(philosophers, concept_depths)

            flagged = [r for r in balance_results if r["issues"]]
            balanced = [
                r for r in balance_results if not r["issues"] and r["known_depths"]
            ]
            unknown = [r for r in balance_results if not r["known_depths"]]

            if flagged:
                print(f"  [!!] {len(flagged)} philosopher(s) with imbalanced recipes:")
                print()
                for r in flagged:
                    depths_str = ", ".join(
                        (
                            f"{i['name']}={i['depth']}"
                            if i["depth"] is not None
                            else f"{i['name']}=?"
                        )
                        for i in r["ingredients"]
                    )
                    print(f"    {r['name']} ({r['era']}):")
                    print(f"      Ingredients: {depths_str}")
                    for issue in r["issues"]:
                        print(f"      [!] {issue}")
                    print()

            if balanced:
                if verbose:
                    print(
                        f"  [OK] {len(balanced)} philosopher(s) with balanced recipes:"
                    )
                    for r in balanced:
                        depths_str = ", ".join(
                            (
                                f"{i['name']}={i['depth']}"
                                if i["depth"] is not None
                                else f"{i['name']}=?"
                            )
                            for i in r["ingredients"]
                        )
                        spread = (
                            max(r["known_depths"]) - min(r["known_depths"])
                            if r["known_depths"]
                            else 0
                        )
                        print(f"    {r['name']}: {depths_str} (spread: {spread})")
                else:
                    print(
                        f"  [OK] {len(balanced)} philosopher(s) with balanced recipes"
                    )

            if unknown:
                print(
                    f"  [..] {len(unknown)} philosopher(s) with no known ingredient depths "
                    f"(all recipe concepts missing from Content Map)"
                )
                if verbose:
                    for r in unknown:
                        names = [i["name"] for i in r["ingredients"]]
                        print(f"    {r['name']}: {', '.join(names)}")
            print()

        except (FileNotFoundError, ImportError, ValueError, KeyError) as e:
            print(f"  [!!] Could not run balance check: {e}")
            print("       Make sure the Content Map exists and is valid.")
            print()

    # ── Depth Placement ──────────────────────────────────────────
    if depth_check:
        print()
        print("  PHILOSOPHER DEPTH PLACEMENT")
        print("  " + "-" * (w - 2))
        print("  Pure-concept depth = depth of recipe ingredients that are NOT")
        print("  philosopher tiles, philosopher outputs, or writing tiles.")
        print()

        try:
            concept_depths = get_concept_depths(content_map_path)
            dp_results = check_philosopher_depth_placement(
                philosophers, writings or {}, concept_depths
            )

            flagged = [r for r in dp_results if r["issues"]]
            ok_list = [r for r in dp_results if not r["issues"] and r["known_depths"]]
            unknown_list = [r for r in dp_results if not r["known_depths"]]

            # Group by era for display
            # (era_names defined at the top of print_report)

            if flagged:
                print(
                    f"  [!!] {len(flagged)} philosopher(s) outside their era's depth window:"
                )
                print()
                for r in flagged:
                    depths_str = ", ".join(
                        (
                            f"{i['name']}={i['depth']}"
                            if i["depth"] is not None
                            else f"{i['name']}=?"
                        )
                        for i in r["pure_ingredients"]
                    )
                    excluded_str = (
                        ", ".join(r["excluded_ingredients"])
                        if r["excluded_ingredients"]
                        else "none"
                    )
                    window = r["era_window"]
                    window_str = (
                        f"Gen {window[0]}-{window[1]}"
                        if window and window[1] < 999
                        else f"Gen {window[0]}+"
                    )
                    print(f"    {r['name']} ({r['era']}, window {window_str}):")
                    print(f"      Pure concepts: {depths_str}")
                    print(f"      Excluded: {excluded_str}")
                    print(f"      Max pure depth: Gen {r['max_pure_depth']}")
                    for issue in r["issues"]:
                        print(f"      [!] {issue}")
                    print()

            if ok_list:
                if verbose:
                    print(
                        f"  [OK] {len(ok_list)} philosopher(s) within their era window:"
                    )
                    for era in era_names:
                        era_phils = [r for r in ok_list if r["era"] == era]
                        if not era_phils:
                            continue
                        print(f"    {era}:")
                        for r in era_phils:
                            depths_str = ", ".join(
                                f"{i['name']}={i['depth']}"
                                for i in r["pure_ingredients"]
                                if i["depth"] is not None
                            )
                            window = r["era_window"]
                            print(
                                f"      {r['name']}: max depth {r['max_pure_depth']} ({depths_str})"
                            )
                    print()
                else:
                    print(
                        f"  [OK] {len(ok_list)} philosopher(s) within their era window"
                    )
                    print()

            if unknown_list:
                print(
                    f"  [..] {len(unknown_list)} philosopher(s) with no known pure-concept depths "
                    f"(all recipe items are philosopher/writing tiles, or not in Content Map)"
                )
                if verbose:
                    for r in unknown_list:
                        excluded_str = (
                            ", ".join(r["excluded_ingredients"])
                            if r["excluded_ingredients"]
                            else "none"
                        )
                        unknown_str = (
                            ", ".join(r["unknown_ingredients"])
                            if r["unknown_ingredients"]
                            else "none"
                        )
                        print(
                            f"    {r['name']}: excluded={excluded_str}, unknown={unknown_str}"
                        )
                print()

            # Summary table by era
            print("  ERA DEPTH SUMMARY")
            print("  " + "-" * (w - 2))
            print(
                f"  {'Era':<16} {'Count':<7} {'Window':<12} {'Actual Range':<18} {'Issues'}"
            )
            for era in era_names:
                era_phils = [r for r in dp_results if r["era"] == era]
                if not era_phils:
                    continue
                era_known = [r for r in era_phils if r["max_pure_depth"] is not None]
                window = era_phils[0]["era_window"]
                window_str = (
                    f"Gen {window[0]}-{window[1]}"
                    if window and window[1] < 999
                    else f"Gen {window[0]}+"
                )
                if era_known:
                    actual_min = min(r["max_pure_depth"] for r in era_known)
                    actual_max = max(r["max_pure_depth"] for r in era_known)
                    actual_str = f"Gen {actual_min}-{actual_max}"
                else:
                    actual_str = "no data"
                era_issues = sum(1 for r in era_phils if r["issues"])
                issue_str = f"{era_issues} flagged" if era_issues else "OK"
                print(
                    f"  {era:<16} {len(era_phils):<7} {window_str:<12} {actual_str:<18} {issue_str}"
                )
            print()

            # ── Depth-Based Era Ordering ─────────────────────────────
            # Check whether any later-era philosopher is discoverable at a
            # lower concept depth than an earlier-era philosopher.
            #
            # Reuse effective depths computed earlier for the unlock order.

            # Use eff_depths computed at the top of the report
            effective_depths = eff_depths

            depth_violations = []
            adjacent_overlaps = []
            for name_a, depth_a in effective_depths.items():
                for name_b, depth_b in effective_depths.items():
                    if name_a == name_b:
                        continue
                    era_a = era_order.get(philosophers[name_a].era, -1)
                    era_b = era_order.get(philosophers[name_b].era, -1)
                    # a is a later era but discoverable at strictly lower depth than b
                    if era_a > era_b and depth_a < depth_b:
                        era_gap = era_a - era_b  # 1 = adjacent, 2+ = non-adjacent
                        entry = {
                            "later": name_a,
                            "later_era": philosophers[name_a].era,
                            "later_depth": depth_a,
                            "earlier": name_b,
                            "earlier_era": philosophers[name_b].era,
                            "earlier_depth": depth_b,
                            "era_gap": era_gap,
                        }
                        if era_gap == 1:
                            adjacent_overlaps.append(entry)
                        else:
                            depth_violations.append(entry)

            if depth_violations:
                depth_violations.sort(
                    key=lambda v: (-v["era_gap"], v["later_depth"], v["later"])
                )
                print(
                    f"  [XX] ERA ORDERING: {len(depth_violations)} non-adjacent violation(s)"
                )
                print("  " + "-" * (w - 2))
                print(
                    f"  Later-era philosopher discoverable before MUCH earlier-era (2+ era gap):"
                )
                shown = 0
                for v in depth_violations:
                    if shown >= 30:
                        print(f"  ... and {len(depth_violations) - 30} more")
                        break
                    print(
                        f"    {v['later']} ({v['later_era']}, eff. Gen {v['later_depth']}) "
                        f"before {v['earlier']} ({v['earlier_era']}, eff. Gen {v['earlier_depth']})"
                    )
                    shown += 1
                print()
            else:
                print("  [OK] Era ordering: no non-adjacent era violations")

            if adjacent_overlaps:
                print(
                    f"  [ii] Adjacent era overlaps: {len(adjacent_overlaps)} (expected from 1-gen overlap windows)"
                )
                # Group by the later-era philosopher to keep output concise
                later_names = sorted(set(v["later"] for v in adjacent_overlaps))
                for name in later_names[:10]:
                    overlaps = [v for v in adjacent_overlaps if v["later"] == name]
                    earlier_names = ", ".join(v["earlier"] for v in overlaps[:3])
                    era = overlaps[0]["later_era"]
                    depth = overlaps[0]["later_depth"]
                    extra = f" +{len(overlaps)-3} more" if len(overlaps) > 3 else ""
                    print(
                        f"    {name} ({era}, Gen {depth}) before: {earlier_names}{extra}"
                    )
                if len(later_names) > 10:
                    print(f"    ... and {len(later_names) - 10} more philosophers")
                print()
            elif not depth_violations:
                print()

            # ── Concept Depth Targets ────────────────────────────────
            # For each undefined concept in philosopher recipes, derive the
            # required depth range based on which philosophers need it.
            concept_targets: dict[str, dict] = {}  # concept -> info

            # Build branch lookup from brainstorm
            branch_lookup: dict[str, str] = {}  # concept -> branch
            if brainstorm_path and brainstorm_path.exists():
                branches = parse_branch_concepts(brainstorm_path)
                for branch, concepts in branches.items():
                    for concept in concepts:
                        branch_lookup[concept] = branch

            for r in dp_results:
                window = r["era_window"]
                if not window:
                    continue
                for ing in r["pure_ingredients"]:
                    if ing["depth"] is not None:
                        continue  # already has a known depth
                    cname = ing["name"]
                    if cname not in concept_targets:
                        # Look up branch
                        branch = branch_lookup.get(cname, "Unknown")
                        concept_targets[cname] = {
                            "name": cname,
                            "branch": branch,
                            "needed_by": [],
                            "min_depth": 0,
                            "max_depth": 999,
                        }
                    ct = concept_targets[cname]
                    ct["needed_by"].append({"philosopher": r["name"], "era": r["era"]})
                    # The concept must be at most era_upper (so it doesn't push
                    # the philosopher beyond their window). Take the strictest
                    # (lowest) upper bound across all philosophers needing it.
                    ct["max_depth"] = min(ct["max_depth"], window[1])
                    # The concept should be at least era_lower (so it's not
                    # trivially early). Take the highest lower bound.
                    ct["min_depth"] = max(ct["min_depth"], window[0])

            if concept_targets:
                # Group by branch
                by_branch: dict[str, list[dict]] = defaultdict(list)
                for ct in concept_targets.values():
                    by_branch[ct["branch"]].append(ct)

                print("  CONCEPT DEPTH TARGETS")
                print("  " + "-" * (w - 2))
                print("  Undefined recipe concepts and their required depth ranges,")
                print("  derived from philosopher era windows.")
                print()

                # Sort branches: known branches first, Unknown last
                known_branches = [
                    "Trunk",
                    "Epistemology",
                    "Ethics",
                    "Metaphysics",
                    "Political Philosophy",
                    "Aesthetics",
                    "Philosophy of Mind",
                    "Philosophy of Religion",
                ]
                branch_order = [b for b in known_branches if b in by_branch]
                branch_order += [
                    b for b in sorted(by_branch) if b not in known_branches
                ]

                for branch in branch_order:
                    concepts = sorted(by_branch[branch], key=lambda c: c["min_depth"])
                    print(f"  {branch} ({len(concepts)} concepts):")
                    for ct in concepts:
                        max_str = str(ct["max_depth"]) if ct["max_depth"] < 999 else "+"
                        phil_names = [
                            f"{nb['philosopher']} ({nb['era'][:3]})"
                            for nb in ct["needed_by"]
                        ]
                        if len(phil_names) <= 3:
                            needed_str = ", ".join(phil_names)
                        else:
                            needed_str = (
                                ", ".join(phil_names[:2])
                                + f", +{len(phil_names)-2} more"
                            )
                        print(
                            f"    {ct['name']:<28} Gen {ct['min_depth']}-{max_str:<4}  <- {needed_str}"
                        )
                    print()

                # Summary stats
                total_undefined = len(concept_targets)
                branches_affected = len(by_branch)
                feasible = sum(
                    1
                    for ct in concept_targets.values()
                    if ct["min_depth"] <= ct["max_depth"]
                )
                infeasible = total_undefined - feasible
                print(
                    f"  Total undefined concepts: {total_undefined} across {branches_affected} branches"
                )
                if infeasible:
                    print(
                        f"  [!!] {infeasible} concept(s) with impossible depth range (min > max):"
                    )
                    for ct in concept_targets.values():
                        if ct["min_depth"] > ct["max_depth"]:
                            phil_names = [nb["philosopher"] for nb in ct["needed_by"]]
                            print(
                                f"    {ct['name']}: needs Gen {ct['min_depth']}-{ct['max_depth']} "
                                f"(required by {', '.join(phil_names)})"
                            )
                else:
                    print(f"  [OK] All concepts have feasible depth ranges")
                print()

        except (FileNotFoundError, ImportError, ValueError, KeyError) as e:
            print(f"  [!!] Could not run depth placement check: {e}")
            print("       Make sure the Content Map exists and is valid.")
            print()

    # ── Effective Recipes ─────────────────────────────────────────
    if effective:
        print()
        print("  EFFECTIVE RECIPE ANALYSIS")
        print("  " + "-" * (w - 2))
        print("  Effective recipe = recipe ingredients that are NOT already")
        print("  required to unlock prerequisite philosophers.")
        print()

        eff_results = compute_effective_recipes(philosophers, writings)

        phil_results = [r for r in eff_results if r["type"] == "philosopher"]
        writing_results = [r for r in eff_results if r["type"] == "writing"]

        flagged = [r for r in phil_results if r["issues"]]
        ok = [r for r in phil_results if not r["issues"]]

        if flagged:
            print(f"  [!!] {len(flagged)} philosopher(s) with short effective recipes:")
            print()
            for r in flagged:
                inherited_str = (
                    f" (inherited: {', '.join(r['inherited'])})"
                    if r["inherited"]
                    else ""
                )
                print(f"    {r['name']} ({r['era']}):")
                print(f"      Full recipe:      {', '.join(r['recipe'])}")
                print(
                    f"      Prerequisites:    {', '.join(r['prerequisite_chain']) or 'none'}"
                )
                print(f"      Inherited:        {', '.join(r['inherited']) or 'none'}")
                print(
                    f"      Effective recipe: {', '.join(r['effective']) or '(empty!)'}"
                )
                print(f"      Effective size:   {r['effective_size']}")
                for issue in r["issues"]:
                    print(f"      [!] {issue}")
                print()

        if ok:
            if verbose:
                print(
                    f"  [OK] {len(ok)} philosopher(s) with sufficient effective recipes:"
                )
                for r in ok:
                    eff_str = (
                        ", ".join(r["effective"])
                        if r["effective"]
                        else "(all inherited)"
                    )
                    print(
                        f"    {r['name']}: effective={eff_str} ({r['effective_size']} new)"
                    )
                print()
            else:
                print(
                    f"  [OK] {len(ok)} philosopher(s) with sufficient effective recipes"
                )
                print()

        # Writing effective recipes
        flagged_w = [r for r in writing_results if r["issues"]]
        ok_w = [r for r in writing_results if not r["issues"]]

        if flagged_w:
            print(f"  [!!] {len(flagged_w)} writing(s) with short effective recipes:")
            print()
            for r in flagged_w:
                print(f"    {r['name']} ({r['era']}):")
                print(f"      Full recipe:      {', '.join(r['recipe'])}")
                print(f"      Prerequisites:    {', '.join(r['prerequisite_chain'])}")
                print(f"      Inherited:        {', '.join(r['inherited']) or 'none'}")
                print(
                    f"      Effective recipe: {', '.join(r['effective']) or '(empty!)'}"
                )
                print(f"      Effective size:   {r['effective_size']}")
                for issue in r["issues"]:
                    print(f"      [!] {issue}")
                print()

        if ok_w:
            if verbose:
                print(
                    f"  [OK] {len(ok_w)} writing(s) with sufficient effective recipes:"
                )
                for r in ok_w:
                    eff_str = (
                        ", ".join(r["effective"])
                        if r["effective"]
                        else "(all inherited)"
                    )
                    print(
                        f"    {r['name']}: effective={eff_str} ({r['effective_size']} new)"
                    )
                print()
            else:
                print(
                    f"  [OK] {len(ok_w)} writing(s) with sufficient effective recipes"
                )
                print()

        # Summary stats
        all_sizes = [r["effective_size"] for r in eff_results]
        phil_sizes = [r["effective_size"] for r in phil_results]
        if phil_sizes:
            print(
                f"  Philosopher effective-recipe sizes: "
                f"min={min(phil_sizes)}, max={max(phil_sizes)}, "
                f"mean={statistics.mean(phil_sizes):.1f}, "
                f"median={statistics.median(phil_sizes):.0f}"
            )
        writing_sizes = [r["effective_size"] for r in writing_results]
        if writing_sizes:
            print(
                f"  Writing effective-recipe sizes:     "
                f"min={min(writing_sizes)}, max={max(writing_sizes)}, "
                f"mean={statistics.mean(writing_sizes):.1f}, "
                f"median={statistics.median(writing_sizes):.0f}"
            )
        print()

    # Writings analysis
    if writings:
        print("  WRITINGS")
        print("  " + "-" * (w - 2))
        writing_concepts = sum(len(w_.produces) for w_ in writings.values())
        eras = defaultdict(int)
        for w_ in writings.values():
            eras[w_.era] += 1

        # Check that all authors exist as philosophers
        missing_authors = []
        for w_ in writings.values():
            if w_.author not in philosophers:
                missing_authors.append(f"{w_.title} by {w_.author}")

        print(f"  Total writings: {len(writings)}")
        for era in ["Ancient", "Medieval", "Modern", "Contemporary"]:
            if era in eras:
                print(f"    {era}: {eras[era]}")
        print(f"  Concepts produced by writings: {writing_concepts}")
        if missing_authors:
            print(f"  [!!] Missing authors: {', '.join(missing_authors)}")
        else:
            print("  [OK] All writing authors are known philosophers")

        # Check for duplicate concept production (same concept from philosopher AND writing)
        phil_concepts = {}
        for p in philosophers.values():
            for c in p.produces:
                phil_concepts[c] = p.name
        duplicates = []
        for w_ in writings.values():
            for c in w_.produces:
                if c in phil_concepts:
                    duplicates.append(
                        f"  '{c}' produced by both {phil_concepts[c]} and {w_.title}"
                    )
        if duplicates:
            print("  [!!] Duplicate concept production:")
            for d in duplicates:
                print(d)

        if verbose:
            print()
            for w_ in sorted(writings.values(), key=lambda x: x.title):
                author_marker = "[OK]" if w_.author in philosophers else "[!!]"
                print(f"  {author_marker} {w_.title} (by {w_.author})")
                print(f"       Recipe: {', '.join(w_.recipe)}")
                print(f"       Produces: {', '.join(w_.produces)}")
        print()

    # ── Concept Coverage ──────────────────────────────────────────
    if check_concepts and brainstorm_path:
        print()
        print("  CONCEPT COVERAGE CHECK")
        print("  " + "-" * (w - 2))

        try:
            coverage = check_concept_coverage(
                philosophers, writings, brainstorm_path, content_map_path
            )

            print(f"  Known concepts in universe: {coverage['defined_count']}")
            for branch, count in sorted(coverage["branches"].items()):
                print(f"    {branch}: {count}")
            print()

            if coverage["undefined"]:
                print(
                    f"  [XX] {len(coverage['undefined'])} UNDEFINED recipe ingredient(s):"
                )
                for item in coverage["undefined"]:
                    near_str = ""
                    if item["near_matches"]:
                        near_str = f"  (similar: {', '.join(item['near_matches'])})"
                    print(
                        f"    '{item['ingredient']}' in {item['used_by']} "
                        f"({item['used_in']}){near_str}"
                    )
                print()
            else:
                print("  [OK] All recipe ingredients are defined")
                print()

            if coverage["name_mismatches"]:
                print(
                    f"  [!!] {len(coverage['name_mismatches'])} name mismatch(es) (recipe vs defined):"
                )
                for item in coverage["name_mismatches"]:
                    print(
                        f"    '{item['recipe_name']}' in {item['used_by']} "
                        f" -> defined as '{item['defined_name']}'"
                    )
                print()

        except (FileNotFoundError, ImportError, ValueError, KeyError) as e:
            print(f"  [!!] Could not run concept check: {e}")
            print()

    print("  SUMMARY")
    print("  " + "-" * (w - 2))
    print(f"  Total philosophers: {total}")
    if total > 0:
        print(
            f"  With output dependencies: {with_deps}/{total} ({100*with_deps//total}%)"
        )
        print(
            f"  Whose outputs are used: {produces_used}/{total} ({100*produces_used//total}%)"
        )
    else:
        print("  With output dependencies: 0/0")
        print("  Whose outputs are used: 0/0")
    print(f"  Total writings: {len(writings)}")
    print(
        f"  Ordering constraints: {len(ordering)} explicit (<) + {len(concept_depth_ordering)} concept-depth (~)"
    )
    total_concepts = sum(len(p.produces) for p in philosophers.values()) + sum(
        len(w_.produces) for w_ in writings.values()
    )
    print(
        f"  Total concepts produced: {total_concepts} ({sum(len(p.produces) for p in philosophers.values())} from philosophers, {sum(len(w_.produces) for w_ in writings.values())} from writings)"
    )
    print()


# ── Main ─────────────────────────────────────────────────────────────


def main():
    """CLI entry point for the philosopher ordering analyzer."""
    parser = argparse.ArgumentParser(description="Philosopher ordering analyzer")
    parser.add_argument(
        "--brainstorm",
        type=str,
        default=None,
        help="Path to the Concept Brainstorm markdown file",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument(
        "--prereqs",
        "-p",
        action="store_true",
        help="Show full prerequisite trace for each philosopher",
    )
    parser.add_argument(
        "--balance",
        "-b",
        action="store_true",
        help="Check recipe ingredient depth balance (requires Content Map)",
    )
    parser.add_argument(
        "--effective",
        "-e",
        action="store_true",
        help="Compute effective recipes (recipe minus inherited prerequisites)",
    )
    parser.add_argument(
        "--check-concepts",
        "-c",
        action="store_true",
        help="Check that all recipe ingredients are defined somewhere",
    )
    parser.add_argument(
        "--depth-check",
        "-d",
        action="store_true",
        help="Check philosopher depth placement against era windows (requires Content Map)",
    )
    parser.add_argument(
        "--content-map",
        type=str,
        default=None,
        help="Path to the Prototype Content Map (for --balance). Auto-detected if not specified.",
    )
    args = parser.parse_args()

    # Find brainstorm file
    if args.brainstorm:
        path = Path(args.brainstorm)
    else:
        # Default: look in Planning notes/Temporary/
        candidates = [
            Path("Planning notes/Temporary/Concept Brainstorm.md"),
            Path("Planning notes/Concept Brainstorm.md"),
        ]
        path = None
        for c in candidates:
            if c.exists():
                path = c
                break
        if path is None:
            print("Error: Could not find Concept Brainstorm.md")
            print("Use --brainstorm to specify the path")
            sys.exit(1)

    print(f"  (reading from: {path})")

    # Resolve content map path for balance/concept check
    content_map_path = None
    if args.content_map:
        content_map_path = Path(args.content_map)
        if not content_map_path.exists():
            print(f"Error: Content map not found: {content_map_path}")
            sys.exit(1)
    elif args.balance or args.check_concepts or args.depth_check:
        # Auto-detect
        candidates = [
            Path("Planning notes/Temporary/Prototype Content Map.md"),
            Path("Planning notes/Prototype Content Map.md"),
        ]
        for c in candidates:
            if c.exists():
                content_map_path = c
                break

    philosophers, writings, ordering, concept_depth_ordering = parse_brainstorm(path)

    if not philosophers:
        print("Error: No philosophers found in the brainstorm file.")
        print(
            "Expected markdown tables with | Philosopher | Recipe | Produces | columns"
        )
        sys.exit(1)

    print_report(
        philosophers,
        ordering,
        concept_depth_ordering=concept_depth_ordering,
        opts=ReportOptions(
            verbose=args.verbose,
            prereqs=args.prereqs,
            balance=args.balance,
            effective=args.effective,
            check_concepts=args.check_concepts,
            depth_check=args.depth_check,
            content_map_path=content_map_path,
            brainstorm_path=path,
        ),
        writings=writings,
    )


if __name__ == "__main__":
    main()
