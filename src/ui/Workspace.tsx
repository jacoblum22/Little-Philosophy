/**
 * Workspace — freeform canvas where players drag tiles and combine them.
 *
 * Tiles from the palette can be dropped anywhere on the canvas.
 * Canvas tiles can be dragged and dropped on each other to combine.
 * Style inspired by Little Alchemy.
 */

import type { RefObject } from "react";
import { useDroppable, useDraggable } from "@dnd-kit/core";
import type { TileMap } from "../hooks/dataLoader";
import type { Tile } from "../types/tile";

/** Icon prefix for a tile type. */
const TILE_ICONS: Record<string, string> = {
  philosopher: "🧠 ",
  writing: "📜 ",
};

function tileIcon(type: string): string {
  return TILE_ICONS[type] ?? "";
}

/** A tile instance placed on the canvas. */
export interface CanvasTile {
  instanceId: string;
  tileId: string;
  x: number;
  y: number;
}

interface WorkspaceProps {
  canvasTiles: CanvasTile[];
  tileMap: TileMap;
  onClearAll: () => void;
  onTileClick?: (tileId: string) => void;
  workspaceRef: RefObject<HTMLElement | null>;
}

interface CanvasTileChipProps {
  instance: CanvasTile;
  tile: Tile | undefined;
  onClick?: () => void;
}

function CanvasTileChip({ instance, tile, onClick }: CanvasTileChipProps) {
  const { attributes, listeners, setNodeRef: setDragRef, isDragging } = useDraggable({
    id: instance.instanceId,
    data: { tileId: instance.tileId, instanceId: instance.instanceId, source: "canvas" },
  });

  const { setNodeRef: setDropRef, isOver } = useDroppable({
    id: `canvas-drop-${instance.instanceId}`,
    data: { tileId: instance.tileId, instanceId: instance.instanceId },
  });

  const typeCls = tile ? `canvas-tile--${tile.type}` : "";
  const highlight = isOver && !isDragging;
  const cls = [
    "canvas-tile",
    typeCls,
    isDragging && "canvas-tile--dragging",
    highlight && "canvas-tile--highlight",
  ].filter(Boolean).join(" ");

  return (
    <div
      ref={(node) => {
        setDragRef(node);
        setDropRef(node);
      }}
      className={cls}
      style={{
        position: "absolute",
        left: instance.x,
        top: instance.y,
      }}
      {...listeners}
      {...attributes}
      onClick={onClick}
    >
      {tile ? tileIcon(tile.type) : ""}
      {tile?.name ?? instance.tileId}
    </div>
  );
}

export default function Workspace({
  canvasTiles,
  tileMap,
  onClearAll,
  onTileClick,
  workspaceRef,
}: WorkspaceProps) {
  const { setNodeRef, isOver } = useDroppable({
    id: "canvas",
    data: { source: "canvas-bg" },
  });

  return (
    <section
      ref={(node) => {
        setNodeRef(node);
        (workspaceRef as React.MutableRefObject<HTMLElement | null>).current = node;
      }}
      className={`workspace${isOver ? " workspace--over" : ""}`}
    >
      {canvasTiles.length === 0 && (
        <div className="workspace__hint">
          Drag ideas here to explore
        </div>
      )}

      {canvasTiles.map((ct) => (
        <CanvasTileChip
          key={ct.instanceId}
          instance={ct}
          tile={tileMap.get(ct.tileId)}
          onClick={() => onTileClick?.(ct.tileId)}
        />
      ))}

      {canvasTiles.length > 0 && (
        <button
          type="button"
          className="workspace__clear"
          aria-label="Clear all tiles from workspace"
          onClick={onClearAll}
        >
          Clear All
        </button>
      )}
    </section>
  );
}
