import * as Tabs from '@radix-ui/react-tabs';
import { useQuery } from '@tanstack/react-query';
import { useVirtualizer } from '@tanstack/react-virtual';
import { Check, Download, Link2, Search, X } from 'lucide-react';
import { useMemo, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Dialog } from '../components/Dialog';
import { EmptyState, ErrorState, LoadingState } from '../components/PageState';
import { SectionHeader } from '../components/SectionHeader';
import { api } from '../lib/api';
import type { MatrixCell, MatrixData } from '../lib/types';
import {
  downloadText,
  formatPercent,
  matrixCellIndex,
  matrixCellKey,
  matrixToCsv,
} from '../lib/utils';

const tabs = [
  { value: 'requirements-tests', label: 'Tests', title: 'Требования ↔ тесты' },
  { value: 'requirements-functions', label: 'Functions', title: 'Требования ↔ функции' },
  { value: 'requirements-components', label: 'Components', title: 'Требования ↔ компоненты' },
  { value: 'functions-components', label: 'Allocations', title: 'Функции ↔ компоненты' },
] as const;

type MatrixKind = (typeof tabs)[number]['value'];

export function MatricesPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const initial = searchParams.get('tab');
  const [kind, setKind] = useState<MatrixKind>(
    tabs.some((tab) => tab.value === initial) ? (initial as MatrixKind) : 'requirements-tests',
  );
  const [text, setText] = useState('');
  const matrix = useQuery({
    queryKey: ['matrix', kind, text],
    queryFn: () => api.matrix(kind, { text }),
  });

  const changeTab = (value: string) => {
    const next = value as MatrixKind;
    setKind(next);
    setSearchParams({ tab: next }, { replace: true });
  };
  const exportCsv = () => {
    if (!matrix.data) return;
    downloadText(`reqpilot-${kind}.csv`, `\ufeff${matrixToCsv(matrix.data)}`, 'text/csv');
  };

  return (
    <>
      <SectionHeader
        eyebrow="Coverage & allocations"
        title="Матрицы"
        description="Проверяемые связи с переходом к исходным объектам. CSV содержит только текущую матрицу и применённый поиск."
        actions={
          <button
            className="button-secondary"
            type="button"
            disabled={!matrix.data}
            onClick={exportCsv}
          >
            <Download aria-hidden="true" className="h-4 w-4" />
            CSV
          </button>
        }
      />
      <Tabs.Root
        value={kind}
        onValueChange={changeTab}
        className="panel flex h-[calc(100vh-185px)] min-h-[620px] flex-col overflow-hidden"
      >
        <div className="flex items-center justify-between gap-4 border-b border-line px-4">
          <Tabs.List className="flex" aria-label="Тип матрицы">
            {tabs.map((tab) => (
              <Tabs.Trigger
                key={tab.value}
                value={tab.value}
                className="tab-trigger"
                data-testid={`matrix-tab-${tab.value}`}
              >
                {tab.label}
              </Tabs.Trigger>
            ))}
          </Tabs.List>
          <label className="relative w-64">
            <span className="sr-only">Поиск по матрице</span>
            <Search
              aria-hidden="true"
              className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400"
            />
            <input
              className="input w-full pl-8"
              placeholder="Фильтр строк и колонок…"
              value={text}
              onChange={(event) => setText(event.target.value)}
            />
          </label>
          {matrix.data ? (
            <div className="flex items-center gap-3 border-l border-line pl-4">
              <div className="text-right">
                <p className="text-[10px] uppercase tracking-wide text-steel">Покрытие</p>
                <p
                  className="text-lg font-bold tabular-nums text-ink"
                  data-testid="matrix-coverage"
                >
                  {formatPercent(matrix.data.coverage)}
                </p>
              </div>
              <div
                className="h-2 w-28 overflow-hidden rounded-full bg-slate-200"
                aria-label={`Покрытие ${formatPercent(matrix.data.coverage)}`}
              >
                <div
                  className="h-full bg-cyan"
                  style={{ width: `${Math.max(0, Math.min(100, matrix.data.coverage))}%` }}
                />
              </div>
              <span className="text-xs tabular-nums text-steel">
                {matrix.data.covered} / {matrix.data.total}
              </span>
            </div>
          ) : null}
        </div>
        {tabs.map((tab) => (
          <Tabs.Content
            key={tab.value}
            value={tab.value}
            className="min-h-0 flex-1 focus:outline-none"
          >
            {matrix.isLoading ? <LoadingState label={`Формирование: ${tab.title}…`} /> : null}
            {matrix.isError ? (
              <ErrorState error={matrix.error} onRetry={() => void matrix.refetch()} />
            ) : null}
            {matrix.data && (matrix.data.rows.length === 0 || matrix.data.columns.length === 0) ? (
              <EmptyState
                title="Матрица пуста"
                description="Для этой комбинации нет объектов. Проверьте адаптер и trace-links."
              />
            ) : null}
            {matrix.data && matrix.data.rows.length > 0 && matrix.data.columns.length > 0 ? (
              <VirtualMatrix matrix={matrix.data} kind={kind} />
            ) : null}
          </Tabs.Content>
        ))}
      </Tabs.Root>
    </>
  );
}

function VirtualMatrix({ matrix, kind }: { matrix: MatrixData; kind: MatrixKind }) {
  const navigate = useNavigate();
  const containerRef = useRef<HTMLDivElement>(null);
  const [selected, setSelected] = useState<{
    cell: MatrixCell;
    rowLabel: string;
    columnLabel: string;
  } | null>(null);
  const cellIndex = useMemo(() => matrixCellIndex(matrix), [matrix]);
  const rowVirtualizer = useVirtualizer({
    count: matrix.rows.length,
    getScrollElement: () => containerRef.current,
    estimateSize: () => 42,
    overscan: 8,
  });
  const columnWidth = 146;
  const totalWidth = 260 + matrix.columns.length * columnWidth;
  const openItem = (id: string, axis: 'row' | 'column') => {
    const isRequirement =
      (kind.startsWith('requirements') && axis === 'row') ||
      (kind === 'requirements-tests' && axis === 'column');
    if (isRequirement) void navigate(`/requirements?uid=${encodeURIComponent(id)}`);
    else void navigate(`/architecture?uuid=${encodeURIComponent(id)}`);
  };

  return (
    <>
      <div ref={containerRef} className="h-full overflow-auto" data-testid={`matrix-${kind}`}>
        <div
          className="relative"
          style={{ width: totalWidth, height: rowVirtualizer.getTotalSize() + 94 }}
        >
          <div
            className="sticky top-0 z-20 flex h-[94px] border-b border-line bg-slate-100"
            style={{ width: totalWidth }}
          >
            <div className="sticky left-0 z-30 flex w-[260px] shrink-0 items-end border-r border-line bg-slate-100 px-3 py-2 text-[11px] font-bold uppercase tracking-wide text-slate-600">
              Объект
            </div>
            {matrix.columns.map((column) => (
              <button
                key={column.id}
                className="flex h-[94px] w-[146px] shrink-0 items-end border-r border-line px-2 py-2 text-left text-[11px] font-semibold text-slate-700 hover:bg-slate-200 focus-visible:relative"
                title={`${column.label} · ${column.type}`}
                type="button"
                onClick={() => openItem(column.id, 'column')}
              >
                <span className="line-clamp-4">{column.label}</span>
              </button>
            ))}
          </div>
          <div
            className="absolute left-0 top-[94px]"
            style={{ height: rowVirtualizer.getTotalSize(), width: totalWidth }}
          >
            {rowVirtualizer.getVirtualItems().map((virtualRow) => {
              const row = matrix.rows[virtualRow.index];
              if (!row) return null;
              return (
                <div
                  key={row.id}
                  className="absolute left-0 flex h-[42px] border-b border-slate-100 bg-white hover:bg-cyan-50/30"
                  style={{ width: totalWidth, transform: `translateY(${virtualRow.start}px)` }}
                >
                  <button
                    className="sticky left-0 z-10 flex w-[260px] shrink-0 items-center gap-2 border-r border-line bg-inherit px-3 text-left focus-visible:z-20"
                    type="button"
                    onClick={() => openItem(row.id, 'row')}
                  >
                    <span className="mono-id w-20 shrink-0 truncate">{row.id}</span>
                    <span className="min-w-0 flex-1 truncate text-xs font-medium">{row.label}</span>
                  </button>
                  {matrix.columns.map((column) => {
                    const cell = cellIndex.get(matrixCellKey(row.id, column.id));
                    return (
                      <button
                        key={column.id}
                        className={
                          cell?.linked
                            ? 'grid w-[146px] shrink-0 place-items-center border-r border-slate-100 bg-emerald-50 text-ok hover:bg-emerald-100'
                            : 'grid w-[146px] shrink-0 place-items-center border-r border-slate-100 text-slate-300 hover:bg-slate-100'
                        }
                        aria-label={`${row.label} — ${column.label}: ${cell?.linked ? `связь ${cell.relation}` : 'нет связи'}`}
                        data-testid={`matrix-cell-${row.id}-${column.id}`}
                        type="button"
                        onClick={() =>
                          cell?.linked &&
                          setSelected({ cell, rowLabel: row.label, columnLabel: column.label })
                        }
                      >
                        {cell?.linked ? (
                          <Check aria-hidden="true" className="h-4 w-4" />
                        ) : (
                          <X aria-hidden="true" className="h-3 w-3 opacity-25" />
                        )}
                      </button>
                    );
                  })}
                </div>
              );
            })}
          </div>
        </div>
      </div>
      <Dialog
        open={Boolean(selected)}
        onOpenChange={(open) => !open && setSelected(null)}
        title="Связь матрицы"
        description={selected ? `${selected.rowLabel} ↔ ${selected.columnLabel}` : undefined}
      >
        {selected ? (
          <dl className="space-y-3 text-sm">
            <div>
              <dt className="field-label">Relation</dt>
              <dd className="flex items-center gap-2 font-semibold text-ink">
                <Link2 aria-hidden="true" className="h-4 w-4 text-cyan" />
                {selected.cell.relation || 'linked'}
              </dd>
            </div>
            <div>
              <dt className="field-label">Идентификаторы связей</dt>
              <dd className="space-y-1">
                {selected.cell.linkIds.length ? (
                  selected.cell.linkIds.map((id) => (
                    <code key={id} className="block rounded bg-slate-100 px-2 py-1 text-xs">
                      {id}
                    </code>
                  ))
                ) : (
                  <span className="text-steel">Источник не передал ID связи</span>
                )}
              </dd>
            </div>
          </dl>
        ) : null}
      </Dialog>
    </>
  );
}
