/**
 * DiscoveryNotification — animated popup when a new tile is discovered.
 */

import { useEffect, useState, useRef } from "react";
import type { TileMap } from "../hooks/dataLoader";

interface DiscoveryNotificationProps {
  tileIds: string[];
  tileMap: TileMap;
  onDismiss: () => void;
}

export default function DiscoveryNotification({
  tileIds,
  tileMap,
  onDismiss,
}: DiscoveryNotificationProps) {
  const [visible, setVisible] = useState(true);
  const onDismissRef = useRef(onDismiss);
  onDismissRef.current = onDismiss;

  useEffect(() => {
    if (tileIds.length === 0) return;
    setVisible(true);
    const timer = setTimeout(() => {
      setVisible(false);
      onDismissRef.current();
    }, 3000);
    return () => clearTimeout(timer);
  }, [tileIds]);

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
