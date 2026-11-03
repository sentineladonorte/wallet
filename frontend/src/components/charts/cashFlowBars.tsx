'use client'

import React from 'react';
import { BarElement, CategoryScale, Chart as ChartJS, Legend, LinearScale, Tooltip } from 'chart.js';
import { Bar } from 'react-chartjs-2';
import { CashMonth } from '@/lib/cashflow';
import { useFormat } from '@/lib/privacy';

ChartJS.register(BarElement, CategoryScale, LinearScale, Tooltip, Legend);

const SURFACE = '#1a1a19';

const shortMonth = (key: string) => `${key.slice(5)}/${key.slice(2, 4)}`;

const CashFlowBars: React.FC<{ months: CashMonth[]; onSelect: (month: CashMonth) => void }> = ({ months, onSelect }) => {
  const { formatCompact, formatCurrency } = useFormat();

  return (
    <div className="h-64">
      <Bar
        aria-label="Entradas previstas por mês: vencimentos de títulos e proventos estimados"
        data={{
          labels: months.map((month) => shortMonth(month.key)),
          datasets: [
            { label: 'Vencimentos', data: months.map((month) => month.maturityValue), backgroundColor: '#3987e5', borderColor: SURFACE, borderWidth: 1, stack: 'cash' },
            { label: 'Proventos estimados', data: months.map((month) => month.expectedIncome), backgroundColor: '#d95926', borderColor: SURFACE, borderWidth: 1, stack: 'cash' },
          ],
        }}
        options={{
          responsive: true,
          maintainAspectRatio: false,
          interaction: { mode: 'index', intersect: false },
          onClick: (_event, elements) => {
            if (elements.length) onSelect(months[elements[0].index]);
          },
          scales: {
            x: { stacked: true, grid: { display: false }, ticks: { color: '#98978d', maxRotation: 0, autoSkipPadding: 12 } },
            y: { stacked: true, grid: { color: '#2a2a28' }, border: { display: false }, ticks: { color: '#98978d', callback: (value) => formatCompact(Number(value)) } },
          },
          plugins: {
            legend: { position: 'top', align: 'end', labels: { color: '#c3c2b7', boxWidth: 10, boxHeight: 10 } },
            tooltip: {
              backgroundColor: '#242422',
              borderColor: '#383835',
              borderWidth: 1,
              callbacks: { label: (context) => ` ${context.dataset.label}: ${formatCurrency(context.parsed.y)}` },
            },
          },
        }}
      />
    </div>
  );
};

export default CashFlowBars;
