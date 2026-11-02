import { Position } from '@/types';
import { CLASS_COLORS, NO_CATEGORY, classLabel } from './assets';

export interface Targets {
  classes: Record<string, number>;
  categories: Record<string, Record<string, number>>;
}

/** Uma linha de meta: uma classe na carteira ou uma categoria dentro da classe. */
export interface TargetEntry {
  key: string;
  label: string;
  color?: string;
  value: number;
  /** "Sem categoria" não recebe meta: o caminho é classificar os ativos. */
  locked?: boolean;
}

export interface TargetProgress {
  currentPercent: number;
  targetPercent: number | null;
  /** Em pontos percentuais; positivo quando está acima da meta. */
  difference: number | null;
  /** Em reais; positivo quando falta aportar, negativo quando precisaria reduzir. */
  toTarget: number | null;
  onTarget: boolean;
}

export const DEFAULT_CLASSES = ['AC', 'FII', 'RF', 'ETF', 'BDR'];
const FIXED_INCOME_CATEGORIES = ['IPCA', 'Prefixado', 'Selic'];
const ON_TARGET_TOLERANCE = 0.5;

const sumValues = (assets: Position[], keyOf: (asset: Position) => string) => {
  const totals: Record<string, number> = {};
  assets.forEach((asset) => {
    const key = keyOf(asset);
    totals[key] = (totals[key] || 0) + (asset.value ?? 0);
  });
  return totals;
};

export const portfolioTotal = (assets: Position[]) =>
  assets.reduce((sum, asset) => sum + (asset.value ?? 0), 0);

export const classEntries = (assets: Position[], targets: Targets): TargetEntry[] => {
  const totals = sumValues(assets, (asset) => asset.asset_class);
  const keys = Array.from(new Set([...DEFAULT_CLASSES, ...Object.keys(totals), ...Object.keys(targets.classes)]));
  return keys
    .map((key) => ({ key, label: classLabel(key), color: CLASS_COLORS[key], value: totals[key] ?? 0 }))
    .sort((a, b) => b.value - a.value);
};

export const categoryEntries = (assets: Position[], assetClass: string, targets: Targets): TargetEntry[] => {
  const inClass = assets.filter((asset) => asset.asset_class === assetClass);
  const totals = sumValues(inClass, (asset) => asset.category || NO_CATEGORY);
  const defaults = assetClass === 'RF' ? FIXED_INCOME_CATEGORIES : [];
  const keys = Array.from(new Set([...defaults, ...Object.keys(totals), ...Object.keys(targets.categories[assetClass] ?? {})]));
  return keys
    .map((key) => ({ key, label: key, value: totals[key] ?? 0, locked: key === NO_CATEGORY }))
    .sort((a, b) => b.value - a.value);
};

export const progressOf = (value: number, total: number, targetPercent: number | null): TargetProgress => {
  const currentPercent = total ? (value / total) * 100 : 0;
  if (targetPercent === null) {
    return { currentPercent, targetPercent, difference: null, toTarget: null, onTarget: false };
  }
  const difference = currentPercent - targetPercent;
  return {
    currentPercent,
    targetPercent,
    difference,
    toTarget: (targetPercent / 100) * total - value,
    onTarget: Math.abs(difference) <= ON_TARGET_TOLERANCE,
  };
};
