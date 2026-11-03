'use client'

import React from 'react';
import {
  CategoryScale, Chart as ChartJS, Legend, LinearScale, LineElement, PointElement, Tooltip,
} from 'chart.js';
import { Line } from 'react-chartjs-2';
import { formatDate, formatSignedPercent } from '@/lib/format';
import { PerformanceWindow } from '@/lib/performance';

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Legend);

const shortDate = (iso: string) => `${iso.slice(8, 10)}/${iso.slice(5, 7)}/${iso.slice(2, 4)}`;

const PerformanceChart: React.FC<{ data: PerformanceWindow }> = ({ data }) => (
  <div className="h-80">
    <Line
      aria-label="Rentabilidade acumulada da carteira comparada ao CDI e ao Ibovespa"
      options={{
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        elements: { point: { radius: 0, hoverRadius: 4 }, line: { borderWidth: 2, tension: 0.1 } },
        scales: {
          x: {
            grid: { display: false },
            ticks: { color: '#98978d', maxTicksLimit: 5, maxRotation: 0, autoSkipPadding: 16, callback: (value) => shortDate(data.dates[Number(value)]) },
          },
          y: {
            grid: { color: '#2a2a28' },
            border: { display: false },
            ticks: { color: '#98978d', callback: (value) => formatSignedPercent(Number(value)) },
          },
        },
        plugins: {
          legend: { position: 'top', align: 'end', labels: { color: '#c3c2b7', boxWidth: 12, boxHeight: 2 } },
          tooltip: {
            backgroundColor: '#242422',
            borderColor: '#383835',
            borderWidth: 1,
            callbacks: {
              title: (items) => formatDate(data.dates[items[0].dataIndex]),
              label: (context) => ` ${context.dataset.label}: ${formatSignedPercent(context.parsed.y)}`,
            },
          },
        },
      }}
      data={{
        labels: data.dates,
        datasets: [
          { label: 'Carteira', data: data.portfolio, borderColor: '#3987e5', backgroundColor: '#3987e5' },
          { label: 'CDI', data: data.cdi, borderColor: '#d95926', backgroundColor: '#d95926' },
          { label: 'Ibovespa', data: data.ibov, borderColor: '#199e70', backgroundColor: '#199e70' },
        ],
      }}
    />
  </div>
);

export default PerformanceChart;
