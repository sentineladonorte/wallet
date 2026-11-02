import { IncomeRow } from '@/types';

export const INCOME_TYPES = ['Rendimentos', 'Dividendos', 'JCP', 'Juros de renda fixa', 'Amortização', 'Outros', 'Taxas'];

/** A cor acompanha o tipo; a ordem é a validada para o fundo escuro. */
export const INCOME_COLORS: Record<string, string> = {
  Rendimentos: '#3987e5',
  Dividendos: '#d95926',
  JCP: '#199e70',
  'Juros de renda fixa': '#c98500',
  'Amortização': '#d55181',
  Outros: '#9085e9',
  Taxas: '#6f6e68',
};

const MONTHS_IN_YEAR = 12;

export const monthKey = (iso: string) => iso.slice(0, 7);

/** Primeiro mês da janela de 12 meses que termina em `today`, no formato aaaa-mm. */
export const twelveMonthsStart = (today: Date) => {
  const start = new Date(today.getFullYear(), today.getMonth() - (MONTHS_IN_YEAR - 1), 1);
  return `${start.getFullYear()}-${String(start.getMonth() + 1).padStart(2, '0')}`;
};

export const sum = (rows: IncomeRow[]) => rows.reduce((total, row) => total + row.value, 0);

export interface AssetIncome {
  name: string;
  description: string;
  assetClass: string;
  total: number;
  lastTwelveMonths: number;
  payments: number;
  lastDate: string;
  cost: number;
}

/** Junta os proventos por ativo. Taxas ficam de fora: não são renda do ativo. */
export const groupByAsset = (rows: IncomeRow[], costs: Record<string, number>, windowStart: string) => {
  const groups: Record<string, AssetIncome> = {};
  rows.filter((row) => row.type !== 'Taxas').forEach((row) => {
    const group = groups[row.name] ?? {
      name: row.name,
      description: row.description,
      assetClass: row.asset_class,
      total: 0,
      lastTwelveMonths: 0,
      payments: 0,
      lastDate: row.date,
      cost: costs[row.name] ?? 0,
    };
    group.total += row.value;
    group.payments += 1;
    if (monthKey(row.date) >= windowStart) group.lastTwelveMonths += row.value;
    if (row.date > group.lastDate) group.lastDate = row.date;
    groups[row.name] = group;
  });
  return Object.values(groups).sort((a, b) => b.total - a.total);
};

/** Meses em ordem, inclusive os sem pagamento, para o eixo não esconder os intervalos. */
export const monthsBetween = (first: string, last: string) => {
  const months: string[] = [];
  let [year, month] = first.split('-').map(Number);
  const [lastYear, lastMonth] = last.split('-').map(Number);
  while (year < lastYear || (year === lastYear && month <= lastMonth)) {
    months.push(`${year}-${String(month).padStart(2, '0')}`);
    month += 1;
    if (month > MONTHS_IN_YEAR) {
      month = 1;
      year += 1;
    }
  }
  return months;
};
