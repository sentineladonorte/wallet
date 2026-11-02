'use client'

import React, { FormEvent, useState } from 'react';
import { Button, Field, Modal, inputClass } from '@/components/ui';
import { CLASS_LABELS } from '@/lib/assets';
import { Order } from '@/types';

export interface OrderFormData {
  name: string;
  broker: string;
  assetType: string;
  orderType: number;
  date: string;
  price: number | null;
  volume: number | null;
  description: string;
  interestRate: number | null;
  maturity: string | null;
  index: string;
  fixedIncomeType: string;
  issuer: string;
}

const BROKERS = ['Nu Invest', 'Rico', 'XP'];
const ORDER_CLASSES = ['AC', 'FII', 'ETF', 'BDR', 'RF'];

const initialForm = (order?: Order): OrderFormData => ({
  name: order?.name ?? '',
  broker: order?.broker ?? 'Nu Invest',
  assetType: order?.asset_type ?? 'AC',
  orderType: order?.order_type ?? 1,
  date: order?.date ?? '',
  price: order?.price ?? null,
  volume: order?.volume ?? null,
  description: order?.description ?? '',
  // Boleta importada não tem taxa: manter nulo evita projetar o título a 0%.
  interestRate: order ? order.interest_rate : 0,
  maturity: order?.maturity_date ?? null,
  index: order?.index ?? 'P',
  fixedIncomeType: order?.fixed_income_type ?? 'CDB',
  issuer: order?.issuer ?? '',
});

const toNumber = (value: string) => (value === '' ? null : Number(value));

const OrderModal: React.FC<{
  order?: Order;
  onClose: () => void;
  onSave: (data: OrderFormData) => Promise<boolean>;
}> = ({ order, onClose, onSave }) => {
  const [form, setForm] = useState<OrderFormData>(initialForm(order));
  const [isSaving, setIsSaving] = useState(false);
  const isFixedIncome = form.assetType === 'RF';

  const update = <K extends keyof OrderFormData>(field: K, value: OrderFormData[K]) => {
    setForm((current) => ({ ...current, [field]: value }));
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setIsSaving(true);
    const saved = await onSave(form);
    setIsSaving(false);
    if (saved) onClose();
  };

  return (
    <Modal title={order ? `Editar boleta de ${order.name}` : 'Nova boleta'} onClose={onClose}>
      <form onSubmit={submit} className="grid grid-cols-2 gap-4">
        <Field label="Classe" htmlFor="assetType">
          <select id="assetType" required className={inputClass} value={form.assetType} onChange={(event) => update('assetType', event.target.value)}>
            {ORDER_CLASSES.map((value) => <option key={value} value={value}>{CLASS_LABELS[value]}</option>)}
            {order && !ORDER_CLASSES.includes(order.asset_type) && <option value={order.asset_type}>{order.asset_type}</option>}
          </select>
        </Field>
        <Field label="Corretora" htmlFor="broker">
          <input id="broker" list="brokers" required maxLength={32} className={inputClass} value={form.broker} onChange={(event) => update('broker', event.target.value)} />
          <datalist id="brokers">{BROKERS.map((value) => <option key={value} value={value} />)}</datalist>
        </Field>
        <Field label={isFixedIncome ? 'Nome do título' : 'Ticker'} htmlFor="name">
          <input id="name" required maxLength={isFixedIncome ? 50 : 8} className={inputClass} value={form.name} onChange={(event) => update('name', event.target.value.toUpperCase())} />
        </Field>
        <fieldset>
          <legend className="block text-xs font-medium text-soft mb-1.5">Operação</legend>
          <div className="flex gap-4 py-2 text-sm">
            <label className="flex items-center gap-1.5">
              <input type="radio" name="orderType" checked={form.orderType === 1} onChange={() => update('orderType', 1)} /> Compra
            </label>
            <label className="flex items-center gap-1.5">
              <input type="radio" name="orderType" checked={form.orderType === -1} onChange={() => update('orderType', -1)} /> Venda
            </label>
          </div>
        </fieldset>
        <Field label="Data" htmlFor="date" className="col-span-2 sm:col-span-1">
          <input id="date" type="date" required className={inputClass} value={form.date} onChange={(event) => update('date', event.target.value)} />
        </Field>
        <div className="col-span-2 sm:col-span-1 grid grid-cols-2 gap-4">
          <Field label="Preço (R$)" htmlFor="price">
            <input id="price" type="number" step="any" min="0" required className={inputClass} value={form.price ?? ''} onChange={(event) => update('price', toNumber(event.target.value))} />
          </Field>
          <Field label="Quantidade" htmlFor="volume">
            <input id="volume" type="number" step="any" min="0" required className={inputClass} value={form.volume ?? ''} onChange={(event) => update('volume', toNumber(event.target.value))} />
          </Field>
        </div>

        {isFixedIncome && (
          <>
            <Field label="Tipo" htmlFor="fixedIncomeType">
              <select id="fixedIncomeType" required className={inputClass} value={form.fixedIncomeType} onChange={(event) => update('fixedIncomeType', event.target.value)}>
                <option value="CDB">CDB</option>
                <option value="LCA">LCA</option>
                <option value="LCI">LCI</option>
                <option value="TD">Tesouro Direto</option>
              </select>
            </Field>
            <Field label="Emissor" htmlFor="issuer">
              <input id="issuer" maxLength={64} className={inputClass} value={form.issuer} onChange={(event) => update('issuer', event.target.value)} />
            </Field>
            <Field label="Vencimento" htmlFor="maturity">
              <input id="maturity" type="date" required className={inputClass} value={form.maturity ?? ''} onChange={(event) => update('maturity', event.target.value)} />
            </Field>
            <div className="grid grid-cols-2 gap-4">
              <Field label="Indexador" htmlFor="index">
                <select id="index" required className={inputClass} value={form.index} onChange={(event) => update('index', event.target.value)}>
                  <option value="P">Prefixado</option>
                  <option value="S">Selic</option>
                  <option value="I">IPCA</option>
                </select>
              </Field>
              <Field label="Taxa (%)" htmlFor="interestRate">
                <input id="interestRate" type="number" step="any" required={!order} className={inputClass} value={form.interestRate ?? ''} onChange={(event) => update('interestRate', toNumber(event.target.value))} />
              </Field>
            </div>
          </>
        )}

        <Field label="Descrição" htmlFor="description" className="col-span-2">
          <input id="description" className={inputClass} value={form.description} onChange={(event) => update('description', event.target.value)} />
        </Field>

        <div className="col-span-2 flex justify-end gap-2">
          <Button onClick={onClose}>Cancelar</Button>
          <Button type="submit" variant="primary" disabled={isSaving}>Salvar</Button>
        </div>
      </form>
    </Modal>
  );
};

export default OrderModal;
