import { Position } from '@/types';
import { Targets, TargetEntry, categoryEntries, classEntries } from './targets';

export interface PlannedAllocation {
  key: string;
  label: string;
  color?: string;
  amount: number;
  targetPercent: number;
  afterPercent: number;
}

export interface ClassPlan extends PlannedAllocation {
  categories: PlannedAllocation[];
  /** Parte do aporte da classe que não tem categoria com meta para onde ir. */
  withoutCategory: number;
  hasCategoryTargets: boolean;
}

export interface ContributionPlan {
  classes: ClassPlan[];
  /** Classes com meta que não recebem nada, porque já estão na meta ou acima dela. */
  aboveTarget: string[];
  /** Parte do aporte que sobra quando as metas já estão atendidas ou não cobrem 100%. */
  unallocated: number;
}

const toCents = (value: number) => Math.round(value * 100);

/** Divide `cents` na proporção de `weights`, garantindo que a soma das partes seja exatamente `cents`. */
const splitCents = (cents: number, weights: number[]) => {
  const totalWeight = weights.reduce((sum, weight) => sum + weight, 0);
  const exact = weights.map((weight) => (cents * weight) / totalWeight);
  const parts = exact.map(Math.floor);
  const leftover = cents - parts.reduce((sum, part) => sum + part, 0);
  exact
    .map((value, index) => ({ index, fraction: value - Math.floor(value) }))
    .sort((a, b) => b.fraction - a.fraction)
    .slice(0, leftover)
    .forEach(({ index }) => { parts[index] += 1; });
  return parts;
};

/**
 * Distribui o aporte entre os grupos abaixo da meta, na proporção do que falta a cada um.
 * A meta é calculada sobre o total depois do aporte, sem nunca sugerir vender.
 */
const distribute = (entries: TargetEntry[], saved: Record<string, number>, amountCents: number) => {
  const total = entries.reduce((sum, entry) => sum + entry.value, 0);
  const after = total + amountCents / 100;
  const targeted = entries.filter((entry) => !entry.locked && saved[entry.key] !== undefined);
  const gaps = targeted.map((entry) => Math.max((saved[entry.key] / 100) * after - entry.value, 0));
  const totalGapCents = toCents(gaps.reduce((sum, gap) => sum + gap, 0));

  // Com folga, cada grupo recebe só o que falta; o restante é devolvido como não alocado.
  const toDistribute = Math.min(amountCents, totalGapCents);
  const parts = toDistribute > 0 ? splitCents(toDistribute, gaps) : targeted.map(() => 0);
  const allocated = parts.reduce((sum, part) => sum + part, 0);

  const allocations: PlannedAllocation[] = targeted.map((entry, index) => ({
    key: entry.key,
    label: entry.label,
    color: entry.color,
    amount: parts[index] / 100,
    targetPercent: saved[entry.key],
    afterPercent: after ? ((entry.value + parts[index] / 100) / after) * 100 : 0,
  }));

  return { allocations, unallocatedCents: amountCents - allocated };
};

export const planContribution = (assets: Position[], targets: Targets, amount: number): ContributionPlan => {
  const amountCents = toCents(amount);
  const { allocations, unallocatedCents } = distribute(classEntries(assets, targets), targets.classes, amountCents);

  const classes: ClassPlan[] = allocations
    .filter((allocation) => allocation.amount > 0)
    .sort((a, b) => b.amount - a.amount)
    .map((allocation) => {
      const saved = targets.categories[allocation.key] ?? {};
      const inner = distribute(categoryEntries(assets, allocation.key, targets), saved, toCents(allocation.amount));
      return {
        ...allocation,
        categories: inner.allocations.filter((item) => item.amount > 0).sort((a, b) => b.amount - a.amount),
        withoutCategory: inner.unallocatedCents / 100,
        hasCategoryTargets: Object.keys(saved).length > 0,
      };
    });

  return {
    classes,
    aboveTarget: allocations.filter((item) => item.amount === 0).map((item) => item.label),
    unallocated: unallocatedCents / 100,
  };
};
