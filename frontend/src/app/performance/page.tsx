'use client'

import React, { useMemo, useState } from 'react';
import Link from 'next/link';
import PerformanceChart from '@/components/charts/performanceChart';
import { Button, Card, CardTitle, EmptyState, ErrorState, LoadingState, PageHeader, ProfitText } from '@/components/ui';
import { CLASS_LABELS, CLASS_COLORS, classLabel } from '@/lib/assets';
import { formatDate, formatSignedPercent } from '@/lib/format';
import { PERIODS, PeriodKey, finalValue, windowFor } from '@/lib/performance';
import { useApi } from '@/lib/useApi';
import { PerformanceSeries } from '@/types';

const CLASSES = Object.keys(CLASS_LABELS).filter((key) => key !== 'INT');

const PerformancePage: React.FC = () => {
  const [assetClass, setAssetClass] = useState('');
  const [period, setPeriod] = useState<PeriodKey>('12m');
  const { data, isLoading, error, reload } = useApi<PerformanceSeries>('/performance', assetClass ? { class: assetClass } : undefined);

  const chosen = useMemo(() => (data ? windowFor(data, period) : null), [data, period]);
  const table = useMemo(
    () => (data ? PERIODS.map((item) => ({ ...item, window: windowFor(data, item.key) })) : []),
    [data],
  );

  if (isLoading && !data) return <LoadingState label="Calculando rentabilidade..." />;
  if (error && !data) return <ErrorState message={error} onRetry={reload} />;
  if (!data) return null;

  const chips = (
    <div role="group" aria-label="Filtrar por classe" className="flex flex-wrap gap-1.5">
      {['', ...CLASSES].map((key) => (
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
          {key ? classLabel(key) : 'Carteira toda'}
        </button>
      ))}
    </div>
  );

  if (data.dates.length === 0) {
    return (
      <>
        <PageHeader title="Rentabilidade" />
        <div className="space-y-4">
          {chips}
          <Card>
            <EmptyState
              title="Ainda sem histórico suficiente"
              description="A rentabilidade precisa de mais de um dia de histórico, com pelo menos R$ 1.000 aplicados. Importe o extrato de movimentação da B3 para calcular desde o começo."
              action={<Link href="/orders?import=1"><Button variant="primary">Importar da B3</Button></Link>}
            />
          </Card>
        </div>
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="Rentabilidade"
        subtitle={`Comparada ao CDI e ao Ibovespa, de ${formatDate(data.dates[0])} a ${formatDate(data.dates[data.dates.length - 1])}. Aportes e resgates não alteram o percentual.`}
      />

      <div className="space-y-4">
        {chips}

        <Card>
          <CardTitle
            action={(
              <div role="group" aria-label="Período" className="flex flex-wrap gap-1">
                {PERIODS.map((item) => (
                  <button
                    key={item.key}
                    type="button"
                    aria-pressed={period === item.key}
                    onClick={() => setPeriod(item.key)}
                    className={`px-2.5 py-1 rounded-md text-xs transition ${period === item.key ? 'bg-raised text-ink' : 'text-muted hover:text-ink'}`}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            )}
          >
            Acumulado
          </CardTitle>
          {chosen ? <PerformanceChart data={chosen} /> : <p className="text-sm text-muted py-8 text-center">Sem dados suficientes neste período.</p>}
        </Card>

        <Card>
          <CardTitle>Por período</CardTitle>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-line text-xs text-muted">
                  <th className="py-2 px-2 text-left font-medium">Período</th>
                  <th className="py-2 px-2 text-right font-medium">Carteira</th>
                  <th className="py-2 px-2 text-right font-medium">CDI</th>
                  <th className="py-2 px-2 text-right font-medium">Ibovespa</th>
                  <th className="py-2 px-2 text-right font-medium">Contra o CDI</th>
                </tr>
              </thead>
              <tbody>
                {table.map(({ key, label, window }) => {
                  const portfolio = window ? finalValue(window.portfolio) : null;
                  const cdi = window ? finalValue(window.cdi) : null;
                  const ibov = window ? finalValue(window.ibov) : null;
                  const versusCdi = portfolio !== null && cdi !== null ? portfolio - cdi : null;
                  return (
                    <tr key={key} className="border-b border-line/50 last:border-b-0">
                      <td className="py-2 px-2">{label}</td>
                      <td className="py-2 px-2 text-right tabular-nums"><ProfitText value={portfolio}>{formatSignedPercent(portfolio)}</ProfitText></td>
                      <td className="py-2 px-2 text-right tabular-nums text-soft">{formatSignedPercent(cdi)}</td>
                      <td className="py-2 px-2 text-right tabular-nums text-soft">{formatSignedPercent(ibov)}</td>
                      <td className="py-2 px-2 text-right tabular-nums"><ProfitText value={versusCdi}>{versusCdi === null ? '-' : `${versusCdi > 0 ? '+' : ''}${versusCdi.toFixed(1).replace('.', ',')} p.p.`}</ProfitText></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>

        <p className="text-xs text-muted">
          Inclui proventos recebidos, sem imposto. O Ibovespa é medido pelo BOVA11, ETF que replica o índice, e o CDI vem do Banco Central.
          A renda fixa é estimada entre os relatórios da B3, então o resultado recente pode mudar quando um relatório novo for enviado.
          {data.ignored_days > 0 && ` ${data.ignored_days} variação(ões) diária(s) acima de 40% sem operação correspondente foram desconsideradas, por serem provável desdobramento na cotação.`}
        </p>
      </div>
    </>
  );
};

export default PerformancePage;
