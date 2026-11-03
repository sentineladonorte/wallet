'use client'

import React, { useMemo, useState } from 'react';
import Link from 'next/link';
import CashFlowBars from '@/components/charts/cashFlowBars';
import ContributionCalculator from '@/components/targets/contributionCalculator';
import { Button, Card, CardTitle, EmptyState, ErrorState, LoadingState, PageHeader } from '@/components/ui';
import {
  CashMonth, assetsAfterMonth, buildCashMonths, daysUntil, expectedMonthlyIncome, maturityValue, monthLabel, titlesWithMaturity,
} from '@/lib/cashflow';
import { formatDate, formatPercent } from '@/lib/format';
import { useFormat } from '@/lib/privacy';
import { Targets } from '@/lib/targets';
import { useApi } from '@/lib/useApi';
import { IncomeResponse, PositionResponse } from '@/types';

const NEAR_WINDOWS = [
  { label: 'Próximos 30 dias', days: 30 },
  { label: 'Próximos 90 dias', days: 90 },
  { label: 'Próximos 12 meses', days: 365 },
];

const Stat: React.FC<{ label: string; children: React.ReactNode; detail?: string }> = ({ label, children, detail }) => (
  <Card>
    <p className="text-xs text-muted mb-1">{label}</p>
    <p className="text-lg sm:text-xl lg:text-2xl font-semibold tabular-nums break-words">{children}</p>
    {detail && <p className="text-xs text-muted mt-1">{detail}</p>}
  </Card>
);

const MaturitiesPage: React.FC = () => {
  const { formatCurrency } = useFormat();
  const position = useApi<PositionResponse>('/position');
  const income = useApi<IncomeResponse>('/income');
  const targets = useApi<Targets>('/targets');
  const [selected, setSelected] = useState<CashMonth | null>(null);
  const today = useMemo(() => new Date(), []);

  const assets = useMemo(() => position.data?.assets ?? [], [position.data]);
  const rows = useMemo(() => income.data?.rows ?? [], [income.data]);
  const titles = useMemo(() => titlesWithMaturity(assets), [assets]);
  const months = useMemo(() => buildCashMonths(assets, rows, today), [assets, rows, today]);

  if (position.isLoading && !position.data) return <LoadingState label="Carregando vencimentos..." />;
  if (position.error && !position.data) return <ErrorState message={position.error} onRetry={position.reload} />;

  if (titles.length === 0) {
    return (
      <>
        <PageHeader title="Vencimentos" />
        <Card>
          <EmptyState
            title="Nenhum título com vencimento"
            description="Os vencimentos vêm do relatório de posição da B3."
            action={<Link href="/orders?import=1"><Button variant="primary">Importar da B3</Button></Link>}
          />
        </Card>
      </>
    );
  }

  const unknownMaturity = assets.filter((asset) => asset.asset_class === 'RF' && !asset.maturity_date);
  const monthsWithMaturity = months.filter((month) => month.maturities.length > 0);

  const simulate = (month: CashMonth) => {
    setSelected(month);
  };

  return (
    <>
      <PageHeader
        title="Vencimentos e caixa"
        subtitle="Quanto deve entrar em cada mês e onde reinvestir. Os valores no vencimento são estimativas pela taxa implícita de cada título."
      />

      <div className="space-y-4">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {NEAR_WINDOWS.map(({ label, days }) => {
            const within = titles.filter((asset) => daysUntil(asset.maturity_date as string, today) <= days);
            return (
              <Stat key={label} label={label} detail={`${within.length} título(s)`}>
                {formatCurrency(within.reduce((sum, asset) => sum + maturityValue(asset), 0))}
              </Stat>
            );
          })}
          <Stat label="Proventos por mês" detail="Média dos últimos 12 meses, sem juros de renda fixa">
            {formatCurrency(expectedMonthlyIncome(rows, today))}
          </Stat>
        </div>

        <Card>
          <CardTitle>Entradas previstas</CardTitle>
          <CashFlowBars months={months} onSelect={simulate} />
        </Card>

        <div className="grid xl:grid-cols-2 gap-4 items-start">
          <Card>
            <CardTitle>Por mês</CardTitle>
            {monthsWithMaturity.length === 0 && <p className="text-sm text-muted">Nenhum vencimento nos próximos 24 meses.</p>}
            <ul className="space-y-1">
              {monthsWithMaturity.map((month) => (
                <li key={month.key}>
                  <details className="group border-b border-line/50 last:border-b-0">
                    <summary className="cursor-pointer list-none py-2 px-2 rounded-lg hover:bg-raised/50 flex flex-wrap justify-between gap-x-4 gap-y-1 text-sm">
                      <span className="font-medium">
                        <span aria-hidden className="inline-block mr-1.5 text-muted transition group-open:rotate-90">›</span>
                        {monthLabel(month.key)}
                      </span>
                      <span className="tabular-nums">{formatCurrency(month.maturityValue)} <span className="text-muted">· {month.maturities.length} título(s)</span></span>
                    </summary>
                    <ul className="px-2 pb-2 text-sm space-y-2">
                      {month.maturities.map((asset) => (
                        <li key={asset.name} className="flex justify-between gap-3">
                          <span className="min-w-0">
                            <Link href={`/tickers/${encodeURIComponent(asset.name)}`} className="text-accent hover:underline break-all">{asset.name}</Link>
                            <span className="block text-xs text-muted">
                              {formatDate(asset.maturity_date)} · {asset.issuer ?? '-'} · {asset.category ?? '-'}
                            </span>
                          </span>
                          <span className="text-right tabular-nums whitespace-nowrap">
                            {formatCurrency(maturityValue(asset))}
                            <span className="block text-xs text-muted">{formatPercent(asset.estimated_rate)} a.a. est.</span>
                          </span>
                        </li>
                      ))}
                      <li>
                        <Button onClick={() => simulate(month)}>Simular reinvestimento</Button>
                      </li>
                    </ul>
                  </details>
                </li>
              ))}
            </ul>
          </Card>

          {selected && targets.data ? (
            <ContributionCalculator
              key={selected.key}
              assets={assetsAfterMonth(assets, selected)}
              targets={targets.data}
              initialAmount={selected.maturityValue + selected.expectedIncome}
              title={`Reinvestir em ${monthLabel(selected.key)}`}
              description="Valor dos títulos que vencem mais os proventos estimados do mês, dividido entre o que está abaixo da meta. Os títulos que vencem já saem da conta."
            />
          ) : (
            <Card>
              <CardTitle>Reinvestimento</CardTitle>
              <p className="text-sm text-muted">Escolha um mês para simular onde colocar o dinheiro, usando suas metas.</p>
            </Card>
          )}
        </div>

        {unknownMaturity.length > 0 && (
          <Card>
            <CardTitle>Títulos sem vencimento conhecido ({unknownMaturity.length})</CardTitle>
            <p className="text-sm text-muted mb-2">
              Comprados depois do último relatório de posição, que é de onde vem o vencimento. Envie um relatório novo para incluí-los no calendário.
            </p>
            <p className="text-sm text-soft break-words">{unknownMaturity.map((asset) => asset.name).join(', ')}</p>
          </Card>
        )}
      </div>
    </>
  );
};

export default MaturitiesPage;
