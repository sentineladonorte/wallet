import { AssetClass } from '@/types';

export const CLASS_LABELS: Record<string, string> = {
  AC: 'Ações',
  FII: 'FIIs',
  RF: 'Renda Fixa',
  ETF: 'ETFs',
  BDR: 'BDRs',
  INT: 'Internacional',
};

/** A cor acompanha a classe, para não mudar quando um filtro altera o que está na tela. */
export const CLASS_COLORS: Record<string, string> = {
  AC: '#3987e5',
  FII: '#d95926',
  RF: '#199e70',
  ETF: '#c98500',
  BDR: '#d55181',
  INT: '#9085e9',
};

/** Paleta categórica para fundo escuro; a ordem é a que garante distinção entre cores vizinhas. */
export const SERIES_COLORS = ['#3987e5', '#d95926', '#199e70', '#c98500', '#d55181', '#008300', '#9085e9'];
export const OTHER_COLOR = '#6f6e68';

export const classLabel = (assetClass: string | null | undefined) =>
  (assetClass && CLASS_LABELS[assetClass]) || assetClass || 'Sem classe';

const INVESTIDOR10_PATHS: Record<string, string> = {
  AC: 'acoes',
  FII: 'fiis',
  BDR: 'bdrs',
  ETF: 'etfs',
};

const inferPath = (assetClass: string | null | undefined, ticker: string) => {
  if (assetClass && INVESTIDOR10_PATHS[assetClass]) return INVESTIDOR10_PATHS[assetClass];
  if (assetClass === 'INT') return ticker.endsWith('11') ? 'etfs' : 'bdrs';
  if (assetClass) return null;
  // Ativos sem classe no cadastro: o final do ticker só é conclusivo para ações e BDRs.
  if (/[A-Z]{4}(3|4|5|6)$/.test(ticker)) return 'acoes';
  if (/3[1-9]$/.test(ticker)) return 'bdrs';
  return null;
};

/** Renda fixa não tem página por título no Investidor10. */
export const investidor10Url = (assetClass: AssetClass | string | null | undefined, ticker: string) => {
  const path = inferPath(assetClass, ticker);
  return path ? `https://investidor10.com.br/${path}/${ticker.toLowerCase()}/` : null;
};

export const NO_CATEGORY = 'Sem categoria';
export const NO_SUB_CATEGORY = 'Sem subcategoria';
