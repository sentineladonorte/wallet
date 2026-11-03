import { IncomeRow, Position } from '@/types';
import { monthKey, monthsBetween, twelveMonthsStart } from './income';

export const HORIZON_MONTHS = 24;
const MONTHS_IN_YEAR = 12;
const DAY_MS = 24 * 60 * 60 * 1000;
/** Pagamentos que se repetem. Juros de renda fixa e amortizações dependem do título e não valem como média. */
const RECURRING_TYPES = ['Rendimentos', 'Dividendos', 'JCP'];

export interface CashMonth {
  key: string;
  maturities: Position[];
  maturityValue: number;
  expectedIncome: number;
}

const toKey = (date: Date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`;

const parseIso = (iso: string) => {
  const [year, month, day] = iso.split('-').map(Number);
  return new Date(year, month - 1, day);
};

export const daysUntil = (iso: string, today: Date) =>
  Math.round((parseIso(iso).getTime() - new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime()) / DAY_MS);

export const titlesWithMaturity = (assets: Position[]) =>
  assets
    .filter((asset) => asset.maturity_date)
    .sort((a, b) => (a.maturity_date as string).localeCompare(b.maturity_date as string));

export const maturityValue = (asset: Position) => asset.maturity_value ?? asset.value ?? 0;

/** Média mensal dos proventos recorrentes dos últimos 12 meses completos ou em andamento. */
export const expectedMonthlyIncome = (rows: IncomeRow[], today: Date) => {
  const start = twelveMonthsStart(today);
  const total = rows
    .filter((row) => RECURRING_TYPES.includes(row.type) && monthKey(row.date) >= start)
    .reduce((sum, row) => sum + row.value, 0);
  return total / MONTHS_IN_YEAR;
};

export const buildCashMonths = (assets: Position[], rows: IncomeRow[], today: Date): CashMonth[] => {
  const last = new Date(today.getFullYear(), today.getMonth() + HORIZON_MONTHS - 1, 1);
  const income = expectedMonthlyIncome(rows, today);
  const titles = titlesWithMaturity(assets);

  return monthsBetween(toKey(today), toKey(last)).map((key) => {
    const maturities = titles.filter((asset) => monthKey(asset.maturity_date as string) === key);
    return {
      key,
      maturities,
      maturityValue: maturities.reduce((sum, asset) => sum + maturityValue(asset), 0),
      expectedIncome: income,
    };
  });
};

/** A carteira depois de um mês: os títulos que vencem deixam de contar para as metas. */
export const assetsAfterMonth = (assets: Position[], month: CashMonth) => {
  const leaving = new Set(month.maturities.map((asset) => asset.name));
  return assets.filter((asset) => !leaving.has(asset.name));
};

export const monthLabel = (key: string) => {
  const [year, month] = key.split('-').map(Number);
  const label = new Date(year, month - 1, 1).toLocaleDateString('pt-BR', { month: 'long', year: 'numeric' });
  return label.charAt(0).toUpperCase() + label.slice(1);
};
