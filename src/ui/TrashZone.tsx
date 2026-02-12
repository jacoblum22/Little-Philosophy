/**
 * TrashZone — a drop target that appears at the bottom of the screen
 * when dragging a canvas tile, allowing individual tile deletion.
 */

import { useDroppable } from "@dnd-kit/core";

interface TrashZoneProps {
  /** Whether the trash zone should be visible (only during canvas tile drags). */
  visible: boolean;
}

export default function TrashZone({ visible }: TrashZoneProps) {
  const { setNodeRef, isOver } = useDroppable({
    id: "trash",
    data: { source: "trash" },
  });

  const cls = [
    "trash-zone",
    visible && "trash-zone--visible",
    isOver && "trash-zone--active",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div ref={setNodeRef} className={cls} aria-label="Drop here to delete tile">
      <span className="trash-zone__icon" aria-hidden="true">
        🗑️
      </span>
      <span className="trash-zone__label">
        {isOver ? "Release to delete" : "Drop here to remove"}
      </span>
    </div>
  );
}
