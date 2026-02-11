/**
 * TilePalette — scrollable sidebar showing all unlocked tiles.
 *
 * Each tile is draggable. Clicking a tile opens it in the Civilopedia.
 */

import { useRef, useEffect } from "react";
import { useDraggable } from "@dnd-kit/core";
import type { Tile } from "../types/tile";
import type { TileMap } from "../hooks/dataLoader";

interface TilePaletteProps {
  unlockedTileIds: string[];
  tileMap: TileMap;
  onTileClick: (tileId: string) => void;
}

interface DraggableTileProps {
  tile: Tile;
  onClick: () => void;
}

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
      className={`tile-chip tile-chip--${tile.type}`}
      style={style}
      onClick={handleClick}
      {...listeners}
      {...attributes}
    >
      {tile.type === "philosopher" && "🧠 "}
      {tile.type === "writing" && "📜 "}
      {tile.name}
    </button>
  );
}

export default function TilePalette({
  unlockedTileIds,
  tileMap,
  onTileClick,
}: TilePaletteProps) {
  const tiles = unlockedTileIds
    .map((id) => tileMap.get(id))
    .filter((t): t is Tile => t !== undefined)
    .sort((a, b) => a.name.localeCompare(b.name));

  return (
    <aside className="tile-palette">
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
