import { useMutation, useQuery } from '@tanstack/react-query';
import {
  Braces,
  Download,
  FileArchive,
  FileCode2,
  FileJson,
  FileSpreadsheet,
  FileText,
  LoaderCircle,
  Play,
} from 'lucide-react';
import { useState } from 'react';
import { api } from '../lib/api';
import type { ExportJob } from '../lib/types';
import { formatBytes, formatDuration } from '../lib/utils';
import { EmptyState } from '../components/PageState';
import { SectionHeader } from '../components/SectionHeader';
import { StatusBadge } from '../components/StatusBadge';

const formats = [
  { id: 'html', label: 'HTML', description: 'Нативный StrictDoc export', icon: FileCode2 },
  { id: 'pdf', label: 'PDF', description: 'Нативный StrictDoc + Chrome', icon: FileText },
  { id: 'excel', label: 'Excel', description: 'Нативный XLSX workbook', icon: FileSpreadsheet },
  { id: 'json', label: 'JSON', description: 'Машиночитаемый StrictDoc', icon: FileJson },
  { id: 'reqif', label: 'ReqIF', description: 'ReqIF 1.0 для обмена', icon: FileArchive },
  {
    id: 'combined-html',
    label: 'Combined HTML',
    description: 'Standalone: reqs + graph + matrices',
    icon: Braces,
  },
] as const;

type ExportFormat = (typeof formats)[number]['id'];

export function ExportsPage() {
  const [jobs, setJobs] = useState<ExportJob[]>([]);
  const [activeFormat, setActiveFormat] = useState<ExportFormat | null>(null);
  const start = useMutation({
    mutationFn: (format: ExportFormat) => api.startExport(format),
    onMutate: (format) => setActiveFormat(format),
    onSuccess: (job) =>
      setJobs((current) => [job, ...current.filter((item) => item.id !== job.id)]),
    onSettled: () => setActiveFormat(null),
  });

  return (
    <>
      <SectionHeader
        eyebrow="Reproducible artifacts"
        title="Экспорт"
        description="StrictDoc запускается штатными командами. ReqPilot показывает stdout/stderr, SHA-256 и не скрывает ошибки совместимости."
      />
      <section className="grid grid-cols-3 gap-3" aria-label="Форматы экспорта">
        {formats.map(({ id, label, description, icon: Icon }) => (
          <article key={id} className="panel flex items-center gap-4 p-4">
            <div className="grid h-11 w-11 shrink-0 place-items-center rounded-md border border-cyan/20 bg-cyan-50 text-cyan-dark">
              <Icon aria-hidden="true" className="h-5 w-5" />
            </div>
            <div className="min-w-0 flex-1">
              <h2 className="font-semibold text-ink">{label}</h2>
              <p className="mt-1 text-xs text-steel">{description}</p>
            </div>
            <button
              className="button-primary"
              data-testid={`export-${id}`}
              type="button"
              disabled={start.isPending}
              onClick={() => start.mutate(id)}
            >
              {activeFormat === id ? (
                <LoaderCircle aria-hidden="true" className="h-4 w-4 animate-spin" />
              ) : (
                <Play aria-hidden="true" className="h-4 w-4" />
              )}
              Запустить
            </button>
          </article>
        ))}
      </section>
      {start.isError ? (
        <div
          className="mt-4 rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-800"
          role="alert"
        >
          <strong>Экспорт не запущен:</strong> {start.error.message}
        </div>
      ) : null}
      <section className="panel mt-4 overflow-hidden">
        <div className="panel-header">
          <div>
            <h2 className="font-semibold">Задания</h2>
            <p className="mt-0.5 text-xs text-steel">
              Синхронный backend также возвращает job с фактическим временем
            </p>
          </div>
          <span className="text-xs tabular-nums text-steel">{jobs.length}</span>
        </div>
        {jobs.length === 0 ? (
          <div className="p-4">
            <EmptyState
              title="Экспорт ещё не запускался"
              description="Выберите формат выше. Файлы создаются backend-ом в output/."
            />
          </div>
        ) : (
          <ul className="divide-y divide-slate-100" data-testid="export-jobs">
            {jobs.map((job) => (
              <ExportJobItem key={job.id} initial={job} />
            ))}
          </ul>
        )}
      </section>
    </>
  );
}

function ExportJobItem({ initial }: { initial: ExportJob }) {
  const job = useQuery({
    queryKey: ['export-job', initial.id],
    queryFn: () => api.exportJob(initial.id),
    initialData: initial,
    refetchInterval: (query) =>
      query.state.data && ['queued', 'running'].includes(query.state.data.status) ? 800 : false,
  });
  const data = job.data;
  return (
    <li className="p-4">
      <div className="flex items-start gap-4">
        <StatusBadge status={data.status} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-3">
            <h3 className="font-semibold uppercase text-ink">{data.format}</h3>
            <code className="text-[10px] text-steel">{data.id}</code>
            <span className="ml-auto text-xs tabular-nums text-steel">
              {formatDuration(data.durationMs)}
            </span>
          </div>
          {data.error ? (
            <p className="mt-2 rounded border border-red-200 bg-red-50 p-2 text-xs text-red-800">
              {data.error}
            </p>
          ) : null}
          {data.createdFiles.length ? (
            <div className="mt-3 grid grid-cols-2 gap-2">
              {data.createdFiles.map((file) => (
                <a
                  key={file.id}
                  className="flex items-center gap-3 rounded-md border border-line bg-slate-50 px-3 py-2 hover:border-slate-400"
                  href={api.exportFileUrl(file.id)}
                  download
                >
                  <Download aria-hidden="true" className="h-4 w-4 shrink-0 text-cyan" />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-xs font-semibold text-ink">
                      {file.name}
                    </span>
                    <span className="mt-0.5 block truncate font-mono text-[9px] text-steel">
                      sha256 {file.sha256 || '—'}
                    </span>
                  </span>
                  <span className="text-[10px] tabular-nums text-steel">
                    {formatBytes(file.size)}
                  </span>
                </a>
              ))}
            </div>
          ) : null}
          {data.stdout || data.stderr ? (
            <details className="mt-3 rounded border border-line bg-slate-950 text-slate-200">
              <summary className="cursor-pointer px-3 py-2 text-xs font-semibold">
                stdout / stderr
              </summary>
              <pre className="max-h-56 overflow-auto border-t border-white/10 p-3 text-[10px] leading-4">
                {data.stdout}
                {data.stderr ? `\n[stderr]\n${data.stderr}` : ''}
              </pre>
            </details>
          ) : null}
        </div>
      </div>
    </li>
  );
}
