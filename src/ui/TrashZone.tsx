/**
 * TrashZone — a drop target that appears at the bottom of the screen
 * when dragging a canvas tile, allowing individual tile deletion.
 */

import { useDroppable } from "@dnd-kit/core";

interface TrashZoneProps {
  /** Whether the trash zone should be visible (only during canvas tile drags). */
  visible: boolean;
}

/** Mobile-only drop target that appears when dragging a canvas tile, allowing deletion. */
export default function TrashZone({ visible }: TrashZoneProps) {
  const { setNodeRef, isOver } = useDroppable({
    id: "trash",
    data: { source: "trash" },
    disabled: !visible,
  });

  const label = isOver ? "Release to delete" : "Drop here to remove";

  const cls = [
    "trash-zone",
    visible && "trash-zone--visible",
    isOver && "trash-zone--active",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div ref={setNodeRef} className={cls} aria-label={label}>
      <span className="trash-zone__icon" aria-hidden="true">
        🗑️
      </span>
      <span className="trash-zone__label" aria-live="polite">
        {label}
      </span>
    </div>
  );
}
