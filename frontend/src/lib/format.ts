const currency = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' });
const compact = new Intl.NumberFormat('pt-BR', { notation: 'compact', maximumFractionDigits: 1 });
const quantity = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 4 });
const percentage = new Intl.NumberFormat('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 });

export const formatCurrency = (value: number | null | undefined) =>
  value === null || value === undefined ? '-' : currency.format(value);

export const formatCompact = (value: number) => compact.format(value);

export const formatQuantity = (value: number | null | undefined) =>
  value === null || value === undefined ? '-' : quantity.format(value);

export const formatPercent = (value: number | null | undefined) =>
  value === null || value === undefined ? '-' : `${percentage.format(value)}%`;

export const formatSignedPercent = (value: number | null | undefined) => {
  if (value === null || value === undefined) return '-';
  return `${value > 0 ? '+' : ''}${percentage.format(value)}%`;
};

export const formatSignedCurrency = (value: number | null | undefined) => {
  if (value === null || value === undefined) return '-';
  return `${value > 0 ? '+' : ''}${currency.format(value)}`;
};

/** Converte a data ISO (aaaa-mm-dd) sem passar por Date, que deslocaria o dia pelo fuso. */
export const formatDate = (iso: string | null | undefined) => {
  if (!iso) return '-';
  const [year, month, day] = iso.split('-');
  return `${day}/${month}/${year}`;
};
