'use client'

import React, { ReactNode, useEffect } from 'react';
import CloseIcon from '@mui/icons-material/Close';

export const Card: React.FC<{ children: ReactNode; className?: string }> = ({ children, className = '' }) => (
  <section className={`min-w-0 bg-surface border border-line rounded-xl p-4 sm:p-5 ${className}`}>{children}</section>
);

export const CardTitle: React.FC<{ children: ReactNode; action?: ReactNode }> = ({ children, action }) => (
  <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
    <h2 className="text-base font-semibold">{children}</h2>
    {action}
  </div>
);

export const PageHeader: React.FC<{ title: string; subtitle?: ReactNode; action?: ReactNode }> = ({ title, subtitle, action }) => (
  <div className="flex flex-wrap items-end justify-between gap-3 mb-6">
    <div className="min-w-0">
      <h1 className="text-2xl font-semibold break-words">{title}</h1>
      {subtitle && <p className="text-sm text-muted mt-1">{subtitle}</p>}
    </div>
    {action && <div className="flex flex-wrap gap-2">{action}</div>}
  </div>
);

type ButtonVariant = 'primary' | 'secondary' | 'danger';

const BUTTON_VARIANTS: Record<ButtonVariant, string> = {
  primary: 'bg-accent text-black font-medium hover:brightness-110',
  secondary: 'bg-raised border border-line text-ink hover:border-muted',
  danger: 'bg-loss text-black font-medium hover:brightness-110',
};

export const Button: React.FC<React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant }> = ({
  variant = 'secondary', className = '', type = 'button', ...props
}) => (
  <button
    type={type}
    className={`inline-flex items-center justify-center gap-1.5 px-3.5 py-2 rounded-lg text-sm transition disabled:opacity-50 disabled:cursor-not-allowed ${BUTTON_VARIANTS[variant]} ${className}`}
    {...props}
  />
);

export const IconButton: React.FC<React.ButtonHTMLAttributes<HTMLButtonElement> & { label: string }> = ({ label, className = '', ...props }) => (
  <button
    type="button"
    aria-label={label}
    title={label}
    className={`p-1.5 rounded-md text-muted hover:text-ink hover:bg-raised transition ${className}`}
    {...props}
  />
);

export const inputClass =
  'w-full px-3 py-2 rounded-lg bg-canvas border border-line text-ink text-sm placeholder:text-muted focus:outline-none focus:border-accent [color-scheme:dark]';

export const Field: React.FC<{ label: string; htmlFor: string; children: ReactNode; hint?: string; className?: string }> = ({
  label, htmlFor, children, hint, className = '',
}) => (
  <div className={className}>
    <label htmlFor={htmlFor} className="block text-xs font-medium text-soft mb-1.5">{label}</label>
    {children}
    {hint && <p className="text-xs text-muted mt-1">{hint}</p>}
  </div>
);

export const Modal: React.FC<{ title: string; onClose: () => void; children: ReactNode; size?: 'md' | 'lg' }> = ({
  title, onClose, children, size = 'md',
}) => {
  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', closeOnEscape);
    return () => document.removeEventListener('keydown', closeOnEscape);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
      onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={`w-full ${size === 'lg' ? 'max-w-4xl' : 'max-w-xl'} max-h-[90vh] overflow-y-auto bg-surface border border-line rounded-xl p-5`}
      >
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold">{title}</h2>
          <IconButton label="Fechar" onClick={onClose}><CloseIcon fontSize="small" /></IconButton>
        </div>
        {children}
      </div>
    </div>
  );
};

export const ConfirmDialog: React.FC<{
  title: string; message: ReactNode; confirmLabel: string; onConfirm: () => void; onClose: () => void;
}> = ({ title, message, confirmLabel, onConfirm, onClose }) => (
  <Modal title={title} onClose={onClose}>
    <div className="text-sm text-soft mb-5">{message}</div>
    <div className="flex justify-end gap-2">
      <Button onClick={onClose}>Cancelar</Button>
      <Button variant="danger" onClick={onConfirm}>{confirmLabel}</Button>
    </div>
  </Modal>
);

export const EmptyState: React.FC<{ title: string; description?: ReactNode; action?: ReactNode }> = ({ title, description, action }) => (
  <div className="flex flex-col items-center text-center py-12 px-4">
    <p className="font-medium">{title}</p>
    {description && <p className="text-sm text-muted mt-1 max-w-md">{description}</p>}
    {action && <div className="mt-4">{action}</div>}
  </div>
);

export const LoadingState: React.FC<{ label?: string }> = ({ label = 'Carregando...' }) => (
  <p role="status" className="text-sm text-muted py-12 text-center">{label}</p>
);

export const ErrorState: React.FC<{ message: string; onRetry?: () => void }> = ({ message, onRetry }) => (
  <div role="alert" className="flex flex-col items-center text-center py-12 gap-3">
    <p className="text-sm text-loss">{message}</p>
    {onRetry && <Button onClick={onRetry}>Tentar novamente</Button>}
  </div>
);

export const EstimatedBadge: React.FC = () => (
  <span
    title="Custo estimado na importação da B3. Edite a boleta para informar o valor real."
    className="inline-block ml-1.5 px-1.5 py-0.5 rounded bg-warn/15 text-warn text-[11px] leading-none align-middle"
  >
    estimado
  </span>
);

export const ProfitText: React.FC<{ value: number | null; children: ReactNode; className?: string }> = ({ value, children, className = '' }) => {
  let tone = 'text-soft';
  if (value !== null && value > 0) tone = 'text-gain';
  if (value !== null && value < 0) tone = 'text-loss';
  return <span className={`${tone} ${className}`}>{children}</span>;
};
