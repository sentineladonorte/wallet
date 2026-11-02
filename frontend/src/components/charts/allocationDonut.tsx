'use client'

import React from 'react';
import { ArcElement, Chart as ChartJS, Tooltip } from 'chart.js';
import { Doughnut } from 'react-chartjs-2';
import { AllocationGroup } from '@/lib/allocation';
import { OTHER_COLOR } from '@/lib/assets';
import { formatPercent } from '@/lib/format';
import { useFormat } from '@/lib/privacy';

ChartJS.register(ArcElement, Tooltip);

const SURFACE = '#1a1a19';
const OTHERS_KEY = '__others__';
const TOOLTIP_LINE_LENGTH = 26;

/** O tooltip não passa da largura do canvas, então nomes longos de emissores precisam quebrar linha. */
const wrapLabel = (label: string) => {
  const lines: string[] = [];
  label.split(' ').forEach((word) => {
    const last = lines[lines.length - 1];
    if (last !== undefined && `${last} ${word}`.length <= TOOLTIP_LINE_LENGTH) {
      lines[lines.length - 1] = `${last} ${word}`;
    } else {
      lines.push(word);
    }
  });
  return lines;
};

const AllocationDonut: React.FC<{
  groups: AllocationGroup[];
  total: number;
  caption: string;
  onSelect: (group: AllocationGroup) => void;
}> = ({ groups, total, caption, onSelect }) => {
  const { formatCurrency } = useFormat();
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
      {/* O tooltip é desenhado no canvas: o texto central precisa ficar atrás dele. */}
      <div className="absolute inset-0 z-0 flex flex-col items-center justify-center pointer-events-none px-12 text-center">
        <span className="text-xs text-muted truncate max-w-full">{caption}</span>
        <span className="text-lg font-semibold tabular-nums">{formatCurrency(total)}</span>
      </div>
      <Doughnut
        style={{ position: 'relative', zIndex: 1 }}
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
              backgroundColor: '#242422',
              borderColor: '#383835',
              borderWidth: 1,
              titleColor: '#f0efec',
              bodyColor: '#f0efec',
              padding: 10,
              callbacks: {
                title: (items) => wrapLabel(slices[items[0].dataIndex].label),
                label: (context) => {
                  const slice = slices[context.dataIndex];
                  return ` ${formatCurrency(slice.value)} (${formatPercent(slice.share)})`;
                },
              },
            },
          },
        }}
      />
    </div>
  );
};

export default AllocationDonut;
