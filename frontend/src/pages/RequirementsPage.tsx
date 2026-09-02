import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ExternalLink, FileCode2, Filter, Link2, Plus, Search, Trash2 } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { ApiError, api } from '../lib/api';
import type { Requirement, RequirementInput } from '../lib/types';
import { cn, humanize } from '../lib/utils';
import { Dialog } from '../components/Dialog';
import { EmptyState, ErrorState, LoadingState } from '../components/PageState';
import { RequirementForm } from '../components/RequirementForm';
import { SectionHeader } from '../components/SectionHeader';
import { StatusBadge } from '../components/StatusBadge';
import { TraceLinkDialog } from '../components/TraceLinkDialog';

const columnHelper = createColumnHelper<Requirement>();

export function RequirementsPage() {
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const [text, setText] = useState(searchParams.get('text') ?? '');
  const [type, setType] = useState('');
  const [selectedUid, setSelectedUid] = useState(searchParams.get('uid') ?? '');
  const [createMode, setCreateMode] = useState(searchParams.get('create') === '1');
  const [linkDialogOpen, setLinkDialogOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [conflictOpen, setConflictOpen] = useState(false);
  const [validationNotice, setValidationNotice] = useState('');

  useEffect(() => {
    if (searchParams.get('create') === '1') setCreateMode(true);
    const uid = searchParams.get('uid');
    if (uid) setSelectedUid(uid);
  }, [searchParams]);

  const list = useQuery({
    queryKey: ['requirements', text, type],
    queryFn: () => api.requirements({ text, type }),
  });
  const selectedFromList = list.data?.items.find((item) => item.uid === selectedUid);
  const detail = useQuery({
    queryKey: ['requirement', selectedUid],
    queryFn: () => api.requirement(selectedUid),
    enabled: Boolean(selectedUid) && !createMode,
    initialData: selectedFromList,
  });
  const links = useQuery({ queryKey: ['trace-links'], queryFn: api.traceLinks });
  const selected = detail.data;
  const requirementLinks = links.data?.filter((link) => link.requirementUid === selectedUid) ?? [];

  const save = useMutation({
    mutationFn: (input: RequirementInput) =>
      createMode ? api.createRequirement(input) : api.updateRequirement(selectedUid, input),
    onSuccess: async (requirement) => {
      setCreateMode(false);
      setSelectedUid(requirement.uid);
      setSearchParams({ uid: requirement.uid }, { replace: true });
      queryClient.setQueryData(['requirement', requirement.uid], requirement);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['requirements'] }),
        queryClient.invalidateQueries({ queryKey: ['dashboard'] }),
        queryClient.invalidateQueries({ queryKey: ['diagnostics'] }),
      ]);
    },
    onError: (error) => {
      if (error instanceof ApiError && (error.status === 409 || error.status === 412)) {
        setConflictOpen(true);
      }
    },
  });
  const validate = useMutation({
    mutationFn: api.validateRequirements,
    onSuccess: () => setValidationNotice('StrictDoc validation: PASS'),
    onError: () => setValidationNotice('StrictDoc validation: FAIL'),
  });
  const remove = useMutation({
    mutationFn: () =>
      api.deleteRequirement(selectedUid, selected?.revision ?? list.data?.revision ?? ''),
    onSuccess: async () => {
      setDeleteOpen(false);
      setSelectedUid('');
      setSearchParams({}, { replace: true });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['requirements'] }),
        queryClient.invalidateQueries({ queryKey: ['dashboard'] }),
      ]);
    },
  });

  const selectRequirement = (uid: string) => {
    setSelectedUid(uid);
    setCreateMode(false);
    setSearchParams({ uid }, { replace: true });
  };
  const startCreate = () => {
    setSelectedUid('');
    setCreateMode(true);
    setSearchParams({ create: '1' }, { replace: true });
  };

  const columns = useMemo(
    () => [
      columnHelper.accessor('uid', {
        header: 'UID',
        cell: (info) => <span className="mono-id">{info.getValue()}</span>,
      }),
      columnHelper.accessor('title', {
        header: 'Название',
        cell: (info) => (
          <span className="line-clamp-2 min-w-44 font-medium text-ink">{info.getValue()}</span>
        ),
      }),
      columnHelper.accessor('type', {
        header: 'Тип',
        cell: (info) => <span className="text-xs text-steel">{info.getValue()}</span>,
      }),
      columnHelper.accessor('status', {
        header: 'Статус',
        cell: (info) => <StatusBadge status={info.getValue()} compact />,
      }),
      columnHelper.accessor('priority', {
        header: 'P',
        cell: (info) => <span className="text-xs font-semibold">{info.getValue()}</span>,
      }),
      columnHelper.accessor('owner', {
        header: 'Владелец',
        cell: (info) => <span className="text-xs text-steel">{info.getValue() || '—'}</span>,
      }),
      columnHelper.display({
        id: 'links',
        header: 'Связи',
        cell: ({ row }) => (
          <span className="whitespace-nowrap text-xs tabular-nums text-steel">
            {row.original.relations.length} / {row.original.architectureLinkCount}
          </span>
        ),
      }),
    ],
    [],
  );
  const table = useReactTable({
    data: list.data?.items ?? [],
    columns,
    getCoreRowModel: getCoreRowModel(),
  });
  const documents = useMemo(() => {
    const counts = new Map<string, number>();
    list.data?.items.forEach((item) =>
      counts.set(
        item.document || 'Без документа',
        (counts.get(item.document || 'Без документа') ?? 0) + 1,
      ),
    );
    return [...counts.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [list.data]);

  return (
    <>
      <SectionHeader
        eyebrow="StrictDoc · canonical"
        title="Требования"
        description="Просмотр и безопасное редактирование управляемых .sdoc-файлов с optimistic locking по ревизии."
        actions={
          <button className="button-primary" type="button" onClick={startCreate}>
            <Plus aria-hidden="true" className="h-4 w-4" />
            Создать
          </button>
        }
      />
      {validationNotice ? (
        <div
          className={cn(
            'mb-3 rounded border px-3 py-2 text-sm',
            validationNotice.endsWith('PASS')
              ? 'border-emerald-200 bg-emerald-50 text-emerald-800'
              : 'border-red-200 bg-red-50 text-red-800',
          )}
          role="status"
        >
          {validationNotice}
        </div>
      ) : null}
      <div className="grid h-[calc(100vh-190px)] min-h-[620px] grid-cols-[180px_minmax(390px,1.05fr)_minmax(360px,0.95fr)] gap-3 2xl:grid-cols-[190px_minmax(410px,1.05fr)_minmax(370px,0.95fr)]">
        <section className="panel min-h-0 overflow-hidden" aria-label="Документы StrictDoc">
          <div className="panel-header">
            <h2 className="text-sm font-semibold">Документы</h2>
            <FileCode2 aria-hidden="true" className="h-4 w-4 text-slate-400" />
          </div>
          <div className="h-[calc(100%-49px)] overflow-y-auto p-2">
            {list.isLoading ? <LoadingState label="Чтение .sdoc…" /> : null}
            {documents.length === 0 && !list.isLoading ? (
              <EmptyState title="Документов нет" />
            ) : null}
            <ul className="space-y-1">
              {documents.map(([document, count]) => (
                <li key={document}>
                  <button
                    className="flex w-full items-start justify-between gap-2 rounded px-2 py-2 text-left text-xs hover:bg-slate-100"
                    type="button"
                    onClick={() => setText(document)}
                  >
                    <span className="min-w-0 break-all font-medium text-slate-700">{document}</span>
                    <span className="rounded bg-slate-100 px-1.5 tabular-nums text-slate-500">
                      {count}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section className="panel min-h-0 overflow-hidden" aria-label="Таблица требований">
          <div className="panel-header flex-wrap">
            <div className="relative min-w-48 flex-1">
              <Search
                aria-hidden="true"
                className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400"
              />
              <label className="sr-only" htmlFor="requirement-search">
                Поиск требований
              </label>
              <input
                id="requirement-search"
                className="input w-full pl-8"
                placeholder="UID или текст…"
                value={text}
                onChange={(event) => setText(event.target.value)}
              />
            </div>
            <label className="relative">
              <span className="sr-only">Фильтр по типу</span>
              <Filter
                aria-hidden="true"
                className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-400"
              />
              <select
                className="select w-32 pl-8"
                value={type}
                onChange={(event) => setType(event.target.value)}
              >
                <option value="">Все типы</option>
                {['Stakeholder', 'System', 'Software', 'Interface', 'Safety', 'TestCase'].map(
                  (value) => (
                    <option key={value}>{value}</option>
                  ),
                )}
              </select>
            </label>
            <span className="text-xs tabular-nums text-steel">{list.data?.total ?? 0}</span>
          </div>
          <div className="h-[calc(100%-61px)] overflow-auto">
            {list.isLoading ? <LoadingState label="Индексация требований…" /> : null}
            {list.isError ? (
              <ErrorState error={list.error} onRetry={() => void list.refetch()} />
            ) : null}
            {list.data?.items.length === 0 ? (
              <EmptyState
                title="Требования не найдены"
                description="Измените фильтр или создайте новое требование."
              />
            ) : null}
            {list.data?.items.length ? (
              <table className="data-table" data-testid="requirements-table">
                <thead>
                  {table.getHeaderGroups().map((headerGroup) => (
                    <tr key={headerGroup.id}>
                      {headerGroup.headers.map((header) => (
                        <th key={header.id}>
                          {header.isPlaceholder
                            ? null
                            : flexRender(header.column.columnDef.header, header.getContext())}
                        </th>
                      ))}
                    </tr>
                  ))}
                </thead>
                <tbody>
                  {table.getRowModel().rows.map((row) => (
                    <tr
                      key={row.id}
                      className={cn(
                        'cursor-pointer',
                        selectedUid === row.original.uid &&
                          'bg-cyan-50 ring-1 ring-inset ring-cyan',
                      )}
                      data-testid={`requirement-row-${row.original.uid}`}
                      tabIndex={0}
                      aria-selected={selectedUid === row.original.uid}
                      onClick={() => selectRequirement(row.original.uid)}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter' || event.key === ' ') {
                          event.preventDefault();
                          selectRequirement(row.original.uid);
                        }
                      }}
                    >
                      {row.getVisibleCells().map((cell) => (
                        <td key={cell.id}>
                          {flexRender(cell.column.columnDef.cell, cell.getContext())}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : null}
          </div>
        </section>

        <section className="panel min-h-0 overflow-hidden" aria-label="Карточка требования">
          {createMode ? (
            <RequirementForm
              isSaving={save.isPending}
              isValidating={validate.isPending}
              saveError={save.isError ? save.error.message : undefined}
              onSubmit={(input) => save.mutate(input)}
              onValidate={() => validate.mutate()}
              onCancel={() => {
                setCreateMode(false);
                setSearchParams({}, { replace: true });
              }}
            />
          ) : null}
          {!createMode && detail.isLoading ? <LoadingState label="Загрузка карточки…" /> : null}
          {!createMode && detail.isError ? (
            <ErrorState error={detail.error} onRetry={() => void detail.refetch()} />
          ) : null}
          {!createMode && !selectedUid ? (
            <EmptyState
              title="Выберите требование"
              description="Карточка, редактор и связи откроются здесь."
            />
          ) : null}
          {!createMode && selected ? (
            <div className="flex h-full min-h-0 flex-col">
              <div className="flex items-center justify-between gap-2 border-b border-line px-4 py-2">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="mono-id">{selected.uid}</span>
                    <StatusBadge status={selected.status} compact />
                  </div>
                  <p className="mt-1 truncate text-xs text-steel">MID {selected.mid || '—'}</p>
                </div>
                <div className="flex items-center gap-1">
                  {selected && (
                    <button
                      className="button-secondary"
                      type="button"
                      onClick={() => setLinkDialogOpen(true)}
                    >
                      <Link2 aria-hidden="true" className="h-4 w-4" />
                      Связать
                    </button>
                  )}
                  <button
                    className="icon-button"
                    type="button"
                    aria-label="Удалить требование"
                    title="Удалить"
                    onClick={() => setDeleteOpen(true)}
                  >
                    <Trash2 aria-hidden="true" className="h-4 w-4" />
                  </button>
                  {selected.document ? (
                    <a
                      className="icon-button"
                      href={`/strictdoc/#${encodeURIComponent(selected.uid)}`}
                      target="_blank"
                      rel="noreferrer"
                      aria-label="Открыть в штатном StrictDoc"
                      title="Открыть в штатном StrictDoc"
                    >
                      <ExternalLink aria-hidden="true" className="h-4 w-4" />
                    </a>
                  ) : null}
                </div>
              </div>
              <div className="min-h-0 flex-1">
                <RequirementForm
                  requirement={selected}
                  isSaving={save.isPending}
                  isValidating={validate.isPending}
                  saveError={save.isError ? save.error.message : undefined}
                  onSubmit={(input) => save.mutate(input)}
                  onValidate={() => validate.mutate()}
                />
              </div>
              <details className="border-t border-line bg-white px-4 py-2">
                <summary className="cursor-pointer text-xs font-semibold text-slate-700">
                  Связи: StrictDoc {selected.relations.length} · Capella {requirementLinks.length}
                </summary>
                <ul className="mt-2 space-y-1 text-xs text-steel">
                  {selected.relations.map((relation, index) => (
                    <li key={`${relation.role}-${relation.value}-${index}`}>
                      <span className="font-semibold">{humanize(relation.role)}</span> →{' '}
                      <span className="font-mono">{relation.value}</span>
                    </li>
                  ))}
                  {requirementLinks.map((link) => (
                    <li key={link.id}>
                      <span className="font-semibold">{humanize(link.relation)}</span> →{' '}
                      {link.targetNameSnapshot || link.targetUuid}{' '}
                      <StatusBadge status={link.status} compact />
                    </li>
                  ))}
                  {selected.relations.length + requirementLinks.length === 0 ? (
                    <li>Связей пока нет.</li>
                  ) : null}
                </ul>
              </details>
            </div>
          ) : null}
        </section>
      </div>

      {selected ? (
        <TraceLinkDialog
          requirement={selected}
          open={linkDialogOpen}
          onOpenChange={setLinkDialogOpen}
        />
      ) : null}
      <Dialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title={`Удалить ${selected?.uid ?? ''}?`}
        description="UID не будет переиспользован. Backend выполнит validation и rollback при ошибке."
        footer={
          <div className="flex justify-end gap-2">
            <button className="button-secondary" type="button" onClick={() => setDeleteOpen(false)}>
              Отмена
            </button>
            <button
              className="button-danger"
              type="button"
              disabled={remove.isPending}
              onClick={() => remove.mutate()}
            >
              <Trash2 aria-hidden="true" className="h-4 w-4" />
              {remove.isPending ? 'Удаление…' : 'Удалить'}
            </button>
          </div>
        }
      >
        {remove.isError ? (
          <p className="rounded border border-red-200 bg-red-50 p-3 text-red-800" role="alert">
            {remove.error.message}
          </p>
        ) : (
          <p className="text-sm text-steel">
            Будет изменён только управляемый .sdoc-документ. Перед заменой создаётся backup.
          </p>
        )}
      </Dialog>
      <Dialog
        open={conflictOpen}
        onOpenChange={setConflictOpen}
        title="Конфликт ревизии"
        description="Документ изменился после загрузки карточки. Ваши данные не отправлены повторно автоматически."
        footer={
          <div className="flex justify-end gap-2">
            <button
              className="button-secondary"
              type="button"
              onClick={() => setConflictOpen(false)}
            >
              Остаться
            </button>
            <button
              className="button-primary"
              type="button"
              onClick={() => {
                setConflictOpen(false);
                void detail.refetch();
              }}
            >
              Загрузить актуальную версию
            </button>
          </div>
        }
      >
        <p className="text-sm leading-6 text-steel">
          Сравните актуальное требование с вашими изменениями и сохраните снова. Это защищает от
          потери параллельных правок.
        </p>
      </Dialog>
    </>
  );
}
