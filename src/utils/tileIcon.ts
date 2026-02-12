/** Icon prefix map for tile types (shared across palette and workspace). */
export const TILE_ICONS: Record<string, string> = {
  philosopher: "🧠 ",
  writing: "📜 ",
};

/** Return the emoji icon prefix for the given tile type, or empty string if none. */
export function tileIcon(type: string): string {
  return TILE_ICONS[type] ?? "";
}
