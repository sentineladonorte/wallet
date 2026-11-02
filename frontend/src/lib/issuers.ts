import { formatCurrency } from './format';
import { Position } from '@/types';

/** Garantia do FGC por CPF, por instituição ou conglomerado. */
export const FGC_LIMIT = 250000;
/** O limite é público: mostrá-lo não revela nada sobre a carteira. */
export const FGC_LIMIT_LABEL = formatCurrency(FGC_LIMIT);
const NEAR_LIMIT_SHARE = 0.8;

export type IssuerStatus = 'ok' | 'near' | 'over';

export interface IssuerExposure {
  name: string;
  value: number;
  remaining: number;
  usedPercent: number;
  status: IssuerStatus;
  titles: Position[];
  nextMaturity: string | null;
}

/** O Tesouro Direto tem garantia do governo, não do FGC. */
const isFgcCovered = (asset: Position) => asset.asset_class === 'RF' && asset.sub_category !== 'Tesouro Direto';

const statusOf = (value: number): IssuerStatus => {
  if (value > FGC_LIMIT) return 'over';
  return value >= FGC_LIMIT * NEAR_LIMIT_SHARE ? 'near' : 'ok';
};

export const groupByIssuer = (assets: Position[]) => {
  const covered = assets.filter(isFgcCovered);
  const titlesByIssuer: Record<string, { name: string; titles: Position[] }> = {};

  covered.filter((asset) => asset.issuer).forEach((asset) => {
    const name = asset.issuer as string;
    // Emissor digitado à mão pode diferir só em maiúsculas ou espaços do que veio da B3.
    const key = name.trim().toUpperCase();
    titlesByIssuer[key] = titlesByIssuer[key] || { name, titles: [] };
    titlesByIssuer[key].titles.push(asset);
  });

  const issuers: IssuerExposure[] = Object.values(titlesByIssuer).map(({ name, titles }) => {
    const value = titles.reduce((sum, title) => sum + (title.value ?? 0), 0);
    const maturities = titles.map((title) => title.maturity_date).filter((date): date is string => Boolean(date)).sort();
    return {
      name,
      value,
      remaining: Math.max(FGC_LIMIT - value, 0),
      usedPercent: (value / FGC_LIMIT) * 100,
      status: statusOf(value),
      titles: [...titles].sort((a, b) => (b.value ?? 0) - (a.value ?? 0)),
      nextMaturity: maturities[0] ?? null,
    };
  });

  return {
    issuers: issuers.sort((a, b) => b.value - a.value),
    withoutIssuer: covered.filter((asset) => !asset.issuer),
  };
};
