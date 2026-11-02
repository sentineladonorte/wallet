'use client'

import React, { useState } from 'react';
import {
  CategoryScale, Chart as ChartJS, Legend, LinearScale, LineElement, PointElement, Tooltip,
} from 'chart.js';
import { Line } from 'react-chartjs-2';
import { formatCompact, formatCurrency } from '@/lib/format';
import { PositionHistory } from '@/types';

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Legend);

const RANGES = [
  { label: '3M', months: 3 },
  { label: '6M', months: 6 },
  { label: '1A', months: 12 },
  { label: 'Tudo', months: null },
];

const parseLabel = (label: string) => {
  const [day, month, year] = label.split('/').map(Number);
  return new Date(year, month - 1, day);
};

const shortLabel = (label: string) => `${label.slice(0, 6)}${label.slice(8)}`;

const firstIndexInRange = (labels: string[], months: number | null) => {
  if (months === null || labels.length === 0) return 0;
  const start = parseLabel(labels[labels.length - 1]);
  start.setMonth(start.getMonth() - months);
  const index = labels.findIndex((label) => parseLabel(label) >= start);
  return index === -1 ? 0 : index;
};

export const Patrimony: React.FC<{ data: PositionHistory }> = ({ data }) => {
  const [months, setMonths] = useState<number | null>(null);
  const start = firstIndexInRange(data.labels, months);
  const labels = data.labels.slice(start);
  const pointRadius = labels.length <= 2 ? 4 : 0;

  return (
    <div>
      <div role="group" aria-label="Período" className="flex gap-1 mb-3">
        {RANGES.map((range) => (
          <button
            key={range.label}
            type="button"
            aria-pressed={months === range.months}
            onClick={() => setMonths(range.months)}
            className={`px-2.5 py-1 rounded-md text-xs transition ${
              months === range.months ? 'bg-raised text-ink' : 'text-muted hover:text-ink'
            }`}
          >
            {range.label}
          </button>
        ))}
      </div>
      <div className="h-64">
        <Line
          aria-label="Evolução do patrimônio e do valor investido"
          options={{
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            elements: { point: { radius: pointRadius, hoverRadius: 4 }, line: { borderWidth: 2, tension: 0.15 } },
            scales: {
              x: { grid: { display: false }, ticks: { color: '#98978d', maxTicksLimit: 5, maxRotation: 0, callback: (value) => shortLabel(labels[Number(value)]) } },
              y: {
                grid: { color: '#2a2a28' },
                border: { display: false },
                ticks: { color: '#98978d', callback: (value) => formatCompact(Number(value)) },
              },
            },
            plugins: {
              legend: { position: 'top', align: 'end', labels: { color: '#c3c2b7', boxWidth: 12, boxHeight: 2 } },
              tooltip: {
                callbacks: { label: (context) => ` ${context.dataset.label}: ${formatCurrency(context.parsed.y)}` },
              },
            },
          }}
          data={{
            labels,
            datasets: [
              { label: 'Patrimônio', data: data.values.slice(start), borderColor: '#3987e5', backgroundColor: '#3987e5' },
              { label: 'Investido', data: data.invested.slice(start), borderColor: '#d95926', backgroundColor: '#d95926' },
            ],
          }}
        />
      </div>
    </div>
  );
};
