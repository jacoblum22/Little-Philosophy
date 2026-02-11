/**
 * useGameInit — React hook that bootstraps the game on mount.
 *
 * Loads JSON data, initializes engines, and loads saved state.
 * Returns the loaded game data (or null while loading) and the tile map.
 */

import { useState, useEffect } from "react";
import { loadGameData, buildTileMap } from "./dataLoader";
import type { GameData, TileMap } from "./dataLoader";
import { initCombinations } from "../engine/combinationEngine";
import { initRecipes } from "../engine/recipeEngine";
import { initGameState, loadSavedState } from "../engine/gameState";

export interface GameInit {
  data: GameData;
  tileMap: TileMap;
}

export interface GameInitResult {
  init: GameInit | null;
  error: string | null;
}

export function useGameInit(): GameInitResult {
  const [init, setInit] = useState<GameInit | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    loadGameData()
      .then((data) => {
        if (cancelled) return;

        const tileMap = buildTileMap(data.tiles);
        initCombinations(data.combinations);
        initRecipes(data.recipes);
        initGameState(data.tiles);
        loadSavedState();

        setInit({ data, tileMap });
      })
      .catch((err) => {
        if (cancelled) return;
        console.error("Failed to load game data:", err);
        setError(err instanceof Error ? err.message : String(err));
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return { init, error };
}
