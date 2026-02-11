import { useState, useCallback, useRef } from "react";
import {
  DndContext,
  DragOverlay,
  type DragStartEvent,
  type DragEndEvent,
  PointerSensor,
  useSensor,
  useSensors,
} from "@dnd-kit/core";

import { useGameInit } from "./hooks/useGameInit";
import { useGameState } from "./hooks/useGameState";
import { attemptCombine } from "./hooks/useCombine";
import { resetGame } from "./engine/gameState";

import TilePalette from "./ui/TilePalette";
import Workspace from "./ui/Workspace";
import type { CanvasTile } from "./ui/Workspace";
import type { TileMap } from "./hooks/dataLoader";
import DiscoveryNotification from "./ui/DiscoveryNotification";
import CivilopediaPanel from "./ui/CivilopediaPanel";
import ProgressBar from "./ui/ProgressBar";

import "./App.css";

let nextInstanceId = 1;

/** Overlay chip that follows the cursor during drag. */
function DragOverlayChip({ tileId, tileMap }: { tileId: string; tileMap: TileMap }) {
  const tile = tileMap.get(tileId);
  const typeCls = tile ? `tile-chip--${tile.type}` : "";
  return (
    <div className={`tile-chip tile-chip--dragging ${typeCls}`}>
      {tile?.type === "philosopher" && "🧠 "}
      {tile?.type === "writing" && "📜 "}
      {tile?.name ?? tileId}
    </div>
  );
}

function App() {
  const { init: gameInit, error } = useGameInit();
  const gameState = useGameState();

  // Freeform canvas tiles
  const [canvasTiles, setCanvasTiles] = useState<CanvasTile[]>([]);
  const canvasTilesRef = useRef(canvasTiles);
  canvasTilesRef.current = canvasTiles;

  // Discovery notification
  const [discoveries, setDiscoveries] = useState<string[]>([]);

  // Civilopedia selected tile
  const [selectedTileId, setSelectedTileId] = useState<string | null>(null);

  // Active drag tile ID (for DragOverlay)
  const [activeDragId, setActiveDragId] = useState<string | null>(null);

  // DnD sensors — add a small distance threshold so clicks still work
  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: { distance: 5 },
    })
  );

  const handleDragStart = useCallback((event: DragStartEvent) => {
    const tileId = event.active.data.current?.tileId as string | undefined;
    setActiveDragId(tileId ?? null);
  }, []);

  const handleReset = useCallback(() => {
    resetGame();
    setCanvasTiles([]);
    setDiscoveries([]);
    setSelectedTileId(null);
  }, []);

  const handleClearAll = useCallback(() => {
    setCanvasTiles([]);
  }, []);

  const handleDismissDiscovery = useCallback(() => {
    setDiscoveries([]);
  }, []);

  const handleDragEnd = useCallback(
    (event: DragEndEvent) => {
      setActiveDragId(null);
      const { active, over, delta } = event;
      if (!active.data.current) return;

      const source = active.data.current.source as string | undefined;
      const tileId = active.data.current.tileId as string;

      // --- Case 1: Palette tile dropped on a canvas tile → combine
      if (over?.data.current?.instanceId && source !== "canvas") {
        const targetTileId = over.data.current.tileId as string;
        const targetInstanceId = over.data.current.instanceId as string;

        const result = attemptCombine(tileId, targetTileId);
        if (result.comboTileId) {
          // Remove the target tile, place the result at its position
          const target = canvasTilesRef.current.find((ct) => ct.instanceId === targetInstanceId);
          const resultId = `canvas-${nextInstanceId++}`;
          setCanvasTiles((prev) => [
            ...prev.filter((ct) => ct.instanceId !== targetInstanceId),
            {
              instanceId: resultId,
              tileId: result.comboTileId!,
              x: target?.x ?? 100,
              y: target?.y ?? 100,
            },
          ]);
          if (result.newlyUnlocked.length > 0) {
            setDiscoveries(result.newlyUnlocked);
          }
        } else {
          // Failed combo — just place the palette tile near the target
          const target = canvasTilesRef.current.find((ct) => ct.instanceId === targetInstanceId);
          if (target) {
            const id = `canvas-${nextInstanceId++}`;
            setCanvasTiles((prev) => [
              ...prev,
              { instanceId: id, tileId, x: target.x + 50, y: target.y + 40 },
            ]);
          }
        }
        return;
      }

      // --- Case 2: Canvas tile dropped on another canvas tile → combine
      if (source === "canvas" && over?.data.current?.instanceId) {
        const dragInstanceId = active.data.current.instanceId as string;
        const targetInstanceId = over.data.current.instanceId as string;
        if (dragInstanceId === targetInstanceId) return;

        const targetTileId = over.data.current.tileId as string;
        const result = attemptCombine(tileId, targetTileId);
        if (result.comboTileId) {
          // Remove both tiles, place result at midpoint
          const dragTile = canvasTilesRef.current.find((ct) => ct.instanceId === dragInstanceId);
          const targetTile = canvasTilesRef.current.find((ct) => ct.instanceId === targetInstanceId);
          const midX = ((dragTile?.x ?? 200) + (targetTile?.x ?? 200)) / 2;
          const midY = ((dragTile?.y ?? 200) + (targetTile?.y ?? 200)) / 2;
          const resultId = `canvas-${nextInstanceId++}`;
          setCanvasTiles((prev) => [
            ...prev.filter(
              (ct) =>
                ct.instanceId !== dragInstanceId &&
                ct.instanceId !== targetInstanceId
            ),
            {
              instanceId: resultId,
              tileId: result.comboTileId!,
              x: midX,
              y: midY,
            },
          ]);
          if (result.newlyUnlocked.length > 0) {
            setDiscoveries(result.newlyUnlocked);
          }
        } else {
          // Failed combo — just move the dragged tile
          setCanvasTiles((prev) =>
            prev.map((ct) =>
              ct.instanceId === dragInstanceId
                ? { ...ct, x: ct.x + delta.x, y: ct.y + delta.y }
                : ct
            )
          );
        }
        return;
      }

      // --- Case 3: Canvas tile dragged within canvas (no target) → reposition
      if (source === "canvas") {
        const dragInstanceId = active.data.current.instanceId as string;
        setCanvasTiles((prev) =>
          prev.map((ct) =>
            ct.instanceId === dragInstanceId
              ? { ...ct, x: ct.x + delta.x, y: ct.y + delta.y }
              : ct
          )
        );
        return;
      }

      // --- Case 4: Palette tile dropped on canvas background → place it
      if (over?.id === "canvas") {
        // Calculate position relative to workspace
        const workspaceEl = document.querySelector(".workspace");
        const rect = workspaceEl?.getBoundingClientRect();
        if (!rect) return;

        // active.rect gives us the initial rect — use delta to compute final pos
        const initialRect = active.rect.current.initial;
        if (!initialRect) return;

        const finalX = initialRect.left + delta.x - rect.left;
        const finalY = initialRect.top + delta.y - rect.top;

        const id = `canvas-${nextInstanceId++}`;
        setCanvasTiles((prev) => [
          ...prev,
          { instanceId: id, tileId, x: Math.max(0, finalX), y: Math.max(0, finalY) },
        ]);
      }
    },
    []
  );

  // Error state
  if (error) {
    return (
      <div className="app app--loading">
        <h1>Little Philosophy</h1>
        <p>Failed to load game data: {error}</p>
      </div>
    );
  }

  // Loading state
  if (!gameInit) {
    return (
      <div className="app app--loading">
        <h1>Little Philosophy</h1>
        <p>Loading ideas…</p>
      </div>
    );
  }

  const { data, tileMap } = gameInit;
  const selectedTile = selectedTileId ? (tileMap.get(selectedTileId) ?? null) : null;

  return (
    <DndContext sensors={sensors} onDragStart={handleDragStart} onDragEnd={handleDragEnd}>
      <div className="app">
        <header className="app__header">
          <h1 className="app__title">Little Philosophy</h1>
          <ProgressBar
            discovered={gameState.unlockedTileIds.length}
            total={data.tiles.length}
          />
          <button type="button" className="app__reset" onClick={handleReset}>
            Reset
          </button>
        </header>

        <main className="app__main">
          <TilePalette
            unlockedTileIds={gameState.unlockedTileIds}
            tileMap={tileMap}
            onTileClick={setSelectedTileId}
          />

          <Workspace
            canvasTiles={canvasTiles}
            tileMap={tileMap}
            onClearAll={handleClearAll}
          />

          <CivilopediaPanel
            tile={selectedTile}
            onClose={() => setSelectedTileId(null)}
          />
        </main>

        <DiscoveryNotification
          tileIds={discoveries}
          tileMap={tileMap}
          onDismiss={handleDismissDiscovery}
        />
      </div>

      <DragOverlay>
        {activeDragId && gameInit ? (
          <DragOverlayChip tileId={activeDragId} tileMap={tileMap} />
        ) : null}
      </DragOverlay>
    </DndContext>
  );
}

export default App;
