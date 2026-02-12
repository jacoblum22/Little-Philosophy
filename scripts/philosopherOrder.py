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

def parse_brainstorm(path: Path) -> tuple[dict[str, Philosopher], list[tuple[str, str]]]:
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
    for line in lines:
        if line.strip().startswith("## Philosopher Ordering"):
            in_ordering = True
            continue
        if in_ordering and line.strip().startswith("## "):
            break
        if in_ordering and "<" in line and line.strip().startswith("- "):
            # Parse chains like "Socrates < Plato < Aristotle"
            names = [n.strip() for n in line.split("<")]
            names = [n.lstrip("- ").strip() for n in names if n.strip()]
            for i in range(len(names) - 1):
                ordering.append((names[i], names[i + 1]))

    return philosophers, ordering


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


# ── Output ───────────────────────────────────────────────────────────

def print_report(
    philosophers: dict[str, Philosopher],
    ordering: list[tuple[str, str]],
    verbose: bool = False,
):
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
    if ordering:
        print("  ORDERING CONSTRAINT CHECK")
        print("  " + "-" * (w - 2))
        warnings = check_implicit_ordering(philosophers, ordering, graph)
        if not warnings:
            print("  [OK] All ordering constraints are satisfied by recipe dependencies")
        else:
            for w_msg in warnings:
                print(w_msg)
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

    print("  SUMMARY")
    print("  " + "-" * (w - 2))
    print(f"  Total philosophers: {total}")
    print(f"  With output dependencies: {with_deps}/{total} ({100*with_deps//total}%)")
    print(f"  Whose outputs are used: {produces_used}/{total} ({100*produces_used//total}%)")
    print(f"  Ordering constraints: {len(ordering)}")
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

    philosophers, ordering = parse_brainstorm(path)

    if not philosophers:
        print("Error: No philosophers found in the brainstorm file.")
        print("Expected markdown tables with | Philosopher | Recipe | Produces | columns")
        sys.exit(1)

    print_report(philosophers, ordering, verbose=args.verbose)


if __name__ == "__main__":
    main()
