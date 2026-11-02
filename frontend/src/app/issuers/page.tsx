'use client'

import React from 'react';
import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutline';
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutline';
import WarningAmberIcon from '@mui/icons-material/WarningAmber';
import Link from 'next/link';
import { Card, CardTitle, EmptyState, ErrorState, LoadingState, PageHeader } from '@/components/ui';
import { formatDate } from '@/lib/format';
import { FGC_LIMIT_LABEL, IssuerExposure, IssuerStatus, groupByIssuer } from '@/lib/issuers';
import { useFormat } from '@/lib/privacy';
import { useApi } from '@/lib/useApi';
import { PositionResponse } from '@/types';

const STATUS: Record<IssuerStatus, { label: string; text: string; bar: string; icon: typeof WarningAmberIcon }> = {
  ok: { label: 'Dentro do limite', text: 'text-soft', bar: 'bg-accent', icon: CheckCircleOutlineIcon },
  near: { label: 'Perto do limite', text: 'text-warn', bar: 'bg-warn', icon: WarningAmberIcon },
  over: { label: 'Acima do limite', text: 'text-loss', bar: 'bg-loss', icon: ErrorOutlineIcon },
};

const Stat: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <Card>
    <p className="text-xs text-muted mb-1">{label}</p>
    <p className="text-lg sm:text-xl lg:text-2xl font-semibold tabular-nums break-words">{children}</p>
  </Card>
);

const IssuerRow: React.FC<{ issuer: IssuerExposure }> = ({ issuer }) => {
  const { formatCurrency, formatQuantity, formatLimitUsage } = useFormat();
  const status = STATUS[issuer.status];
  const StatusIcon = status.icon;

  return (
    <details className="group border-b border-line/50 last:border-b-0">
      <summary className="cursor-pointer list-none py-3 px-2 rounded-lg hover:bg-raised/50">
        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <span className="font-medium min-w-0 break-words">
            <span aria-hidden className="inline-block mr-1.5 text-muted transition group-open:rotate-90">›</span>
            {issuer.name}
          </span>
          <span className="tabular-nums text-sm">
            {formatCurrency(issuer.value)}
            <span className="text-muted"> ({formatLimitUsage(issuer.usedPercent)})</span>
          </span>
        </div>
        <div
          role="meter"
          aria-label={`Uso do limite do FGC em ${issuer.name}`}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.min(issuer.usedPercent, 100)}
          className="h-1.5 my-2 rounded-full bg-raised overflow-hidden"
        >
          <div className={`h-full rounded-full ${status.bar}`} style={{ width: `${Math.min(issuer.usedPercent, 100)}%` }} />
        </div>
        <div className="flex flex-wrap justify-between gap-x-4 gap-y-1 text-xs text-muted">
          <span className={`inline-flex items-center gap-1 ${status.text}`}>
            <StatusIcon sx={{ fontSize: 14 }} /> {status.label}
          </span>
          <span>
            {issuer.titles.length} título(s) · Disponível: <span className="tabular-nums">{formatCurrency(issuer.remaining)}</span>
            {issuer.nextMaturity && <> · Próximo vencimento: <span className="tabular-nums">{formatDate(issuer.nextMaturity)}</span></>}
          </span>
        </div>
      </summary>
      <div className="overflow-x-auto px-2 pb-3">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs text-muted border-b border-line">
              <th className="py-1.5 pr-2 text-left font-medium">Título</th>
              <th className="py-1.5 px-2 text-left font-medium">Tipo</th>
              <th className="py-1.5 px-2 text-left font-medium hidden sm:table-cell">Indexador</th>
              <th className="py-1.5 px-2 text-left font-medium">Vencimento</th>
              <th className="py-1.5 px-2 text-right font-medium hidden sm:table-cell">Qtd.</th>
              <th className="py-1.5 pl-2 text-right font-medium">Valor</th>
            </tr>
          </thead>
          <tbody>
            {issuer.titles.map((title) => (
              <tr key={title.name} className="border-b border-line/50 last:border-b-0">
                <td className="py-1.5 pr-2">
                  <Link href={`/tickers/${encodeURIComponent(title.name)}`} className="text-accent hover:underline">{title.name}</Link>
                </td>
                <td className="py-1.5 px-2">{title.sub_category ?? '-'}</td>
                <td className="py-1.5 px-2 hidden sm:table-cell">{title.category ?? '-'}</td>
                <td className="py-1.5 px-2 tabular-nums">{formatDate(title.maturity_date)}</td>
                <td className="py-1.5 px-2 text-right tabular-nums hidden sm:table-cell">{formatQuantity(title.volume)}</td>
                <td className="py-1.5 pl-2 text-right tabular-nums whitespace-nowrap">{formatCurrency(title.value)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
};

const IssuersPage: React.FC = () => {
  const { formatCurrency, formatLimitUsage } = useFormat();
  const { data, isLoading, error, reload } = useApi<PositionResponse>('/position');

  if (isLoading && !data) return <LoadingState label="Carregando emissores..." />;
  if (error && !data) return <ErrorState message={error} onRetry={reload} />;
  if (!data) return null;

  const { issuers, withoutIssuer } = groupByIssuer(data.assets);
  const total = issuers.reduce((sum, issuer) => sum + issuer.value, 0);
  const attention = issuers.filter((issuer) => issuer.status !== 'ok').length;

  return (
    <>
      <PageHeader title="Emissores" subtitle={<>Limite de garantia do FGC: <span className="tabular-nums">{FGC_LIMIT_LABEL}</span> por CPF, em cada instituição ou conglomerado.</>} />

      <div className="space-y-4">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <Stat label="Total em CDB, LCI e LCA">{formatCurrency(total)}</Stat>
          <Stat label="Emissores">{issuers.length}</Stat>
          <Stat label="Maior exposição">{issuers.length ? formatLimitUsage(issuers[0].usedPercent) : '-'}</Stat>
          <Stat label="Perto ou acima do limite">{attention}</Stat>
        </div>

        <Card>
          <CardTitle>Uso do limite por emissor</CardTitle>
          {issuers.length > 0
            ? issuers.map((issuer) => <IssuerRow key={issuer.name} issuer={issuer} />)
            : <EmptyState title="Nenhum emissor para acompanhar" description="Os emissores aparecem aqui quando a carteira tem CDB, LCI ou LCA." />}
        </Card>

        {withoutIssuer.length > 0 && (
          <Card>
            <CardTitle>Títulos sem emissor ({withoutIssuer.length})</CardTitle>
            <p className="text-sm text-muted mb-3">
              Eles ficam fora do controle de limites. Informe o emissor editando a boleta em{' '}
              <Link href="/orders" className="text-accent hover:underline">Boletas</Link>.
            </p>
            <ul className="text-sm space-y-1">
              {withoutIssuer.map((title) => (
                <li key={title.name} className="flex justify-between gap-3">
                  <span className="min-w-0 break-words">{title.name}</span>
                  <span className="tabular-nums text-soft whitespace-nowrap">{formatCurrency(title.value)}</span>
                </li>
              ))}
            </ul>
          </Card>
        )}

        <p className="text-xs text-muted">
          O limite inclui os rendimentos, então considera o valor atualizado de cada título. Bancos do mesmo conglomerado dividem a
          mesma garantia, o que esta tela não identifica: cada emissor aparece separado. Há ainda um teto global de R$ 1 milhão por CPF
          a cada 4 anos. Tesouro Direto não entra porque não tem cobertura do FGC. Confira as regras vigentes
          em <a href="https://www.fgc.org.br" target="_blank" rel="noopener noreferrer" className="text-accent hover:underline">fgc.org.br</a>.
        </p>
      </div>
    </>
  );
};

export default IssuersPage;
