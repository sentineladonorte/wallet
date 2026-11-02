'use client'

import React, { useMemo } from 'react';
import { Card, CardTitle, ErrorState, LoadingState, PageHeader } from '@/components/ui';
import ContributionCalculator from '@/components/targets/contributionCalculator';
import TargetsTable from '@/components/targets/targetsTable';
import { CLASS_COLORS, NO_CATEGORY, classLabel } from '@/lib/assets';
import { useFormat } from '@/lib/privacy';
import { Targets, categoryEntries, classEntries, portfolioTotal } from '@/lib/targets';
import { useApi } from '@/lib/useApi';
import { AssetInfo, PositionResponse } from '@/types';

const TargetsPage: React.FC = () => {
  const { formatCurrency } = useFormat();
  const position = useApi<PositionResponse>('/position');
  const targetsApi = useApi<Targets>('/targets');
  const catalog = useApi<AssetInfo[]>('/assets');
  const [saved, setSaved] = React.useState<Targets | null>(null);
  const targets = saved ?? targetsApi.data;

  const suggestionsByClass = useMemo(() => {
    const result: Record<string, string[]> = {};
    (catalog.data ?? []).forEach((asset) => {
      if (asset.asset_class && asset.category) {
        result[asset.asset_class] = result[asset.asset_class] || [];
        if (!result[asset.asset_class].includes(asset.category)) result[asset.asset_class].push(asset.category);
      }
    });
    Object.keys(result).forEach((key) => result[key].sort());
    return result;
  }, [catalog.data]);

  if ((position.isLoading && !position.data) || (targetsApi.isLoading && !targets)) return <LoadingState label="Carregando metas..." />;
  if (position.error && !position.data) return <ErrorState message={position.error} onRetry={position.reload} />;
  if (targetsApi.error && !targets) return <ErrorState message={targetsApi.error} onRetry={targetsApi.reload} />;
  if (!position.data || !targets) return null;

  const assets = position.data.assets;
  const total = portfolioTotal(assets);
  const classes = classEntries(assets, targets);
  const classesToShow = classes.filter((entry) =>
    entry.value > 0 || targets.classes[entry.key] > 0 || targets.categories[entry.key]
  );

  return (
    <>
      <PageHeader
        title="Metas"
        subtitle="Defina quanto quer ter em cada classe e em cada categoria dentro dela. Deixe em branco o que não quer acompanhar."
      />

      <div className="space-y-4">
        <ContributionCalculator assets={assets} targets={targets} />

        <Card>
          <CardTitle>Classes na carteira</CardTitle>
          <TargetsTable
            assetClass={null}
            entries={classes}
            total={total}
            saved={targets.classes}
            firstColumn="Classe"
            onSaved={setSaved}
          />
        </Card>

        {classesToShow.map((entry) => {
          const entries = categoryEntries(assets, entry.key, targets);
          const count = Object.keys(targets.categories[entry.key] ?? {}).length;
          const unclassified = entries.find((item) => item.key === NO_CATEGORY && item.value > 0);

          return (
            <Card key={entry.key}>
              <details open className="group">
                <summary className="cursor-pointer list-none flex flex-wrap items-center justify-between gap-2">
                  <span className="flex items-center gap-2 font-semibold">
                    <span aria-hidden className="text-muted transition group-open:rotate-90">›</span>
                    <span aria-hidden className="w-2.5 h-2.5 rounded-sm" style={{ backgroundColor: CLASS_COLORS[entry.key] }} />
                    Dentro de {classLabel(entry.key)}
                  </span>
                  <span className="text-xs text-muted tabular-nums">
                    {formatCurrency(entry.value)} · {count ? `${count} meta(s)` : 'sem metas'}
                  </span>
                </summary>
                <div className="mt-3">
                  <p className="text-xs text-muted mb-2">Percentuais sobre o total de {classLabel(entry.key)}, não sobre a carteira.</p>
                  {unclassified && (
                    <p className="text-xs text-warn mb-2">
                      Há ativos sem categoria nesta classe. Classifique-os na tabela de posições da Carteira para acompanhar as metas.
                    </p>
                  )}
                  <TargetsTable
                    assetClass={entry.key}
                    entries={entries}
                    total={entry.value}
                    saved={targets.categories[entry.key] ?? {}}
                    suggestions={suggestionsByClass[entry.key]}
                    firstColumn="Categoria"
                    onSaved={setSaved}
                  />
                </div>
              </details>
            </Card>
          );
        })}
      </div>
    </>
  );
};

export default TargetsPage;
