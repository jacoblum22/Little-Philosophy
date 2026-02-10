/**
 * useGameState — React hook that subscribes to game state changes.
 *
 * Returns the current game state and re-renders the component whenever
 * the state changes (tile unlocked, combination recorded, etc.).
 */

import { useSyncExternalStore } from "react";
import { subscribe, getSnapshot } from "../engine/gameState";
import type { GameState } from "../types/gameState";

export function useGameState(): GameState {
  return useSyncExternalStore(subscribe, getSnapshot);
}
