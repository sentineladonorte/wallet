'use client'

import React, { useState } from 'react';
import DeleteIcon from '@mui/icons-material/Delete';
import EditIcon from '@mui/icons-material/Edit';
import AssetLink from '@/components/assetLink';
import OrderModal, { OrderFormData } from '@/components/modals/order';
import { ConfirmDialog, EstimatedBadge, IconButton } from '@/components/ui';
import { useToast } from '@/components/ui/toast';
import { classLabel } from '@/lib/assets';
import { formatDate } from '@/lib/format';
import { useFormat } from '@/lib/privacy';
import { errorMessage } from '@/lib/useApi';
import api from '@/services/api';
import { Order } from '@/types';

const OrdersTable: React.FC<{ orders: Order[]; onChanged: () => void }> = ({ orders, onChanged }) => {
  const { formatCurrency, formatQuantity } = useFormat();
  const toast = useToast();
  const [editing, setEditing] = useState<Order | null>(null);
  const [deleting, setDeleting] = useState<Order | null>(null);

  const updateOrder = async (data: OrderFormData) => {
    try {
      await api.patch(`/order/${editing?.id}`, data);
      toast('Boleta atualizada');
      onChanged();
      return true;
    } catch (error) {
      toast(errorMessage(error, 'Não foi possível atualizar a boleta'), 'error');
      return false;
    }
  };

  const deleteOrder = async () => {
    if (!deleting) return;
    try {
      await api.delete(`/order/${deleting.id}`);
      toast('Boleta excluída');
      onChanged();
    } catch (error) {
      toast(errorMessage(error, 'Não foi possível excluir a boleta'), 'error');
    }
    setDeleting(null);
  };

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-line text-xs text-muted">
            <th className="py-2 px-2 text-left font-medium">Data</th>
            <th className="py-2 px-2 text-left font-medium">Ativo</th>
            <th className="py-2 px-2 text-left font-medium hidden md:table-cell">Classe</th>
            <th className="py-2 px-2 text-left font-medium hidden md:table-cell">Corretora</th>
            <th className="py-2 px-2 text-left font-medium">Operação</th>
            <th className="py-2 px-2 text-right font-medium hidden sm:table-cell">Qtd.</th>
            <th className="py-2 px-2 text-right font-medium hidden sm:table-cell">Preço</th>
            <th className="py-2 px-2 text-right font-medium">Total</th>
            <th aria-label="Ações" className="py-2 px-2" />
          </tr>
        </thead>
        <tbody>
          {orders.map((order) => (
            <tr key={order.id} className="border-b border-line/50 hover:bg-raised/50">
              <td className="py-2 px-2 tabular-nums whitespace-nowrap">{formatDate(order.date)}</td>
              <td className="py-2 px-2 max-w-[200px] sm:max-w-[280px]">
                <AssetLink name={order.name} assetClass={order.asset_type} />
                {order.cost_estimated && <EstimatedBadge />}
                {order.description && <div className="text-xs text-muted truncate" title={order.description}>{order.description}</div>}
              </td>
              <td className="py-2 px-2 hidden md:table-cell whitespace-nowrap">{classLabel(order.asset_type)}</td>
              <td className="py-2 px-2 hidden md:table-cell whitespace-nowrap text-soft">{order.broker}</td>
              <td className="py-2 px-2">{order.order_type === 1 ? 'Compra' : 'Venda'}</td>
              <td className="py-2 px-2 text-right tabular-nums hidden sm:table-cell">{formatQuantity(order.volume)}</td>
              <td className="py-2 px-2 text-right tabular-nums hidden sm:table-cell whitespace-nowrap">{formatCurrency(order.price)}</td>
              <td className="py-2 px-2 text-right tabular-nums whitespace-nowrap">{formatCurrency(order.total)}</td>
              <td className="py-2 px-2 text-right whitespace-nowrap">
                <IconButton label={`Editar boleta de ${order.name}`} onClick={() => setEditing(order)}><EditIcon fontSize="small" /></IconButton>
                <IconButton label={`Excluir boleta de ${order.name}`} onClick={() => setDeleting(order)}><DeleteIcon fontSize="small" /></IconButton>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {editing && <OrderModal order={editing} onClose={() => setEditing(null)} onSave={updateOrder} />}
      {deleting && (
        <ConfirmDialog
          title="Excluir boleta"
          message={`Excluir a ${deleting.order_type === 1 ? 'compra' : 'venda'} de ${formatQuantity(deleting.volume)} ${deleting.name} em ${formatDate(deleting.date)}? Essa ação não pode ser desfeita.`}
          confirmLabel="Excluir"
          onConfirm={deleteOrder}
          onClose={() => setDeleting(null)}
        />
      )}
    </div>
  );
};

export default OrdersTable;
