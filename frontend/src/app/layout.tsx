import './globals.css'
import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import Navbar from "../components/navbar";
import { ToastProvider } from '@/components/ui/toast';
import { PrivacyProvider } from '@/lib/privacy';
import { AuthProvider } from '@/services/authContext';

const inter = Inter({ subsets: ['latin'] })

export const metadata: Metadata = {
  title: 'Wallet',
  description: 'Sua carteira de investimentos',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="pt-BR">
      <body className={inter.className}>
        <AuthProvider>
          <PrivacyProvider>
            <ToastProvider>
              <Navbar />
              <main className="max-w-7xl mx-auto px-4 py-6">{children}</main>
            </ToastProvider>
          </PrivacyProvider>
        </AuthProvider>
      </body>
    </html>
  )
}
