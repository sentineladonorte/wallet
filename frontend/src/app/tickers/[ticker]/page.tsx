'use client'

import React from 'react';
import dynamic from 'next/dynamic';
import { Patrimony } from '@/components/charts/patrimony';
import AssetLink from '@/components/assetLink';
import OrdersTable from '@/components/ordersTable';
import { Card, CardTitle, EmptyState, EstimatedBadge, LoadingState, PageHeader, ProfitText } from '@/components/ui';
import { classLabel } from '@/lib/assets';
import { formatDate, formatSignedPercent } from '@/lib/format';
import { useFormat } from '@/lib/privacy';
import { useApi } from '@/lib/useApi';
import { Order, PositionHistory, PositionResponse } from '@/types';

// O Highcharts depende do navegador e não roda na renderização do servidor.
const Stock = dynamic(() => import('@/components/charts/stock'), { ssr: false });

const Detail: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <div>
    <dt className="text-xs text-muted">{label}</dt>
    <dd className="font-medium tabular-nums">{children}</dd>
  </div>
);

const TickerPage: React.FC<{ params: { ticker: string } }> = ({ params }) => {
  const { formatCurrency, formatQuantity } = useFormat();
  const ticker = decodeURIComponent(params.ticker).toUpperCase();
  const position = useApi<PositionResponse>('/position');
  const history = useApi<PositionHistory>('/position-history', { ticker });
  const prices = useApi<number[][]>(`/asset/${encodeURIComponent(ticker)}/`);
  const orders = useApi<Order[]>('/orders/', { ticker });

  const asset = position.data?.assets.find((item) => item.name === ticker);
  const orderClass = orders.data?.[0]?.asset_type;

  return (
    <>
      <PageHeader
        title={ticker}
        subtitle={asset?.description ?? undefined}
        action={<AssetLink name={ticker} assetClass={asset?.asset_class ?? orderClass ?? null} className="text-sm" label="Abrir no Investidor10" />}
      />

      <div className="space-y-4">
        {position.isLoading && !position.data && <LoadingState />}

        {asset && (
          <Card>
            <dl className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
              <Detail label="Classe">{classLabel(asset.asset_class)}</Detail>
              <Detail label="Categoria">{asset.category || '-'}</Detail>
              <Detail label="Quantidade">{formatQuantity(asset.volume)}</Detail>
              <Detail label="Preço médio">
                {formatCurrency(asset.volume ? asset.cost / asset.volume : null)}
                {asset.cost_estimated && <EstimatedBadge />}
              </Detail>
              <Detail label="Valor">{formatCurrency(asset.value)}</Detail>
              <Detail label="Proventos">{formatCurrency(asset.income)}</Detail>
              <Detail label="Resultado">
                <ProfitText value={asset.profit}>{formatSignedPercent(asset.profit_pct)}</ProfitText>
              </Detail>
              {asset.issuer && <Detail label="Emissor">{asset.issuer}</Detail>}
              {asset.maturity_date && <Detail label="Vencimento">{formatDate(asset.maturity_date)}</Detail>}
            </dl>
          </Card>
        )}

        <Card>
          <CardTitle>Preço</CardTitle>
          {prices.data && prices.data.length > 0
            ? <Stock data={prices.data} orders={orders.data ?? []} />
            : !prices.isLoading && <EmptyState title="Sem cotações" description="Títulos de renda fixa não têm cotação diária, e os demais ativos podem ainda não ter sido importados." />}
        </Card>

        {history.data && history.data.labels.length > 0 && (
          <Card>
            <CardTitle>Evolução da posição</CardTitle>
            <Patrimony data={history.data} />
          </Card>
        )}

        <Card>
          <CardTitle>Boletas</CardTitle>
          {orders.data && orders.data.length > 0
            ? <OrdersTable orders={orders.data} onChanged={() => { orders.reload(); position.reload(); }} />
            : !orders.isLoading && <EmptyState title="Nenhuma boleta deste ativo" />}
        </Card>
      </div>
    </>
  );
};

export default TickerPage;
