import { Position } from '@/types';
import { CLASS_COLORS, NO_CATEGORY, NO_SUB_CATEGORY, OTHER_COLOR, SERIES_COLORS, classLabel } from './assets';

export type Dimension =
  | 'asset_class' | 'category' | 'sub_category' | 'name'
  | 'broker' | 'issuer' | 'index' | 'maturity_year';

export interface AllocationFilter {
  dimension: Dimension;
  key: string;
  label: string;
}

export interface AllocationGroup {
  key: string;
  label: string;
  value: number;
  share: number;
  count: number;
  color: string;
  folded: boolean;
}

const FIXED_INCOME_ONLY: Dimension[] = ['issuer', 'index', 'maturity_year'];

export const DIMENSIONS: { key: Dimension; label: string }[] = [
  { key: 'asset_class', label: 'Classe' },
  { key: 'category', label: 'Categoria' },
  { key: 'sub_category', label: 'Subcategoria' },
  { key: 'name', label: 'Ativo' },
  { key: 'broker', label: 'Corretora' },
  { key: 'issuer', label: 'Emissor' },
  { key: 'index', label: 'Indexador' },
  { key: 'maturity_year', label: 'Vencimento' },
];

const HIERARCHY: Dimension[] = ['asset_class', 'category', 'sub_category', 'name'];

const keyOf = (asset: Position, dimension: Exclude<Dimension, 'broker'>): string => {
  switch (dimension) {
    case 'asset_class': return asset.asset_class;
    case 'category': return asset.category || NO_CATEGORY;
    case 'sub_category': return asset.sub_category || NO_SUB_CATEGORY;
    case 'name': return asset.name;
    case 'issuer': return asset.issuer || 'Sem emissor';
    case 'index': return asset.index || 'Sem indexador';
    case 'maturity_year': return asset.maturity_date ? asset.maturity_date.slice(0, 4) : 'Sem vencimento';
  }
};

const labelOf = (key: string, dimension: Dimension) => (dimension === 'asset_class' ? classLabel(key) : key);

const brokerShare = (asset: Position, broker: string) => {
  const total = asset.brokers.reduce((sum, item) => sum + item.volume, 0);
  const volume = asset.brokers.find((item) => item.broker === broker)?.volume ?? 0;
  return total ? volume / total : 0;
};

/** Filtrar por corretora reduz o ativo à parte que está nela, proporcional à quantidade. */
const scaleToBroker = (asset: Position, broker: string): Position => {
  const share = brokerShare(asset, broker);
  const scale = (value: number | null) => (value === null ? null : value * share);
  return {
    ...asset,
    volume: asset.volume * share,
    cost: asset.cost * share,
    value: scale(asset.value),
    profit: scale(asset.profit),
    brokers: asset.brokers.filter((item) => item.broker === broker),
  };
};

export const applyFilters = (assets: Position[], filters: AllocationFilter[]) =>
  filters.reduce<Position[]>((current, filter) => {
    if (filter.dimension === 'broker') {
      return current
        .filter((asset) => asset.brokers.some((item) => item.broker === filter.key))
        .map((asset) => scaleToBroker(asset, filter.key));
    }
    const dimension = filter.dimension;
    return current.filter((asset) => {
      if (FIXED_INCOME_ONLY.includes(dimension) && asset.asset_class !== 'RF') return false;
      return keyOf(asset, dimension) === filter.key;
    });
  }, assets);

export const groupAssets = (assets: Position[], dimension: Dimension): AllocationGroup[] => {
  const totals: Record<string, { value: number; count: number }> = {};
  const add = (key: string, value: number) => {
    totals[key] = totals[key] || { value: 0, count: 0 };
    totals[key].value += value;
    totals[key].count += 1;
  };

  assets.forEach((asset) => {
    if (!asset.value) return;
    if (dimension === 'broker') {
      asset.brokers.forEach(({ broker }) => add(broker, (asset.value as number) * brokerShare(asset, broker)));
    } else if (!FIXED_INCOME_ONLY.includes(dimension) || asset.asset_class === 'RF') {
      add(keyOf(asset, dimension), asset.value);
    }
  });

  const total = Object.values(totals).reduce((sum, item) => sum + item.value, 0);
  const sorted = Object.keys(totals).sort((a, b) =>
    dimension === 'maturity_year' ? a.localeCompare(b) : totals[b].value - totals[a].value
  );
  // A cor vai para os maiores grupos, mesmo quando a lista é exibida em outra ordem; o restante vira "Outros".
  const colorRank = [...sorted]
    .sort((a, b) => totals[b].value - totals[a].value)
    .slice(0, SERIES_COLORS.length);

  return sorted.map((key) => {
    const rank = colorRank.indexOf(key);
    const folded = rank === -1;
    const classColor = dimension === 'asset_class' ? CLASS_COLORS[key] : undefined;
    return {
      key,
      label: labelOf(key, dimension),
      value: totals[key].value,
      share: total ? (totals[key].value / total) * 100 : 0,
      count: totals[key].count,
      color: classColor || (folded ? OTHER_COLOR : SERIES_COLORS[rank]),
      folded: !classColor && folded,
    };
  });
};

export const availableDimensions = (filters: AllocationFilter[]) =>
  DIMENSIONS.filter(({ key }) => !filters.some((filter) => filter.dimension === key));

/** Próximo nível ao clicar numa fatia, pulando níveis que teriam uma única fatia. */
export const nextDimension = (assets: Position[], current: Dimension): Dimension => {
  const position = HIERARCHY.indexOf(current);
  if (position === -1) return 'name';
  for (let index = position + 1; index < HIERARCHY.length; index += 1) {
    if (HIERARCHY[index] === 'name' || groupAssets(assets, HIERARCHY[index]).length > 1) {
      return HIERARCHY[index];
    }
  }
  return 'name';
};

export const dimensionLabel = (dimension: Dimension) =>
  DIMENSIONS.find(({ key }) => key === dimension)?.label ?? dimension;
