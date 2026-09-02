import {
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  MiniMap,
  Position,
  ReactFlow,
  ReactFlowProvider,
  type Node,
  type NodeProps,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { useQuery } from '@tanstack/react-query';
import {
  Box,
  Braces,
  Download,
  Focus,
  Route,
  Search,
  TestTube2,
  TriangleAlert,
} from 'lucide-react';
import { useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { api } from '../lib/api';
import { graphSvgToPng, graphToSvg, layoutGraph, shortestPath } from '../lib/graph';
import type { GraphNode } from '../lib/types';
import { cn, downloadText, humanize } from '../lib/utils';
import { EmptyState, ErrorState, LoadingState } from '../components/PageState';
import { SectionHeader } from '../components/SectionHeader';

type EngineeringFlowNode = Node<GraphNode>;

function EngineeringNode({ data, selected }: NodeProps<EngineeringFlowNode>) {
  const Icon =
    data.kind === 'capella'
      ? Box
      : data.kind === 'test'
        ? TestTube2
        : data.kind === 'broken'
          ? TriangleAlert
          : Braces;
  return (
    <div
      className={cn(
        'w-[190px] border-2 bg-white px-3 py-2 shadow-sm',
        data.kind === 'requirement' && 'rounded-lg border-cyan',
        data.kind === 'test' && 'rounded-[24px] border-ok',
        data.kind === 'capella' && 'rounded-sm border-violet-600',
        data.kind === 'broken' &&
          'border-danger bg-red-50 [clip-path:polygon(6%_0,94%_0,100%_18%,100%_82%,94%_100%,6%_100%,0_82%,0_18%)]',
        selected && 'ring-4 ring-cyan/25',
      )}
    >
      <Handle
        type="target"
        position={Position.Left}
        className="!h-2 !w-2 !border-white !bg-slate-500"
      />
      <div className="flex items-center gap-2">
        <Icon aria-hidden="true" className="h-4 w-4 shrink-0 text-slate-500" />
        <span className="truncate text-xs font-bold text-ink">{data.label}</span>
      </div>
      <p className="mt-1 truncate pl-6 text-[10px] text-steel">
        {data.type || humanize(data.kind)}
      </p>
      <Handle
        type="source"
        position={Position.Right}
        className="!h-2 !w-2 !border-white !bg-slate-500"
      />
    </div>
  );
}

const nodeTypes = { engineering: EngineeringNode };

export function TraceabilityPage() {
  return (
    <ReactFlowProvider>
      <TraceabilityCanvas />
    </ReactFlowProvider>
  );
}

function TraceabilityCanvas() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [focus, setFocus] = useState(searchParams.get('focus') ?? 'SYS-002');
  const [depth, setDepth] = useState(2);
  const [source, setSource] = useState('');
  const [type, setType] = useState('');
  const [relation, setRelation] = useState('');
  const [text, setText] = useState('');
  const [pathFrom, setPathFrom] = useState('');
  const [pathTo, setPathTo] = useState('');
  const [pathMessage, setPathMessage] = useState('');
  const [pathNodes, setPathNodes] = useState<Set<string>>(new Set());
  const [pathEdges, setPathEdges] = useState<Set<string>>(new Set());
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set());

  const graph = useQuery({
    queryKey: ['graph', focus, depth, source, type, relation, text],
    queryFn: () => api.graph({ focus, depth, source, type, relation, text }),
  });
  const filteredData = useMemo(() => {
    if (!graph.data || collapsedGroups.size === 0) return graph.data;
    const nodes = graph.data.nodes.filter((node) => !collapsedGroups.has(node.group));
    const ids = new Set(nodes.map((node) => node.id));
    return {
      ...graph.data,
      nodes,
      edges: graph.data.edges.filter((edge) => ids.has(edge.source) && ids.has(edge.target)),
    };
  }, [graph.data, collapsedGroups]);
  const layout = useMemo(
    () => (filteredData ? layoutGraph(filteredData) : { nodes: [], edges: [] }),
    [filteredData],
  );
  const nodes = useMemo(
    () =>
      layout.nodes.map((node) => ({
        ...node,
        ...(pathNodes.size === 0 || pathNodes.has(node.id) ? {} : { style: { opacity: 0.28 } }),
      })),
    [layout.nodes, pathNodes],
  );
  const edges = useMemo(
    () =>
      layout.edges.map((edge) => ({
        ...edge,
        style: pathEdges.has(edge.id)
          ? { stroke: '#0d7180', strokeWidth: 3 }
          : pathEdges.size
            ? { ...(edge.style ?? {}), opacity: 0.2 }
            : (edge.style ?? {}),
      })),
    [layout.edges, pathEdges],
  );
  const groups = useMemo(
    () => [...new Set(graph.data?.nodes.map((node) => node.group).filter(Boolean) ?? [])].sort(),
    [graph.data],
  );
  const types = useMemo(
    () => [...new Set(graph.data?.nodes.map((node) => node.type).filter(Boolean) ?? [])].sort(),
    [graph.data],
  );
  const relations = useMemo(
    () => [...new Set(graph.data?.edges.map((edge) => edge.relation).filter(Boolean) ?? [])].sort(),
    [graph.data],
  );

  const findPath = () => {
    if (!graph.data) return;
    const result = shortestPath(graph.data, pathFrom, pathTo);
    if (!result) {
      setPathNodes(new Set());
      setPathEdges(new Set());
      setPathMessage('Связный путь не найден');
      return;
    }
    setPathNodes(new Set(result.nodeIds));
    setPathEdges(new Set(result.edgeIds));
    setPathMessage(`Путь: ${result.nodeIds.join(' → ')}`);
  };
  const exportSvg = () => {
    if (!filteredData) return;
    downloadText('reqpilot-graph.svg', graphToSvg(filteredData), 'image/svg+xml');
  };
  const exportPng = async () => {
    if (!filteredData) return;
    const png = await graphSvgToPng(graphToSvg(filteredData));
    const url = URL.createObjectURL(png);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = 'reqpilot-graph.png';
    anchor.click();
    URL.revokeObjectURL(url);
  };
  const openNode = (_event: React.MouseEvent, node: EngineeringFlowNode) => {
    if (node.data.kind === 'requirement' || node.data.kind === 'test')
      void navigate(`/requirements?uid=${encodeURIComponent(node.id)}`);
    else if (node.data.kind === 'capella')
      void navigate(`/architecture?uuid=${encodeURIComponent(node.id)}`);
  };

  return (
    <>
      <SectionHeader
        eyebrow="Unified graph"
        title="Трассировка"
        description="StrictDoc relations, отношения Capella и внешние MID ↔ UUID links в одном ограниченном connected component."
        actions={
          <div className="flex items-center gap-2">
            <button
              className="button-secondary"
              type="button"
              disabled={!filteredData}
              onClick={exportSvg}
            >
              <Download aria-hidden="true" className="h-4 w-4" />
              SVG
            </button>
            <button
              className="button-secondary"
              type="button"
              disabled={!filteredData}
              onClick={() => void exportPng()}
            >
              <Download aria-hidden="true" className="h-4 w-4" />
              PNG
            </button>
          </div>
        }
      />
      <div className="grid h-[calc(100vh-185px)] min-h-[620px] grid-cols-[260px_1fr] gap-3">
        <aside className="panel min-h-0 overflow-y-auto p-4" aria-label="Фильтры графа">
          <div className="space-y-4">
            <label className="block">
              <span className="field-label">Focus UID / UUID</span>
              <div className="relative">
                <Focus
                  aria-hidden="true"
                  className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400"
                />
                <input
                  className="input w-full pl-8 font-mono"
                  value={focus}
                  onChange={(event) => setFocus(event.target.value)}
                />
              </div>
            </label>
            <label className="block">
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
            <label className="block">
              <span className="field-label">Поиск</span>
              <div className="relative">
                <Search
                  aria-hidden="true"
                  className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400"
                />
                <input
                  className="input w-full pl-8"
                  placeholder="Название…"
                  value={text}
                  onChange={(event) => setText(event.target.value)}
                />
              </div>
            </label>
            <label className="block">
              <span className="field-label">Источник</span>
              <select
                className="select w-full"
                value={source}
                onChange={(event) => setSource(event.target.value)}
              >
                <option value="">Все источники</option>
                <option value="strictdoc">StrictDoc</option>
                <option value="capella">Capella</option>
                <option value="trace-link">Trace links</option>
              </select>
            </label>
            <label className="block">
              <span className="field-label">Тип узла</span>
              <select
                className="select w-full"
                value={type}
                onChange={(event) => setType(event.target.value)}
              >
                <option value="">Все типы</option>
                {types.map((item) => (
                  <option key={item}>{item}</option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="field-label">Relation</span>
              <select
                className="select w-full"
                value={relation}
                onChange={(event) => setRelation(event.target.value)}
              >
                <option value="">Все связи</option>
                {relations.map((item) => (
                  <option key={item}>{item}</option>
                ))}
              </select>
            </label>
          </div>
          <div className="my-5 border-t border-line" />
          <h2 className="text-xs font-bold uppercase tracking-wide text-slate-600">Path finder</h2>
          <div className="mt-3 space-y-2">
            <select
              className="select w-full"
              aria-label="Начало пути"
              value={pathFrom}
              onChange={(event) => setPathFrom(event.target.value)}
            >
              <option value="">От…</option>
              {graph.data?.nodes.map((node) => (
                <option key={node.id} value={node.id}>
                  {node.label}
                </option>
              ))}
            </select>
            <select
              className="select w-full"
              aria-label="Конец пути"
              value={pathTo}
              onChange={(event) => setPathTo(event.target.value)}
            >
              <option value="">До…</option>
              {graph.data?.nodes.map((node) => (
                <option key={node.id} value={node.id}>
                  {node.label}
                </option>
              ))}
            </select>
            <button
              className="button-secondary w-full"
              type="button"
              disabled={!pathFrom || !pathTo}
              onClick={findPath}
            >
              <Route aria-hidden="true" className="h-4 w-4" />
              Найти путь
            </button>
            {pathMessage ? (
              <p
                className="break-words rounded bg-slate-50 p-2 text-[11px] leading-4 text-steel"
                role="status"
              >
                {pathMessage}
              </p>
            ) : null}
          </div>
          {groups.length ? (
            <>
              <div className="my-5 border-t border-line" />
              <h2 className="text-xs font-bold uppercase tracking-wide text-slate-600">Группы</h2>
              <div className="mt-2 flex flex-wrap gap-1">
                {groups.map((group) => (
                  <button
                    key={group}
                    className={cn(
                      'rounded border px-2 py-1 text-[11px]',
                      collapsedGroups.has(group)
                        ? 'border-slate-300 bg-slate-100 text-slate-500 line-through'
                        : 'border-cyan/30 bg-cyan-50 text-cyan-dark',
                    )}
                    type="button"
                    aria-pressed={collapsedGroups.has(group)}
                    onClick={() =>
                      setCollapsedGroups((current) => {
                        const next = new Set(current);
                        if (next.has(group)) next.delete(group);
                        else next.add(group);
                        return next;
                      })
                    }
                  >
                    {group}
                  </button>
                ))}
              </div>
            </>
          ) : null}
        </aside>

        <section
          className="panel relative min-h-0 overflow-hidden"
          aria-label="Общий граф"
          data-testid="traceability-graph"
        >
          {graph.isLoading ? <LoadingState label="Формирование connected component…" /> : null}
          {graph.isError ? (
            <ErrorState error={graph.error} onRetry={() => void graph.refetch()} />
          ) : null}
          {graph.data && graph.data.nodes.length === 0 ? (
            <EmptyState title="Граф пуст" description="Проверьте focus и фильтры." />
          ) : null}
          {graph.data && graph.data.nodes.length > 0 ? (
            <ReactFlow<EngineeringFlowNode>
              nodes={nodes}
              edges={edges}
              nodeTypes={nodeTypes}
              fitView
              minZoom={0.15}
              maxZoom={2}
              nodesConnectable={false}
              onNodeDoubleClick={openNode}
              proOptions={{ hideAttribution: true }}
            >
              <Background variant={BackgroundVariant.Dots} gap={18} size={1} color="#c9d1d9" />
              <Controls position="bottom-right" showInteractive={false} />
              <MiniMap
                position="bottom-left"
                pannable
                zoomable
                nodeColor={(node) =>
                  node.data.kind === 'capella'
                    ? '#6b4f9b'
                    : node.data.kind === 'test'
                      ? '#24734a'
                      : node.data.kind === 'broken'
                        ? '#ae2e24'
                        : '#0d7180'
                }
              />
            </ReactFlow>
          ) : null}
          <div
            className="absolute right-3 top-3 rounded-md border border-line bg-white/95 p-2 shadow-sm"
            aria-label="Легенда"
          >
            <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[10px] font-semibold text-steel">
              <span className="flex items-center gap-1.5">
                <span className="h-3 w-4 rounded border-2 border-cyan" />
                Требование
              </span>
              <span className="flex items-center gap-1.5">
                <span className="h-3 w-4 rounded-full border-2 border-ok" />
                Тест
              </span>
              <span className="flex items-center gap-1.5">
                <span className="h-3 w-4 border-2 border-violet-600" />
                Capella
              </span>
              <span className="flex items-center gap-1.5">
                <span className="h-3 w-4 border-2 border-danger bg-red-50" />
                Broken
              </span>
            </div>
          </div>
          {graph.data?.truncated ? (
            <div className="absolute bottom-3 left-1/2 -translate-x-1/2 rounded border border-amber-300 bg-amber-50 px-3 py-1.5 text-xs font-semibold text-amber-900">
              Граф ограничен backend-фильтром. Уточните focus или тип.
            </div>
          ) : null}
        </section>
      </div>
    </>
  );
}
