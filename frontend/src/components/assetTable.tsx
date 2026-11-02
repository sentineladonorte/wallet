'use client'

import React, { useMemo, useState } from 'react';
import ShowChartIcon from '@mui/icons-material/ShowChart';
import Link from 'next/link';
import AssetLink from '@/components/assetLink';
import { inputClass } from '@/components/ui';
import { classLabel } from '@/lib/assets';
import { AssetInfo } from '@/types';

const MAX_ROWS = 100;

const AssetTable: React.FC<{ assets: AssetInfo[] }> = ({ assets }) => {
  const [search, setSearch] = useState('');

  const matches = useMemo(() => {
    const query = search.trim().toLowerCase();
    return assets
      .filter((asset) => `${asset.ticker} ${asset.trading_name ?? ''} ${asset.company_name ?? ''}`.toLowerCase().includes(query))
      .sort((a, b) => a.ticker.localeCompare(b.ticker));
  }, [assets, search]);

  return (
    <div>
      <input
        type="search"
        aria-label="Buscar ativo"
        placeholder="Buscar por ticker ou nome"
        className={`${inputClass} sm:max-w-sm mb-3`}
        value={search}
        onChange={(event) => setSearch(event.target.value)}
      />
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-line text-xs text-muted">
              <th className="py-2 px-2 text-left font-medium">Ticker</th>
              <th className="py-2 px-2 text-left font-medium">Nome</th>
              <th className="py-2 px-2 text-left font-medium hidden sm:table-cell">Classe</th>
              <th className="py-2 px-2 text-left font-medium hidden md:table-cell">Categoria</th>
              <th className="py-2 px-2 text-left font-medium hidden lg:table-cell">Subcategoria</th>
              <th aria-label="Ações" className="py-2 px-2" />
            </tr>
          </thead>
          <tbody>
            {matches.slice(0, MAX_ROWS).map((asset) => (
              <tr key={asset.ticker} className="border-b border-line/50 hover:bg-raised/50">
                <td className="py-2 px-2"><AssetLink name={asset.ticker} assetClass={asset.asset_class} /></td>
                <td className="py-2 px-2 text-soft">{asset.trading_name || asset.company_name || '-'}</td>
                <td className="py-2 px-2 hidden sm:table-cell whitespace-nowrap">{asset.asset_class ? classLabel(asset.asset_class) : '-'}</td>
                <td className="py-2 px-2 hidden md:table-cell text-soft">{asset.category || '-'}</td>
                <td className="py-2 px-2 hidden lg:table-cell text-soft">{asset.sub_category || '-'}</td>
                <td className="py-2 px-2 text-right">
                  <Link href={`/tickers/${asset.ticker}`} aria-label={`Ver detalhes de ${asset.ticker}`} title="Ver detalhes" className="inline-block p-1.5 rounded-md text-muted hover:text-ink hover:bg-raised">
                    <ShowChartIcon fontSize="small" />
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-muted mt-3">
        {matches.length > MAX_ROWS
          ? `Mostrando ${MAX_ROWS} de ${matches.length} ativos. Refine a busca para ver os demais.`
          : `${matches.length} ativo(s).`}
      </p>
    </div>
  );
};

export default AssetTable;
