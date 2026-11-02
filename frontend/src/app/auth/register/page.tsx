'use client'

import { FormEvent, useState } from 'react'
import AuthForm from '@/components/authForm';
import { Field, inputClass } from '@/components/ui';
import { errorMessage } from '@/lib/useApi';
import api from '@/services/api';

const Register: React.FC = () => {
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleRegister = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    setIsSubmitting(true);
    setError(null);

    try {
      await api.post('/register', {
        username: formData.get('username')?.toString() ?? '',
        email: formData.get('email')?.toString() ?? '',
        password: formData.get('password')?.toString() ?? '',
      });
      window.location.href = '/';
    } catch (requestError) {
      setError(errorMessage(requestError, 'Não foi possível criar a conta.'));
      setIsSubmitting(false);
    }
  };

  return (
    <AuthForm title="Crie sua conta" submitLabel="Cadastrar" error={error} isSubmitting={isSubmitting} footerHref="/auth" footerLabel="Já tenho conta" onSubmit={handleRegister}>
      <Field label="Usuário" htmlFor="username">
        <input type="text" id="username" name="username" autoComplete="username" required className={inputClass} />
      </Field>
      <Field label="E-mail" htmlFor="email">
        <input type="email" id="email" name="email" autoComplete="email" required className={inputClass} />
      </Field>
      <Field label="Senha" htmlFor="password">
        <input type="password" id="password" name="password" autoComplete="new-password" required className={inputClass} />
      </Field>
    </AuthForm>
  );
}

export default Register;
