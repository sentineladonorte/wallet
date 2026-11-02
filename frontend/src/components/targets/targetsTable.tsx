'use client'

import React, { FormEvent, useEffect, useMemo, useState } from 'react';
import AddIcon from '@mui/icons-material/Add';
import TargetBar from '@/components/targets/targetBar';
import { Button, inputClass } from '@/components/ui';
import { useToast } from '@/components/ui/toast';
import { formatPercent, formatSignedPercent } from '@/lib/format';
import { useFormat } from '@/lib/privacy';
import { Targets, TargetEntry, progressOf } from '@/lib/targets';
import { errorMessage } from '@/lib/useApi';
import api from '@/services/api';

const HUNDRED = 100;
const SUM_TOLERANCE = 0.001;

const toDrafts = (saved: Record<string, number>) => {
  const drafts: Record<string, string> = {};
  Object.keys(saved).forEach((key) => { drafts[key] = String(saved[key]); });
  return drafts;
};

const parseDraft = (draft: string | undefined) => {
  if (draft === undefined || draft.trim() === '') return null;
  const value = Number(draft);
  return Number.isNaN(value) ? null : value;
};

const TargetsTable: React.FC<{
  /** `null` edita as metas das classes na carteira; uma classe edita as categorias dela. */
  assetClass: string | null;
  entries: TargetEntry[];
  total: number;
  saved: Record<string, number>;
  suggestions?: string[];
  firstColumn: string;
  onSaved: (targets: Targets) => void;
}> = ({ assetClass, entries, total, saved, suggestions = [], firstColumn, onSaved }) => {
  const { formatCurrency } = useFormat();
  const toast = useToast();
  const [drafts, setDrafts] = useState(() => toDrafts(saved));
  const [newCategory, setNewCategory] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const savedKey = JSON.stringify(saved);

  useEffect(() => {
    setDrafts(toDrafts(JSON.parse(savedKey)));
  }, [savedKey]);

  const rows = useMemo(() => {
    const known = new Set(entries.map((entry) => entry.key));
    const added: TargetEntry[] = Object.keys(drafts)
      .filter((key) => !known.has(key))
      .map((key) => ({ key, label: key, value: 0 }));
    return [...entries, ...added];
  }, [entries, drafts]);

  const filled = Object.keys(drafts)
    .map((key) => ({ key, percent: parseDraft(drafts[key]) }))
    .filter((item): item is { key: string; percent: number } => item.percent !== null);
  const sum = filled.reduce((acc, item) => acc + item.percent, 0);
  const isOver = sum > HUNDRED + SUM_TOLERANCE;
  const remaining = HUNDRED - sum;
  const hasInvalid = filled.some((item) => item.percent < 0 || item.percent > HUNDRED);

  const normalized = (values: { key: string; percent: number }[]) =>
    JSON.stringify([...values].sort((a, b) => a.key.localeCompare(b.key)));
  const savedList = Object.keys(saved).map((key) => ({ key, percent: saved[key] }));
  const isDirty = normalized(filled) !== normalized(savedList);

  const setDraft = (key: string, value: string) => {
    setDrafts((current) => ({ ...current, [key]: value }));
  };

  const save = async (event: FormEvent) => {
    event.preventDefault();
    setIsSaving(true);
    try {
      const response = await api.put<Targets>('/targets', { asset_class: assetClass, targets: filled });
      onSaved(response.data);
      toast('Metas salvas');
    } catch (error) {
      toast(errorMessage(error, 'Não foi possível salvar as metas'), 'error');
    } finally {
      setIsSaving(false);
    }
  };

  const addCategory = () => {
    const name = newCategory.trim();
    if (!name) return;
    const existing = rows.find((row) => row.key.toLowerCase() === name.toLowerCase());
    setDraft(existing ? existing.key : name, existing ? drafts[existing.key] ?? '' : '');
    setNewCategory('');
  };

  const pending = (assetClass ?? 'portfolio').replace(/\W/g, '');

  return (
    <form onSubmit={save}>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-line text-xs text-muted">
              <th className="py-2 pr-2 text-left font-medium">{firstColumn}</th>
              <th className="py-2 px-2 text-left font-medium w-1/4 hidden sm:table-cell">Atual × meta</th>
              <th className="py-2 px-2 text-right font-medium">Atual</th>
              <th className="py-2 px-2 text-right font-medium">Meta (%)</th>
              <th className="py-2 px-2 text-right font-medium hidden md:table-cell">Diferença</th>
              <th className="py-2 pl-2 text-right font-medium hidden sm:table-cell">Para a meta</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const target = parseDraft(drafts[row.key]);
              const progress = progressOf(row.value, total, target);
              let action = '-';
              if (progress.onTarget) action = 'Na meta';
              else if (progress.toTarget !== null) {
                action = `${progress.toTarget > 0 ? 'Aportar' : 'Reduzir'} ${formatCurrency(Math.abs(progress.toTarget))}`;
              }
              const inputId = `target-${pending}-${row.key.replace(/\W/g, '_')}`;

              return (
                <tr key={row.key} className="border-b border-line/50 last:border-b-0">
                  <td className="py-2 pr-2">
                    <label htmlFor={inputId} className="inline-flex items-center gap-2">
                      {row.color && <span aria-hidden className="w-2.5 h-2.5 rounded-sm shrink-0" style={{ backgroundColor: row.color }} />}
                      {row.label}
                    </label>
                    <div className="text-xs text-muted tabular-nums">{formatCurrency(row.value)}</div>
                    {action !== '-' && <div className="sm:hidden text-xs text-soft tabular-nums mt-0.5">{action}</div>}
                  </td>
                  <td className="py-2 px-2 hidden sm:table-cell">
                    <TargetBar current={progress.currentPercent} target={target} label={row.label} />
                  </td>
                  <td className="py-2 px-2 text-right tabular-nums">{formatPercent(progress.currentPercent)}</td>
                  <td className="py-2 px-2 text-right">
                    <input
                      id={inputId}
                      type="number"
                      min="0"
                      max="100"
                      step="any"
                      disabled={row.locked}
                      title={row.locked ? 'Classifique estes ativos na tabela de posições para definir metas.' : undefined}
                      placeholder="-"
                      className={`${inputClass} !w-20 text-right ml-auto disabled:opacity-50`}
                      value={drafts[row.key] ?? ''}
                      onChange={(event) => setDraft(row.key, event.target.value)}
                    />
                  </td>
                  <td className="py-2 px-2 text-right tabular-nums text-soft hidden md:table-cell whitespace-nowrap">
                    {progress.difference === null ? '-' : `${formatSignedPercent(progress.difference)}`}
                  </td>
                  <td className="py-2 pl-2 text-right tabular-nums text-soft hidden sm:table-cell">{action}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {assetClass && (
        <div className="flex flex-wrap items-center gap-2 mt-3">
          <input
            aria-label="Nova categoria"
            list={`suggestions-${pending}`}
            maxLength={64}
            placeholder="Adicionar outra categoria"
            className={`${inputClass} sm:max-w-xs`}
            value={newCategory}
            onChange={(event) => setNewCategory(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                event.preventDefault();
                addCategory();
              }
            }}
          />
          <datalist id={`suggestions-${pending}`}>
            {suggestions.map((value) => <option key={value} value={value} />)}
          </datalist>
          <Button onClick={addCategory} disabled={!newCategory.trim()}><AddIcon fontSize="small" /> Adicionar</Button>
        </div>
      )}

      <div className="flex flex-wrap items-center justify-between gap-3 mt-4">
        <p className={`text-sm tabular-nums ${isOver ? 'text-loss' : 'text-soft'}`} role="status">
          Soma das metas: <strong>{formatPercent(sum)}</strong>
          {isOver && ` · passou ${formatPercent(-remaining)}`}
          {!isOver && remaining > SUM_TOLERANCE && filled.length > 0 && ` · faltam ${formatPercent(remaining)}`}
        </p>
        <div className="flex gap-2">
          {isDirty && <Button onClick={() => setDrafts(toDrafts(saved))}>Descartar</Button>}
          <Button type="submit" variant="primary" disabled={!isDirty || isOver || hasInvalid || isSaving}>Salvar metas</Button>
        </div>
      </div>
    </form>
  );
};

export default TargetsTable;
