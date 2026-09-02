import { useQuery } from '@tanstack/react-query';
import {
  Box,
  ChevronRight,
  Copy,
  FileImage,
  Focus,
  Layers3,
  Maximize2,
  Search,
} from 'lucide-react';
import { useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { api } from '../lib/api';
import type { CapellaElement } from '../lib/types';
import { cn, copyText } from '../lib/utils';
import { EmptyState, ErrorState, LoadingState } from '../components/PageState';
import { SectionHeader } from '../components/SectionHeader';
import { StatusBadge } from '../components/StatusBadge';

type SvgPresentation = {
  width: number;
  height: number | undefined;
  labels: string[];
};

function inspectSvg(svgMarkup: string | undefined): SvgPresentation {
  const fallback = { width: 900, height: undefined, labels: [] };
  if (!svgMarkup || typeof DOMParser === 'undefined') return fallback;
  const document = new DOMParser().parseFromString(svgMarkup, 'image/svg+xml');
  if (document.querySelector('parsererror')) return fallback;
  const root = document.documentElement;
  const viewBox = root.getAttribute('viewBox')?.trim().split(/\s+/).map(Number);
  const parseLength = (value: string | null) => {
    const parsed = Number.parseFloat(value ?? '');
    return Number.isFinite(parsed) && parsed > 0 ? parsed : undefined;
  };
  const width = parseLength(root.getAttribute('width')) ?? viewBox?.[2] ?? fallback.width;
  const height = parseLength(root.getAttribute('height')) ?? viewBox?.[3];
  const labels = [
    ...new Set(
      [...document.querySelectorAll('text')]
        .map((node) => node.textContent?.trim() ?? '')
        .filter(Boolean),
    ),
  ];
  return {
    width: Number.isFinite(width) && width > 0 ? width : fallback.width,
    height: height && Number.isFinite(height) && height > 0 ? height : undefined,
    labels,
  };
}

export function ArchitecturePage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [text, setText] = useState('');
  const [type, setType] = useState('');
  const [layer, setLayer] = useState('');
  const [selectedUuid, setSelectedUuid] = useState(searchParams.get('uuid') ?? '');
  const [selectedDiagram, setSelectedDiagram] = useState('');
  const [diagramFitted, setDiagramFitted] = useState(true);
  const [copied, setCopied] = useState(false);
  const status = useQuery({ queryKey: ['capella-status'], queryFn: api.capellaStatus });
  const elements = useQuery({
    queryKey: ['capella-elements', text, type, layer],
    queryFn: () => api.capellaElements({ text, type, layer }),
    enabled: status.data?.mode !== 'disabled',
  });
  const selectedFromList = elements.data?.find((element) => element.uuid === selectedUuid);
  const detail = useQuery({
    queryKey: ['capella-element', selectedUuid],
    queryFn: () => api.capellaElement(selectedUuid),
    enabled: Boolean(selectedUuid),
    initialData: selectedFromList,
  });
  const diagrams = useQuery({
    queryKey: ['capella-diagrams'],
    queryFn: api.diagrams,
    enabled: status.data?.mode !== 'disabled',
  });
  const traceLinks = useQuery({ queryKey: ['trace-links'], queryFn: api.traceLinks });
  const svg = useQuery({
    queryKey: ['capella-diagram-svg', selectedDiagram],
    queryFn: () => api.diagramSvg(selectedDiagram),
    enabled: Boolean(selectedDiagram),
  });
  const layers = useMemo(() => {
    const grouped = new Map<string, CapellaElement[]>();
    elements.data?.forEach((element) => {
      const key = element.layer || 'Без слоя';
      grouped.set(key, [...(grouped.get(key) ?? []), element]);
    });
    return [...grouped.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [elements.data]);
  const types = useMemo(
    () => [...new Set(elements.data?.map((element) => element.type) ?? [])].sort(),
    [elements.data],
  );
  const relevantDiagrams = useMemo(() => {
    if (!selectedUuid) return diagrams.data ?? [];
    const matching =
      diagrams.data?.filter((diagram) => diagram.representedElementUuids.includes(selectedUuid)) ??
      [];
    return matching.length ? matching : (diagrams.data ?? []);
  }, [diagrams.data, selectedUuid]);
  const selectedDiagramInfo = useMemo(
    () => diagrams.data?.find((diagram) => diagram.uuid === selectedDiagram),
    [diagrams.data, selectedDiagram],
  );
  const svgPresentation = useMemo(() => inspectSvg(svg.data), [svg.data]);
  const diagramDescription = useMemo(() => {
    if (!selectedDiagramInfo) return 'Диаграмма Capella.';
    const labels = svgPresentation.labels.length
      ? ` Подписи: ${svgPresentation.labels.join(', ')}.`
      : '';
    return `${selectedDiagramInfo.name}. Тип: ${selectedDiagramInfo.type}.${labels}`;
  }, [selectedDiagramInfo, svgPresentation.labels]);
  const linkedRequirementUids = useMemo(
    () => [
      ...new Set([
        ...(detail.data?.linkedRequirementUids ?? []),
        ...(traceLinks.data
          ?.filter((link) => link.targetUuid === selectedUuid)
          .map((link) => link.requirementUid) ?? []),
      ]),
    ],
    [detail.data?.linkedRequirementUids, selectedUuid, traceLinks.data],
  );

  const chooseElement = (uuid: string) => {
    setSelectedUuid(uuid);
    setSearchParams({ uuid }, { replace: true });
  };
  const copyUuid = async () => {
    if (!selectedUuid) return;
    await copyText(selectedUuid);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1200);
  };

  if (status.isLoading) return <LoadingState label="Проверка адаптера Capella…" />;
  if (status.isError)
    return <ErrorState error={status.error} onRetry={() => void status.refetch()} />;

  return (
    <>
      <SectionHeader
        eyebrow={`Capella adapter · ${status.data?.mode ?? 'disabled'}`}
        title="Архитектура"
        description="Read-only индекс модели: элементы идентифицируются UUID, исходные Capella-файлы не изменяются."
        actions={
          <StatusBadge
            status={status.data?.status ?? 'unknown'}
            label={`${status.data?.elementCount ?? 0} elements`}
          />
        }
      />
      {status.data?.mode === 'disabled' ? (
        <div className="panel p-8">
          <EmptyState
            title="Модель Capella не подключена"
            description="Укажите путь к модели и mode: live в project.yaml либо включите явно маркированный fixture для демонстрации. Backend никогда не создаёт .aird и не изменяет модель."
            action={
              <Link className="button-secondary" to="/diagnostics">
                Открыть диагностику
              </Link>
            }
          />
        </div>
      ) : (
        <div className="grid h-[calc(100vh-185px)] min-h-[620px] grid-cols-[230px_minmax(300px,0.8fr)_minmax(360px,1.2fr)] gap-3 2xl:grid-cols-[280px_minmax(360px,0.8fr)_minmax(400px,1.2fr)]">
          <section className="panel min-h-0 overflow-hidden" aria-label="Дерево архитектуры">
            <div className="panel-header">
              <h2 className="text-sm font-semibold">Слои и элементы</h2>
              <Layers3 aria-hidden="true" className="h-4 w-4 text-slate-400" />
            </div>
            <div className="space-y-2 border-b border-line p-3">
              <label className="relative block">
                <span className="sr-only">Поиск по архитектуре</span>
                <Search
                  aria-hidden="true"
                  className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400"
                />
                <input
                  className="input w-full pl-8"
                  placeholder="Имя или UUID…"
                  value={text}
                  onChange={(event) => setText(event.target.value)}
                />
              </label>
              <div className="grid grid-cols-2 gap-2">
                <select
                  className="select w-full"
                  aria-label="Слой"
                  value={layer}
                  onChange={(event) => setLayer(event.target.value)}
                >
                  <option value="">Все слои</option>
                  {layers.map(([name]) => (
                    <option key={name}>{name}</option>
                  ))}
                </select>
                <select
                  className="select w-full"
                  aria-label="Тип"
                  value={type}
                  onChange={(event) => setType(event.target.value)}
                >
                  <option value="">Все типы</option>
                  {types.map((name) => (
                    <option key={name}>{name}</option>
                  ))}
                </select>
              </div>
            </div>
            <div className="h-[calc(100%-146px)] overflow-y-auto p-2">
              {elements.isLoading ? <LoadingState label="Чтение индекса…" /> : null}
              {elements.isError ? (
                <ErrorState error={elements.error} onRetry={() => void elements.refetch()} />
              ) : null}
              {elements.data?.length === 0 ? <EmptyState title="Элементы не найдены" /> : null}
              {layers.map(([layerName, items]) => (
                <details key={layerName} open className="mb-2">
                  <summary className="cursor-pointer rounded px-2 py-1.5 text-xs font-bold uppercase tracking-wide text-slate-600 hover:bg-slate-100">
                    {layerName}{' '}
                    <span className="font-normal text-slate-400">({items?.length ?? 0})</span>
                  </summary>
                  <ul className="mt-1 space-y-0.5 border-l border-slate-200 pl-2">
                    {items?.map((element) => (
                      <li key={element.uuid}>
                        <button
                          className={cn(
                            'flex w-full items-start gap-2 rounded px-2 py-2 text-left hover:bg-slate-100',
                            selectedUuid === element.uuid &&
                              'bg-cyan-50 text-cyan-dark ring-1 ring-inset ring-cyan',
                          )}
                          data-testid={`architecture-element-${element.uuid}`}
                          type="button"
                          onClick={() => chooseElement(element.uuid)}
                        >
                          <Box aria-hidden="true" className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                          <span className="min-w-0">
                            <span className="block truncate text-xs font-semibold">
                              {element.name}
                            </span>
                            <span className="block truncate text-[10px] text-slate-500">
                              {element.type}
                            </span>
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </details>
              ))}
            </div>
          </section>

          <section className="panel min-h-0 overflow-y-auto" aria-label="Карточка элемента">
            {!selectedUuid ? (
              <EmptyState
                title="Выберите элемент"
                description="UUID, свойства и связи появятся в карточке."
              />
            ) : null}
            {detail.isLoading ? <LoadingState label="Загрузка элемента…" /> : null}
            {detail.isError ? (
              <ErrorState error={detail.error} onRetry={() => void detail.refetch()} />
            ) : null}
            {detail.data ? (
              <div>
                <div className="border-b border-line p-4">
                  <div className="flex flex-wrap items-center gap-1 text-xs text-steel">
                    {detail.data.path.map((item, index) => (
                      <span key={`${item}-${index}`} className="inline-flex items-center gap-1">
                        {index ? <ChevronRight aria-hidden="true" className="h-3 w-3" /> : null}
                        {item}
                      </span>
                    ))}
                  </div>
                  <h2 className="mt-3 text-xl font-semibold text-ink">{detail.data.name}</h2>
                  <div className="mt-2 flex items-center gap-2">
                    <StatusBadge
                      status={detail.data.layer}
                      label={detail.data.layer || 'Слой не указан'}
                    />
                    <span className="rounded border border-line bg-slate-50 px-2 py-0.5 text-xs font-semibold">
                      {detail.data.type}
                    </span>
                  </div>
                </div>
                <dl className="space-y-4 p-4 text-sm">
                  <div>
                    <dt className="field-label">UUID</dt>
                    <dd className="flex items-center gap-2 rounded border border-line bg-slate-50 px-3 py-2">
                      <code className="min-w-0 flex-1 break-all text-xs">{detail.data.uuid}</code>
                      <button
                        className="icon-button h-7 w-7 shrink-0"
                        type="button"
                        aria-label="Копировать UUID"
                        onClick={() => void copyUuid()}
                      >
                        <Copy aria-hidden="true" className="h-3.5 w-3.5" />
                      </button>
                    </dd>
                    {copied ? (
                      <p className="mt-1 text-xs text-ok" role="status">
                        UUID скопирован
                      </p>
                    ) : null}
                  </div>
                  <div>
                    <dt className="field-label">Описание</dt>
                    <dd className="whitespace-pre-wrap leading-6 text-steel">
                      {detail.data.description || '—'}
                    </dd>
                  </div>
                  <div>
                    <dt className="field-label">Связанные требования</dt>
                    <dd>
                      {linkedRequirementUids.length ? (
                        <ul className="space-y-1">
                          {linkedRequirementUids.map((uid) => (
                            <li key={uid}>
                              <Link
                                className="mono-id hover:underline"
                                to={`/requirements?uid=${encodeURIComponent(uid)}`}
                              >
                                {uid}
                              </Link>
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <span className="text-steel">Связей нет</span>
                      )}
                    </dd>
                  </div>
                  <div>
                    <dt className="field-label">Отношения модели</dt>
                    <dd>
                      {detail.data.relations.length ? (
                        <ul className="space-y-1">
                          {detail.data.relations.map((relation, index) => (
                            <li
                              key={`${relation.role}-${relation.value}-${index}`}
                              className="rounded border border-line px-2 py-1.5 text-xs"
                            >
                              <strong>{relation.role}</strong> → <code>{relation.value}</code>
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <span className="text-steel">Отношений нет</span>
                      )}
                    </dd>
                  </div>
                </dl>
              </div>
            ) : null}
          </section>

          <section className="panel min-h-0 overflow-hidden" aria-label="Диаграммы">
            <div className="panel-header">
              <div>
                <h2 className="text-sm font-semibold">Диаграммы</h2>
                <p className="mt-0.5 text-[11px] text-steel">SVG через capellambse · read-only</p>
              </div>
              <FileImage aria-hidden="true" className="h-4 w-4 text-slate-400" />
            </div>
            <div className="flex h-[calc(100%-57px)] min-h-0">
              <div className="w-44 shrink-0 overflow-y-auto border-r border-line p-2">
                {diagrams.isLoading ? <LoadingState label="Диаграммы…" /> : null}
                {relevantDiagrams.length === 0 && !diagrams.isLoading ? (
                  <EmptyState title="Диаграмм нет" />
                ) : null}
                {relevantDiagrams.map((diagram) => (
                  <button
                    key={diagram.uuid}
                    className={cn(
                      'mb-1 w-full rounded px-2 py-2 text-left text-xs hover:bg-slate-100',
                      selectedDiagram === diagram.uuid && 'bg-cyan-50 ring-1 ring-inset ring-cyan',
                    )}
                    type="button"
                    onClick={() => {
                      setSelectedDiagram(diagram.uuid);
                      setDiagramFitted(true);
                    }}
                  >
                    <span className="block font-semibold">{diagram.name}</span>
                    <span className="mt-1 block text-[10px] text-steel">{diagram.type}</span>
                  </button>
                ))}
              </div>
              <div className="relative min-w-0 flex-1 bg-slate-100">
                {!selectedDiagram ? <EmptyState title="Выберите диаграмму" /> : null}
                {svg.isLoading ? <LoadingState label="Рендер SVG…" /> : null}
                {svg.isError ? (
                  <ErrorState error={svg.error} onRetry={() => void svg.refetch()} />
                ) : null}
                {svg.data ? (
                  <div className="h-full w-full overflow-auto bg-white p-3">
                    <img
                      alt={selectedDiagramInfo?.name ?? 'Диаграмма Capella'}
                      aria-describedby="capella-diagram-description"
                      className={cn(
                        'block transition-none',
                        diagramFitted ? 'h-full w-full object-contain' : 'h-auto w-auto max-w-none',
                      )}
                      src={`data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg.data)}`}
                      style={
                        diagramFitted
                          ? undefined
                          : {
                              width: svgPresentation.width,
                              height: svgPresentation.height,
                            }
                      }
                    />
                    <p className="sr-only" id="capella-diagram-description">
                      {diagramDescription}
                    </p>
                  </div>
                ) : null}
                {svg.data ? (
                  <div className="absolute right-3 top-3 flex gap-1 rounded-md bg-white/90 p-1 shadow-sm">
                    <button
                      className="icon-button"
                      type="button"
                      aria-label="Показать диаграмму в исходном размере"
                      aria-pressed={!diagramFitted}
                      title="Исходный размер"
                      onClick={() => setDiagramFitted(false)}
                    >
                      <Maximize2 aria-hidden="true" className="h-4 w-4" />
                    </button>
                    <button
                      className="icon-button"
                      type="button"
                      aria-label="Вписать диаграмму"
                      aria-pressed={diagramFitted}
                      title="Вписать"
                      onClick={() => setDiagramFitted(true)}
                    >
                      <Focus aria-hidden="true" className="h-4 w-4" />
                    </button>
                  </div>
                ) : null}
              </div>
            </div>
          </section>
        </div>
      )}
    </>
  );
}
