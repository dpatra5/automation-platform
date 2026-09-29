import {
  Activity,
  FlaskConical,
  LayoutDashboard,
  ListChecks,
  Menu,
  Monitor,
  Moon,
  PlayCircle,
  Radar,
  Server,
  Sun,
  X,
} from 'lucide-react';
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router';

import { Badge } from '@/components/ui/Badge';
import { useHealth } from '@/hooks/queries';
import { useTheme, type Theme } from '@/hooks/useTheme';
import { cn } from '@/lib/cn';

const NAV = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/scans', label: 'Auto scan', icon: Radar, end: false },
  { to: '/runs', label: 'Runs', icon: ListChecks, end: false },
  { to: '/runs/new', label: 'New run', icon: PlayCircle, end: true },
  { to: '/demo-server', label: 'Demo server', icon: Server, end: true },
] as const;

function NavItems({ onNavigate }: { onNavigate?: () => void }) {
  const { pathname } = useLocation();
  return (
    <nav aria-label="Main" className="space-y-1">
      {NAV.map(({ to, label, icon: Icon, end }) => (
        <NavLink
          key={to}
          to={to}
          end={end}
          onClick={onNavigate}
          className={({ isActive }) =>
            cn(
              'flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors',
              isActive && !(to === '/runs' && pathname === '/runs/new')
                ? 'bg-brand-600/10 text-brand-700 dark:bg-brand-500/15 dark:text-brand-100'
                : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100',
            )
          }
        >
          <Icon className="size-4" aria-hidden />
          {label}
        </NavLink>
      ))}
    </nav>
  );
}

function ApiStatus() {
  const { data, isError, isPending } = useHealth();
  if (isPending) return <Badge>Connecting…</Badge>;
  if (isError)
    return (
      <Badge tone="danger" dot>
        API offline
      </Badge>
    );
  return (
    <Badge tone="success" dot>
      API v{data.version}
    </Badge>
  );
}

const THEMES: { id: Theme; icon: ReactNode; label: string }[] = [
  { id: 'light', icon: <Sun className="size-3.5" />, label: 'Light' },
  { id: 'system', icon: <Monitor className="size-3.5" />, label: 'System' },
  { id: 'dark', icon: <Moon className="size-3.5" />, label: 'Dark' },
];

function ThemeSwitcher() {
  const { theme, setTheme } = useTheme();
  return (
    <div
      role="radiogroup"
      aria-label="Color theme"
      className="inline-flex rounded-md bg-slate-100 p-0.5 dark:bg-slate-800"
    >
      {THEMES.map((t) => (
        <button
          key={t.id}
          type="button"
          role="radio"
          aria-checked={theme === t.id}
          aria-label={t.label}
          title={t.label}
          onClick={() => setTheme(t.id)}
          className={cn(
            'rounded px-2 py-1 text-slate-500 transition-colors dark:text-slate-400',
            theme === t.id &&
              'bg-white text-slate-900 shadow-xs dark:bg-slate-700 dark:text-slate-100',
          )}
        >
          {t.icon}
        </button>
      ))}
    </div>
  );
}

function Brand() {
  return (
    <div className="flex items-center gap-2.5 px-3">
      <div className="flex size-8 items-center justify-center rounded-lg bg-brand-600 text-white shadow-sm">
        <Activity className="size-4" />
      </div>
      <div className="leading-tight">
        <div className="text-sm font-semibold">lt console</div>
        <div className="text-[11px] text-slate-500 dark:text-slate-400">
          Load & rate-limit testing
        </div>
      </div>
    </div>
  );
}

export function AppLayout() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const location = useLocation();
  const mainRef = useRef<HTMLElement>(null);

  useEffect(() => {
    setMobileOpen(false);
    mainRef.current?.scrollTo({ top: 0 });
  }, [location.pathname]);

  return (
    <div className="flex h-full">
      <a
        href="#main"
        className="sr-only z-50 rounded bg-white px-3 py-2 focus:not-sr-only focus:absolute focus:top-2 focus:left-2"
      >
        Skip to content
      </a>

      <aside className="hidden w-60 shrink-0 flex-col border-r border-slate-200 bg-white py-5 lg:flex dark:border-slate-800 dark:bg-slate-900">
        <Brand />
        <div className="mt-6 flex-1 px-3">
          <NavItems />
        </div>
        <div className="space-y-3 px-6">
          <ApiStatus />
          <div className="flex items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
            <FlaskConical className="size-3.5" /> CO-safe open-model scheduler
          </div>
        </div>
      </aside>

      {mobileOpen && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true">
          <div className="absolute inset-0 bg-slate-900/50" onClick={() => setMobileOpen(false)} />
          <div className="absolute inset-y-0 left-0 flex w-64 animate-fade-in flex-col bg-white py-5 dark:bg-slate-900">
            <div className="flex items-center justify-between pr-3">
              <Brand />
              <button
                type="button"
                onClick={() => setMobileOpen(false)}
                aria-label="Close menu"
                className="rounded p-1 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800"
              >
                <X className="size-5" />
              </button>
            </div>
            <div className="mt-6 px-3">
              <NavItems onNavigate={() => setMobileOpen(false)} />
            </div>
          </div>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center justify-between gap-3 border-b border-slate-200 bg-white/80 px-4 backdrop-blur sm:px-6 dark:border-slate-800 dark:bg-slate-900/80">
          <button
            type="button"
            className="rounded p-1.5 text-slate-500 hover:bg-slate-100 lg:hidden dark:hover:bg-slate-800"
            onClick={() => setMobileOpen(true)}
            aria-label="Open menu"
          >
            <Menu className="size-5" />
          </button>
          <div className="lg:hidden">
            <ApiStatus />
          </div>
          <div className="ml-auto">
            <ThemeSwitcher />
          </div>
        </header>
        <main ref={mainRef} id="main" className="flex-1 overflow-y-auto">
          <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}

interface PageHeaderProps {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  meta?: ReactNode;
}

export function PageHeader({ title, description, actions, meta }: PageHeaderProps) {
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
      <div className="min-w-0">
        <h1 className="truncate text-xl font-semibold tracking-tight">{title}</h1>
        {description && (
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">{description}</p>
        )}
        {meta && <div className="mt-2 flex flex-wrap items-center gap-2">{meta}</div>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}
