/**
 * Workspace — freeform canvas where players drag tiles and combine them.
 *
 * Tiles from the palette can be dropped anywhere on the canvas.
 * Canvas tiles can be dragged and dropped on each other to combine.
 * Style inspired by Little Alchemy.
 */

import { useDroppable, useDraggable } from "@dnd-kit/core";
import type { TileMap } from "../hooks/dataLoader";
import type { Tile } from "../types/tile";

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
}

interface CanvasTileChipProps {
  instance: CanvasTile;
  tile: Tile | undefined;
}

function CanvasTileChip({ instance, tile }: CanvasTileChipProps) {
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

  return (
    <div
      ref={(node) => {
        setDragRef(node);
        setDropRef(node);
      }}
      className={`canvas-tile ${typeCls} ${isDragging ? "canvas-tile--dragging" : ""} ${highlight ? "canvas-tile--highlight" : ""}`}
      style={{
        position: "absolute",
        left: instance.x,
        top: instance.y,
      }}
      {...listeners}
      {...attributes}
    >
      {tile?.type === "philosopher" && "🧠 "}
      {tile?.type === "writing" && "📜 "}
      {tile?.name ?? instance.tileId}
    </div>
  );
}

export default function Workspace({
  canvasTiles,
  tileMap,
  onClearAll,
}: WorkspaceProps) {
  const { setNodeRef, isOver } = useDroppable({
    id: "canvas",
    data: { source: "canvas-bg" },
  });

  return (
    <section
      ref={setNodeRef}
      className={`workspace ${isOver ? "workspace--over" : ""}`}
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
        />
      ))}

      {canvasTiles.length > 0 && (
        <button
          type="button"
          className="workspace__clear"
          onClick={onClearAll}
        >
          Clear All
        </button>
      )}
    </section>
  );
}
