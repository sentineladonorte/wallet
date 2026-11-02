'use client'

import React, { useEffect, useMemo, useState } from 'react';
import AddIcon from '@mui/icons-material/Add';
import UploadFileIcon from '@mui/icons-material/UploadFile';
import ImportB3Modal from '@/components/modals/importB3';
import OrderModal, { OrderFormData } from '@/components/modals/order';
import OrdersTable from '@/components/ordersTable';
import { Button, Card, EmptyState, ErrorState, LoadingState, PageHeader, inputClass } from '@/components/ui';
import { useToast } from '@/components/ui/toast';
import { CLASS_LABELS } from '@/lib/assets';
import { errorMessage, useApi } from '@/lib/useApi';
import api from '@/services/api';
import { Order } from '@/types';

const OrdersPage: React.FC = () => {
  const toast = useToast();
  const { data: orders, isLoading, error, reload } = useApi<Order[]>('/orders/');
  const [isCreating, setIsCreating] = useState(false);
  const [isImporting, setIsImporting] = useState(false);
  const [search, setSearch] = useState('');
  const [assetClass, setAssetClass] = useState('');
  const [onlyEstimated, setOnlyEstimated] = useState(false);

  useEffect(() => {
    if (new URLSearchParams(window.location.search).has('import')) setIsImporting(true);
  }, []);

  const visible = useMemo(() => {
    const query = search.trim().toLowerCase();
    return (orders ?? []).filter((order) =>
      `${order.name} ${order.description ?? ''} ${order.broker}`.toLowerCase().includes(query)
      && (!assetClass || order.asset_type === assetClass)
      && (!onlyEstimated || order.cost_estimated)
    );
  }, [orders, search, assetClass, onlyEstimated]);

  const estimatedCount = (orders ?? []).filter((order) => order.cost_estimated).length;

  const createOrder = async (data: OrderFormData) => {
    try {
      await api.post('/order', data);
      toast('Boleta criada');
      reload();
      return true;
    } catch (requestError) {
      toast(errorMessage(requestError, 'Não foi possível criar a boleta'), 'error');
      return false;
    }
  };

  return (
    <>
      <PageHeader
        title="Boletas"
        subtitle={orders ? `${orders.length} boleta(s)${estimatedCount ? `, ${estimatedCount} com custo estimado` : ''}` : undefined}
        action={(
          <>
            <Button onClick={() => setIsImporting(true)}><UploadFileIcon fontSize="small" /> Importar da B3</Button>
            <Button variant="primary" onClick={() => setIsCreating(true)}><AddIcon fontSize="small" /> Nova boleta</Button>
          </>
        )}
      />

      <Card>
        {isLoading && !orders && <LoadingState />}
        {error && !orders && <ErrorState message={error} onRetry={reload} />}
        {orders && orders.length === 0 && (
          <EmptyState
            title="Nenhuma boleta ainda"
            description="Importe o relatório de posição da B3 ou registre sua primeira boleta."
            action={<Button variant="primary" onClick={() => setIsImporting(true)}><UploadFileIcon fontSize="small" /> Importar da B3</Button>}
          />
        )}
        {orders && orders.length > 0 && (
          <>
            <div className="flex flex-wrap items-center gap-3 mb-3">
              <input type="search" aria-label="Buscar boleta" placeholder="Buscar por ativo, descrição ou corretora" className={`${inputClass} sm:max-w-sm`} value={search} onChange={(event) => setSearch(event.target.value)} />
              <select aria-label="Filtrar por classe" className={`${inputClass} !w-auto`} value={assetClass} onChange={(event) => setAssetClass(event.target.value)}>
                <option value="">Todas as classes</option>
                {Object.keys(CLASS_LABELS).map((key) => <option key={key} value={key}>{CLASS_LABELS[key]}</option>)}
              </select>
              <label className="flex items-center gap-1.5 text-sm text-soft">
                <input type="checkbox" checked={onlyEstimated} onChange={(event) => setOnlyEstimated(event.target.checked)} />
                Só custo estimado
              </label>
            </div>
            <OrdersTable orders={visible} onChanged={reload} />
            {visible.length === 0 && <p className="text-sm text-muted text-center py-8">Nenhuma boleta encontrada.</p>}
          </>
        )}
      </Card>

      {isCreating && <OrderModal onClose={() => setIsCreating(false)} onSave={createOrder} />}
      {isImporting && <ImportB3Modal onClose={() => setIsImporting(false)} onImported={reload} />}
    </>
  );
};

export default OrdersPage;
