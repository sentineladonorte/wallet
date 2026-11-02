'use client'

import React, { createContext, ReactNode, useContext } from 'react';
import api from './api';

interface AuthContextProps {
  login: (username: string, password: string) => Promise<boolean>;
  logout: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextProps | undefined>(undefined);

export const AuthProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const login = async (username: string, password: string) => {
    try {
      await api.post('/login', { username, password });
      return true;
    } catch {
      return false;
    }
  };

  const logout = async () => {
    await api.post('/logout');
  };

  return <AuthContext.Provider value={{ login, logout }}>{children}</AuthContext.Provider>;
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
