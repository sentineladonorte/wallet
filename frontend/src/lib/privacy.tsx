'use client'

import React, { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { formatCompact, formatCurrency, formatPercent, formatQuantity, formatSignedCurrency } from './format';

const STORAGE_KEY = 'wallet:hide-values';
const MASK = '••••';
const MONEY_MASK = `R$ ${MASK}`;

interface PrivacyContextValue {
  hidden: boolean;
  toggleHidden: () => void;
}

const PrivacyContext = createContext<PrivacyContextValue | undefined>(undefined);

export const PrivacyProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [hidden, setHidden] = useState(false);

  // Lido depois da montagem para o HTML do servidor e o do navegador coincidirem.
  // Os valores vêm da API, então só chegam à tela depois desta leitura.
  useEffect(() => {
    try {
      setHidden(window.localStorage.getItem(STORAGE_KEY) === 'true');
    } catch {
      // Sem acesso ao armazenamento, a preferência só vale até recarregar a página.
    }
  }, []);

  const toggleHidden = useCallback(() => {
    setHidden((current) => {
      try {
        window.localStorage.setItem(STORAGE_KEY, String(!current));
      } catch {
        // Idem: a preferência continua valendo nesta página.
      }
      return !current;
    });
  }, []);

  const value = useMemo(() => ({ hidden, toggleHidden }), [hidden, toggleHidden]);

  return <PrivacyContext.Provider value={value}>{children}</PrivacyContext.Provider>;
};

/**
 * Formatadores de valores da carteira, que respeitam o botão de ocultar.
 * Percentuais da carteira continuam em `lib/format`: não revelam quanto o usuário tem.
 * O uso do limite do FGC é exceção: é uma fração de um valor público, logo revela o valor aplicado.
 */
export const useFormat = () => {
  const context = useContext(PrivacyContext);
  if (context === undefined) throw new Error('useFormat must be used within a PrivacyProvider');
  const { hidden, toggleHidden } = context;

  return useMemo(() => {
    const masked = (mask: string) => (value: number | null | undefined) =>
      (value === null || value === undefined ? '-' : mask);

    return {
      hidden,
      toggleHidden,
      formatCurrency: hidden ? masked(MONEY_MASK) : formatCurrency,
      formatSignedCurrency: hidden ? masked(MONEY_MASK) : formatSignedCurrency,
      formatQuantity: hidden ? masked(MASK) : formatQuantity,
      formatCompact: hidden ? masked(MASK) : formatCompact,
      formatLimitUsage: hidden ? masked(MASK) : formatPercent,
    };
  }, [hidden, toggleHidden]);
};
