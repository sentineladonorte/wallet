'use client'

import React from 'react';
import ChevronRightIcon from '@mui/icons-material/ChevronRight';
import AllocationDonut from '@/components/charts/allocationDonut';
import { Card, EmptyState } from '@/components/ui';
import {
  AllocationFilter, AllocationGroup, Dimension, availableDimensions, dimensionLabel, groupAssets,
} from '@/lib/allocation';
import { investidor10Url, OTHER_COLOR } from '@/lib/assets';
import { formatCurrency, formatPercent } from '@/lib/format';
import { Position } from '@/types';

const AllocationExplorer: React.FC<{
  assets: Position[];
  filters: AllocationFilter[];
  dimension: Dimension;
  onDimensionChange: (dimension: Dimension) => void;
  onSelect: (group: AllocationGroup) => void;
  onBreadcrumb: (depth: number) => void;
}> = ({ assets, filters, dimension, onDimensionChange, onSelect, onBreadcrumb }) => {
  const groups = groupAssets(assets, dimension);
  const total = groups.reduce((sum, group) => sum + group.value, 0);
  const isAssetLevel = dimension === 'name';
  const classOf = (name: string) => assets.find((asset) => asset.name === name)?.asset_class;
  const canSelect = (group: AllocationGroup) =>
    !isAssetLevel || Boolean(investidor10Url(classOf(group.key), group.key));

  return (
    <Card className="h-full">
      <nav aria-label="Nível da distribuição" className="flex flex-wrap items-center gap-1 text-sm mb-3">
        <button
          type="button"
          onClick={() => onBreadcrumb(0)}
          className={filters.length ? 'text-muted hover:text-ink' : 'font-semibold'}
        >
          Carteira
        </button>
        {filters.map((filter, index) => (
          <React.Fragment key={filter.dimension}>
            <ChevronRightIcon sx={{ fontSize: 16 }} className="text-muted" />
            <button
              type="button"
              onClick={() => onBreadcrumb(index + 1)}
              className={index === filters.length - 1 ? 'font-semibold' : 'text-muted hover:text-ink'}
            >
              {filter.label}
            </button>
          </React.Fragment>
        ))}
      </nav>

      <div role="tablist" aria-label="Agrupar por" className="flex flex-wrap gap-1 mb-4">
        {availableDimensions(filters).map(({ key, label }) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={dimension === key}
            onClick={() => onDimensionChange(key)}
            className={`px-2.5 py-1 rounded-md text-xs transition ${
              dimension === key ? 'bg-raised text-ink' : 'text-muted hover:text-ink'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {groups.length === 0 ? (
        <EmptyState title="Nada para mostrar nesta visão" description="Nenhum ativo com valor se encaixa nessa seleção." />
      ) : (
        <div className="grid md:grid-cols-[280px_1fr] gap-6 items-start">
          <AllocationDonut
            groups={groups}
            total={total}
            caption={dimensionLabel(dimension)}
            onSelect={onSelect}
          />
          <ul className="max-h-[300px] overflow-y-auto pr-1 space-y-0.5">
            {groups.map((group) => (
              <li key={group.key}>
                <button
                  type="button"
                  disabled={!canSelect(group)}
                  onClick={() => onSelect(group)}
                  title={isAssetLevel ? `Abrir ${group.label} no Investidor10` : `Ver ${group.label}`}
                  className="w-full text-left rounded-lg px-2 py-1.5 enabled:hover:bg-raised transition disabled:cursor-default"
                >
                  <span className="flex items-center gap-2 text-sm">
                    <span
                      aria-hidden
                      className="w-2.5 h-2.5 rounded-sm shrink-0"
                      style={{ backgroundColor: group.folded ? OTHER_COLOR : group.color }}
                    />
                    <span className="truncate flex-1 min-w-0">{group.label}</span>
                    <span className="tabular-nums text-soft">{formatCurrency(group.value)}</span>
                    <span className="tabular-nums text-muted w-14 text-right">{formatPercent(group.share)}</span>
                  </span>
                  <span aria-hidden className="block h-1 mt-1 ml-[18px] rounded-full bg-raised overflow-hidden">
                    <span className="block h-full rounded-full bg-muted" style={{ width: `${group.share}%` }} />
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  );
};

export default AllocationExplorer;
