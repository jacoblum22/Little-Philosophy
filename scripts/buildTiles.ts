/**
 * Build script: parse tile Markdown files → JSON for the game engine.
 *
 * Reads every .md file in src/data/tiles/, extracts YAML frontmatter and
 * Markdown body, then writes three JSON files into public/data/build/:
 *
 *   tiles.json        – all tile data (id, name, type, description, tags, …)
 *   combinations.json – flattened list of { input1, input2, output }
 *   recipes.json      – philosopher/writing unlock recipes
 *
 * Run with:  npx tsx scripts/buildTiles.ts
 */

import fs from "node:fs";
import path from "node:path";

// ---------------------------------------------------------------------------
// Paths
// ---------------------------------------------------------------------------

const TILES_DIR = path.resolve("src/data/tiles");
const BUILD_DIR = path.resolve("public/data/build");

// ---------------------------------------------------------------------------
// Types (mirrors src/types/ but for the build script's own use)
// ---------------------------------------------------------------------------

interface TileFrontmatter {
  id: string;
  name: string;
  type: "concept" | "philosopher" | "writing";
  quote?: string;
  quoteAuthor?: string;
  // Philosopher-specific
  born?: string;
  died?: string;
  tradition?: string;
  // Writing-specific
  author?: string;
  written?: string;
  // Content graph
  createdFrom?: string[];
  combinations?: { with: string; produces: string }[];
  recipe?: string[];
}

interface TileJSON {
  id: string;
  name: string;
  type: "concept" | "philosopher" | "writing";
  quote?: string;
  quoteAuthor?: string;
  description: string;
  tags: string[];
  // Shared extras (philosopher & writing)
  tradition?: string;
  // Philosopher extras
  born?: string;
  died?: string;
  // Writing extras
  author?: string;
  written?: string;
}

interface CombinationJSON {
  input1: string;
  input2: string;
  output: string;
}

interface RecipeJSON {
  tileId: string;
  requiredConcepts: string[];
}

// ---------------------------------------------------------------------------
// Simple YAML frontmatter parser (no external dependency)
// ---------------------------------------------------------------------------

function parseFrontmatter(raw: string): {
  data: TileFrontmatter;
  body: string;
} {
  const fmRegex = /^---\r?\n([\s\S]*?)\r?\n---\r?\n?([\s\S]*)$/;
  const match = raw.match(fmRegex);
  if (!match) {
    throw new Error("No YAML frontmatter found");
  }

  const yamlStr = match[1];
  const body = match[2];

  const rawData = parseSimpleYaml(yamlStr);

  // Validate required fields
  if (typeof rawData.id !== "string" || !rawData.id) {
    throw new Error("Missing required field: id");
  }
  if (typeof rawData.name !== "string" || !rawData.name) {
    throw new Error("Missing required field: name");
  }
  if (
    rawData.type !== "concept" &&
    rawData.type !== "philosopher" &&
    rawData.type !== "writing"
  ) {
    throw new Error(
      `Invalid or missing type: "${rawData.type}" (must be concept, philosopher, or writing)`
    );
  }

  const data = rawData as TileFrontmatter;
  return { data, body };
}

/**
 * Minimal YAML parser — handles the subset we use in tile files:
 *   - scalar key: value
 *   - lists (- item)
 *   - lists of objects (- key: val\n  key: val)
 */
function parseSimpleYaml(yaml: string): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  const lines = yaml.split(/\r?\n/);

  let i = 0;
  while (i < lines.length) {
    const line = lines[i];

    // Skip blank lines
    if (line.trim() === "") {
      i++;
      continue;
    }

    // Match top-level key
    const keyMatch = line.match(/^(\w[\w-]*):\s*(.*)/);
    if (!keyMatch) {
      i++;
      continue;
    }

    const key = keyMatch[1];
    const inlineValue = keyMatch[2].trim();

    if (inlineValue !== "") {
      // Scalar value — strip surrounding quotes if present
      let value = inlineValue.replace(/^["']|["']$/g, "");
      i++;
      // Handle multi-line plain scalars (continuation lines indented with spaces)
      while (i < lines.length) {
        const contLine = lines[i];
        if (/^\s+\S/.test(contLine) && !contLine.match(/^\s*- /)) {
          value += " " + contLine.trim();
          i++;
        } else {
          break;
        }
      }
      result[key] = value;
    } else {
      // Could be a list or list-of-objects
      const items: unknown[] = [];
      i++;
      while (i < lines.length) {
        const nextLine = lines[i];
        // List item? (allow optional leading whitespace)
        const itemMatch = nextLine.match(/^\s*- (.+)/);
        if (!itemMatch) break;

        const itemValue = itemMatch[1].trim();

        // Check if this is an object item (- key: value)
        const objMatch = itemValue.match(/^(\w[\w-]*):\s*(.*)/);
        if (objMatch) {
          // It's an object — collect subsequent indented key: value lines
          const obj: Record<string, string> = {};
          obj[objMatch[1]] = objMatch[2].trim().replace(/^["']|["']$/g, "");
          i++;
          while (i < lines.length) {
            const indentedMatch = lines[i].match(
              /^\s{2,}(\w[\w-]*):\s*(.*)/
            );
            if (!indentedMatch) break;
            obj[indentedMatch[1]] = indentedMatch[2]
              .trim()
              .replace(/^["']|["']$/g, "");
            i++;
          }
          items.push(obj);
        } else {
          // Plain list item
          items.push(itemValue.replace(/^["']|["']$/g, ""));
          i++;
        }
      }
      result[key] = items;
    }
  }

  return result;
}

// ---------------------------------------------------------------------------
// Body text processing
// ---------------------------------------------------------------------------

function extractDescription(body: string): string {
  return body
    .split(/\r?\n/)
    .filter((line) => {
      const trimmed = line.trim();
      // Strip Parents: / Children: lines
      if (trimmed.startsWith("Parents:") || trimmed.startsWith("Children:"))
        return false;
      // Strip lines that are only #tags
      if (/^#[\w-]+(\s+#[\w-]+)*$/.test(trimmed)) return false;
      return true;
    })
    .join("\n")
    .trim();
}

function extractTags(body: string): string[] {
  const tags: string[] = [];
  for (const line of body.split(/\r?\n/)) {
    const trimmed = line.trim();
    // Lines that are only hashtags
    if (/^#[\w-]+(\s+#[\w-]+)*$/.test(trimmed)) {
      const matches = trimmed.match(/#[\w-]+/g);
      if (matches) {
        tags.push(...matches.map((t) => t.slice(1))); // remove leading #
      }
    }
  }
  return tags;
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

function build() {
  const files = fs
    .readdirSync(TILES_DIR)
    .filter((f) => f.endsWith(".md"))
    .sort();

  const tiles: TileJSON[] = [];
  const combinations: CombinationJSON[] = [];
  const recipes: RecipeJSON[] = [];
  const seenCombos = new Map<string, string>();
  const seenTileIds = new Set<string>();
  const errors: string[] = [];

  for (const file of files) {
    const raw = fs.readFileSync(path.join(TILES_DIR, file), "utf-8");

    let fm: TileFrontmatter;
    let body: string;
    try {
      const parsed = parseFrontmatter(raw);
      fm = parsed.data;
      body = parsed.body;
    } catch (e) {
      errors.push(`${file}: failed to parse frontmatter — ${e}`);
      continue;
    }

    // --- Tile ---
    const tile: TileJSON = {
      id: fm.id,
      name: fm.name,
      type: fm.type,
      description: extractDescription(body),
      tags: extractTags(body),
    };
    if (fm.quote) tile.quote = fm.quote;
    if (fm.quoteAuthor) tile.quoteAuthor = fm.quoteAuthor;
    if (fm.tradition) tile.tradition = fm.tradition;
    if (fm.type === "philosopher") {
      if (fm.born) tile.born = fm.born;
      if (fm.died) tile.died = fm.died;
    }
    if (fm.type === "writing") {
      if (fm.author) tile.author = fm.author;
      if (fm.written) tile.written = fm.written;
    }

    if (seenTileIds.has(fm.id)) {
      errors.push(`Duplicate tile ID "${fm.id}" found in ${file}`);
      continue; // skip duplicate — don't add to output
    }
    seenTileIds.add(fm.id);
    tiles.push(tile);

    // --- Combinations ---
    if (fm.combinations) {
      for (const combo of fm.combinations) {
        if (typeof combo.with !== "string" || !combo.with) {
          errors.push(`${file}: combination missing "with" field`);
          continue;
        }
        if (typeof combo.produces !== "string" || !combo.produces) {
          errors.push(`${file}: combination missing "produces" field`);
          continue;
        }
        // Deduplicate: A+B = B+A
        const key = [fm.id, combo.with].sort().join("+");
        if (!seenCombos.has(key)) {
          seenCombos.set(key, combo.produces);
          combinations.push({
            input1: fm.id,
            input2: combo.with,
            output: combo.produces,
          });
        } else {
          const existingOutput = seenCombos.get(key);
          if (existingOutput !== combo.produces) {
            errors.push(
              `Conflicting combination: ${key} → "${existingOutput}" vs "${combo.produces}" (in ${file})`
            );
          }
        }
      }
    }

    // --- Recipes (philosophers & writings) ---
    if (fm.recipe && fm.recipe.length > 0) {
      recipes.push({
        tileId: fm.id,
        requiredConcepts: fm.recipe,
      });
    }
  }

  // ---------------------------------------------------------------------------
  // Validation
  // ---------------------------------------------------------------------------

  const tileIds = new Set(tiles.map((t) => t.id));

  for (const combo of combinations) {
    if (!tileIds.has(combo.input1))
      errors.push(`Combination references unknown tile: ${combo.input1}`);
    if (!tileIds.has(combo.input2))
      errors.push(`Combination references unknown tile: ${combo.input2}`);
    if (!tileIds.has(combo.output))
      errors.push(`Combination references unknown tile: ${combo.output}`);
  }

  for (const recipe of recipes) {
    if (!tileIds.has(recipe.tileId))
      errors.push(`Recipe references unknown tile: ${recipe.tileId}`);
    for (const req of recipe.requiredConcepts) {
      if (!tileIds.has(req))
        errors.push(
          `Recipe for ${recipe.tileId} references unknown tile: ${req}`
        );
    }
  }

  // Check for tiles with no way to obtain them (not starting, not combo output, not recipe)
  const comboOutputs = new Set(combinations.map((c) => c.output));
  const recipeTiles = new Set(recipes.map((r) => r.tileId));
  for (const tile of tiles) {
    if (
      !tile.tags.includes("starting") &&
      !comboOutputs.has(tile.id) &&
      !recipeTiles.has(tile.id)
    ) {
      errors.push(
        `Tile "${tile.id}" has no way to be obtained (not starting, not a combo output, not a recipe)`
      );
    }
  }

  // ---------------------------------------------------------------------------
  // Output
  // ---------------------------------------------------------------------------

  if (errors.length > 0) {
    console.error("\n❌ Validation errors:");
    for (const err of errors) {
      console.error(`   • ${err}`);
    }
    console.error("");
    process.exit(1);
  }

  fs.mkdirSync(BUILD_DIR, { recursive: true });

  fs.writeFileSync(
    path.join(BUILD_DIR, "tiles.json"),
    JSON.stringify(tiles, null, 2)
  );
  fs.writeFileSync(
    path.join(BUILD_DIR, "combinations.json"),
    JSON.stringify(combinations, null, 2)
  );
  fs.writeFileSync(
    path.join(BUILD_DIR, "recipes.json"),
    JSON.stringify(recipes, null, 2)
  );

  console.log(`\n✅ Build complete!`);
  console.log(`   ${tiles.length} tiles`);
  console.log(`   ${combinations.length} combinations`);
  console.log(`   ${recipes.length} recipes`);
  console.log(`   Output: ${BUILD_DIR}/\n`);
}

build();
