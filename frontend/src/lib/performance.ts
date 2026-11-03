import { PerformanceSeries } from '@/types';

export interface PerformanceWindow {
  dates: string[];
  portfolio: number[];
  cdi: (number | null)[];
  ibov: (number | null)[];
}

/** Folga para o primeiro pregão não invalidar um período que começa num fim de semana ou feriado. */
const START_TOLERANCE_DAYS = 7;

const toIso = (date: Date) =>
  `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;

export const PERIODS = [
  { key: 'month', label: 'No mês', start: (end: Date) => new Date(end.getFullYear(), end.getMonth(), 1) },
  { key: 'year', label: 'No ano', start: (end: Date) => new Date(end.getFullYear(), 0, 1) },
  { key: '12m', label: '12 meses', start: (end: Date) => new Date(end.getFullYear() - 1, end.getMonth(), end.getDate()) },
  { key: '24m', label: '24 meses', start: (end: Date) => new Date(end.getFullYear() - 2, end.getMonth(), end.getDate()) },
  { key: 'all', label: 'Tudo', start: () => null },
] as const;

export type PeriodKey = (typeof PERIODS)[number]['key'];

const rebase = (values: (number | null)[], start: number) => {
  const base = values[start];
  return values.slice(start).map((value) => (value === null || base === null ? null : (value / base - 1) * 100));
};

/** Recorta a série no período e a recalcula a partir de zero, para os três começarem no mesmo ponto. */
export const windowFor = (series: PerformanceSeries, key: PeriodKey): PerformanceWindow | null => {
  if (series.dates.length < 2) return null;
  const last = series.dates[series.dates.length - 1];
  const [year, month, day] = last.split('-').map(Number);
  const period = PERIODS.find((item) => item.key === key);
  const startDate = period?.start(new Date(year, month - 1, day));
  const startIso = startDate ? toIso(startDate) : series.dates[0];
  // Histórico mais curto que o período: mostrar o acumulado total sob esse nome seria enganoso.
  if (startDate) {
    const earliest = new Date(startDate);
    earliest.setDate(earliest.getDate() + START_TOLERANCE_DAYS);
    if (series.dates[0] > toIso(earliest)) return null;
  }

  // Começa no último pregão antes do período: é a base de comparação do primeiro dia.
  let start = series.dates.findIndex((date) => date >= startIso);
  if (start === -1) return null;
  if (start > 0 && series.dates[start] > startIso) start -= 1;
  if (start >= series.dates.length - 1) return null;

  return {
    dates: series.dates.slice(start),
    portfolio: rebase(series.portfolio, start) as number[],
    cdi: rebase(series.cdi, start),
    ibov: rebase(series.ibov, start),
  };
};

export const finalValue = (values: (number | null)[]) => {
  for (let index = values.length - 1; index >= 0; index -= 1) {
    if (values[index] !== null) return values[index];
  }
  return null;
};
