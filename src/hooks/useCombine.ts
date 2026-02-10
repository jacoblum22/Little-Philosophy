/**
 * useCombine — React hook encapsulating the combination + recipe check flow.
 *
 * Given two tile IDs, attempts to combine them, records the attempt,
 * unlocks the result if successful, then checks for recipe unlocks.
 * Returns the list of all newly unlocked tile IDs (combo + recipes).
 */

import { combine } from "../engine/combinationEngine";
import { checkRecipes } from "../engine/recipeEngine";
import { unlockTile, recordAttempt, getUnlockedIds } from "../engine/gameState";

export interface CombineResult {
  /** The direct combination output, or null if no combo exists. */
  comboTileId: string | null;
  /** All tiles unlocked (direct combo + any triggered recipes). */
  newlyUnlocked: string[];
}

/**
 * Attempt to combine two tiles.
 * This is a plain function (not a hook) — safe to call from event handlers.
 */
export function attemptCombine(tileA: string, tileB: string): CombineResult {
  const comboTileId = combine(tileA, tileB);
  recordAttempt(tileA, tileB, comboTileId);

  const newlyUnlocked: string[] = [];

  if (comboTileId) {
    const wasNew = unlockTile(comboTileId);
    if (wasNew) {
      newlyUnlocked.push(comboTileId);
    }

    // Check if any recipes are now fulfilled
    const recipeUnlocks = checkRecipes(getUnlockedIds());
    for (const id of recipeUnlocks) {
      const wasNewRecipe = unlockTile(id);
      if (wasNewRecipe) {
        newlyUnlocked.push(id);
      }
    }
  }

  return { comboTileId, newlyUnlocked };
}
