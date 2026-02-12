/**
 * DiscoveryNotification — animated popup when a new tile is discovered.
 */

import { useEffect, useState, useRef, useMemo } from "react";
import type { TileMap } from "../hooks/dataLoader";

interface DiscoveryNotificationProps {
  tileIds: string[];
  tileMap: TileMap;
  onDismiss: () => void;
}

/** Animated popup that shows newly discovered tile names, auto-dismisses after 3 seconds. */
export default function DiscoveryNotification({
  tileIds,
  tileMap,
  onDismiss,
}: DiscoveryNotificationProps) {
  const [visible, setVisible] = useState(true);
  const onDismissRef = useRef(onDismiss);
  onDismissRef.current = onDismiss;

  // Derive a stable key from tileIds content so the timer only resets
  // when the actual IDs change, not when the parent creates a new array reference.
  const tileKey = useMemo(() => JSON.stringify(tileIds), [tileIds]);

  // Using a ref for onDismiss to avoid resetting the timer on every render
  // when the parent doesn't memoize the callback.
  useEffect(() => {
    if (tileIds.length === 0) return;
    setVisible(true);
    const timer = setTimeout(() => {
      setVisible(false);
      onDismissRef.current();
    }, 3000);
    return () => clearTimeout(timer);
  }, [tileKey]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!visible || tileIds.length === 0) return null;

  return (
    <div className="discovery-notification" onClick={onDismiss}>
      {tileIds.map((id) => {
        const tile = tileMap.get(id);
        return (
          <div key={id} className="discovery-notification__item">
            <span className="discovery-notification__label">✨ Discovered</span>
            <span className="discovery-notification__name">
              {tile?.name ?? id}
            </span>
          </div>
        );
      })}
    </div>
  );
}
