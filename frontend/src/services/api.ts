import axios from 'axios';

const api = axios.create({
    baseURL: process.env.NEXT_PUBLIC_BACKEND_URL,
    withCredentials: true,
});

api.interceptors.response.use(undefined, async (error) => {
    const isAuthRequest = /\/(login|logout|register)$/.test(error.config?.url ?? '');
    if (error.response?.status === 401 && !isAuthRequest && typeof window !== 'undefined') {
        // Sessão expirada: remove o cookie antes, senão o middleware devolveria para a página atual.
        await api.post('/logout').catch(() => undefined);
        window.location.href = '/auth';
    }
    return Promise.reject(error);
});

export default api;
