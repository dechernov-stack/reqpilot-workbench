import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  AlertTriangle,
  Boxes,
  Braces,
  CheckCircle2,
  FileWarning,
  GitBranch,
  Link2,
  RefreshCw,
  ShieldCheck,
  TerminalSquare,
  Wrench,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { api } from '../lib/api';
import type { Diagnostic } from '../lib/types';
import { EmptyState, ErrorState, LoadingState } from '../components/PageState';
import { SectionHeader } from '../components/SectionHeader';
import { StatusBadge } from '../components/StatusBadge';

export function DiagnosticsPage() {
  const queryClient = useQueryClient();
  const diagnostics = useQuery({ queryKey: ['diagnostics'], queryFn: api.diagnostics });
  const capella = useQuery({ queryKey: ['capella-status'], queryFn: api.capellaStatus });
  const health = useQuery({ queryKey: ['health'], queryFn: api.health });
  const validateRequirements = useMutation({
    mutationFn: api.validateRequirements,
    onSuccess: async () => queryClient.invalidateQueries({ queryKey: ['diagnostics'] }),
  });
  const validateLinks = useMutation({
    mutationFn: api.validateTraceLinks,
    onSuccess: async () => queryClient.invalidateQueries({ queryKey: ['diagnostics'] }),
  });
  const refreshSnapshots = useMutation({
    mutationFn: api.refreshTraceLinkSnapshots,
    onSuccess: async () => queryClient.invalidateQueries(),
  });
  const reloadCapella = useMutation({
    mutationFn: api.reloadCapella,
    onSuccess: async () => queryClient.invalidateQueries(),
  });

  if (diagnostics.isLoading) return <LoadingState label="Сбор диагностик…" />;
  if (diagnostics.isError)
    return <ErrorState error={diagnostics.error} onRetry={() => void diagnostics.refetch()} />;
  if (!diagnostics.data) return <EmptyState title="Диагностика недоступна" />;

  const data = diagnostics.data;
  const matches = (terms: string[]) =>
    data.items.filter((item) =>
      terms.some((term) =>
        `${item.source} ${item.code} ${item.message}`.toLowerCase().includes(term),
      ),
    );
  const categories: Array<{
    title: string;
    description: string;
    icon: LucideIcon;
    items: Diagnostic[];
  }> = [
    {
      title: 'StrictDoc errors',
      description: 'Parser, grammar, validate и запись',
      icon: Braces,
      items: matches(['strictdoc', 'sdoc', 'grammar']),
    },
    {
      title: 'Capella load / render',
      description: 'Model loader, index, diagram SVG',
      icon: Boxes,
      items: matches(['capella', 'diagram', 'svg']),
    },
    {
      title: 'Broken UID',
      description: 'Требование для trace-link не найдено',
      icon: Link2,
      items: matches(['broken_uid', 'unknown_uid', 'uid not']),
    },
    {
      title: 'Broken UUID',
      description: 'Архитектурный элемент не разрешается',
      icon: Link2,
      items: matches(['broken_uuid', 'unknown_uuid', 'uuid not']),
    },
    {
      title: 'Revision conflicts',
      description: 'Optimistic locking и rollback',
      icon: FileWarning,
      items: matches(['revision', 'conflict', 'if-match']),
    },
    {
      title: 'Export / PDF',
      description: 'StrictDoc command, ChromeDriver, файлы',
      icon: TerminalSquare,
      items: matches(['export', 'pdf', 'chrome', 'reqif']),
    },
  ];

  return (
    <>
      <SectionHeader
        eyebrow="Transparent failures"
        title="Диагностика"
        description="Ошибки разделены по источникам; совместимость ReqIF, Capella и PDF не маскируется общим зелёным статусом."
        actions={
          <button
            className="button-secondary"
            type="button"
            onClick={() => void diagnostics.refetch()}
          >
            <RefreshCw aria-hidden="true" className="h-4 w-4" />
            Обновить
          </button>
        }
      />
      <section className="grid grid-cols-6 gap-3" aria-label="Состояние окружения">
        <StatusCard
          label="Backend"
          status={health.data?.status ?? (health.isError ? 'error' : 'unknown')}
          value={health.data?.strictdocVersion ? `StrictDoc ${health.data.strictdocVersion}` : '—'}
          icon={ShieldCheck}
        />
        <StatusCard
          label="Capella"
          status={capella.data?.status ?? (capella.isError ? 'error' : 'unknown')}
          value={`${capella.data?.mode ?? 'unknown'} · ${capella.data?.version || '—'}`}
          icon={Boxes}
        />
        <StatusCard
          label="Stale cache"
          status={data.staleCache ? 'warning' : 'ok'}
          value={data.staleCache ? 'Обновить индекс' : 'Нет'}
          icon={RefreshCw}
        />
        <StatusCard
          label="Git tree"
          status={data.gitDirty ? 'warning' : 'ok'}
          value={data.gitDirty ? 'Dirty' : 'Clean'}
          icon={GitBranch}
        />
        <StatusCard
          label="PDF"
          status={data.pdfAvailable ? 'ok' : 'warning'}
          value={data.pdfAvailable ? 'Доступен' : 'Недоступен'}
          icon={FileWarning}
        />
        <StatusCard
          label="ChromeDriver"
          status={data.chromeDriver ? 'ok' : 'warning'}
          value={data.chromeDriver || 'Не найден'}
          icon={Wrench}
        />
      </section>

      <section className="panel mt-4 p-4">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="mr-auto font-semibold">Проверки и обслуживание</h2>
          <ActionButton
            label="Validate .sdoc"
            pending={validateRequirements.isPending}
            error={validateRequirements.isError ? validateRequirements.error.message : ''}
            onClick={() => validateRequirements.mutate()}
          />
          <ActionButton
            label="Validate links"
            pending={validateLinks.isPending}
            error={validateLinks.isError ? validateLinks.error.message : ''}
            onClick={() => validateLinks.mutate()}
          />
          <ActionButton
            label="Refresh snapshots"
            pending={refreshSnapshots.isPending}
            error={refreshSnapshots.isError ? refreshSnapshots.error.message : ''}
            onClick={() => refreshSnapshots.mutate()}
          />
          <ActionButton
            label="Reload Capella"
            pending={reloadCapella.isPending}
            error={reloadCapella.isError ? reloadCapella.error.message : ''}
            onClick={() => reloadCapella.mutate()}
          />
        </div>
      </section>

      <div className="mt-4 grid grid-cols-3 gap-3">
        {categories.map(({ title, description, icon: Icon, items }) => (
          <section key={title} className="panel min-h-48 overflow-hidden">
            <div className="panel-header">
              <div>
                <h2 className="text-sm font-semibold">{title}</h2>
                <p className="mt-0.5 text-[10px] text-steel">{description}</p>
              </div>
              <div className="flex items-center gap-2">
                <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs font-semibold tabular-nums text-steel">
                  {items.length}
                </span>
                <Icon aria-hidden="true" className="h-4 w-4 text-slate-400" />
              </div>
            </div>
            {items.length ? (
              <ul className="max-h-64 divide-y divide-slate-100 overflow-y-auto">
                {items.map((item) => (
                  <DiagnosticItem key={item.id} item={item} />
                ))}
              </ul>
            ) : (
              <div className="flex h-32 flex-col items-center justify-center gap-2 p-4 text-xs text-steel">
                <CheckCircle2 aria-hidden="true" className="h-5 w-5 text-ok" />
                Нет диагностик
              </div>
            )}
          </section>
        ))}
      </div>

      <section className="panel mt-4 overflow-hidden">
        <div className="panel-header">
          <div>
            <h2 className="font-semibold">Фактические версии инструментов</h2>
            <p className="mt-0.5 text-xs text-steel">
              Данные возвращены backend-ом текущего процесса
            </p>
          </div>
          <code className="text-[10px] text-steel">rev {data.revision || '—'}</code>
        </div>
        {Object.keys(data.tools).length ? (
          <dl className="grid grid-cols-4 gap-px bg-line">
            {Object.entries(data.tools)
              .sort(([a], [b]) => a.localeCompare(b))
              .map(([name, version]) => (
                <div key={name} className="bg-white p-3">
                  <dt className="text-xs font-semibold text-steel">{name}</dt>
                  <dd className="mt-1 font-mono text-xs text-ink">{version || '—'}</dd>
                </div>
              ))}
          </dl>
        ) : (
          <div className="p-4">
            <EmptyState title="Версии не переданы" />
          </div>
        )}
      </section>
    </>
  );
}

function StatusCard({
  label,
  status,
  value,
  icon: Icon,
}: {
  label: string;
  status: string;
  value: string;
  icon: LucideIcon;
}) {
  return (
    <article className="panel min-w-0 p-3">
      <div className="flex items-center justify-between gap-2">
        <p className="text-[10px] font-bold uppercase tracking-wide text-steel">{label}</p>
        <Icon aria-hidden="true" className="h-4 w-4 text-slate-400" />
      </div>
      <div className="mt-3">
        <StatusBadge status={status} compact />
      </div>
      <p className="mt-2 truncate text-[10px] text-steel" title={value}>
        {value}
      </p>
    </article>
  );
}

function DiagnosticItem({ item }: { item: Diagnostic }) {
  return (
    <li className="p-3">
      <div className="flex items-start gap-2">
        <StatusBadge status={item.severity} compact />
        <div className="min-w-0">
          <p className="text-xs font-medium leading-5 text-ink">{item.message}</p>
          <p className="mt-1 truncate font-mono text-[9px] text-steel">
            {item.code} {item.path}
          </p>
        </div>
      </div>
    </li>
  );
}

function ActionButton({
  label,
  pending,
  error,
  onClick,
}: {
  label: string;
  pending: boolean;
  error: string;
  onClick: () => void;
}) {
  return (
    <div className="relative">
      <button
        className="button-secondary"
        type="button"
        disabled={pending}
        title={error || undefined}
        onClick={onClick}
      >
        {pending ? (
          <RefreshCw aria-hidden="true" className="h-4 w-4 animate-spin" />
        ) : error ? (
          <AlertTriangle aria-hidden="true" className="h-4 w-4 text-danger" />
        ) : (
          <CheckCircle2 aria-hidden="true" className="h-4 w-4 text-ok" />
        )}
        {label}
      </button>
    </div>
  );
}
