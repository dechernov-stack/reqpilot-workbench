import * as Select from '@radix-ui/react-select';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, ChevronDown, Link2, Search } from 'lucide-react';
import { useMemo, useState } from 'react';
import { api } from '../lib/api';
import type { Requirement, TraceRelation } from '../lib/types';
import { cn } from '../lib/utils';
import { Dialog } from './Dialog';
import { EmptyState, ErrorState, LoadingState } from './PageState';

interface TraceLinkDialogProps {
  requirement: Requirement;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function TraceLinkDialog({ requirement, open, onOpenChange }: TraceLinkDialogProps) {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState('');
  const [selectedUuid, setSelectedUuid] = useState('');
  const [relation, setRelation] = useState<TraceRelation>('satisfied_by');
  const elements = useQuery({
    queryKey: ['capella-elements', search],
    queryFn: () => api.capellaElements({ text: search }),
    enabled: open,
  });
  const selected = useMemo(
    () => elements.data?.find((element) => element.uuid === selectedUuid),
    [elements.data, selectedUuid],
  );
  const create = useMutation({
    mutationFn: () =>
      api.createTraceLink({
        requirement_uid: requirement.uid,
        requirement_mid: requirement.mid,
        model_id: selected?.modelId || 'default',
        target_uuid: selectedUuid,
        target_type: selected?.type ?? 'Element',
        target_name: selected?.name ?? '',
        relation,
        rationale: `Связь создана в ReqPilot для ${requirement.uid}`,
      }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['trace-links'] }),
        queryClient.invalidateQueries({ queryKey: ['graph'] }),
        queryClient.invalidateQueries({ queryKey: ['matrix'] }),
        queryClient.invalidateQueries({ queryKey: ['requirements'] }),
      ]);
      setSelectedUuid('');
      onOpenChange(false);
    },
  });

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="Связать с архитектурой"
      description={`${requirement.uid} · связь хранится по UUID элемента Capella`}
      footer={
        <div className="flex items-center justify-between gap-3">
          <p className="text-xs text-steel">
            Имя хранится только как снимок; UUID остаётся идентичностью.
          </p>
          <div className="flex items-center gap-2">
            <button className="button-secondary" type="button" onClick={() => onOpenChange(false)}>
              Отмена
            </button>
            <button
              className="button-primary"
              data-testid="create-trace-link"
              type="button"
              disabled={!selectedUuid || create.isPending}
              onClick={() => create.mutate()}
            >
              <Link2 aria-hidden="true" className="h-4 w-4" />
              {create.isPending ? 'Создание…' : 'Создать связь'}
            </button>
          </div>
        </div>
      }
    >
      <div className="space-y-4">
        <label className="block">
          <span className="field-label">Тип связи</span>
          <Select.Root value={relation} onValueChange={setRelation}>
            <Select.Trigger
              className="select flex w-full items-center justify-between"
              aria-label="Тип связи"
            >
              <Select.Value />
              <Select.Icon>
                <ChevronDown aria-hidden="true" className="h-4 w-4" />
              </Select.Icon>
            </Select.Trigger>
            <Select.Portal>
              <Select.Content className="z-[60] overflow-hidden rounded-md border border-line bg-white shadow-xl">
                <Select.Viewport className="p-1">
                  {(
                    [
                      ['satisfied_by', 'satisfied_by — удовлетворяется'],
                      ['allocated_to', 'allocated_to — назначено'],
                      ['implemented_by', 'implemented_by — реализуется'],
                      ['verified_by', 'verified_by — проверяется'],
                    ] as const
                  ).map(([value, label]) => (
                    <Select.Item
                      key={value}
                      value={value}
                      className="relative flex cursor-default select-none items-center rounded px-8 py-2 text-sm outline-none data-[highlighted]:bg-cyan-50"
                    >
                      <Select.ItemIndicator className="absolute left-2">
                        <Check aria-hidden="true" className="h-4 w-4" />
                      </Select.ItemIndicator>
                      <Select.ItemText>{label}</Select.ItemText>
                    </Select.Item>
                  ))}
                </Select.Viewport>
              </Select.Content>
            </Select.Portal>
          </Select.Root>
        </label>
        <label className="block">
          <span className="field-label">Найти элемент</span>
          <span className="relative block">
            <Search
              aria-hidden="true"
              className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400"
            />
            <input
              className="input w-full pl-9"
              placeholder="Название, тип или UUID"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </span>
        </label>
        <div
          className="max-h-72 overflow-y-auto rounded-md border border-line"
          role="listbox"
          aria-label="Элементы Capella"
        >
          {elements.isLoading ? <LoadingState label="Загрузка архитектуры…" /> : null}
          {elements.isError ? (
            <ErrorState error={elements.error} onRetry={() => void elements.refetch()} />
          ) : null}
          {elements.data?.length === 0 ? <EmptyState title="Элементы не найдены" /> : null}
          {elements.data?.map((element) => (
            <button
              key={element.uuid}
              className={cn(
                'flex w-full items-start gap-3 border-b border-slate-100 p-3 text-left last:border-0 hover:bg-slate-50 focus-visible:relative',
                selectedUuid === element.uuid && 'bg-cyan-50 ring-1 ring-inset ring-cyan',
              )}
              role="option"
              aria-selected={selectedUuid === element.uuid}
              data-testid={`capella-option-${element.uuid}`}
              type="button"
              onClick={() => setSelectedUuid(element.uuid)}
            >
              <span className="mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded border border-slate-300 bg-white">
                {selectedUuid === element.uuid ? (
                  <Check aria-hidden="true" className="h-3.5 w-3.5 text-cyan" />
                ) : null}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block font-semibold text-ink">{element.name}</span>
                <span className="mt-0.5 block text-xs text-steel">
                  {element.layer} · {element.type}
                </span>
                <span className="mt-1 block truncate font-mono text-[10px] text-slate-500">
                  {element.uuid}
                </span>
              </span>
            </button>
          ))}
        </div>
        {create.isError ? (
          <p
            className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-800"
            role="alert"
          >
            {create.error.message}
          </p>
        ) : null}
      </div>
    </Dialog>
  );
}
