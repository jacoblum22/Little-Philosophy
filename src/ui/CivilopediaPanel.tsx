/**
 * CivilopediaPanel — detail view for a selected tile.
 *
 * Shows the tile's name, type, quote, description, and tags.
 */

import type { Tile } from "../types/tile";
import type { PhilosopherTile, WritingTile } from "../types/tile";

interface CivilopediaPanelProps {
  tile: Tile | null;
  onClose: () => void;
  /** Whether the mobile panel is open. */
  isOpen?: boolean;
}

/** Right-side detail panel showing a tile's name, type, quote, description, and tags. */
export default function CivilopediaPanel({
  tile,
  onClose,
  isOpen,
}: CivilopediaPanelProps) {
  if (!tile) return null;

  const isPhilosopher = tile.type === "philosopher";
  const isWriting = tile.type === "writing";

  const cls = `civilopedia${isOpen ? " civilopedia--open" : ""}`;

  return (
    <aside className={cls}>
      <button type="button" className="civilopedia__close" onClick={onClose} aria-label="Close panel">
        ✕
      </button>

      <h2 className="civilopedia__name">{tile.name}</h2>

      <span className={`civilopedia__type civilopedia__type--${tile.type}`}>
        {tile.type}
      </span>

      {isPhilosopher && (
        <div className="civilopedia__meta">
          {(tile as PhilosopherTile).born && (
            <span>Born: {(tile as PhilosopherTile).born}</span>
          )}
          {(tile as PhilosopherTile).died && (
            <span>Died: {(tile as PhilosopherTile).died}</span>
          )}
          {tile.tradition && <span>Tradition: {tile.tradition}</span>}
        </div>
      )}

      {isWriting && (
        <div className="civilopedia__meta">
          {(tile as WritingTile).written && (
            <span>Written: {(tile as WritingTile).written}</span>
          )}
          {tile.tradition && <span>Tradition: {tile.tradition}</span>}
        </div>
      )}

      {tile.quote && (
        <blockquote className="civilopedia__quote">
          "{tile.quote}"
          {tile.quoteAuthor && (
            <cite className="civilopedia__cite">— {tile.quoteAuthor}</cite>
          )}
        </blockquote>
      )}

      <p className="civilopedia__description">{tile.description}</p>

      {tile.tags.length > 0 && (
        <div className="civilopedia__tags">
          {tile.tags.map((tag, i) => (
            <span key={`${tag}-${i}`} className="civilopedia__tag">
              #{tag}
            </span>
          ))}
        </div>
      )}
    </aside>
  );
}
