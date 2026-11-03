'use client'

import React, { useMemo, useState } from 'react';
import Link from 'next/link';
import { Card, CardTitle, Field, inputClass } from '@/components/ui';
import { planContribution, PlannedAllocation } from '@/lib/contribution';
import { formatPercent } from '@/lib/format';
import { useFormat } from '@/lib/privacy';
import { Targets } from '@/lib/targets';
import { Position } from '@/types';

const AllocationRow: React.FC<{ allocation: PlannedAllocation; amount: number; compact?: boolean }> = ({ allocation, amount, compact }) => {
  const { formatCurrency } = useFormat();
  const share = (allocation.amount / amount) * 100;

  return (
    <div className={compact ? 'text-sm' : ''}>
      <div className="flex flex-wrap items-baseline justify-between gap-x-3">
        <span className={`inline-flex items-center gap-2 ${compact ? 'text-soft' : 'font-medium'}`}>
          {allocation.color && <span aria-hidden className="w-2.5 h-2.5 rounded-sm" style={{ backgroundColor: allocation.color }} />}
          {allocation.label}
        </span>
        <span className={`tabular-nums ${compact ? 'text-soft' : 'font-semibold'}`}>{formatCurrency(allocation.amount)}</span>
      </div>
      <p className="text-xs text-muted tabular-nums mt-0.5">
        {formatPercent(share)} do aporte · fica em {formatPercent(allocation.afterPercent)}, meta {formatPercent(allocation.targetPercent)}
      </p>
    </div>
  );
};

const ContributionCalculator: React.FC<{
  assets: Position[];
  targets: Targets;
  initialAmount?: number;
  title?: string;
  description?: string;
}> = ({
  assets,
  targets,
  initialAmount,
  title = 'Calculadora de aporte',
  description = 'Informe quanto vai investir para ver como dividir o valor e se aproximar das metas salvas, sem vender nada.',
}) => {
  const { formatCurrency } = useFormat();
  const [draft, setDraft] = useState(initialAmount ? initialAmount.toFixed(2) : '');
  const amount = Number(draft);
  const isValid = draft !== '' && Number.isFinite(amount) && amount > 0;
  const hasClassTargets = Object.keys(targets.classes).length > 0;

  const plan = useMemo(
    () => (isValid && hasClassTargets ? planContribution(assets, targets, amount) : null),
    [assets, targets, amount, isValid, hasClassTargets],
  );

  return (
    <Card>
      <CardTitle>{title}</CardTitle>
      <p className="text-sm text-muted mb-3">{description}</p>
      <Field label="Valor do aporte (R$)" htmlFor="contribution" className="max-w-xs mb-4">
        <input
          id="contribution"
          type="number"
          min="0"
          step="0.01"
          placeholder="0,00"
          className={inputClass}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
        />
      </Field>

      {!hasClassTargets && (
        <p className="text-sm text-muted">
          Defina as metas por classe na página <Link href="/targets" className="text-accent hover:underline">Metas</Link> para usar a calculadora.
        </p>
      )}

      {plan && (
        <div className="space-y-4">
          {plan.classes.length > 0 && (
            <ul className="space-y-4">
              {plan.classes.map((item) => (
                <li key={item.key} className="border-b border-line/50 pb-4 last:border-b-0 last:pb-0">
                  <AllocationRow allocation={item} amount={amount} />
                  {item.categories.length > 0 && (
                    <ul className="mt-3 ml-4 pl-3 border-l border-line space-y-2.5">
                      {item.categories.map((category) => (
                        <li key={category.key}><AllocationRow allocation={category} amount={item.amount} compact /></li>
                      ))}
                    </ul>
                  )}
                  {item.withoutCategory > 0 && (
                    <p className="text-xs text-soft mt-2 ml-4 pl-3 tabular-nums">
                      {item.hasCategoryTargets
                        ? `${formatCurrency(item.withoutCategory)} em ${item.label} ficam livres: as metas de categoria já seriam atendidas sem esse valor ou não cobrem 100%.`
                        : `Defina metas de categoria em ${item.label} para detalhar como dividir ${formatCurrency(item.withoutCategory)}.`}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          )}

          {plan.unallocated > 0 && (
            <p className="text-sm text-warn tabular-nums">
              {formatCurrency(plan.unallocated)} ficam sem destino: suas metas de classe já seriam atendidas sem esse valor.
            </p>
          )}

          {plan.aboveTarget.length > 0 && (
            <p className="text-xs text-muted">Sem aporte, por já estarem na meta ou acima dela: {plan.aboveTarget.join(', ')}.</p>
          )}

          <p className="text-xs text-muted">
            É uma conta sobre as metas, não uma recomendação de investimento: não considera preço de cada ativo, lote mínimo, impostos ou liquidez.
          </p>
        </div>
      )}
    </Card>
  );
};

export default ContributionCalculator;
