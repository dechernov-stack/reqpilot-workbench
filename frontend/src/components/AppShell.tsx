import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Activity,
  Boxes,
  Braces,
  ChartNoAxesColumnIncreasing,
  CircleGauge,
  FileOutput,
  GitBranch,
  Network,
  Plus,
  RefreshCw,
  Search,
  Settings2,
} from 'lucide-react';
import { useState } from 'react';
import type { FormEvent } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { api } from '../lib/api';
import { cn } from '../lib/utils';
import { StatusBadge } from './StatusBadge';

const navigation = [
  { to: '/', label: 'Обзор', icon: CircleGauge, end: true },
  { to: '/requirements', label: 'Требования', icon: Braces },
  { to: '/architecture', label: 'Архитектура', icon: Boxes },
  { to: '/traceability', label: 'Трассировка', icon: Network },
  { to: '/matrices', label: 'Матрицы', icon: ChartNoAxesColumnIncreasing },
  { to: '/impact', label: 'Impact', icon: GitBranch },
  { to: '/exports', label: 'Экспорт', icon: FileOutput },
  { to: '/diagnostics', label: 'Диагностика', icon: Activity },
] as const;

export function AppShell() {
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState('');
  const health = useQuery({ queryKey: ['health'], queryFn: api.health, retry: 1 });
  const project = useQuery({ queryKey: ['project'], queryFn: api.project, retry: 1 });
  const capella = useQuery({ queryKey: ['capella-status'], queryFn: api.capellaStatus, retry: 1 });
  const dashboard = useQuery({ queryKey: ['dashboard'], queryFn: api.dashboard, retry: 1 });
  const reload = useMutation({
    mutationFn: api.reload,
    onSuccess: async () => {
      await queryClient.invalidateQueries();
    },
  });

  const handleSearch = (event: FormEvent) => {
    event.preventDefault();
    const value = search.trim();
    if (value) void navigate(`/requirements?text=${encodeURIComponent(value)}`);
  };

  const createRequirement = () => {
    void navigate('/requirements?create=1');
  };

  const capellaMode = capella.data?.mode ?? project.data?.capellaMode ?? 'disabled';

  return (
    <div className="min-h-screen min-w-[1180px] bg-canvas text-ink">
      <a className="skip-link" href="#main-content">
        Перейти к содержимому
      </a>
      <aside className="fixed inset-y-0 left-0 z-30 flex w-60 flex-col bg-navy text-slate-100">
        <div className="flex h-16 items-center gap-3 border-b border-white/10 px-5">
          <div className="grid h-9 w-9 place-items-center rounded-md border border-cyan-300/35 bg-cyan-950 text-sm font-bold text-cyan-100">
            RP
          </div>
          <div className="min-w-0">
            <p className="font-semibold tracking-tight">ReqPilot</p>
            <p className="truncate text-[11px] text-slate-400">Engineering Workbench</p>
          </div>
        </div>
        <nav className="flex-1 px-3 py-5" aria-label="Основная навигация">
          <p className="px-3 pb-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">
            Рабочее пространство
          </p>
          <ul className="space-y-1">
            {navigation.map(({ to, label, icon: Icon }) => (
              <li key={to}>
                <NavLink
                  to={to}
                  end={to === '/'}
                  className={({ isActive }) =>
                    cn(
                      'flex items-center gap-3 rounded-md border border-transparent px-3 py-2 text-sm font-medium text-slate-300 outline-none transition-colors focus-visible:ring-2 focus-visible:ring-cyan-300',
                      isActive
                        ? 'border-cyan-300/20 bg-cyan-950/70 text-white'
                        : 'hover:bg-white/5 hover:text-white',
                    )
                  }
                >
                  <Icon aria-hidden="true" className="h-[18px] w-[18px]" />
                  {label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
        <div className="border-t border-white/10 p-4 text-xs text-slate-400">
          <div className="flex items-center justify-between gap-2">
            <span>Canonical source</span>
            <span className="font-mono text-slate-300">.sdoc</span>
          </div>
          <div className="mt-2 flex items-center justify-between gap-2">
            <span>Ревизия</span>
            <span
              className="max-w-[105px] truncate font-mono text-slate-300"
              title={project.data?.revision}
            >
              {health.data?.revision || project.data?.revision || '—'}
            </span>
          </div>
        </div>
      </aside>

      <div className="pl-60">
        <header className="fixed left-60 right-0 top-0 z-20 flex h-16 items-center gap-4 border-b border-line bg-white px-6 shadow-panel">
          <div className="min-w-0 max-w-[340px]">
            <p className="truncate text-sm font-semibold text-ink">
              {project.data?.name ?? 'ReqPilot Engineering Workbench'}
            </p>
            <p className="truncate text-[11px] text-steel">
              StrictDoc + Capella · локальный контур
            </p>
          </div>
          <form
            className="relative ml-auto w-[min(32vw,420px)]"
            role="search"
            onSubmit={handleSearch}
          >
            <Search
              aria-hidden="true"
              className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400"
            />
            <label className="sr-only" htmlFor="global-search">
              Глобальный поиск
            </label>
            <input
              id="global-search"
              className="input h-9 w-full pl-9 pr-16"
              placeholder="UID, название или UUID…"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
            <kbd className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 rounded border border-line bg-slate-50 px-1.5 py-0.5 text-[10px] text-slate-500">
              Enter
            </kbd>
          </form>
          <div className="flex items-center gap-2 border-l border-line pl-4">
            <StatusBadge
              status={
                project.isError || health.isError
                  ? 'error'
                  : (health.data?.status ?? project.data?.strictdocStatus ?? 'unknown')
              }
              label={`StrictDoc ${health.data?.strictdocVersion || project.data?.strictdocVersion || ''}`.trim()}
              compact
            />
            <StatusBadge
              status={capella.isError ? 'error' : capellaMode}
              label={`Capella · ${capellaMode}`}
              compact
            />
            <StatusBadge
              status={(dashboard.data?.brokenLinks ?? 0) > 0 ? 'error' : 'ok'}
              label={`${dashboard.data?.brokenLinks ?? '—'} broken`}
              compact
            />
          </div>
          <button
            className="icon-button"
            type="button"
            aria-label="Перезагрузить индексы"
            title="Перезагрузить индексы"
            disabled={reload.isPending}
            onClick={() => reload.mutate()}
          >
            <RefreshCw
              aria-hidden="true"
              className={cn('h-4 w-4', reload.isPending && 'animate-spin')}
            />
          </button>
          <button className="button-primary" type="button" onClick={createRequirement}>
            <Plus aria-hidden="true" className="h-4 w-4" />
            Требование
          </button>
          <button
            className="icon-button"
            type="button"
            aria-label="Открыть диагностику"
            title="Диагностика"
            onClick={() => void navigate('/diagnostics')}
          >
            <Settings2 aria-hidden="true" className="h-4 w-4" />
          </button>
        </header>

        <div className="pt-16">
          {capellaMode === 'fixture' ? (
            <div
              className="border-b border-amber-300 bg-amber-50 px-6 py-2 text-center text-sm font-semibold text-amber-950"
              role="status"
              data-testid="fixture-banner"
            >
              Демо-архитектура, не загруженная из Capella
            </div>
          ) : null}
          {reload.isError ? (
            <div
              className="border-b border-red-200 bg-red-50 px-6 py-2 text-sm text-red-800"
              role="alert"
            >
              Перезагрузка не выполнена: {reload.error.message}
            </div>
          ) : null}
          <main id="main-content" className="min-h-[calc(100vh-4rem)] p-6" tabIndex={-1}>
            <Outlet key={location.pathname} />
          </main>
        </div>
      </div>
    </div>
  );
}
