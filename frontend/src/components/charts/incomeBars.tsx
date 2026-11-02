'use client'

import React from 'react';
import { BarElement, CategoryScale, Chart as ChartJS, Legend, LinearScale, Tooltip } from 'chart.js';
import { Bar } from 'react-chartjs-2';
import { INCOME_COLORS, INCOME_TYPES, monthKey, monthsBetween } from '@/lib/income';
import { useFormat } from '@/lib/privacy';
import { IncomeRow } from '@/types';

ChartJS.register(BarElement, CategoryScale, LinearScale, Tooltip, Legend);

const SURFACE = '#1a1a19';

const shortMonth = (key: string) => `${key.slice(5)}/${key.slice(2, 4)}`;

const IncomeBars: React.FC<{ rows: IncomeRow[] }> = ({ rows }) => {
  const { formatCompact, formatCurrency } = useFormat();
  const keys = rows.map((row) => monthKey(row.date)).sort();
  if (keys.length === 0) return null;

  const months = monthsBetween(keys[0], keys[keys.length - 1]);
  const types = INCOME_TYPES.filter((type) => rows.some((row) => row.type === type));
  const totals: Record<string, Record<string, number>> = {};
  rows.forEach((row) => {
    const month = monthKey(row.date);
    totals[month] = totals[month] || {};
    totals[month][row.type] = (totals[month][row.type] || 0) + row.value;
  });

  return (
    <div className="h-72">
      <Bar
        aria-label="Proventos recebidos por mês e por tipo"
        data={{
          labels: months.map(shortMonth),
          datasets: types.map((type) => ({
            label: type,
            data: months.map((month) => totals[month]?.[type] ?? 0),
            backgroundColor: INCOME_COLORS[type],
            borderColor: SURFACE,
            borderWidth: 1,
            stack: 'income',
          })),
        }}
        options={{
          responsive: true,
          maintainAspectRatio: false,
          interaction: { mode: 'index', intersect: false },
          scales: {
            x: { stacked: true, grid: { display: false }, ticks: { color: '#98978d', maxRotation: 0, autoSkipPadding: 16 } },
            y: {
              stacked: true,
              grid: { color: '#2a2a28' },
              border: { display: false },
              ticks: { color: '#98978d', callback: (value) => formatCompact(Number(value)) },
            },
          },
          plugins: {
            legend: { position: 'top', align: 'end', labels: { color: '#c3c2b7', boxWidth: 10, boxHeight: 10 } },
            tooltip: {
              backgroundColor: '#242422',
              borderColor: '#383835',
              borderWidth: 1,
              filter: (item) => item.parsed.y !== 0,
              callbacks: {
                label: (context) => ` ${context.dataset.label}: ${formatCurrency(context.parsed.y)}`,
              },
            },
          },
        }}
      />
    </div>
  );
};

export default IncomeBars;
