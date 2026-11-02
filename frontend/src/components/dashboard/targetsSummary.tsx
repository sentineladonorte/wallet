import React from 'react';
import Link from 'next/link';
import TargetBar from '@/components/targets/targetBar';
import { Card, CardTitle } from '@/components/ui';
import { classLabel } from '@/lib/assets';
import { formatPercent } from '@/lib/format';
import { useFormat } from '@/lib/privacy';
import { Targets, categoryEntries, classEntries, portfolioTotal, progressOf } from '@/lib/targets';
import { Position } from '@/types';

/** Mostra as metas das classes ou, com uma classe selecionada na pizza, as das categorias dela. */
const TargetsSummary: React.FC<{ assets: Position[]; targets: Targets; assetClass: string | null }> = ({ assets, targets, assetClass }) => {
  const { formatCurrency } = useFormat();
  const entries = assetClass ? categoryEntries(assets, assetClass, targets) : classEntries(assets, targets);
  const saved = assetClass ? targets.categories[assetClass] ?? {} : targets.classes;
  const inScope = assetClass ? assets.filter((asset) => asset.asset_class === assetClass) : assets;
  const total = portfolioTotal(inScope);
  const rows = entries.filter((entry) => saved[entry.key] !== undefined);
  const title = assetClass ? `Metas em ${classLabel(assetClass)}` : 'Metas por classe';
  const editLink = <Link href="/targets" className="text-xs text-accent hover:underline">{rows.length ? 'Editar' : 'Definir metas'}</Link>;

  if (rows.length === 0) {
    return (
      <Card>
        <CardTitle action={editLink}>{title}</CardTitle>
        <p className="text-sm text-muted">Nenhuma meta definida aqui. Defina metas para ver o quanto falta em cada grupo.</p>
      </Card>
    );
  }

  return (
    <Card>
      <CardTitle action={editLink}>{title}</CardTitle>
      <ul className="grid md:grid-cols-2 gap-x-8 gap-y-4">
        {rows.map((entry) => {
          const progress = progressOf(entry.value, total, saved[entry.key]);
          let action = 'Na meta';
          if (!progress.onTarget) {
            action = `${(progress.toTarget as number) > 0 ? 'Aportar' : 'Reduzir'} ${formatCurrency(Math.abs(progress.toTarget as number))}`;
          }
          return (
            <li key={entry.key}>
              <div className="flex flex-wrap justify-between gap-x-3 text-sm mb-1.5">
                <span>{entry.label}</span>
                <span className="tabular-nums text-soft">
                  {formatPercent(progress.currentPercent)} <span className="text-muted">de {formatPercent(progress.targetPercent)}</span>
                </span>
              </div>
              <TargetBar current={progress.currentPercent} target={progress.targetPercent} label={entry.label} />
              <p className="text-xs text-muted mt-1.5 tabular-nums">{action}</p>
            </li>
          );
        })}
      </ul>
    </Card>
  );
};

export default TargetsSummary;
