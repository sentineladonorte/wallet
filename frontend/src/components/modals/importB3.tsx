'use client'

import React, { useState } from 'react';
import { Button, Field, Modal, inputClass } from '@/components/ui';
import { useToast } from '@/components/ui/toast';
import { formatDate } from '@/lib/format';
import { useFormat } from '@/lib/privacy';
import { errorMessage } from '@/lib/useApi';
import api from '@/services/api';

interface PlannedOrder {
  name: string;
  broker: string;
  description: string | null;
  order_type: number;
  date: string;
  price: number;
  volume: number;
}

interface MissingPosition {
  key: string;
  name: string;
  broker: string;
  volume: number;
  price: number | null;
  possible_duplicate: boolean;
}

interface Preview {
  snapshot_date: string;
  total_value: number;
  positions: number;
  new: PlannedOrder[];
  adjustments: PlannedOrder[];
  unchanged: { name: string }[];
  missing: MissingPosition[];
  errors: { sheet: string; row: number; name: string | null; message: string }[];
  sheets: { sheet: string; rows: number; total: number; footer_total: number | null; matches_footer: boolean | null }[];
}

interface MovementPreview {
  file_type: 'movements';
  total_rows: number;
  new_rows: number;
  duplicate_rows: number;
  first_date: string | null;
  last_date: string | null;
  errors: { row: number; message: string }[];
  unknown_types: Record<string, number>;
  snapshot_date: string | null;
  positions_in_snapshot: number;
  positions_matched: number;
  differences: { name: string; ledger: number; snapshot: number; action: 'estimated_buy' | 'closed' }[];
  successions: { old: string; new: string }[];
  orders_replaced: number;
  orders_after: number;
  manual_conflicts: { name: string; count: number }[];
}

const MovementSummary: React.FC<{
  preview: MovementPreview;
  replaceManual: boolean;
  onReplaceManualChange: (value: boolean) => void;
}> = ({ preview, replaceManual, onReplaceManualChange }) => {
  const { formatQuantity } = useFormat();
  const estimated = preview.differences.filter((item) => item.action === 'estimated_buy');
  const closed = preview.differences.filter((item) => item.action === 'closed');
  const unknown = Object.keys(preview.unknown_types);

  return (
    <>
      <dl className="flex flex-wrap gap-x-6 gap-y-2 text-sm mb-4">
        <div><dt className="text-xs text-muted">Período</dt><dd className="font-semibold tabular-nums">{formatDate(preview.first_date)} a {formatDate(preview.last_date)}</dd></div>
        <div><dt className="text-xs text-muted">Linhas novas</dt><dd className="font-semibold tabular-nums">{preview.new_rows}</dd></div>
        <div><dt className="text-xs text-muted">Já importadas</dt><dd className="font-semibold tabular-nums">{preview.duplicate_rows}</dd></div>
        <div><dt className="text-xs text-muted">Boletas depois</dt><dd className="font-semibold tabular-nums">{preview.orders_after}</dd></div>
      </dl>

      {preview.new_rows === 0 && (
        <p className="mb-4 p-3 rounded-lg bg-raised text-soft text-sm">Todas as linhas deste arquivo já foram importadas. Nada será duplicado.</p>
      )}

      {preview.snapshot_date ? (
        <p className="mb-4 text-sm text-soft">
          Conferência com a posição da B3 de {formatDate(preview.snapshot_date)}:{' '}
          <strong className="tabular-nums">{preview.positions_matched} de {preview.positions_in_snapshot}</strong> ativos com a quantidade exata.
        </p>
      ) : (
        <p className="mb-4 p-3 rounded-lg bg-warn/10 text-warn text-sm">
          Importe também o relatório de posição da B3. O extrato não informa vencimentos nem todas as saídas da carteira,
          então, sem o relatório, títulos de renda fixa não aparecem e ativos antigos podem continuar listados.
        </p>
      )}

      {preview.orders_replaced > 0 && (
        <p className="mb-4 text-sm text-soft">
          As {preview.orders_replaced} boletas geradas por importações anteriores serão recalculadas com o histórico real.
        </p>
      )}

      {preview.manual_conflicts.length > 0 && (
        <section className="mb-4 p-3 rounded-lg bg-warn/10 text-sm">
          <h3 className="font-medium text-warn mb-1">Boletas manuais de ativos que estão no extrato</h3>
          <p className="text-soft mb-2">
            {preview.manual_conflicts.map((item) => `${item.name} (${item.count})`).join(', ')}.
            {' '}Se elas registram as mesmas operações, a quantidade ficará dobrada.
          </p>
          <label className="flex items-center gap-2 text-soft">
            <input type="checkbox" checked={replaceManual} onChange={(event) => onReplaceManualChange(event.target.checked)} />
            Apagar essas boletas manuais e usar só o extrato
          </label>
        </section>
      )}

      {estimated.length > 0 && (
        <section className="mb-4 text-sm">
          <h3 className="font-medium mb-1">Sem registro de compra no extrato ({estimated.length})</h3>
          <p className="text-xs text-muted mb-1">A quantidade que falta entra com custo estimado pelo preço atual.</p>
          <ul className="list-disc pl-5 text-soft">
            {estimated.map((item) => <li key={item.name}>{item.name}: {formatQuantity(item.ledger)} no extrato, {formatQuantity(item.snapshot)} na posição</li>)}
          </ul>
        </section>
      )}

      {preview.successions.length > 0 && (
        <p className="mb-4 text-sm text-soft">
          Trocas de ticker identificadas, com o custo levado para o novo:{' '}
          {preview.successions.map((item) => `${item.old} → ${item.new}`).join(', ')}.
        </p>
      )}

      {closed.length > 0 && (
        <details className="mb-4 border border-line rounded-lg">
          <summary className="cursor-pointer px-3 py-2 text-sm font-medium">Encerrados sem baixa no extrato ({closed.length})</summary>
          <p className="px-3 text-xs text-muted">
            O extrato não registra a saída destes ativos, e eles não estão na posição oficial. Saem da carteira sem gerar lucro nem prejuízo.
          </p>
          <p className="px-3 py-2 text-sm text-soft">{closed.map((item) => item.name).join(', ')}</p>
        </details>
      )}

      {unknown.length > 0 && (
        <section className="mb-4 p-3 rounded-lg bg-warn/10 text-sm">
          <h3 className="font-medium text-warn mb-1">Tipos de movimentação não reconhecidos</h3>
          <p className="text-soft">
            {unknown.map((type) => `${type} (${preview.unknown_types[type]})`).join(', ')}.
            {' '}Essas linhas ficam guardadas, mas não alteram a carteira.
          </p>
        </section>
      )}

      {preview.errors.length > 0 && (
        <section className="mb-4 p-3 rounded-lg bg-loss/10 text-sm">
          <h3 className="font-medium text-loss mb-1">Linhas que não serão importadas ({preview.errors.length})</h3>
          <p>{preview.errors.slice(0, 20).map((item) => `linha ${item.row}`).join(', ')}.</p>
        </section>
      )}
    </>
  );
};

const PlannedOrders: React.FC<{ title: string; orders: PlannedOrder[] }> = ({ title, orders }) => {
  const { formatCurrency, formatQuantity } = useFormat();
  if (orders.length === 0) return null;

  return (
    <details className="mb-4 border border-line rounded-lg" open={orders.length <= 10}>
      <summary className="cursor-pointer px-3 py-2 text-sm font-medium">{title} ({orders.length})</summary>
      <div className="overflow-x-auto px-3 pb-2">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs text-muted border-b border-line">
              <th className="py-1.5 pr-2 text-left font-medium">Ativo</th>
              <th className="py-1.5 px-2 text-left font-medium">Operação</th>
              <th className="py-1.5 px-2 text-left font-medium">Data</th>
              <th className="py-1.5 px-2 text-right font-medium">Qtd.</th>
              <th className="py-1.5 pl-2 text-right font-medium whitespace-nowrap">Preço estimado</th>
            </tr>
          </thead>
          <tbody>
            {orders.map((order) => (
              <tr key={`${order.name}|${order.broker}`} className="border-b border-line/50">
                <td className="py-1.5 pr-2">
                  {order.name}
                  <div className="text-xs text-muted">{order.description}</div>
                </td>
                <td className="py-1.5 px-2">{order.order_type === 1 ? 'Compra' : 'Venda'}</td>
                <td className="py-1.5 px-2 tabular-nums">{formatDate(order.date)}</td>
                <td className="py-1.5 px-2 text-right tabular-nums">{formatQuantity(order.volume)}</td>
                <td className="py-1.5 pl-2 text-right tabular-nums">{formatCurrency(order.price)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
};

const ImportB3Modal: React.FC<{ onClose: () => void; onImported: () => void }> = ({ onClose, onImported }) => {
  const { formatCurrency, formatQuantity } = useFormat();
  const toast = useToast();
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [movementPreview, setMovementPreview] = useState<MovementPreview | null>(null);
  const [replaceManual, setReplaceManual] = useState(false);
  const [snapshotDate, setSnapshotDate] = useState('');
  const [closeMissing, setCloseMissing] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const buildForm = (date: string) => {
    const form = new FormData();
    form.append('file', file as File);
    if (date) form.append('snapshot_date', date);
    return form;
  };

  const loadPreview = async (date: string) => {
    if (!file) return;
    setIsLoading(true);
    setError(null);
    try {
      const response = await api.post<Preview | MovementPreview>('/orders/import/preview', buildForm(date));
      if ('total_rows' in response.data) {
        setMovementPreview(response.data);
        return;
      }
      const positionPreview = response.data;
      setPreview(positionPreview);
      setSnapshotDate(positionPreview.snapshot_date);
      setCloseMissing((selected) => selected.filter((key) => positionPreview.missing.some((item) => item.key === key)));
    } catch (requestError) {
      setPreview(null);
      setMovementPreview(null);
      setError(errorMessage(requestError, 'Não foi possível ler o arquivo'));
    } finally {
      setIsLoading(false);
    }
  };

  const confirm = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const form = buildForm(snapshotDate);
      closeMissing.forEach((key) => form.append('close_missing', key));
      if (replaceManual) form.append('replace_manual', 'true');
      const response = await api.post<{ created_orders: number; new_rows?: number }>('/orders/import/confirm', form);
      onImported();
      toast(movementPreview
        ? `Importação concluída: ${response.data.new_rows} linha(s) nova(s). O histórico está sendo recalculado.`
        : `Importação concluída: ${response.data.created_orders} boleta(s) criada(s)`);
      onClose();
    } catch (requestError) {
      setError(errorMessage(requestError, 'Não foi possível concluir a importação'));
      setIsLoading(false);
    }
  };

  const toggleMissing = (key: string) => {
    setCloseMissing((selected) => (selected.includes(key) ? selected.filter((item) => item !== key) : [...selected, key]));
  };

  const hasChanges = preview && preview.new.length + preview.adjustments.length + closeMissing.length > 0;

  return (
    <Modal title="Importar da B3" onClose={onClose} size="lg">
      <Field
        label="Relatório da B3 (.xlsx)"
        htmlFor="b3File"
        hint="Na Área do Investidor: Extratos › Posição ou Movimentação › Baixar em Excel. O tipo é identificado pelo arquivo."
        className="mb-4"
      >
        <input
          type="file"
          id="b3File"
          accept=".xlsx"
          className="block w-full text-sm text-soft file:mr-3 file:px-3 file:py-2 file:rounded-lg file:border file:border-line file:bg-raised file:text-ink file:text-sm"
          onChange={(event) => {
            setFile(event.target.files?.[0] || null);
            setPreview(null);
            setMovementPreview(null);
            setReplaceManual(false);
            setSnapshotDate('');
            setCloseMissing([]);
            setError(null);
          }}
        />
      </Field>

      {error && <p role="alert" className="mb-4 p-3 rounded-lg bg-loss/10 text-loss text-sm">{error}</p>}

      {movementPreview && (
        <MovementSummary preview={movementPreview} replaceManual={replaceManual} onReplaceManualChange={setReplaceManual} />
      )}

      {preview && (
        <>
          <p className="mb-4 p-3 rounded-lg bg-warn/10 text-warn text-sm">
            O relatório não informa data nem preço de compra. Os custos são estimados e ficam marcados nas boletas
            para você corrigir depois. O histórico começa na data da posição.
          </p>

          <div className="flex flex-wrap gap-4 items-end mb-4">
            <Field label="Data da posição" htmlFor="snapshotDate">
              <input
                type="date"
                id="snapshotDate"
                className={inputClass}
                value={snapshotDate}
                onChange={(event) => setSnapshotDate(event.target.value)}
                onBlur={() => { if (snapshotDate !== preview.snapshot_date) loadPreview(snapshotDate); }}
              />
            </Field>
            <dl className="flex flex-wrap gap-x-6 gap-y-1 text-sm">
              <div><dt className="text-xs text-muted">Total no arquivo</dt><dd className="font-semibold tabular-nums">{formatCurrency(preview.total_value)}</dd></div>
              <div><dt className="text-xs text-muted">Novas</dt><dd className="font-semibold tabular-nums">{preview.new.length}</dd></div>
              <div><dt className="text-xs text-muted">Ajustes</dt><dd className="font-semibold tabular-nums">{preview.adjustments.length}</dd></div>
              <div><dt className="text-xs text-muted">Sem alteração</dt><dd className="font-semibold tabular-nums">{preview.unchanged.length}</dd></div>
            </dl>
          </div>

          <details className="mb-4 border border-line rounded-lg" open={preview.sheets.some((sheet) => sheet.matches_footer === false)}>
            <summary className="cursor-pointer px-3 py-2 text-sm font-medium">Conferência por aba ({preview.sheets.length})</summary>
            <div className="overflow-x-auto px-3 pb-2">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-xs text-muted border-b border-line">
                    <th className="py-1.5 pr-2 text-left font-medium">Aba</th>
                    <th className="py-1.5 px-2 text-right font-medium">Posições</th>
                    <th className="py-1.5 px-2 text-right font-medium">Soma lida</th>
                    <th className="py-1.5 px-2 text-right font-medium">Total do arquivo</th>
                    <th className="py-1.5 pl-2 text-right font-medium">Confere</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.sheets.map((sheet) => (
                    <tr key={sheet.sheet} className="border-b border-line/50">
                      <td className="py-1.5 pr-2">{sheet.sheet}</td>
                      <td className="py-1.5 px-2 text-right tabular-nums">{sheet.rows}</td>
                      <td className="py-1.5 px-2 text-right tabular-nums">{formatCurrency(sheet.total)}</td>
                      <td className="py-1.5 px-2 text-right tabular-nums">{formatCurrency(sheet.footer_total)}</td>
                      <td className={`py-1.5 pl-2 text-right ${sheet.matches_footer === false ? 'text-loss' : 'text-soft'}`}>
                        {sheet.matches_footer === false ? 'Não' : 'Sim'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>

          {preview.errors.length > 0 && (
            <section className="mb-4 p-3 rounded-lg bg-loss/10">
              <h3 className="text-sm font-medium text-loss mb-1">Linhas que não serão importadas ({preview.errors.length})</h3>
              <ul className="text-sm list-disc pl-5">
                {preview.errors.map((rowError) => (
                  <li key={`${rowError.sheet}-${rowError.row}-${rowError.name}`}>
                    {rowError.sheet}, linha {rowError.row}{rowError.name ? ` (${rowError.name})` : ''}: {rowError.message}
                  </li>
                ))}
              </ul>
            </section>
          )}

          {preview.missing.length > 0 && (
            <section className="mb-4 border border-line rounded-lg p-3">
              <h3 className="text-sm font-medium mb-1">Na carteira, mas fora do arquivo ({preview.missing.length})</h3>
              <p className="text-xs text-muted mb-2">
                Nada é zerado sem sua escolha. Marque o que deve receber uma boleta de venda pelo último preço conhecido.
              </p>
              <ul className="text-sm space-y-1">
                {preview.missing.map((item) => (
                  <li key={item.key}>
                    <label className="flex items-start gap-2">
                      <input type="checkbox" className="mt-1" checked={closeMissing.includes(item.key)} onChange={() => toggleMissing(item.key)} />
                      <span>
                        {item.name} ({item.broker}): {formatQuantity(item.volume)} a {formatCurrency(item.price)}
                        {item.possible_duplicate && (
                          <span className="block text-xs text-warn">
                            Renda fixa: se este título estiver no arquivo com outro código, fica duplicado até ser zerado aqui.
                          </span>
                        )}
                      </span>
                    </label>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <PlannedOrders title="Novas posições" orders={preview.new} />
          <PlannedOrders title="Ajustes" orders={preview.adjustments} />
        </>
      )}

      <div className="flex justify-end gap-2 mt-4">
        <Button onClick={onClose}>Fechar</Button>
        {movementPreview && (
          <Button variant="primary" onClick={confirm} disabled={isLoading}>
            {movementPreview.new_rows > 0 ? 'Confirmar importação' : 'Recalcular com o que já existe'}
          </Button>
        )}
        {preview && (
          <Button variant="primary" onClick={confirm} disabled={isLoading || preview.positions === 0}>
            {hasChanges ? 'Confirmar importação' : 'Atualizar valores'}
          </Button>
        )}
        {!preview && !movementPreview && (
          <Button variant="primary" onClick={() => loadPreview('')} disabled={isLoading || !file}>
            {isLoading ? 'Lendo arquivo...' : 'Ver prévia'}
          </Button>
        )}
      </div>
    </Modal>
  );
};

export default ImportB3Modal;
