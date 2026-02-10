/**
 * Combination engine — given two tile IDs, return the result tile ID or null.
 *
 * This module is pure logic: it knows about combination data and tile IDs,
 * but nothing about UI, state, or how combinations are triggered.
 */

import type { Combination } from "../types/combination";

/** Pre-built lookup map for O(1) combination checks. */
let comboMap: Map<string, string> | null = null;

/** Create a canonical key for a pair of tile IDs (order-independent). */
function comboKey(a: string, b: string): string {
  return a < b ? `${a}+${b}` : `${b}+${a}`;
}

/** Initialize the engine with combination data (call once at startup). */
export function initCombinations(combinations: Combination[]): void {
  comboMap = new Map();
  for (const c of combinations) {
    comboMap.set(comboKey(c.input1, c.input2), c.output);
  }
}

/**
 * Given two tile IDs, return the output tile ID if a combination exists,
 * or null if no combination is defined for this pair.
 *
 * Order doesn't matter — (A, B) and (B, A) produce the same result.
 */
export function combine(tileA: string, tileB: string): string | null {
  if (!comboMap) {
    throw new Error("Combination engine not initialized. Call initCombinations first.");
  }
  if (tileA === tileB) return null;
  return comboMap.get(comboKey(tileA, tileB)) ?? null;
}
