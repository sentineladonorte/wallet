'use client'

import React, { useMemo, useState } from 'react';
import DownloadIcon from '@mui/icons-material/Download';
import EditIcon from '@mui/icons-material/Edit';
import ShowChartIcon from '@mui/icons-material/ShowChart';
import Link from 'next/link';
import AssetLink from '@/components/assetLink';
import { Button, EstimatedBadge, IconButton, ProfitText, inputClass } from '@/components/ui';
import { CLASS_COLORS, classLabel } from '@/lib/assets';
import { formatCurrency, formatPercent, formatQuantity, formatSignedPercent } from '@/lib/format';
import { Position } from '@/types';

type SortKey = 'name' | 'asset_class' | 'category' | 'volume' | 'average' | 'price' | 'value' | 'profit_pct';

const COLUMNS: { key: SortKey; label: string; numeric?: boolean; className?: string }[] = [
  { key: 'name', label: 'Ativo' },
  { key: 'asset_class', label: 'Classe', className: 'hidden md:table-cell' },
  { key: 'category', label: 'Categoria', className: 'hidden lg:table-cell' },
  { key: 'volume', label: 'Qtd.', numeric: true, className: 'hidden sm:table-cell' },
  { key: 'average', label: 'Preço médio', numeric: true, className: 'hidden lg:table-cell' },
  { key: 'price', label: 'Preço', numeric: true, className: 'hidden sm:table-cell' },
  { key: 'value', label: 'Valor', numeric: true },
  { key: 'profit_pct', label: 'Resultado', numeric: true },
];

const averagePrice = (asset: Position) => (asset.volume ? asset.cost / asset.volume : null);

const sortValue = (asset: Position, key: SortKey) => (key === 'average' ? averagePrice(asset) : asset[key]);

const compare = (a: Position, b: Position, key: SortKey) => {
  const first = sortValue(a, key);
  const second = sortValue(b, key);
  // Sem valor vai sempre para o fim, por isso retorna antes de aplicar a direção.
  if (first === null) return second === null ? 0 : Infinity;
  if (second === null) return -Infinity;
  if (typeof first === 'string') return first.localeCompare(String(second), 'pt-BR');
  return first - (second as number);
};

const csvCell = (value: string | number | null) => {
  if (value === null) return '';
  const text = typeof value === 'number' ? value.toString().replace('.', ',') : value;
  return /[;"\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
};

const exportCsv = (assets: Position[]) => {
  const header = ['Ativo', 'Descrição', 'Classe', 'Categoria', 'Subcategoria', 'Quantidade', 'Custo', 'Preço', 'Valor', 'Resultado (R$)', 'Resultado (%)', 'Custo estimado'];
  const rows = assets.map((asset) => [
    asset.name, asset.description, classLabel(asset.asset_class), asset.category, asset.sub_category,
    asset.volume, asset.cost, asset.price, asset.value, asset.profit, asset.profit_pct, asset.cost_estimated ? 'Sim' : 'Não',
  ]);
  const content = [header, ...rows].map((row) => row.map(csvCell).join(';')).join('\n');
  // O BOM faz o Excel reconhecer os acentos.
  const url = URL.createObjectURL(new Blob([`﻿${content}`], { type: 'text/csv;charset=utf-8' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = 'carteira.csv';
  link.click();
  URL.revokeObjectURL(url);
};

const PositionsTable: React.FC<{
  assets: Position[];
  total: number;
  onEditClassification: (asset: Position) => void;
}> = ({ assets, total, onEditClassification }) => {
  const [search, setSearch] = useState('');
  const [sort, setSort] = useState<{ key: SortKey; ascending: boolean }>({ key: 'value', ascending: false });

  const visible = useMemo(() => {
    const query = search.trim().toLowerCase();
    const matches = assets.filter((asset) =>
      `${asset.name} ${asset.description ?? ''} ${asset.category ?? ''}`.toLowerCase().includes(query)
    );
    return matches.sort((a, b) => {
      const result = compare(a, b, sort.key);
      if (Math.abs(result) === Infinity) return result;
      return sort.ascending ? result : -result;
    });
  }, [assets, search, sort]);

  const toggleSort = (key: SortKey) => {
    setSort((current) => ({
      key,
      ascending: current.key === key ? !current.ascending : key === 'name' || key === 'asset_class' || key === 'category',
    }));
  };

  return (
    <div>
      <div className="flex flex-wrap gap-2 justify-between mb-3">
        <input
          type="search"
          aria-label="Buscar ativo"
          placeholder="Buscar por ativo, descrição ou categoria"
          className={`${inputClass} sm:max-w-sm`}
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
        <Button onClick={() => exportCsv(visible)}>
          <DownloadIcon fontSize="small" /> Exportar CSV
        </Button>
      </div>
      <div className="overflow-auto max-h-[640px]">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-line text-xs text-muted">
              {COLUMNS.map((column) => {
                const isSorted = sort.key === column.key;
                let ariaSort: 'ascending' | 'descending' | 'none' = 'none';
                if (isSorted) ariaSort = sort.ascending ? 'ascending' : 'descending';
                return (
                  <th key={column.key} aria-sort={ariaSort} className={`sticky top-0 z-10 bg-surface py-2 px-2 font-medium whitespace-nowrap ${column.numeric ? 'text-right' : 'text-left'} ${column.className ?? ''}`}>
                    <button type="button" onClick={() => toggleSort(column.key)} className="hover:text-ink">
                      {column.label}{isSorted && (sort.ascending ? ' ↑' : ' ↓')}
                    </button>
                  </th>
                );
              })}
              <th aria-label="Ações" className="sticky top-0 bg-surface py-2 px-2" />
            </tr>
          </thead>
          <tbody>
            {visible.map((asset) => (
              <tr key={asset.name} className="border-b border-line/50 hover:bg-raised/50">
                <td className="py-2 px-2 max-w-[220px] sm:max-w-[300px]">
                  <AssetLink name={asset.name} assetClass={asset.asset_class} />
                  {asset.description && (
                    <div className="text-xs text-muted truncate" title={asset.description}>{asset.description}</div>
                  )}
                </td>
                <td className="py-2 px-2 hidden md:table-cell whitespace-nowrap">
                  <span className="inline-flex items-center gap-1.5">
                    <span aria-hidden className="w-2 h-2 rounded-sm" style={{ backgroundColor: CLASS_COLORS[asset.asset_class] }} />
                    {classLabel(asset.asset_class)}
                  </span>
                </td>
                <td className="py-2 px-2 hidden lg:table-cell text-soft">
                  {asset.category || '-'}
                  {asset.sub_category && <div className="text-xs text-muted">{asset.sub_category}</div>}
                </td>
                <td className="py-2 px-2 text-right tabular-nums hidden sm:table-cell">{formatQuantity(asset.volume)}</td>
                <td className="py-2 px-2 text-right tabular-nums hidden lg:table-cell whitespace-nowrap">
                  {formatCurrency(averagePrice(asset))}
                  {asset.cost_estimated && <div><EstimatedBadge /></div>}
                </td>
                <td className="py-2 px-2 text-right tabular-nums hidden sm:table-cell whitespace-nowrap">{formatCurrency(asset.price)}</td>
                <td className="py-2 px-2 text-right tabular-nums whitespace-nowrap">
                  {formatCurrency(asset.value)}
                  {asset.value !== null && total > 0 && (
                    <div className="text-xs text-muted">{formatPercent((asset.value / total) * 100)}</div>
                  )}
                </td>
                <td className="py-2 px-2 text-right tabular-nums whitespace-nowrap">
                  <ProfitText value={asset.profit}>{formatSignedPercent(asset.profit_pct)}</ProfitText>
                  {asset.profit !== null && <div className="text-xs text-muted">{formatCurrency(asset.profit)}</div>}
                </td>
                <td className="py-2 px-2 whitespace-nowrap text-right">
                  <Link
                    href={`/tickers/${encodeURIComponent(asset.name)}`}
                    aria-label={`Ver detalhes de ${asset.name}`}
                    title="Ver detalhes"
                    className="inline-block p-1.5 rounded-md text-muted hover:text-ink hover:bg-raised"
                  >
                    <ShowChartIcon fontSize="small" />
                  </Link>
                  {asset.asset_class !== 'RF' && (
                    <IconButton label={`Editar classificação de ${asset.name}`} onClick={() => onEditClassification(asset)}>
                      <EditIcon fontSize="small" />
                    </IconButton>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {visible.length === 0 && <p className="text-sm text-muted text-center py-8">Nenhum ativo encontrado.</p>}
      </div>
    </div>
  );
};

export default PositionsTable;
