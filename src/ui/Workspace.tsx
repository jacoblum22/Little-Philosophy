/**
 * Workspace — freeform canvas where players drag tiles and combine them.
 *
 * Tiles from the palette can be dropped anywhere on the canvas.
 * Canvas tiles can be dragged and dropped on each other to combine.
 * Style inspired by Little Alchemy.
 */

import { type RefObject } from "react";
import { useDroppable, useDraggable } from "@dnd-kit/core";
import type { TileMap } from "../hooks/dataLoader";
import type { Tile } from "../types/tile";
import { tileIcon } from "../utils/tileIcon";

/** A tile instance placed on the canvas. */
export interface CanvasTile {
  instanceId: string;
  tileId: string;
  x: number;
  y: number;
}

/** Animation state for canvas tile feedback. */
export type TileAnimation = "appear" | "combo-success" | "shake";

interface WorkspaceProps {
  canvasTiles: CanvasTile[];
  tileMap: TileMap;
  onClearAll: () => void;
  onTileClick?: (tileId: string) => void;
  workspaceRef: RefObject<HTMLElement | null>;
  /** Map of instanceId → animation class to apply. */
  animatingTiles?: Map<string, TileAnimation>;
  /** Callback when an animation ends on a tile. */
  onAnimationEnd?: (instanceId: string) => void;
}

interface CanvasTileChipProps {
  instance: CanvasTile;
  tile: Tile | undefined;
  onClick?: () => void;
  animation?: TileAnimation;
  onAnimationEnd?: () => void;
}

/** A single tile chip on the workspace canvas — draggable, droppable, and animatable. */
function CanvasTileChip({ instance, tile, onClick, animation, onAnimationEnd }: CanvasTileChipProps) {
  const { attributes, listeners, setNodeRef: setDragRef, isDragging } = useDraggable({
    id: instance.instanceId,
    data: { tileId: instance.tileId, instanceId: instance.instanceId, source: "canvas" },
  });

  const { setNodeRef: setDropRef, isOver } = useDroppable({
    id: `canvas-drop-${instance.instanceId}`,
    data: { tileId: instance.tileId, instanceId: instance.instanceId },
  });

  /** Forward CSS animationend event to the parent so it can clear the animation state. */
  const handleAnimEnd = (e: React.AnimationEvent) => {
    // Only respond to animations on this element (not bubbled from children)
    if (e.currentTarget === e.target) onAnimationEnd?.();
  };

  const typeCls = tile ? `canvas-tile--${tile.type}` : "";
  const highlight = isOver && !isDragging;
  const cls = [
    "canvas-tile",
    typeCls,
    isDragging && "canvas-tile--dragging",
    highlight && "canvas-tile--highlight",
    animation && `canvas-tile--${animation}`,
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
      onAnimationEnd={handleAnimEnd}
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
  animatingTiles,
  onAnimationEnd,
}: WorkspaceProps) {
  const { setNodeRef, isOver } = useDroppable({
    id: "canvas",
    data: { source: "canvas-bg" },
  });

  return (
    <section
      ref={(node) => {
        setNodeRef(node);
        workspaceRef.current = node;
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
          animation={animatingTiles?.get(ct.instanceId)}
          onAnimationEnd={() => onAnimationEnd?.(ct.instanceId)}
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
