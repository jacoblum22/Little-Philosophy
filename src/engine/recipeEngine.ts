/**
 * Recipe engine — check if any philosopher/writing recipes are fulfilled.
 *
 * A recipe is fulfilled when ALL of its required concepts are unlocked.
 * This module knows about recipes and tile IDs, but nothing about UI.
 */

import type { Recipe } from "../types/combination";

let recipes: Recipe[] = [];

/** Initialize the engine with recipe data (call once at startup). */
export function initRecipes(recipeData: Recipe[]): void {
  recipes = [...recipeData];
}

/**
 * Given a set of unlocked tile IDs, return the IDs of any tiles whose
 * recipes are now fulfilled but aren't yet unlocked.
 *
 * Call this after each new discovery to check for auto-unlocks.
 */
export function checkRecipes(unlockedIds: Set<string>): string[] {
  const newUnlocks: string[] = [];
  for (const recipe of recipes) {
    if (unlockedIds.has(recipe.tileId)) continue; // already unlocked
    const fulfilled = recipe.requiredConcepts.every((id) => unlockedIds.has(id));
    if (fulfilled) {
      newUnlocks.push(recipe.tileId);
    }
  }
  return newUnlocks;
}
