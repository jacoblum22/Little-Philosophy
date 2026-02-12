"""
Philosopher ordering analyzer for Little Philosophy.

Reads philosopher recipes and ordering constraints from the Concept Brainstorm,
builds a dependency graph, and checks for contradictions or impossibilities.

Usage:
    python scripts/philosopherOrder.py
    python scripts/philosopherOrder.py --verbose
    python scripts/philosopherOrder.py --brainstorm "path/to/Concept Brainstorm.md"
"""

import re
import sys
import argparse
import statistics
from pathlib import Path
from collections import defaultdict, deque
from dataclasses import dataclass, field

# ── Data structures ──────────────────────────────────────────────────

@dataclass
class Philosopher:
    name: str
    era: str                          # Ancient, Medieval, Modern, Contemporary
    recipe: list[str] = field(default_factory=list)
    produces: list[str] = field(default_factory=list)
    depends_on_output_of: list[str] = field(default_factory=list)  # philosophers whose outputs appear in recipe

# ── Parser ───────────────────────────────────────────────────────────

def parse_brainstorm(path: Path) -> tuple[dict[str, Philosopher], list[tuple[str, str]], list[tuple[str, str]]]:
    """Parse the Concept Brainstorm markdown for philosopher data and ordering constraints."""
    text = path.read_text(encoding="utf-8")
    philosophers: dict[str, Philosopher] = {}
    ordering: list[tuple[str, str]] = []

    # Build a lookup: concept -> which philosopher produces it
    concept_to_producer: dict[str, str] = {}

    current_era = None
    era_pattern = re.compile(r"^###\s+(Ancient|Medieval|Modern|Contemporary)", re.IGNORECASE)

    # First pass: extract all philosophers and their recipes/outputs
    lines = text.split("\n")
    in_philosopher_section = False

    for line in lines:
        # Detect philosopher section
        if line.strip().startswith("## Philosophers"):
            in_philosopher_section = True
            continue

        if in_philosopher_section and line.strip().startswith("## ") and "Philosopher" not in line:
            # Hit a new top-level section, stop
            if "Ordering" not in line and "Writing" not in line:
                pass  # keep going for Ordering and Writings sections
            if line.strip().startswith("## Philosopher Ordering"):
                in_philosopher_section = False
                continue
            if line.strip().startswith("## Writings"):
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
            parts = [p for p in parts if p]  # remove empty strings from leading/trailing |

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
            recipe_items = [r.strip().rstrip("*") for r in recipe_str.split(",")]
            starred_items = [r.strip().rstrip("*") for r in recipe_str.split(",") if "*" in r]

            # Parse produces: comma-separated
            produces_items = [p.strip() for p in produces_str.split(",")]

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
                if producer != phil.name:
                    phil.depends_on_output_of.append(producer)

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
            tokens = re.split(r'\s*([<~])\s*', raw)
            # tokens = [name, sep, name, sep, name, ...]
            names = tokens[0::2]  # every other element starting at 0
            seps = tokens[1::2]   # every other element starting at 1
            names = [n.strip() for n in names if n.strip()]
            for i, sep in enumerate(seps):
                if i < len(names) - 1:
                    pair = (names[i], names[i + 1])
                    if sep == '<':
                        ordering.append(pair)
                    else:  # ~
                        concept_depth_ordering.append(pair)

    return philosophers, ordering, concept_depth_ordering


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


def topological_sort(graph: dict[str, set[str]]) -> list[str] | None:
    """Return topological order, or None if cycles exist."""
    in_degree: dict[str, int] = defaultdict(int)
    for node in graph:
        in_degree.setdefault(node, 0)
        for neighbor in graph[node]:
            in_degree[neighbor] = in_degree.get(neighbor, 0) + 1

    queue = deque(sorted(n for n in in_degree if in_degree[n] == 0))
    order: list[str] = []

    while queue:
        node = queue.popleft()
        order.append(node)
        for neighbor in sorted(graph.get(node, set())):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(order) != len(in_degree):
        return None  # cycle detected
    return order


def check_implicit_ordering(
    philosophers: dict[str, Philosopher],
    ordering: list[tuple[str, str]],
    graph: dict[str, set[str]],
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


def find_missing_order_pairs(
    philosophers: dict[str, Philosopher],
    ordering: list[tuple[str, str]],
    graph: dict[str, set[str]],
) -> list[str]:
    """Identify philosopher pairs that might need ordering but have none."""
    # Build transitive closure of the full graph
    reachable: dict[str, set[str]] = {}
    for node in graph:
        visited = set()
        queue = deque([node])
        while queue:
            current = queue.popleft()
            if current in visited:
                continue
            visited.add(current)
            queue.extend(graph.get(current, set()))
        reachable[node] = visited - {node}

    era_order = {"Ancient": 0, "Medieval": 1, "Modern": 2, "Contemporary": 3}
    suggestions = []

    for name_a, phil_a in sorted(philosophers.items()):
        for name_b, phil_b in sorted(philosophers.items()):
            if name_a >= name_b:
                continue
            era_a = era_order.get(phil_a.era, -1)
            era_b = era_order.get(phil_b.era, -1)

            # If A is from an earlier era than B, A should unlock before B
            if era_a < era_b:
                if name_b not in reachable.get(name_a, set()):
                    # A doesn't necessarily unlock before B — might be a problem
                    # Only flag if they're in the same tradition or have a known relationship
                    pass  # Too many false positives, skip for now

            # If same era, check if one should come before the other
            # (this would need specific knowledge — skip for now)

    return suggestions


# ── Recipe Balance ───────────────────────────────────────────────────

def name_to_id(name: str) -> str:
    """Convert a tile name to a slug ID (matches analyzeTree)."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def get_concept_depths(content_map_path: Path | None = None) -> dict[str, int]:
    """Get depth of every concept from the Content Map using BFS.
    
    Returns a dict mapping concept name (lowered) -> BFS depth.
    Also returns depths by tile ID for cross-referencing.
    """
    # Import here to avoid circular dependency
    sys.path.insert(0, str(Path(__file__).parent))
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
            # If it's a philosopher output (*), estimate from producer's depth
            elif item.strip().endswith("*"):
                # Find the producer philosopher
                for other_phil in philosophers.values():
                    if clean in other_phil.produces:
                        # Producer's depth + 1 (need to unlock producer, then combine)
                        # But we don't know producer's exact depth yet...
                        # Use "producer" as source type
                        pass
            
            ingredients.append({
                "name": clean,
                "depth": depth,
                "is_output": item.strip().endswith("*"),
                "source": "content-map" if depth is not None else (
                    "philosopher-output" if item.strip().endswith("*") else "unknown"
                ),
            })
        
        known_depths = [i["depth"] for i in ingredients if i["depth"] is not None]
        unknown = [i for i in ingredients if i["depth"] is None]
        
        issues = []
        
        if len(known_depths) >= 2:
            min_d = min(known_depths)
            max_d = max(known_depths)
            spread = max_d - min_d
            median_d = statistics.median(known_depths)
            
            if spread > max_spread:
                # Find the bottleneck ingredient(s) — ones at max depth
                bottlenecks = [i["name"] for i in ingredients 
                              if i["depth"] is not None and i["depth"] == max_d]
                trivial = [i["name"] for i in ingredients 
                          if i["depth"] is not None and i["depth"] <= min_d + 1]
                issues.append(
                    f"Wide spread: depths span {min_d}–{max_d} (range {spread}). "
                    f"Bottleneck: {', '.join(bottlenecks)}. "
                    f"Trivially early: {', '.join(trivial)}"
                )
            
            # Check trivial ratio
            trivial_count = sum(1 for d in known_depths if d <= 2)
            if len(known_depths) >= 3 and trivial_count / len(known_depths) >= max_trivial_ratio:
                issues.append(
                    f"High trivial ratio: {trivial_count}/{len(known_depths)} ingredients "
                    f"at depth <= 2"
                )
            
            # Check if single ingredient is doing all the gating
            if len(known_depths) >= 3 and max_d > 2:
                at_max = sum(1 for d in known_depths if d == max_d)
                at_low = sum(1 for d in known_depths if d < max_d - 1)
                if at_max == 1 and at_low >= 2:
                    gating_concept = [i["name"] for i in ingredients 
                                    if i["depth"] is not None and i["depth"] == max_d][0]
                    issues.append(
                        f"Single gatekeeper: '{gating_concept}' (depth {max_d}) "
                        f"while {at_low} others are <= depth {max_d - 2}"
                    )
        
        results.append({
            "name": phil.name,
            "era": phil.era,
            "ingredients": ingredients,
            "known_depths": known_depths,
            "unknown_count": len(unknown),
            "issues": issues,
        })
    
    return results


# ── Output ───────────────────────────────────────────────────────────

def print_report(
    philosophers: dict[str, Philosopher],
    ordering: list[tuple[str, str]],
    concept_depth_ordering: list[tuple[str, str]] = None,
    verbose: bool = False,
    prereqs: bool = False,
    balance: bool = False,
    content_map_path: Path | None = None,
):
    if concept_depth_ordering is None:
        concept_depth_ordering = []
    w = 70
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

    # Topological sort
    topo = topological_sort(graph)
    if topo:
        print("  UNLOCK ORDER (earliest to latest)")
        print("  " + "-" * (w - 2))
        era_order = {"Ancient": 0, "Medieval": 1, "Modern": 2, "Contemporary": 3}
        for i, name in enumerate(topo, 1):
            phil = philosophers[name]
            deps = phil.depends_on_output_of
            dep_str = f" (after {', '.join(deps)})" if deps else ""
            era_tag = f"[{phil.era[:3].upper()}]"
            print(f"  {i:3d}. {era_tag} {name}{dep_str}")
        print()

        # Check for era violations (later era unlocking before earlier era)
        violations = []
        for i, name_a in enumerate(topo):
            for name_b in topo[i + 1:]:
                era_a = era_order.get(philosophers[name_a].era, -1)
                era_b = era_order.get(philosophers[name_b].era, -1)
                if era_a > era_b:
                    violations.append((name_a, name_b))

        if violations:
            print(f"  [!!] ERA ORDERING WARNINGS: {len(violations)} potential issue(s)")
            print("  " + "-" * (w - 2))
            for a, b in violations[:20]:
                era_a = philosophers[a].era
                era_b = philosophers[b].era
                print(f"  {a} ({era_a}) unlocks before {b} ({era_b})")
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
    roots = [name for name, phil in philosophers.items() if not phil.depends_on_output_of]
    # Trace chains from roots
    visited_chains: set[str] = set()
    for root in sorted(roots):
        chain = [root]
        current = root
        while True:
            # Find who depends on current
            followers = [
                name for name, phil in philosophers.items()
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
    all_constraints = len(ordering) + len(concept_depth_ordering)
    if ordering or concept_depth_ordering:
        print("  ORDERING CONSTRAINT CHECK")
        print("  " + "-" * (w - 2))

        # Check explicit constraints (must be guaranteed by output deps)
        explicit_warnings = check_implicit_ordering(philosophers, ordering, graph)
        if not explicit_warnings:
            print(f"  [OK] All {len(ordering)} explicit constraints (<) satisfied by recipe dependencies")
        else:
            for w_msg in explicit_warnings:
                print(w_msg)

        # Report concept-depth constraints (will be verified when tree is built)
        if concept_depth_ordering:
            verified = 0
            pending = []
            for before, after in concept_depth_ordering:
                if before not in philosophers or after not in philosophers:
                    pending.append(f"  {before} ~ {after}: unknown philosopher")
                    continue
                # Check if output deps happen to satisfy this anyway
                output_graph: dict[str, set[str]] = defaultdict(set)
                for phil in philosophers.values():
                    output_graph[phil.name]
                    for dep in phil.depends_on_output_of:
                        output_graph[dep].add(phil.name)
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
                print(f"  [..] {len(concept_depth_ordering)} concept-depth constraints (~): "
                      f"{verified} already satisfied, {len(pending)} pending tree completion:")
                for p in pending:
                    print(p)
            else:
                print(f"  [OK] All {len(concept_depth_ordering)} concept-depth constraints (~) "
                      f"happen to be satisfied by output deps")

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
                p.name for p in philosophers.values()
                if concept in p.recipe and p.name != producer
            ]
            consumer_str = f" -> used by {', '.join(consumers)}" if consumers else " (unused)"
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

        # For each philosopher in topological order, show prerequisites
        if topo:
            for name in topo:
                phil = philosophers[name]
                # Gather all prerequisite concepts recursively
                all_concepts: list[str] = []   # own recipe
                all_philosophers: list[str] = []  # philosophers that must unlock first
                visited_phils: set[str] = set()

                def trace_prereqs(p_name: str):
                    if p_name in visited_phils:
                        return
                    visited_phils.add(p_name)
                    p = philosophers[p_name]
                    for concept in p.recipe:
                        if concept not in all_concepts:
                            all_concepts.append(concept)
                        # If this concept is produced by another philosopher, trace that philosopher too
                        if concept in concept_to_producer:
                            producer = concept_to_producer[concept]
                            if producer != p_name and producer not in all_philosophers:
                                all_philosophers.append(producer)
                                trace_prereqs(producer)

                trace_prereqs(name)

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
                    print(f"    No philosopher prerequisites (foundational)")
                print()

    # Stats
    total = len(philosophers)
    with_deps = sum(1 for p in philosophers.values() if p.depends_on_output_of)
    produces_used = sum(
        1 for p in philosophers.values()
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
            balanced = [r for r in balance_results if not r["issues"] and r["known_depths"]]
            unknown = [r for r in balance_results if not r["known_depths"]]
            
            if flagged:
                print(f"  [!!] {len(flagged)} philosopher(s) with imbalanced recipes:")
                print()
                for r in flagged:
                    depths_str = ", ".join(
                        f"{i['name']}={i['depth']}" if i['depth'] is not None 
                        else f"{i['name']}=?" 
                        for i in r["ingredients"]
                    )
                    print(f"    {r['name']} ({r['era']}):")
                    print(f"      Ingredients: {depths_str}")
                    for issue in r["issues"]:
                        print(f"      [!] {issue}")
                    print()
            
            if balanced:
                if verbose:
                    print(f"  [OK] {len(balanced)} philosopher(s) with balanced recipes:")
                    for r in balanced:
                        depths_str = ", ".join(
                            f"{i['name']}={i['depth']}" if i['depth'] is not None 
                            else f"{i['name']}=?" 
                            for i in r["ingredients"]
                        )
                        spread = max(r["known_depths"]) - min(r["known_depths"]) if r["known_depths"] else 0
                        print(f"    {r['name']}: {depths_str} (spread: {spread})")
                else:
                    print(f"  [OK] {len(balanced)} philosopher(s) with balanced recipes")
            
            if unknown:
                print(f"  [..] {len(unknown)} philosopher(s) with no known ingredient depths "
                      f"(all recipe concepts missing from Content Map)")
                if verbose:
                    for r in unknown:
                        names = [i["name"] for i in r["ingredients"]]
                        print(f"    {r['name']}: {', '.join(names)}")
            print()
            
        except Exception as e:
            print(f"  [!!] Could not run balance check: {e}")
            print(f"       Make sure the Content Map exists and is valid.")
            print()

    print("  SUMMARY")
    print("  " + "-" * (w - 2))
    print(f"  Total philosophers: {total}")
    print(f"  With output dependencies: {with_deps}/{total} ({100*with_deps//total}%)")
    print(f"  Whose outputs are used: {produces_used}/{total} ({100*produces_used//total}%)")
    print(f"  Ordering constraints: {len(ordering)} explicit (<) + {len(concept_depth_ordering)} concept-depth (~)")
    print(f"  Total concepts produced: {sum(len(p.produces) for p in philosophers.values())}")
    print()


# ── Main ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Philosopher ordering analyzer")
    parser.add_argument(
        "--brainstorm",
        type=str,
        default=None,
        help="Path to the Concept Brainstorm markdown file",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument(
        "--prereqs", "-p", action="store_true",
        help="Show full prerequisite trace for each philosopher",
    )
    parser.add_argument(
        "--balance", "-b", action="store_true",
        help="Check recipe ingredient depth balance (requires Content Map)",
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

    # Resolve content map path for balance check
    content_map_path = None
    if args.content_map:
        content_map_path = Path(args.content_map)
    elif args.balance:
        # Auto-detect
        candidates = [
            Path("Planning notes/Temporary/Prototype Content Map.md"),
            Path("Planning notes/Prototype Content Map.md"),
        ]
        for c in candidates:
            if c.exists():
                content_map_path = c
                break

    philosophers, ordering, concept_depth_ordering = parse_brainstorm(path)

    if not philosophers:
        print("Error: No philosophers found in the brainstorm file.")
        print("Expected markdown tables with | Philosopher | Recipe | Produces | columns")
        sys.exit(1)

    print_report(
        philosophers, ordering,
        concept_depth_ordering=concept_depth_ordering,
        verbose=args.verbose,
        prereqs=args.prereqs,
        balance=args.balance,
        content_map_path=content_map_path,
    )


if __name__ == "__main__":
    main()
