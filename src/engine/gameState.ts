/**
 * Game state management — unlocked tiles, combination history, save/load.
 *
 * Uses a simple reactive store pattern. UI components subscribe to state
 * changes. State is persisted to localStorage.
 */

import type { GameState, CombinationAttempt } from "../types/gameState";

const STORAGE_KEY = "little-philosophy-save";

/** The starting tile IDs that every new game begins with. */
const STARTING_TILES = ["self", "world", "other"];

type Listener = () => void;

let state: GameState = createFreshState();
const listeners = new Set<Listener>();

function createFreshState(): GameState {
  return {
    unlockedTileIds: [...STARTING_TILES],
    combinationHistory: [],
  };
}

// ---------------------------------------------------------------------------
// Subscriptions (React integration)
// ---------------------------------------------------------------------------

/** Subscribe to state changes. Returns an unsubscribe function. */
export function subscribe(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function notify(): void {
  for (const listener of listeners) {
    listener();
  }
}

// ---------------------------------------------------------------------------
// Getters (read-only access to state)
// ---------------------------------------------------------------------------

export function getState(): GameState {
  return state;
}

export function getUnlockedIds(): Set<string> {
  return new Set(state.unlockedTileIds);
}

export function isUnlocked(tileId: string): boolean {
  return state.unlockedTileIds.includes(tileId);
}

// ---------------------------------------------------------------------------
// Actions (mutate state)
// ---------------------------------------------------------------------------

/** Unlock a tile. Returns true if it was newly unlocked, false if already known. */
export function unlockTile(tileId: string): boolean {
  if (state.unlockedTileIds.includes(tileId)) return false;
  state = {
    ...state,
    unlockedTileIds: [...state.unlockedTileIds, tileId],
  };
  save();
  notify();
  return true;
}

/** Record a combination attempt (successful or not). */
export function recordAttempt(input1: string, input2: string, result: string | null): void {
  const attempt: CombinationAttempt = {
    input1,
    input2,
    result,
    timestamp: Date.now(),
  };
  state = {
    ...state,
    combinationHistory: [...state.combinationHistory, attempt],
  };
  save();
  notify();
}

/** Reset the game to a fresh state. */
export function resetGame(): void {
  state = createFreshState();
  save();
  notify();
}

// ---------------------------------------------------------------------------
// Persistence (localStorage)
// ---------------------------------------------------------------------------

function save(): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    // localStorage may be unavailable (private browsing, full, etc.)
  }
}

/** Load saved state from localStorage. Call once at startup. */
export function loadSavedState(): void {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as GameState;
      // Basic validation
      if (Array.isArray(parsed.unlockedTileIds) && Array.isArray(parsed.combinationHistory)) {
        state = parsed;
        notify();
      }
    }
  } catch {
    // Corrupted save data — start fresh
  }
}
