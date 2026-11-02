'use client'

import React, { useCallback, useEffect, useRef, useState } from 'react';
import SyncIcon from '@mui/icons-material/Sync';
import { Button } from '@/components/ui';
import { useToast } from '@/components/ui/toast';
import { formatDate } from '@/lib/format';
import { errorMessage } from '@/lib/useApi';
import api from '@/services/api';

interface MarketDataStatus {
  running: boolean;
  last_session: string | null;
  status: 'success' | 'error' | null;
  message: string;
  prices_saved: number;
  categories_filled: number;
}

const POLL_INTERVAL_MS = 2000;

const summarize = ({ prices_saved: prices, categories_filled: categories }: MarketDataStatus) => {
  const parts: string[] = [];
  if (prices > 0) parts.push(`${prices.toLocaleString('pt-BR')} cotações`);
  if (categories > 0) parts.push(`${categories} categoria(s) preenchida(s)`);
  return parts.length ? `Atualizado: ${parts.join(', ')}` : 'Tudo já estava atualizado';
};

/** Mostra a data do último pregão e permite atualizar sem esperar o agendador. */
const MarketDataStatusBar: React.FC<{ onUpdated: () => void }> = ({ onUpdated }) => {
  const toast = useToast();
  const [status, setStatus] = useState<MarketDataStatus | null>(null);
  const [isStarting, setIsStarting] = useState(false);
  const notifyWhenDone = useRef(false);
  const isRunning = isStarting || Boolean(status?.running);

  const load = useCallback(async () => {
    try {
      const response = await api.get<MarketDataStatus>('/market-data');
      setStatus(response.data);
    } catch {
      // A data é informativa: se falhar, o restante da carteira continua utilizável.
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!status?.running) return undefined;
    const timer = setInterval(load, POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [status?.running, load]);

  useEffect(() => {
    if (!status || status.running || !notifyWhenDone.current) return;
    notifyWhenDone.current = false;
    if (status.status === 'error') toast(status.message || 'Não foi possível atualizar', 'error');
    else toast(summarize(status));
    onUpdated();
  }, [status, toast, onUpdated]);

  const update = async () => {
    setIsStarting(true);
    try {
      const response = await api.post<MarketDataStatus>('/market-data');
      notifyWhenDone.current = true;
      setStatus(response.data);
    } catch (error) {
      toast(errorMessage(error, 'Não foi possível iniciar a atualização'), 'error');
    } finally {
      setIsStarting(false);
    }
  };

  return (
    <>
      <span className="self-center text-xs text-muted tabular-nums" role="status">
        {status?.last_session ? `Cotações do pregão de ${formatDate(status.last_session)}` : 'Cotações da última importação'}
      </span>
      <Button onClick={update} disabled={isRunning}>
        <SyncIcon fontSize="small" className={isRunning ? 'animate-spin' : undefined} />
        {isRunning ? 'Atualizando...' : 'Atualizar cotações'}
      </Button>
    </>
  );
};

export default MarketDataStatusBar;
