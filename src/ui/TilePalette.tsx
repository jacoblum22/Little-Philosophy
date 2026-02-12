/**
 * TilePalette — scrollable sidebar showing all unlocked tiles.
 *
 * Each tile is draggable. Clicking a tile opens it in the Civilopedia.
 */

import { useRef, useEffect } from "react";
import { useDraggable, useDroppable } from "@dnd-kit/core";
import type { Tile } from "../types/tile";
import type { TileMap } from "../hooks/dataLoader";
import { tileIcon } from "../utils/tileIcon";

interface TilePaletteProps {
  unlockedTileIds: string[];
  tileMap: TileMap;
  onTileClick: (tileId: string) => void;
  /** Whether the mobile drawer is open. */
  isOpen?: boolean;
  /** Source type of the currently active drag. */
  activeDragSource?: "canvas" | "palette" | null;
}

interface DraggableTileProps {
  tile: Tile;
  onClick: () => void;
}

/**
 * A single draggable tile chip inside the palette sidebar.
 * Tracks drag state to suppress click events after a completed drag.
 */
function DraggableTile({ tile, onClick }: DraggableTileProps) {
  const { attributes, listeners, setNodeRef, isDragging } =
    useDraggable({ id: `palette-${tile.id}`, data: { tileId: tile.id } });

  // When dragging, hide the original — the DragOverlay renders the visible copy
  const style: React.CSSProperties = {
    opacity: isDragging ? 0.3 : 1,
  };

  const wasDragging = useRef(false);

  useEffect(() => {
    if (isDragging) {
      wasDragging.current = true;
    } else {
      // Reset after a short delay to allow the click handler to see the flag
      const timer = setTimeout(() => {
        wasDragging.current = false;
      }, 50);
      return () => clearTimeout(timer);
    }
  }, [isDragging]);

  /** Suppress click if the pointer just finished a drag gesture. */
  const handleClick = () => {
    if (wasDragging.current) {
      wasDragging.current = false;
      return;
    }
    onClick();
  };

  return (
    <button
      ref={setNodeRef}
      type="button"
      className={`tile-chip tile-chip--${tile.type}`}
      style={style}
      onClick={handleClick}
      {...listeners}
      {...attributes}
    >
      {tileIcon(tile.type)}
      {tile.name}
    </button>
  );
}

/** Scrollable sidebar listing all unlocked tiles with drag-to-workspace and click-to-inspect. */
export default function TilePalette({
  unlockedTileIds,
  tileMap,
  onTileClick,
  isOpen,
  activeDragSource,
}: TilePaletteProps) {
  const tiles = unlockedTileIds
    .map((id) => tileMap.get(id))
    .filter((t): t is Tile => t !== undefined)
    .sort((a, b) => a.name.localeCompare(b.name));

  const { setNodeRef: setPaletteDropRef, isOver: isPaletteOver } = useDroppable({
    id: "palette",
    data: { source: "palette" },
  });

  // Only show the red drop-target highlight when a canvas tile is being dragged over
  const showDropHighlight = isPaletteOver && activeDragSource === "canvas";

  const cls = [
    "tile-palette",
    isOpen && "tile-palette--open",
    showDropHighlight && "tile-palette--drop-target",
  ].filter(Boolean).join(" ");

  return (
    <aside ref={setPaletteDropRef} className={cls}>
      <h2 className="tile-palette__title">Ideas</h2>
      <div className="tile-palette__list">
        {tiles.map((tile) => (
          <DraggableTile
            key={tile.id}
            tile={tile}
            onClick={() => onTileClick(tile.id)}
          />
        ))}
      </div>
    </aside>
  );
}
