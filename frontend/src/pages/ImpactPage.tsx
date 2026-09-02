import { useQuery } from '@tanstack/react-query';
import { AlertTriangle, ArrowRight, Box, Braces, GitBranch, Route } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../lib/api';
import { humanize } from '../lib/utils';
import { EmptyState, ErrorState, LoadingState } from '../components/PageState';
import { SectionHeader } from '../components/SectionHeader';
import { StatusBadge } from '../components/StatusBadge';

type SubjectKind = 'requirement' | 'capella';

export function ImpactPage() {
  const [kind, setKind] = useState<SubjectKind>('requirement');
  const [identifier, setIdentifier] = useState('SYS-002');
  const [depth, setDepth] = useState(3);
  const [active, setActive] = useState<{ kind: SubjectKind; id: string; depth: number }>({
    kind: 'requirement',
    id: 'SYS-002',
    depth: 3,
  });
  const requirements = useQuery({
    queryKey: ['requirements', 'impact-picker'],
    queryFn: () => api.requirements(),
  });
  const elements = useQuery({
    queryKey: ['capella-elements', 'impact-picker'],
    queryFn: () => api.capellaElements(),
  });
  const impact = useQuery({
    queryKey: ['impact', active.kind, active.id, active.depth],
    queryFn: () =>
      active.kind === 'requirement'
        ? api.impactRequirement(active.id, active.depth)
        : api.impactCapella(active.id, active.depth),
    enabled: Boolean(active.id),
  });
  const choices =
    kind === 'requirement'
      ? (requirements.data?.items.map((item) => ({
          id: item.uid,
          label: `${item.uid} · ${item.title}`,
        })) ?? [])
      : (elements.data?.map((item) => ({ id: item.uuid, label: `${item.name} · ${item.type}` })) ??
        []);

  const changeKind = (next: SubjectKind) => {
    setKind(next);
    setIdentifier(next === 'requirement' ? 'SYS-002' : (elements.data?.[0]?.uuid ?? ''));
  };

  return (
    <>
      <SectionHeader
        eyebrow="Graph traversal"
        title="Impact analysis"
        description="Детерминированный обход с защитой от циклов: связанные объекты сгруппированы, каждый результат объясняется конкретным путём."
      />
      <div className="grid grid-cols-[310px_1fr] gap-4">
        <aside className="panel h-fit p-4" aria-label="Параметры impact analysis">
          <fieldset>
            <legend className="field-label">Исходный объект</legend>
            <div className="grid grid-cols-2 rounded-md border border-line p-1">
              <button
                className={
                  kind === 'requirement'
                    ? 'rounded bg-cyan px-2 py-1.5 text-xs font-semibold text-white'
                    : 'rounded px-2 py-1.5 text-xs font-semibold text-steel hover:bg-slate-100'
                }
                type="button"
                onClick={() => changeKind('requirement')}
              >
                <Braces aria-hidden="true" className="mr-1 inline h-3.5 w-3.5" />
                Требование
              </button>
              <button
                className={
                  kind === 'capella'
                    ? 'rounded bg-cyan px-2 py-1.5 text-xs font-semibold text-white'
                    : 'rounded px-2 py-1.5 text-xs font-semibold text-steel hover:bg-slate-100'
                }
                type="button"
                onClick={() => changeKind('capella')}
              >
                <Box aria-hidden="true" className="mr-1 inline h-3.5 w-3.5" />
                Capella
              </button>
            </div>
          </fieldset>
          <label className="mt-4 block">
            <span className="field-label">UID / UUID</span>
            <input
              className="input w-full font-mono"
              list="impact-choices"
              value={identifier}
              onChange={(event) => setIdentifier(event.target.value)}
            />
            <datalist id="impact-choices">
              {choices.map((choice) => (
                <option key={choice.id} value={choice.id}>
                  {choice.label}
                </option>
              ))}
            </datalist>
          </label>
          <label className="mt-4 block">
            <span className="field-label">Глубина: {depth}</span>
            <input
              className="w-full accent-cyan"
              type="range"
              min="1"
              max="4"
              value={depth}
              onChange={(event) => setDepth(Number(event.target.value))}
            />
          </label>
          <button
            className="button-primary mt-4 w-full"
            type="button"
            disabled={!identifier.trim()}
            onClick={() => setActive({ kind, id: identifier.trim(), depth })}
          >
            <GitBranch aria-hidden="true" className="h-4 w-4" />
            Рассчитать impact
          </button>
          <div className="mt-5 rounded-md border border-line bg-slate-50 p-3 text-xs leading-5 text-steel">
            <strong className="text-ink">Правило:</strong> depth ограничивает число рёбер от
            исходного объекта. Повторно посещённые узлы не раскрываются.
          </div>
        </aside>

        <div className="min-w-0 space-y-4">
          {impact.isLoading ? <LoadingState label="Обход unified graph…" /> : null}
          {impact.isError ? (
            <ErrorState error={impact.error} onRetry={() => void impact.refetch()} />
          ) : null}
          {impact.data ? (
            <>
              <section className="panel flex items-center justify-between gap-4 p-4">
                <div className="flex min-w-0 items-center gap-3">
                  <div className="grid h-10 w-10 shrink-0 place-items-center rounded-md border border-cyan/30 bg-cyan-50 text-cyan-dark">
                    {active.kind === 'requirement' ? (
                      <Braces aria-hidden="true" className="h-5 w-5" />
                    ) : (
                      <Box aria-hidden="true" className="h-5 w-5" />
                    )}
                  </div>
                  <div className="min-w-0">
                    <p className="mono-id">{impact.data.root.id || active.id}</p>
                    <h2 className="truncate text-lg font-semibold">
                      {impact.data.root.label || active.id}
                    </h2>
                  </div>
                </div>
                <div className="text-right">
                  <p className="text-xs text-steel">Глубина обхода</p>
                  <p className="text-xl font-bold tabular-nums">{impact.data.depth}</p>
                </div>
              </section>
              {impact.data.groups.length === 0 ? (
                <EmptyState title="Зависимые объекты не найдены" />
              ) : (
                <section className="grid grid-cols-3 gap-3" aria-label="Группы влияния">
                  {impact.data.groups.map((group) => (
                    <div key={group.name} className="panel overflow-hidden">
                      <div className="panel-header">
                        <h2 className="text-sm font-semibold">{humanize(group.name)}</h2>
                        <span className="rounded bg-slate-100 px-2 py-0.5 text-xs font-semibold tabular-nums text-steel">
                          {group.items.length}
                        </span>
                      </div>
                      {group.items.length ? (
                        <ul className="max-h-56 divide-y divide-slate-100 overflow-y-auto">
                          {group.items.map((item) => (
                            <li key={item.id}>
                              <Link
                                className="flex items-center gap-2 px-3 py-2 hover:bg-slate-50"
                                to={
                                  item.id.includes('-') && !item.id.includes('uuid')
                                    ? `/requirements?uid=${encodeURIComponent(item.id)}`
                                    : `/architecture?uuid=${encodeURIComponent(item.id)}`
                                }
                              >
                                <span className="min-w-0 flex-1">
                                  <span className="block truncate text-xs font-semibold text-ink">
                                    {item.label}
                                  </span>
                                  <span className="mt-0.5 block truncate font-mono text-[10px] text-steel">
                                    {item.id}
                                  </span>
                                </span>
                                {item.status ? (
                                  <StatusBadge status={item.status} compact />
                                ) : (
                                  <ArrowRight
                                    aria-hidden="true"
                                    className="h-3.5 w-3.5 text-slate-400"
                                  />
                                )}
                              </Link>
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <p className="p-4 text-xs text-steel">Объектов нет</p>
                      )}
                    </div>
                  ))}
                </section>
              )}
              <section className="panel overflow-hidden" data-testid="impact-paths">
                <div className="panel-header">
                  <div>
                    <h2 className="font-semibold">Кратчайшие пути</h2>
                    <p className="mt-0.5 text-xs text-steel">Почему объект попал в impact</p>
                  </div>
                  <Route aria-hidden="true" className="h-4 w-4 text-cyan" />
                </div>
                {impact.data.paths.length ? (
                  <ol className="divide-y divide-slate-100">
                    {impact.data.paths.map((path, index) => (
                      <li key={`${path.nodes.join('-')}-${index}`} className="p-4">
                        <p className="text-xs font-semibold text-ink">
                          {path.summary || `Путь ${index + 1}`}
                        </p>
                        <div className="mt-2 flex flex-wrap items-center gap-1 text-xs">
                          {path.nodes.map((node, nodeIndex) => (
                            <span
                              key={`${node}-${nodeIndex}`}
                              className="inline-flex items-center gap-1"
                            >
                              <code className="rounded border border-line bg-slate-50 px-1.5 py-1">
                                {node}
                              </code>
                              {nodeIndex < path.nodes.length - 1 ? (
                                <span className="inline-flex items-center gap-1 text-steel">
                                  <span>{humanize(path.relations[nodeIndex] ?? '')}</span>
                                  <ArrowRight aria-hidden="true" className="h-3 w-3" />
                                </span>
                              ) : null}
                            </span>
                          ))}
                        </div>
                      </li>
                    ))}
                  </ol>
                ) : (
                  <p className="p-4 text-sm text-steel">Backend не вернул пути.</p>
                )}
              </section>
              {impact.data.brokenLinks.length ? (
                <section className="panel border-red-200 bg-red-50 p-4">
                  <h2 className="flex items-center gap-2 font-semibold text-red-900">
                    <AlertTriangle aria-hidden="true" className="h-4 w-4" />
                    Битые ссылки
                  </h2>
                  <ul className="mt-3 space-y-2">
                    {impact.data.brokenLinks.map((link) => (
                      <li key={link.id} className="flex items-center gap-2 text-sm text-red-800">
                        <StatusBadge status={link.status} compact />
                        <code>{link.requirementUid}</code>
                        <ArrowRight aria-hidden="true" className="h-3 w-3" />
                        <code>{link.targetUuid}</code>
                      </li>
                    ))}
                  </ul>
                </section>
              ) : null}
            </>
          ) : null}
        </div>
      </div>
    </>
  );
}
