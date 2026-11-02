'use client'

import { FormEvent, useState } from 'react'
import AuthForm from '@/components/authForm';
import { Field, inputClass } from '@/components/ui';
import { useAuth } from '@/services/authContext';

const LoginPage = () => {
  const { login } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleLogin = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    setIsSubmitting(true);
    setError(null);

    const success = await login(formData.get('username')?.toString() ?? '', formData.get('password')?.toString() ?? '');

    if (success) {
      window.location.href = '/';
    } else {
      setError('Usuário ou senha inválidos.');
      setIsSubmitting(false);
    }
  };

  return (
    <AuthForm title="Entre na sua conta" submitLabel="Entrar" error={error} isSubmitting={isSubmitting} footerHref="/auth/register" footerLabel="Criar uma conta" onSubmit={handleLogin}>
      <Field label="Usuário" htmlFor="username">
        <input type="text" id="username" name="username" autoComplete="username" required className={inputClass} />
      </Field>
      <Field label="Senha" htmlFor="password">
        <input type="password" id="password" name="password" autoComplete="current-password" required className={inputClass} />
      </Field>
    </AuthForm>
  );
}

export default LoginPage;
