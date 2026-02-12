/**
 * ProgressBar — shows "X of Y discovered" at the top.
 */

interface ProgressBarProps {
  discovered: number;
  total: number;
}

/** Neon-glow progress bar showing discovery count as a percentage. */
export default function ProgressBar({ discovered, total }: ProgressBarProps) {
  const pct = total > 0 ? Math.round((discovered / total) * 100) : 0;

  return (
    <div
      className="progress-bar"
      role="progressbar"
      aria-valuenow={discovered}
      aria-valuemin={0}
      aria-valuemax={total}
      aria-label={`${discovered} of ${total} ideas discovered`}
    >
      <div className="progress-bar__track">
        <div
          className="progress-bar__fill"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="progress-bar__label">
        {discovered} / {total} ideas discovered ({pct}%)
      </span>
    </div>
  );
}
