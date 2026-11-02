'use client'

import Link from 'next/link';
import { usePathname } from 'next/navigation'
import DashboardIcon from '@mui/icons-material/Dashboard';
import ReceiptLongIcon from '@mui/icons-material/ReceiptLong';
import ShowChartIcon from '@mui/icons-material/ShowChart';
import PersonIcon from '@mui/icons-material/Person';
import LogoutIcon from '@mui/icons-material/Logout';
import { useAuth } from '@/services/authContext';

const LINKS = [
  { href: '/', label: 'Carteira', icon: DashboardIcon },
  { href: '/orders', label: 'Boletas', icon: ReceiptLongIcon },
  { href: '/tickers', label: 'Ativos', icon: ShowChartIcon },
  { href: '/profile', label: 'Perfil', icon: PersonIcon },
];

const Navbar = () => {
  const pathname = usePathname();
  const { logout } = useAuth();

  if (pathname.startsWith('/auth')) return null;

  const handleLogout = async () => {
    await logout();
    window.location.href = '/auth';
  };

  const isActive = (href: string) => (href === '/' ? pathname === '/' : pathname.startsWith(href));

  return (
    <header className="sticky top-0 z-40 bg-canvas/90 backdrop-blur border-b border-line">
      <nav aria-label="Principal" className="max-w-7xl mx-auto flex items-center justify-between gap-2 px-4 h-14">
        <Link href="/" className="font-semibold text-lg tracking-tight">Wallet</Link>
        <div className="flex items-center gap-1">
          {LINKS.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              aria-label={label}
              aria-current={isActive(href) ? 'page' : undefined}
              className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-sm transition ${
                isActive(href) ? 'bg-raised text-ink' : 'text-muted hover:text-ink'
              }`}
            >
              <Icon fontSize="small" />
              <span className="hidden sm:inline">{label}</span>
            </Link>
          ))}
          <button
            type="button"
            onClick={handleLogout}
            aria-label="Sair"
            title="Sair"
            className="flex items-center px-2.5 py-1.5 rounded-lg text-muted hover:text-ink transition"
          >
            <LogoutIcon fontSize="small" />
          </button>
        </div>
      </nav>
    </header>
  );
};

export default Navbar;
