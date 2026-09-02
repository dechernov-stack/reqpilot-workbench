import { useQuery } from '@tanstack/react-query';
import {
  AlertTriangle,
  Boxes,
  Braces,
  CheckCheck,
  Clock3,
  FileOutput,
  GitBranch,
  Link2,
  Network,
  TestTube2,
} from 'lucide-react';
import { Link } from 'react-router-dom';
import { api } from '../lib/api';
import { formatDuration, formatPercent } from '../lib/utils';
import { EmptyState, ErrorState, LoadingState } from '../components/PageState';
import { SectionHeader } from '../components/SectionHeader';
import { StatusBadge } from '../components/StatusBadge';

export function DashboardPage() {
  const dashboard = useQuery({ queryKey: ['dashboard'], queryFn: api.dashboard });

  if (dashboard.isLoading) return <LoadingState label="Формирование сводки…" />;
  if (dashboard.isError)
    return <ErrorState error={dashboard.error} onRetry={() => void dashboard.refetch()} />;
  if (!dashboard.data) return <EmptyState title="Сводка пока недоступна" />;

  const data = dashboard.data;
  const metrics = [
    {
      label: 'Требования',
      value: data.requirements,
      detail: 'StrictDoc nodes',
      icon: Braces,
      to: '/requirements',
    },
    {
      label: 'Capella elements',
      value: data.capellaElements,
      detail: 'read-only index',
      icon: Boxes,
      to: '/architecture',
    },
    {
      label: 'Внутренние связи',
      value: data.internalRelations,
      detail: 'relations в .sdoc',
      icon: Network,
      to: '/traceability',
    },
    {
      label: 'Trace links',
      value: data.traceLinks,
      detail: 'MID ↔ UUID',
      icon: Link2,
      to: '/traceability',
    },
    {
      label: 'Тестовое покрытие',
      value: formatPercent(data.testCoverage),
      detail: 'System + Safety',
      icon: TestTube2,
      to: '/matrices?tab=requirements-tests',
    },
    {
      label: 'Арх. покрытие',
      value: formatPercent(data.architectureCoverage),
      detail: 'валидные UUID',
      icon: CheckCheck,
      to: '/matrices?tab=requirements-functions',
    },
    {
      label: 'Broken links',
      value: data.brokenLinks,
      detail: data.brokenLinks ? 'требуют внимания' : 'не обнаружены',
      icon: AlertTriangle,
      to: '/diagnostics',
      danger: data.brokenLinks > 0,
    },
    {
      label: 'Индексация',
      value: formatDuration(data.indexDurationMs),
      detail: 'последний проход',
      icon: Clock3,
      to: '/diagnostics',
    },
    {
      label: 'Git status',
      value: data.gitDirty ? 'Dirty' : 'Clean',
      detail: data.gitBranch || 'ветка не определена',
      icon: GitBranch,
      to: '/diagnostics',
      danger: data.gitDirty,
    },
    {
      label: 'Последний экспорт',
      value: data.lastExport || '—',
      detail: 'StrictDoc native',
      icon: FileOutput,
      to: '/exports',
    },
  ];

  return (
    <>
      <SectionHeader
        eyebrow="Единый инженерный контур"
        title="Обзор"
        description="Состояние требований, архитектуры, трассировки и воспроизводимых артефактов проекта."
      />
      <section className="grid grid-cols-5 gap-3" aria-label="Ключевые показатели">
        {metrics.map(({ label, value, detail, icon: Icon, to, danger }) => (
          <Link
            key={label}
            to={to}
            className="panel group min-h-28 p-4 outline-none hover:border-slate-400 focus-visible:ring-2 focus-visible:ring-cyan"
          >
            <div className="flex items-start justify-between gap-2">
              <p className="text-xs font-semibold text-steel">{label}</p>
              <Icon
                aria-hidden="true"
                className={danger ? 'h-4 w-4 text-danger' : 'h-4 w-4 text-cyan'}
              />
            </div>
            <p className={danger ? 'metric-value mt-3 text-danger' : 'metric-value mt-3'}>
              {value}
            </p>
            <p className="mt-1 truncate text-[11px] text-slate-500">{detail}</p>
          </Link>
        ))}
      </section>
      <div className="mt-4 grid grid-cols-2 gap-4">
        <section className="panel overflow-hidden">
          <div className="panel-header">
            <div>
              <h2 className="font-semibold">Непокрытые требования</h2>
              <p className="mt-0.5 text-xs text-steel">Проверка и архитектурная трассировка</p>
            </div>
            <Link className="text-xs font-semibold text-cyan-dark hover:underline" to="/matrices">
              Открыть матрицы
            </Link>
          </div>
          {data.uncoveredRequirements.length === 0 ? (
            <div className="p-4">
              <EmptyState title="Все требования покрыты" />
            </div>
          ) : (
            <ul className="divide-y divide-slate-100">
              {data.uncoveredRequirements.slice(0, 8).map((requirement) => (
                <li key={requirement.uid}>
                  <Link
                    className="flex items-center gap-3 px-4 py-3 hover:bg-slate-50"
                    to={`/requirements?uid=${encodeURIComponent(requirement.uid)}`}
                  >
                    <span className="mono-id w-20 shrink-0">{requirement.uid}</span>
                    <span className="min-w-0 flex-1 truncate font-medium">{requirement.title}</span>
                    <StatusBadge status={requirement.priority} compact />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>
        <section className="panel overflow-hidden">
          <div className="panel-header">
            <div>
              <h2 className="font-semibold">Последние ошибки</h2>
              <p className="mt-0.5 text-xs text-steel">Validation, adapter и export</p>
            </div>
            <Link
              className="text-xs font-semibold text-cyan-dark hover:underline"
              to="/diagnostics"
            >
              Все диагностики
            </Link>
          </div>
          {data.recentErrors.length === 0 ? (
            <div className="p-4">
              <EmptyState
                title="Ошибок нет"
                description="Последняя индексация завершилась без диагностик уровня error."
              />
            </div>
          ) : (
            <ul className="divide-y divide-slate-100">
              {data.recentErrors.slice(0, 8).map((diagnostic) => (
                <li key={diagnostic.id} className="flex items-start gap-3 px-4 py-3">
                  <StatusBadge status={diagnostic.severity} compact />
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-ink">{diagnostic.message}</p>
                    <p className="mt-1 truncate font-mono text-[10px] text-slate-500">
                      {diagnostic.code} {diagnostic.path}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </>
  );
}
