import React, { FormEvent, ReactNode } from 'react';
import Link from 'next/link';
import { Button } from '@/components/ui';

const AuthForm: React.FC<{
  title: string;
  submitLabel: string;
  error: string | null;
  isSubmitting: boolean;
  footerHref: string;
  footerLabel: string;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  children: ReactNode;
}> = ({ title, submitLabel, error, isSubmitting, footerHref, footerLabel, onSubmit, children }) => (
  <div className="flex justify-center items-center min-h-[80vh]">
    <form onSubmit={onSubmit} className="bg-surface border border-line rounded-xl p-6 sm:p-8 max-w-sm w-full space-y-4">
      <div className="text-center mb-2">
        <p className="font-semibold text-xl tracking-tight">Wallet</p>
        <h1 className="text-sm text-muted mt-1">{title}</h1>
      </div>
      {children}
      {error && <p role="alert" className="text-sm text-loss">{error}</p>}
      <Button type="submit" variant="primary" className="w-full" disabled={isSubmitting}>{submitLabel}</Button>
      <p className="text-center text-sm"><Link href={footerHref} className="text-accent hover:underline">{footerLabel}</Link></p>
    </form>
  </div>
);

export default AuthForm;
