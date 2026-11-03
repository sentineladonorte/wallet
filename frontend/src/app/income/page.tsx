'use client'

import React, { useMemo, useState } from 'react';
import Link from 'next/link';
import AssetLink from '@/components/assetLink';
import IncomeBars, { IncomePeriod } from '@/components/charts/incomeBars';
import { Button, Card, CardTitle, EmptyState, ErrorState, LoadingState, PageHeader, inputClass } from '@/components/ui';
import { CLASS_COLORS, classLabel } from '@/lib/assets';
import { formatDate, formatPercent } from '@/lib/format';
import { groupByAsset, monthKey, sum, twelveMonthsStart } from '@/lib/income';
import { useFormat } from '@/lib/privacy';
import { useApi } from '@/lib/useApi';
import { IncomeResponse } from '@/types';

const MONTHS_IN_YEAR = 12;
const RECENT_PAYMENTS = 12;

const Stat: React.FC<{ label: string; children: React.ReactNode; detail?: string }> = ({ label, children, detail }) => (
  <Card>
    <p className="text-xs text-muted mb-1">{label}</p>
    <p className="text-lg sm:text-xl lg:text-2xl font-semibold tabular-nums break-words">{children}</p>
    {detail && <p className="text-xs text-muted mt-1">{detail}</p>}
  </Card>
);

const IncomePage: React.FC = () => {
  const { formatCurrency } = useFormat();
  const { data, isLoading, error, reload } = useApi<IncomeResponse>('/income');
  const [year, setYear] = useState('');
  const [assetClass, setAssetClass] = useState('');
  const [period, setPeriod] = useState<IncomePeriod>('month');

  const rows = useMemo(() => data?.rows ?? [], [data]);
  const years = useMemo(() => Array.from(new Set(rows.map((row) => row.date.slice(0, 4)))).sort().reverse(), [rows]);
  const classes = useMemo(() => Array.from(new Set(rows.map((row) => row.asset_class))).sort(), [rows]);
  const windowStart = useMemo(() => twelveMonthsStart(new Date()), []);

  const filtered = useMemo(
    () => rows.filter((row) => (!year || row.date.startsWith(year)) && (!assetClass || row.asset_class === assetClass)),
    [rows, year, assetClass],
  );
  const received = filtered.filter((row) => row.type !== 'Taxas');
  const assets = useMemo(() => groupByAsset(filtered, data?.costs ?? {}, windowStart), [filtered, data, windowStart]);

  if (isLoading && !data) return <LoadingState label="Carregando proventos..." />;
  if (error && !data) return <ErrorState message={error} onRetry={reload} />;
  if (!data) return null;

  if (rows.length === 0) {
    return (
      <>
        <PageHeader title="Proventos" />
        <Card>
          <EmptyState
            title="Nenhum provento registrado"
            description="Os proventos vêm do extrato de movimentação da B3. Importe o arquivo para ver dividendos, rendimentos e juros."
            action={<Link href="/orders?import=1"><Button variant="primary">Importar da B3</Button></Link>}
          />
        </Card>
      </>
    );
  }

  const lastTwelve = received.filter((row) => monthKey(row.date) >= windowStart);
  const fees = filtered.filter((row) => row.type === 'Taxas');

  return (
    <>
      <PageHeader title="Proventos" subtitle="Valores como aparecem no extrato da B3." />

      <div className="space-y-4">
        <div className="flex flex-wrap items-center gap-3">
          <select aria-label="Filtrar por ano" className={`${inputClass} !w-auto`} value={year} onChange={(event) => setYear(event.target.value)}>
            <option value="">Todos os anos</option>
            {years.map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
          <div role="group" aria-label="Filtrar por classe" className="flex flex-wrap gap-1.5">
            {['', ...classes].map((key) => (
              <button
                key={key || 'all'}
                type="button"
                aria-pressed={assetClass === key}
                onClick={() => setAssetClass(key)}
                className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-xs transition ${
                  assetClass === key ? 'bg-raised border-muted text-ink' : 'border-line text-muted hover:text-ink'
                }`}
              >
                {key && <span aria-hidden className="w-2 h-2 rounded-sm" style={{ backgroundColor: CLASS_COLORS[key] }} />}
                {key ? classLabel(key) : 'Todas'}
              </button>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <Stat label={year ? `Recebido em ${year}` : 'Recebido no total'} detail={`${received.length} pagamento(s)`}>
            {formatCurrency(sum(received))}
          </Stat>
          <Stat label="Últimos 12 meses">{formatCurrency(sum(lastTwelve))}</Stat>
          <Stat label="Média mensal (12 meses)">{formatCurrency(sum(lastTwelve) / MONTHS_IN_YEAR)}</Stat>
          <Stat label="Taxas pagas" detail="Custódia do Tesouro Direto">{formatCurrency(Math.abs(sum(fees)))}</Stat>
        </div>

        <Card>
          <CardTitle
            action={(
              <div role="group" aria-label="Agrupar gráfico por" className="flex gap-1">
                {([['month', 'Mês'], ['year', 'Ano']] as [IncomePeriod, string][]).map(([key, label]) => (
                  <button
                    key={key}
                    type="button"
                    aria-pressed={period === key}
                    onClick={() => setPeriod(key)}
                    className={`px-2.5 py-1 rounded-md text-xs transition ${period === key ? 'bg-raised text-ink' : 'text-muted hover:text-ink'}`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            )}
          >
            Recebido por {period === 'year' ? 'ano' : 'mês'}
          </CardTitle>
          <IncomeBars rows={filtered} period={period} />
        </Card>

        <div className="grid xl:grid-cols-3 gap-4">
          <Card className="xl:col-span-2">
            <CardTitle>Por ativo</CardTitle>
            <div className="overflow-auto max-h-[560px]">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-line text-xs text-muted">
                    <th className="sticky top-0 bg-surface py-2 px-2 text-left font-medium">Ativo</th>
                    <th className="sticky top-0 bg-surface py-2 px-2 text-right font-medium">Total</th>
                    <th className="sticky top-0 bg-surface py-2 px-2 text-right font-medium hidden sm:table-cell">12 meses</th>
                    <th className="sticky top-0 bg-surface py-2 px-2 text-right font-medium hidden md:table-cell" title="Proventos dos últimos 12 meses sobre o custo atual">Sobre o custo</th>
                    <th className="sticky top-0 bg-surface py-2 px-2 text-right font-medium hidden md:table-cell">Último</th>
                  </tr>
                </thead>
                <tbody>
                  {assets.map((asset) => (
                    <tr key={asset.name} className="border-b border-line/50 hover:bg-raised/50">
                      <td className="py-2 px-2 max-w-[200px] sm:max-w-[300px]">
                        <AssetLink name={asset.name} assetClass={asset.assetClass} />
                        <div className="text-xs text-muted truncate" title={asset.description}>{asset.description}</div>
                      </td>
                      <td className="py-2 px-2 text-right tabular-nums whitespace-nowrap">{formatCurrency(asset.total)}</td>
                      <td className="py-2 px-2 text-right tabular-nums whitespace-nowrap hidden sm:table-cell text-soft">{formatCurrency(asset.lastTwelveMonths)}</td>
                      <td className="py-2 px-2 text-right tabular-nums hidden md:table-cell text-soft">
                        {asset.cost > 0 ? formatPercent((asset.lastTwelveMonths / asset.cost) * 100) : '-'}
                      </td>
                      <td className="py-2 px-2 text-right tabular-nums hidden md:table-cell text-soft whitespace-nowrap">{formatDate(asset.lastDate)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>

          <Card>
            <CardTitle>Últimos pagamentos</CardTitle>
            <ul className="text-sm space-y-2.5">
              {received.slice(0, RECENT_PAYMENTS).map((row, index) => (
                <li key={`${row.name}-${row.date}-${index}`} className="flex justify-between gap-3">
                  <span className="min-w-0">
                    <span className="block truncate">{row.name}</span>
                    <span className="block text-xs text-muted tabular-nums">{formatDate(row.date)} · {row.type}</span>
                  </span>
                  <span className="tabular-nums text-soft whitespace-nowrap">{formatCurrency(row.value)}</span>
                </li>
              ))}
            </ul>
          </Card>
        </div>
      </div>
    </>
  );
};

export default IncomePage;
