'use client'

import React, { createContext, ReactNode, useCallback, useContext, useRef, useState } from 'react';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import ErrorIcon from '@mui/icons-material/Error';

type ToastKind = 'success' | 'error';
interface Toast { id: number; kind: ToastKind; message: string }

const ToastContext = createContext<((message: string, kind?: ToastKind) => void) | undefined>(undefined);
const TOAST_DURATION_MS = 5000;

export const ToastProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(0);

  const show = useCallback((message: string, kind: ToastKind = 'success') => {
    nextId.current += 1;
    const id = nextId.current;
    setToasts((current) => [...current, { id, kind, message }]);
    setTimeout(() => setToasts((current) => current.filter((toast) => toast.id !== id)), TOAST_DURATION_MS);
  }, []);

  return (
    <ToastContext.Provider value={show}>
      {children}
      <div aria-live="polite" className="fixed bottom-4 right-4 left-4 sm:left-auto z-[60] flex flex-col gap-2 sm:w-96">
        {toasts.map((toast) => (
          <div key={toast.id} className="flex items-start gap-2 bg-raised border border-line rounded-lg p-3 text-sm shadow-lg">
            {toast.kind === 'success'
              ? <CheckCircleIcon fontSize="small" className="text-gain" />
              : <ErrorIcon fontSize="small" className="text-loss" />}
            <span>{toast.message}</span>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
};

export const useToast = () => {
  const context = useContext(ToastContext);
  if (context === undefined) throw new Error('useToast must be used within a ToastProvider');
  return context;
};
