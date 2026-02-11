/**
 * Game state management — unlocked tiles, combination history, save/load.
 *
 * Uses a simple reactive store pattern. UI components subscribe to state
 * changes. State is persisted to localStorage.
 */

import type { GameState, CombinationAttempt } from "../types/gameState";
import type { Tile } from "../types/tile";

const STORAGE_KEY = "little-philosophy-save";

/** Starting tile IDs, derived from loaded tile data at init time. */
let startingTileIds: string[] = [];

type Listener = () => void;

let state: GameState = createFreshState();
let unlockedSet: Set<string> = new Set(state.unlockedTileIds);
const listeners = new Set<Listener>();

function createFreshState(): GameState {
  return {
    unlockedTileIds: [...startingTileIds],
    combinationHistory: [],
  };
}

/**
 * Initialize the game state with tile data.
 * Derives starting tiles from tiles tagged "starting".
 * Call once at startup, before loadSavedState().
 */
export function initGameState(tiles: Tile[]): void {
  startingTileIds = tiles
    .filter((t) => t.tags.includes("starting"))
    .map((t) => t.id);
  state = createFreshState();
  unlockedSet = new Set(state.unlockedTileIds);
  notify();
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
  snapshot = structuredClone(state);
  for (const listener of listeners) {
    try {
      listener();
    } catch (e) {
      console.error("Error in game state listener:", e);
    }
  }
}

// ---------------------------------------------------------------------------
// Getters (read-only access to state)
// ---------------------------------------------------------------------------

/** Returns a deep copy of the current state to prevent accidental mutation. */
export function getState(): GameState {
  return structuredClone(state);
}

/**
 * Returns a stable snapshot reference for useSyncExternalStore.
 * Only creates a new reference when state actually changes (in notify).
 */
let snapshot: GameState = structuredClone(state);
export function getSnapshot(): GameState {
  return snapshot;
}

export function getUnlockedIds(): Set<string> {
  return new Set(state.unlockedTileIds);
}

export function isUnlocked(tileId: string): boolean {
  return unlockedSet.has(tileId);
}

// ---------------------------------------------------------------------------
// Actions (mutate state)
// ---------------------------------------------------------------------------

/** Unlock a tile. Returns true if it was newly unlocked, false if already known. */
export function unlockTile(tileId: string): boolean {
  if (unlockedSet.has(tileId)) return false;
  state = {
    ...state,
    unlockedTileIds: [...state.unlockedTileIds, tileId],
  };
  unlockedSet = new Set(state.unlockedTileIds);
  save();
  notify();
  return true;
}

const MAX_HISTORY = 1000;

/** Record a combination attempt (successful or not). */
export function recordAttempt(input1: string, input2: string, result: string | null): void {
  const attempt: CombinationAttempt = {
    input1,
    input2,
    result,
    timestamp: Date.now(),
  };
  const history = [...state.combinationHistory, attempt];
  state = {
    ...state,
    combinationHistory: history.length > MAX_HISTORY
      ? history.slice(-MAX_HISTORY)
      : history,
  };
  save();
  notify();
}

/** Reset the game to a fresh state. */
export function resetGame(): void {
  state = createFreshState();
  unlockedSet = new Set(state.unlockedTileIds);
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

/** Load saved state from localStorage. Call once at startup, after initGameState(). */
export function loadSavedState(): void {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as GameState;
      // Basic validation
      if (Array.isArray(parsed.unlockedTileIds) && Array.isArray(parsed.combinationHistory)) {
        // Merge in any new starting tiles that weren't in the old save
        const merged = new Set(parsed.unlockedTileIds);
        for (const id of startingTileIds) {
          merged.add(id);
        }
        state = {
          unlockedTileIds: [...merged],
          combinationHistory: parsed.combinationHistory,
        };
        unlockedSet = new Set(state.unlockedTileIds);
        notify();
      }
    }
  } catch {
    // Corrupted save data — start fresh
  }
}
