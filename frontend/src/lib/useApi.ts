import { useCallback, useEffect, useState } from 'react';
import api from '@/services/api';

export const errorMessage = (error: any, fallback: string) => {
  const data = error?.response?.data;
  if (typeof data?.message === 'string') return data.message;
  if (typeof data === 'string' && data.length < 200) return data;
  return fallback;
};

/** Busca um recurso e controla carregamento e erro. Passe `null` em `path` para não buscar. */
export function useApi<T>(path: string | null, params?: Record<string, string | undefined>) {
  const [data, setData] = useState<T | null>(null);
  const [isLoading, setIsLoading] = useState(path !== null);
  const [error, setError] = useState<string | null>(null);
  const serializedParams = JSON.stringify(params ?? {});

  const load = useCallback(async () => {
    if (path === null) return;
    setIsLoading(true);
    try {
      const response = await api.get<T>(path, { params: JSON.parse(serializedParams) });
      setData(response.data);
      setError(null);
    } catch (requestError) {
      setError(errorMessage(requestError, 'Não foi possível carregar os dados'));
    } finally {
      setIsLoading(false);
    }
  }, [path, serializedParams]);

  useEffect(() => {
    load();
  }, [load]);

  return { data, isLoading, error, reload: load };
}
