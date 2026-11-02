'use client'

import React from 'react';
import { ArcElement, Chart as ChartJS, Tooltip } from 'chart.js';
import { Doughnut } from 'react-chartjs-2';
import { AllocationGroup } from '@/lib/allocation';
import { OTHER_COLOR } from '@/lib/assets';
import { formatCurrency, formatPercent } from '@/lib/format';

ChartJS.register(ArcElement, Tooltip);

const SURFACE = '#1a1a19';
const OTHERS_KEY = '__others__';

const AllocationDonut: React.FC<{
  groups: AllocationGroup[];
  total: number;
  caption: string;
  onSelect: (group: AllocationGroup) => void;
}> = ({ groups, total, caption, onSelect }) => {
  const visible = groups.filter((group) => !group.folded);
  const folded = groups.filter((group) => group.folded);
  const slices = folded.length
    ? [...visible, {
        key: OTHERS_KEY,
        label: `Outros (${folded.length})`,
        value: folded.reduce((sum, group) => sum + group.value, 0),
        share: folded.reduce((sum, group) => sum + group.share, 0),
        count: folded.length,
        color: OTHER_COLOR,
        folded: true,
      }]
    : visible;

  return (
    <div className="relative w-full max-w-[280px] aspect-square mx-auto">
      <Doughnut
        aria-label={`Distribuição: ${slices.map((slice) => `${slice.label} ${formatPercent(slice.share)}`).join(', ')}`}
        data={{
          labels: slices.map((slice) => slice.label),
          datasets: [{
            data: slices.map((slice) => slice.value),
            backgroundColor: slices.map((slice) => slice.color),
            borderColor: SURFACE,
            borderWidth: 2,
            hoverOffset: 6,
          }],
        }}
        options={{
          cutout: '64%',
          maintainAspectRatio: false,
          layout: { padding: 6 },
          onClick: (_event, elements) => {
            const slice = elements.length ? slices[elements[0].index] : undefined;
            if (slice && slice.key !== OTHERS_KEY) onSelect(slice);
          },
          onHover: (event, elements) => {
            const target = event.native?.target as HTMLElement | undefined;
            if (!target) return;
            const slice = elements.length ? slices[elements[0].index] : undefined;
            target.style.cursor = slice && slice.key !== OTHERS_KEY ? 'pointer' : 'default';
          },
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                label: (context) => {
                  const slice = slices[context.dataIndex];
                  return ` ${formatCurrency(slice.value)} (${formatPercent(slice.share)})`;
                },
              },
            },
          },
        }}
      />
      <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none px-12 text-center">
        <span className="text-xs text-muted truncate max-w-full">{caption}</span>
        <span className="text-lg font-semibold tabular-nums">{formatCurrency(total)}</span>
      </div>
    </div>
  );
};

export default AllocationDonut;
