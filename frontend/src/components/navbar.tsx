'use client'

import Link from 'next/link';
import { usePathname } from 'next/navigation'
import AccountBalanceIcon from '@mui/icons-material/AccountBalance';
import DashboardIcon from '@mui/icons-material/Dashboard';
import EventIcon from '@mui/icons-material/Event';
import PaidIcon from '@mui/icons-material/Paid';
import QueryStatsIcon from '@mui/icons-material/QueryStats';
import VisibilityIcon from '@mui/icons-material/Visibility';
import VisibilityOffIcon from '@mui/icons-material/VisibilityOff';
import ReceiptLongIcon from '@mui/icons-material/ReceiptLong';
import ShowChartIcon from '@mui/icons-material/ShowChart';
import TrackChangesIcon from '@mui/icons-material/TrackChanges';
import PersonIcon from '@mui/icons-material/Person';
import LogoutIcon from '@mui/icons-material/Logout';
import { useFormat } from '@/lib/privacy';
import { useAuth } from '@/services/authContext';

const LINKS = [
  { href: '/', label: 'Carteira', icon: DashboardIcon },
  { href: '/performance', label: 'Rentabilidade', icon: QueryStatsIcon },
  { href: '/targets', label: 'Metas', icon: TrackChangesIcon },
  { href: '/income', label: 'Proventos', icon: PaidIcon },
  { href: '/maturities', label: 'Vencimentos', icon: EventIcon },
  { href: '/orders', label: 'Boletas', icon: ReceiptLongIcon },
  { href: '/tickers', label: 'Ativos', icon: ShowChartIcon },
  { href: '/issuers', label: 'Emissores', icon: AccountBalanceIcon },
  { href: '/profile', label: 'Perfil', icon: PersonIcon },
];

const Navbar = () => {
  const pathname = usePathname();
  const { logout } = useAuth();
  const { hidden, toggleHidden } = useFormat();

  if (pathname.startsWith('/auth')) return null;

  const handleLogout = async () => {
    await logout();
    window.location.href = '/auth';
  };

  const isActive = (href: string) => (href === '/' ? pathname === '/' : pathname.startsWith(href));

  return (
    <header className="sticky top-0 z-40 bg-canvas/90 backdrop-blur border-b border-line">
      <nav aria-label="Principal" className="max-w-7xl mx-auto flex items-center justify-between gap-2 px-4 h-14">
        <Link href="/" className="hidden sm:inline font-semibold text-lg tracking-tight">Wallet</Link>
        <div className="flex items-center ml-auto min-w-0 overflow-x-auto xl:gap-0.5">
          {LINKS.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              aria-label={label}
              title={label}
              aria-current={isActive(href) ? 'page' : undefined}
              className={`flex items-center gap-1.5 px-1.5 sm:px-2 py-1.5 rounded-lg text-sm transition shrink-0 ${
                isActive(href) ? 'bg-raised text-ink' : 'text-muted hover:text-ink'
              }`}
            >
              <Icon fontSize="small" />
              <span className="hidden xl:inline">{label}</span>
            </Link>
          ))}
          <button
            type="button"
            onClick={toggleHidden}
            aria-pressed={hidden}
            aria-label={hidden ? 'Mostrar valores' : 'Ocultar valores'}
            title={hidden ? 'Mostrar valores' : 'Ocultar valores'}
            className="shrink-0 flex items-center px-1.5 sm:px-2 lg:px-2.5 py-1.5 rounded-lg text-muted hover:text-ink transition"
          >
            {hidden ? <VisibilityOffIcon fontSize="small" /> : <VisibilityIcon fontSize="small" />}
          </button>
          <button
            type="button"
            onClick={handleLogout}
            aria-label="Sair"
            title="Sair"
            className="shrink-0 flex items-center px-1.5 sm:px-2 lg:px-2.5 py-1.5 rounded-lg text-muted hover:text-ink transition"
          >
            <LogoutIcon fontSize="small" />
          </button>
        </div>
      </nav>
    </header>
  );
};

export default Navbar;
