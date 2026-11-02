import React from 'react';
import WarningAmberIcon from '@mui/icons-material/WarningAmber';
import { Card, CardTitle } from '@/components/ui';
import { formatCurrency, formatDate, formatPercent } from '@/lib/format';
import { Position } from '@/types';

const FGC_LIMIT = 250000;
const TOP_ASSETS = 5;
const NEXT_MATURITIES = 5;

const Insights: React.FC<{ assets: Position[] }> = ({ assets }) => {
  const priced = assets.filter((asset) => asset.value);
  const total = priced.reduce((sum, asset) => sum + (asset.value as number), 0);
  const top = [...priced].sort((a, b) => (b.value as number) - (a.value as number)).slice(0, TOP_ASSETS);
  const topShare = total ? (top.reduce((sum, asset) => sum + (asset.value as number), 0) / total) * 100 : 0;

  const issuers: Record<string, number> = {};
  priced
    .filter((asset) => asset.asset_class === 'RF' && asset.sub_category !== 'Tesouro Direto' && asset.issuer)
    .forEach((asset) => {
      const issuer = asset.issuer as string;
      issuers[issuer] = (issuers[issuer] || 0) + (asset.value as number);
    });
  const topIssuers = Object.keys(issuers).sort((a, b) => issuers[b] - issuers[a]);
  const largestIssuer = topIssuers[0];
  const overLimit = topIssuers.filter((issuer) => issuers[issuer] > FGC_LIMIT);

  const maturities = priced
    .filter((asset) => asset.maturity_date)
    .sort((a, b) => (a.maturity_date as string).localeCompare(b.maturity_date as string))
    .slice(0, NEXT_MATURITIES);

  const hasFixedIncome = priced.some((asset) => asset.asset_class === 'RF');
  const columns = hasFixedIncome ? 'md:grid-cols-3' : '';

  if (priced.length === 0) return null;

  return (
    <div className={`grid ${columns} gap-4`}>
      <Card>
        <CardTitle>Concentração</CardTitle>
        <p className="text-2xl font-semibold tabular-nums">{formatPercent(topShare)}</p>
        <p className="text-sm text-muted mb-3">da seleção nos {top.length} maiores ativos</p>
        <ul className="text-sm space-y-1">
          {top.map((asset) => (
            <li key={asset.name} className="flex justify-between gap-2">
              <span className="truncate">{asset.name}</span>
              <span className="tabular-nums text-soft">{formatPercent(((asset.value as number) / total) * 100)}</span>
            </li>
          ))}
        </ul>
      </Card>

      {hasFixedIncome && (
        <>
          <Card>
            <CardTitle>Exposição por emissor</CardTitle>
            {largestIssuer ? (
              <>
                <p className="text-2xl font-semibold tabular-nums">{formatCurrency(issuers[largestIssuer])}</p>
                <p className="text-sm text-muted mb-3 truncate" title={largestIssuer}>{largestIssuer}</p>
                {overLimit.length > 0 ? (
                  <p className="flex items-start gap-1.5 text-sm text-warn">
                    <WarningAmberIcon sx={{ fontSize: 18 }} />
                    <span>{overLimit.length} emissor(es) acima de {formatCurrency(FGC_LIMIT)}, o limite de garantia do FGC.</span>
                  </p>
                ) : (
                  <p className="text-sm text-soft">
                    Todos abaixo de {formatCurrency(FGC_LIMIT)}, o limite de garantia do FGC por instituição.
                  </p>
                )}
              </>
            ) : (
              <p className="text-sm text-muted">Sem CDB, LCI ou LCA com emissor informado.</p>
            )}
          </Card>

          <Card>
            <CardTitle>Próximos vencimentos</CardTitle>
            <ul className="text-sm space-y-2">
              {maturities.map((asset) => (
                <li key={asset.name} className="flex justify-between gap-2">
                  <span className="min-w-0">
                    <span className="block tabular-nums">{formatDate(asset.maturity_date)}</span>
                    <span className="block text-xs text-muted truncate" title={asset.issuer ?? asset.name}>
                      {asset.issuer ?? asset.name}
                    </span>
                  </span>
                  <span className="tabular-nums text-soft">{formatCurrency(asset.value)}</span>
                </li>
              ))}
            </ul>
          </Card>
        </>
      )}
    </div>
  );
};

export default Insights;
