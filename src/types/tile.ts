export type TileType = "concept" | "philosopher" | "writing";

export interface Tile {
  id: string;
  name: string;
  type: TileType;
  quote?: string;
  quoteAuthor?: string;
  description: string;
  tags: string[];
  tradition?: string;
}

export interface PhilosopherTile extends Tile {
  type: "philosopher";
  born?: string;
  died?: string;
}

export interface WritingTile extends Tile {
  type: "writing";
  author?: string;
  written?: string;
}
