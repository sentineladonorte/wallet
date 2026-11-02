import React from 'react';
import { formatPercent } from '@/lib/format';

/** Barra da alocação atual com um traço na posição da meta. */
const TargetBar: React.FC<{ current: number; target: number | null; label: string }> = ({ current, target, label }) => (
  <div
    role="meter"
    aria-label={`${label}: atual ${formatPercent(current)}${target === null ? ', sem meta' : `, meta ${formatPercent(target)}`}`}
    aria-valuemin={0}
    aria-valuemax={100}
    aria-valuenow={Math.min(current, 100)}
    className="relative h-1.5 rounded-full bg-raised"
  >
    <div className="h-full rounded-full bg-accent" style={{ width: `${Math.min(current, 100)}%` }} />
    {target !== null && (
      <div aria-hidden className="absolute -top-1 -bottom-1 w-0.5 rounded bg-ink" style={{ left: `${Math.min(target, 100)}%` }} />
    )}
  </div>
);

export default TargetBar;
