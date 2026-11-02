'use client'

import React, { useCallback, useState } from 'react';
import Link from 'next/link';
import UploadFileIcon from '@mui/icons-material/UploadFile';
import { Patrimony } from '@/components/charts/patrimony';
import AllocationExplorer from '@/components/dashboard/allocationExplorer';
import Insights from '@/components/dashboard/insights';
import MarketDataStatusBar from '@/components/dashboard/marketDataStatus';
import TargetsSummary from '@/components/dashboard/targetsSummary';
import ClassificationModal from '@/components/modals/classification';
import PositionsTable from '@/components/positionsTable';
import { Button, Card, CardTitle, EmptyState, ErrorState, LoadingState, PageHeader, ProfitText } from '@/components/ui';
import {
  AllocationFilter, AllocationGroup, Dimension, applyFilters, availableDimensions, nextDimension,
} from '@/lib/allocation';
import { investidor10Url } from '@/lib/assets';
import { formatSignedPercent } from '@/lib/format';
import { useFormat } from '@/lib/privacy';
import { Targets } from '@/lib/targets';
import { useApi } from '@/lib/useApi';
import { Position, PositionHistory, PositionResponse } from '@/types';

const Stat: React.FC<{ label: string; children: React.ReactNode; detail?: React.ReactNode }> = ({ label, children, detail }) => (
  <Card>
    <p className="text-xs text-muted mb-1">{label}</p>
    <p className="text-lg sm:text-xl lg:text-2xl font-semibold tabular-nums break-words">{children}</p>
    {detail && <p className="text-xs text-muted mt-1">{detail}</p>}
  </Card>
);

export default function Home() {
  const { formatCurrency, formatSignedCurrency } = useFormat();
  const { data, isLoading, error, reload } = useApi<PositionResponse>('/position');
  const [filters, setFilters] = useState<AllocationFilter[]>([]);
  const [dimension, setDimension] = useState<Dimension>('asset_class');
  const [editing, setEditing] = useState<Position | null>(null);

  const classFilter = filters.find((filter) => filter.dimension === 'asset_class');
  const onlyClassFiltered = filters.length === 1 && classFilter;
  const history = useApi<PositionHistory>(
    '/position-history',
    onlyClassFiltered ? { class: classFilter.key } : undefined,
  );

  const targets = useApi<Targets>('/targets');
  const reloadHistory = history.reload;
  const refreshAfterMarketUpdate = useCallback(() => {
    reload();
    reloadHistory();
  }, [reload, reloadHistory]);

  if (isLoading && !data) return <LoadingState label="Carregando carteira..." />;
  if (error && !data) return <ErrorState message={error} onRetry={reload} />;
  if (!data) return null;

  const { assets, summary } = data;

  if (assets.length === 0) {
    return (
      <>
        <PageHeader title="Carteira" />
        <Card>
          <EmptyState
            title="Sua carteira está vazia"
            description="Importe o relatório de posição da B3 para começar, ou registre as boletas uma a uma."
            action={(
              <Link href="/orders?import=1">
                <Button variant="primary"><UploadFileIcon fontSize="small" /> Importar da B3</Button>
              </Link>
            )}
          />
        </Card>
      </>
    );
  }

  const selected = applyFilters(assets, filters);
  const selectedTotal = selected.reduce((sum, asset) => sum + (asset.value ?? 0), 0);

  const selectGroup = (group: AllocationGroup) => {
    if (dimension === 'name') {
      const asset = selected.find((item) => item.name === group.key);
      const url = asset && investidor10Url(asset.asset_class, asset.name);
      if (url) window.open(url, '_blank', 'noopener,noreferrer');
      return;
    }
    const nextFilters = [...filters, { dimension, key: group.key, label: group.label }];
    setFilters(nextFilters);
    setDimension(nextDimension(applyFilters(assets, nextFilters), dimension));
  };

  const goToDepth = (depth: number) => {
    const nextFilters = filters.slice(0, depth);
    setFilters(nextFilters);
    if (depth === filters.length) return;
    // Volta para a dimensão do filtro removido, que é a visão de onde o usuário desceu.
    const removed = filters[depth].dimension;
    setDimension(availableDimensions(nextFilters).some(({ key }) => key === removed) ? removed : 'asset_class');
  };

  return (
    <>
      <PageHeader
        title="Carteira"
        action={(
          <>
            <MarketDataStatusBar onUpdated={refreshAfterMarketUpdate} />
            <Link href="/orders?import=1">
              <Button><UploadFileIcon fontSize="small" /> Importar da B3</Button>
            </Link>
          </>
        )}
      />

      <div className="space-y-4">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <Stat label="Patrimônio" detail={`${summary.assets} ativo(s)${summary.assets_without_price > 0 ? `, ${summary.assets_without_price} sem preço` : ''}`}>
            {formatCurrency(summary.value)}
          </Stat>
          <Stat label="Investido" detail={summary.estimated_assets > 0 ? `${summary.estimated_assets} ativo(s) com custo estimado` : undefined}>
            {formatCurrency(summary.invested)}
          </Stat>
          <Stat label="Resultado" detail={formatSignedPercent(summary.profit_pct)}>
            <ProfitText value={summary.profit}>{formatSignedCurrency(summary.profit)}</ProfitText>
          </Stat>
          <Stat label="Proventos recebidos" detail={<>Lucro realizado: {formatSignedCurrency(summary.realized_gain)}</>}>
            <Link href="/income" className="hover:underline">{formatCurrency(summary.income_total)}</Link>
          </Stat>
        </div>

        <div className="grid xl:grid-cols-5 gap-4">
          <div className="xl:col-span-3 min-w-0">
          <AllocationExplorer
            assets={selected}
            filters={filters}
            dimension={dimension}
            onDimensionChange={setDimension}
            onSelect={selectGroup}
            onBreadcrumb={goToDepth}
          />
          </div>
          <Card className="xl:col-span-2">
            <CardTitle>Evolução{onlyClassFiltered ? `: ${classFilter.label}` : ''}</CardTitle>
            {!history.data && history.isLoading && <LoadingState label="Carregando histórico..." />}
            {history.data && history.data.labels.length > 0 && (
              <>
                <Patrimony data={history.data} />
                {history.data.labels.length === 1 && (
                  <p className="text-xs text-muted mt-2">O gráfico ganha linha a partir da próxima importação.</p>
                )}
              </>
            )}
            {history.data && history.data.labels.length === 0 && (
              <EmptyState title="Ainda sem histórico" description="O histórico é gravado a cada importação e a cada pregão." />
            )}
          </Card>
        </div>

        {targets.data && (filters.length === 0 || onlyClassFiltered) && (
          <TargetsSummary assets={assets} targets={targets.data} assetClass={onlyClassFiltered ? classFilter.key : null} />
        )}

        <Insights assets={selected} />

        <Card>
          <CardTitle>
            Posições{filters.length > 0 ? `: ${filters.map((filter) => filter.label).join(' › ')}` : ''}
          </CardTitle>
          <PositionsTable assets={selected} total={selectedTotal} onEditClassification={setEditing} />
        </Card>
      </div>

      {editing && (
        <ClassificationModal asset={editing} assets={assets} onClose={() => setEditing(null)} onSaved={reload} />
      )}
    </>
  );
}
