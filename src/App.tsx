import { useState, useCallback, useRef, useEffect } from "react";
import {
  DndContext,
  DragOverlay,
  type DragStartEvent,
  type DragEndEvent,
  PointerSensor,
  useSensor,
  useSensors,
  pointerWithin,
  type CollisionDetection,
} from "@dnd-kit/core";

import { useGameInit } from "./hooks/useGameInit";
import { useGameState } from "./hooks/useGameState";
import { attemptCombine } from "./hooks/useCombine";
import { resetGame } from "./engine/gameState";

import TilePalette from "./ui/TilePalette";
import Workspace from "./ui/Workspace";
import type { CanvasTile, TileAnimation } from "./ui/Workspace";
import type { TileMap } from "./hooks/dataLoader";
import DiscoveryNotification from "./ui/DiscoveryNotification";
import CivilopediaPanel from "./ui/CivilopediaPanel";
import ProgressBar from "./ui/ProgressBar";
import ParticleCanvas from "./particles/ParticleCanvas";
import type { ParticleHandle } from "./particles/ParticleCanvas";
import TrashZone from "./ui/TrashZone";

import "./App.css";

/** Icon prefix for a tile type. */
const TILE_ICONS: Record<string, string> = {
  philosopher: "🧠 ",
  writing: "📜 ",
};

/** Return the emoji icon prefix for the given tile type, or empty string if none. */
function tileIcon(type: string): string {
  return TILE_ICONS[type] ?? "";
}

/** Overlay chip that follows the cursor during drag. */
function DragOverlayChip({ tileId, tileMap }: { tileId: string; tileMap: TileMap }) {
  const tile = tileMap.get(tileId);
  const typeCls = tile ? `tile-chip--${tile.type}` : "";
  return (
    <div className={`tile-chip tile-chip--dragging ${typeCls}`}>
      {tile ? tileIcon(tile.type) : ""}
      {tile?.name ?? tileId}
    </div>
  );
}

/**
 * Custom collision detection: uses pointerWithin for most droppables,
 * but for the sidebar palette uses the dragged element's center point
 * so deletion triggers when the tile's center crosses the sidebar edge.
 * When the center is inside the palette, palette wins over other targets.
 */
const collisionDetection: CollisionDetection = (args) => {
  const { collisionRect, droppableRects, droppableContainers } = args;
  const centerX = collisionRect.left + collisionRect.width / 2;
  const centerY = collisionRect.top + collisionRect.height / 2;

  // Check if the dragged element's center is inside the palette rect
  const paletteRect = droppableRects.get("palette");
  if (paletteRect) {
    const inside =
      centerX >= paletteRect.left &&
      centerX <= paletteRect.left + paletteRect.width &&
      centerY >= paletteRect.top &&
      centerY <= paletteRect.top + paletteRect.height;

    if (inside) {
      // Palette wins — return it as the sole collision
      const paletteContainer = droppableContainers.find(
        (c) => c.id === "palette"
      );
      if (paletteContainer) {
        return [
          { id: "palette", data: { droppableContainer: paletteContainer, value: 0 } },
        ];
      }
    }
  }

  // Default: pointer-based collision for everything else
  return pointerWithin(args);
};

/** Root application component — manages DnD context, game state, and panel layout. */
function App() {
  const { init: gameInit, error } = useGameInit();
  const gameState = useGameState();

  // Freeform canvas tiles
  const [canvasTiles, setCanvasTiles] = useState<CanvasTile[]>([]);
  const canvasTilesRef = useRef(canvasTiles);
  canvasTilesRef.current = canvasTiles;

  // Instance ID counter scoped to component lifecycle
  const nextInstanceId = useRef(1);

  // Workspace element ref (avoids document.querySelector)
  const workspaceRef = useRef<HTMLElement>(null);

  // Particle system handle (for burst on discovery)
  const particleHandle = useRef<ParticleHandle | null>(null);

  // Discovery notification
  const [discoveries, setDiscoveries] = useState<string[]>([]);

  // Canvas tile animations (appear, combo-success, shake)
  const [animatingTiles, setAnimatingTiles] = useState<Map<string, TileAnimation>>(new Map());

  /** Queue a CSS animation class on a canvas tile instance. */
  const addAnimation = useCallback((instanceId: string, anim: TileAnimation) => {
    setAnimatingTiles((prev) => new Map(prev).set(instanceId, anim));
  }, []);

  /** Remove a completed animation from the tracking map. */
  const clearAnimation = useCallback((instanceId: string) => {
    setAnimatingTiles((prev) => {
      const next = new Map(prev);
      next.delete(instanceId);
      return next;
    });
  }, []);

  // Civilopedia selected tile
  const [selectedTileId, setSelectedTileId] = useState<string | null>(null);

  // Mobile sidebar drawer state
  const [sidebarOpen, setSidebarOpen] = useState(false);

  // Active drag tile ID and source (for DragOverlay + trash zone visibility)
  const [activeDragId, setActiveDragId] = useState<string | null>(null);
  const [activeDragSource, setActiveDragSource] = useState<string | null>(null);

  // DnD sensors — add a small distance threshold so clicks still work
  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: { distance: 5 },
    })
  );

  /** Track the tile ID and source type when a drag begins. */
  const handleDragStart = useCallback((event: DragStartEvent) => {
    const tileId = event.active.data.current?.tileId as string | undefined;
    const source = event.active.data.current?.source as string | undefined;
    setActiveDragId(tileId ?? null);
    setActiveDragSource(source ?? null);
  }, []);

  /** Remove a single canvas tile by instanceId. */
  const removeCanvasTile = useCallback((instanceId: string) => {
    setCanvasTiles((prev) => prev.filter((ct) => ct.instanceId !== instanceId));
  }, []);

  /** Reset entire game: clear save data, canvas tiles, and UI state. */
  const handleReset = useCallback(() => {
    resetGame();
    setCanvasTiles([]);
    setDiscoveries([]);
    setSelectedTileId(null);
  }, []);

  /** Remove all tiles from the workspace canvas without affecting save data. */
  const handleClearAll = useCallback(() => {
    setCanvasTiles([]);
  }, []);

  /** Select a tile in the Civilopedia and close mobile sidebar. */
  const handleTileSelect = useCallback((tileId: string) => {
    setSelectedTileId(tileId);
    setSidebarOpen(false);
  }, []);

  /** Close any mobile overlay panel. */
  const handleOverlayClose = useCallback(() => {
    setSidebarOpen(false);
    setSelectedTileId(null);
  }, []);

  /** Clear the discovery notification popup. */
  const handleDismissDiscovery = useCallback(() => {
    setDiscoveries([]);
  }, []);

  // Keyboard: Escape closes open panels
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        if (selectedTileId) {
          setSelectedTileId(null);
        } else if (sidebarOpen) {
          setSidebarOpen(false);
        } else if (discoveries.length > 0) {
          setDiscoveries([]);
        }
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [selectedTileId, sidebarOpen, discoveries.length]);

  /**
   * Handle the end of a drag operation.
   * Routes to one of five cases: trash/sidebar delete, palette→canvas combine,
   * canvas→canvas combine, canvas reposition, or palette→canvas placement.
   */
  const handleDragEnd = useCallback(
    (event: DragEndEvent) => {
      setActiveDragId(null);
      setActiveDragSource(null);
      const { active, over, delta } = event;
      if (!active.data.current) return;

      const source = active.data.current.source as string | undefined;
      const tileId = active.data.current.tileId as string;

      // --- Case 0: Dropped on trash zone or sidebar → delete the canvas tile
      if ((over?.id === "trash" || over?.id === "palette") && source === "canvas") {
        const dragInstanceId = active.data.current.instanceId as string;
        removeCanvasTile(dragInstanceId);
        return;
      }

      // --- Case 1: Palette tile dropped on a canvas tile → combine
      if (over?.data.current?.instanceId && source !== "canvas") {
        const targetTileId = over.data.current.tileId as string;
        const targetInstanceId = over.data.current.instanceId as string;

        const result = attemptCombine(tileId, targetTileId);
        if (result.comboTileId) {
          // Remove the target tile, place the result at its position
          const target = canvasTilesRef.current.find((ct) => ct.instanceId === targetInstanceId);
          const resultId = `canvas-${nextInstanceId.current++}`;
          setCanvasTiles((prev) => [
            ...prev.filter((ct) => ct.instanceId !== targetInstanceId),
            {
              instanceId: resultId,
              tileId: result.comboTileId!,
              x: target?.x ?? 100,
              y: target?.y ?? 100,
            },
          ]);
          addAnimation(resultId, "combo-success");
          if (result.newlyUnlocked.length > 0) {
            setDiscoveries(result.newlyUnlocked);
            particleHandle.current?.burst();
          }
        } else {
          // Failed combo — place the palette tile near the target, shake target
          addAnimation(targetInstanceId, "shake");
          const target = canvasTilesRef.current.find((ct) => ct.instanceId === targetInstanceId);
          if (target) {
            const id = `canvas-${nextInstanceId.current++}`;
            setCanvasTiles((prev) => [
              ...prev,
              { instanceId: id, tileId, x: target.x + 50, y: target.y + 40 },
            ]);
            addAnimation(id, "appear");
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
          const resultId = `canvas-${nextInstanceId.current++}`;
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
          addAnimation(resultId, "combo-success");
          if (result.newlyUnlocked.length > 0) {
            setDiscoveries(result.newlyUnlocked);
            particleHandle.current?.burst();
          }
        } else {
          // Failed combo — move the dragged tile and shake it
          setCanvasTiles((prev) =>
            prev.map((ct) =>
              ct.instanceId === dragInstanceId
                ? { ...ct, x: ct.x + delta.x, y: ct.y + delta.y }
                : ct
            )
          );
          addAnimation(dragInstanceId, "shake");
        }
        return;
      }

      // --- Case 3: Canvas tile dragged within canvas (no target) → reposition
      // Only reposition when dropped on the workspace background, not when
      // dropped outside (e.g. onto the sidebar) — leave tile in place.
      if (source === "canvas" && over?.id === "canvas") {
        const dragInstanceId = active.data.current.instanceId as string;
        const wsRect = workspaceRef.current?.getBoundingClientRect();
        const maxX = wsRect ? wsRect.width - 40 : Infinity;
        const maxY = wsRect ? wsRect.height - 30 : Infinity;
        setCanvasTiles((prev) =>
          prev.map((ct) => {
            if (ct.instanceId !== dragInstanceId) return ct;
            return {
              ...ct,
              x: Math.max(0, Math.min(ct.x + delta.x, maxX)),
              y: Math.max(0, Math.min(ct.y + delta.y, maxY)),
            };
          })
        );
        return;
      }

      // --- Case 4: Palette tile dropped on canvas background → place it
      if (over?.id === "canvas") {
        // Calculate position relative to workspace
        const rect = workspaceRef.current?.getBoundingClientRect();
        if (!rect) return;

        // active.rect gives us the initial rect — use delta to compute final pos
        const initialRect = active.rect.current.initial;
        if (!initialRect) return;

        const rawX = initialRect.left + delta.x - rect.left;
        const rawY = initialRect.top + delta.y - rect.top;
        const maxX = rect.width - 40;
        const maxY = rect.height - 30;

        const id = `canvas-${nextInstanceId.current++}`;
        setCanvasTiles((prev) => [
          ...prev,
          {
            instanceId: id,
            tileId,
            x: Math.max(0, Math.min(rawX, maxX)),
            y: Math.max(0, Math.min(rawY, maxY)),
          },
        ]);
        addAnimation(id, "appear");
      }
    },
    [addAnimation, removeCanvasTile]
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
  const anyPanelOpen = sidebarOpen || selectedTileId !== null;

  return (
    <>
    <ParticleCanvas onReady={(h) => { particleHandle.current = h; }} />
    <DndContext sensors={sensors} collisionDetection={collisionDetection} onDragStart={handleDragStart} onDragEnd={handleDragEnd}>
      <div className="app">
        <header className="app__header">
          <button
            type="button"
            className="app__menu-toggle"
            aria-label={sidebarOpen ? "Close sidebar" : "Open sidebar"}
            onClick={() => setSidebarOpen((v) => !v)}
          >
            {sidebarOpen ? "✕" : "☰"}
          </button>
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
          {/* Overlay backdrop for mobile panels */}
          <div
            className={`app__overlay${anyPanelOpen ? " app__overlay--visible" : ""}`}
            onClick={handleOverlayClose}
            aria-hidden="true"
          />

          <TilePalette
            unlockedTileIds={gameState.unlockedTileIds}
            tileMap={tileMap}
            onTileClick={handleTileSelect}
            isOpen={sidebarOpen}
            activeDragSource={activeDragSource}
          />

          <Workspace
            canvasTiles={canvasTiles}
            tileMap={tileMap}
            onClearAll={handleClearAll}
            onTileClick={handleTileSelect}
            workspaceRef={workspaceRef}
            animatingTiles={animatingTiles}
            onAnimationEnd={clearAnimation}
          />

          <TrashZone visible={activeDragSource === "canvas"} />

          <CivilopediaPanel
            tile={selectedTile}
            onClose={() => setSelectedTileId(null)}
            isOpen={selectedTileId !== null}
          />
        </main>

        <DiscoveryNotification
          tileIds={discoveries}
          tileMap={tileMap}
          onDismiss={handleDismissDiscovery}
        />
      </div>

      <DragOverlay>
        {activeDragId ? (
          <DragOverlayChip tileId={activeDragId} tileMap={tileMap} />
        ) : null}
      </DragOverlay>
    </DndContext>
    </>
  );
}

export default App;
