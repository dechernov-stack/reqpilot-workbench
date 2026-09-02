import dagre from '@dagrejs/dagre';
import { MarkerType, type Edge, type Node } from '@xyflow/react';
import type { GraphData, GraphEdge, GraphNode } from './types';

const nodeWidth = 190;
const nodeHeight = 64;

export interface LayoutResult {
  nodes: Node<GraphNode>[];
  edges: Edge[];
}

export function layoutGraph(data: GraphData, direction: 'LR' | 'TB' = 'LR'): LayoutResult {
  const graph = new dagre.graphlib.Graph();
  graph.setDefaultEdgeLabel(() => ({}));
  graph.setGraph({
    rankdir: direction,
    ranksep: 90,
    nodesep: 35,
    marginx: 24,
    marginy: 24,
  });
  data.nodes.forEach((node) => graph.setNode(node.id, { width: nodeWidth, height: nodeHeight }));
  data.edges.forEach((edge) => graph.setEdge(edge.source, edge.target));
  dagre.layout(graph);

  const nodes: Node<GraphNode>[] = data.nodes.map((node) => {
    const position = graph.node(node.id) as { x: number; y: number } | undefined;
    return {
      id: node.id,
      type: 'engineering',
      data: node,
      position: {
        x: (position?.x ?? 0) - nodeWidth / 2,
        y: (position?.y ?? 0) - nodeHeight / 2,
      },
      draggable: true,
    };
  });
  const edges: Edge[] = data.edges.map((edge) => ({
    id: edge.id,
    source: edge.source,
    target: edge.target,
    label: edge.relation,
    type: 'smoothstep',
    animated: false,
    style: { stroke: edge.broken ? '#ae2e24' : '#778696', strokeWidth: edge.broken ? 2 : 1.25 },
    labelStyle: { fill: '#526274', fontSize: 10, fontWeight: 600 },
    labelBgStyle: { fill: '#f8fafc', fillOpacity: 0.92 },
    markerEnd: { type: MarkerType.ArrowClosed, color: edge.broken ? '#ae2e24' : '#778696' },
  }));
  return { nodes, edges };
}

export interface PathResult {
  nodeIds: string[];
  edgeIds: string[];
}

export function shortestPath(data: GraphData, source: string, target: string): PathResult | null {
  if (!source || !target) return null;
  if (source === target) return { nodeIds: [source], edgeIds: [] };
  const adjacency = new Map<string, Array<{ node: string; edge: GraphEdge }>>();
  data.edges.forEach((edge) => {
    adjacency.set(edge.source, [
      ...(adjacency.get(edge.source) ?? []),
      { node: edge.target, edge },
    ]);
    adjacency.set(edge.target, [
      ...(adjacency.get(edge.target) ?? []),
      { node: edge.source, edge },
    ]);
  });
  adjacency.forEach((items) =>
    items.sort((a, b) => a.node.localeCompare(b.node) || a.edge.id.localeCompare(b.edge.id)),
  );
  const queue = [source];
  const visited = new Set([source]);
  const previous = new Map<string, { node: string; edgeId: string }>();
  while (queue.length) {
    const current = queue.shift();
    if (!current) break;
    for (const next of adjacency.get(current) ?? []) {
      if (visited.has(next.node)) continue;
      visited.add(next.node);
      previous.set(next.node, { node: current, edgeId: next.edge.id });
      if (next.node === target) {
        const nodeIds = [target];
        const edgeIds: string[] = [];
        let cursor = target;
        while (cursor !== source) {
          const step = previous.get(cursor);
          if (!step) return null;
          edgeIds.unshift(step.edgeId);
          nodeIds.unshift(step.node);
          cursor = step.node;
        }
        return { nodeIds, edgeIds };
      }
      queue.push(next.node);
    }
  }
  return null;
}

function escapeXml(value: string): string {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;');
}

export function graphToSvg(data: GraphData): string {
  const layout = layoutGraph(data);
  const maxX = Math.max(800, ...layout.nodes.map((node) => node.position.x + nodeWidth + 30));
  const maxY = Math.max(500, ...layout.nodes.map((node) => node.position.y + nodeHeight + 30));
  const positions = new Map(layout.nodes.map((node) => [node.id, node.position]));
  const edgeSvg = data.edges
    .map((edge) => {
      const start = positions.get(edge.source);
      const end = positions.get(edge.target);
      if (!start || !end) return '';
      const x1 = start.x + nodeWidth;
      const y1 = start.y + nodeHeight / 2;
      const x2 = end.x;
      const y2 = end.y + nodeHeight / 2;
      return `<g><line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${edge.broken ? '#ae2e24' : '#778696'}" stroke-width="${edge.broken ? 2 : 1.25}" marker-end="url(#arrow)"/><text x="${(x1 + x2) / 2}" y="${(y1 + y2) / 2 - 5}" text-anchor="middle" font-size="10" fill="#526274">${escapeXml(edge.relation)}</text></g>`;
    })
    .join('');
  const nodeSvg = layout.nodes
    .map((node) => {
      const item = node.data;
      const shape =
        item.kind === 'capella'
          ? 'rx="2"'
          : item.kind === 'test'
            ? 'rx="18"'
            : item.kind === 'broken'
              ? 'rx="0"'
              : 'rx="7"';
      const stroke =
        item.kind === 'broken'
          ? '#ae2e24'
          : item.kind === 'capella'
            ? '#6b4f9b'
            : item.kind === 'test'
              ? '#24734a'
              : '#0d7180';
      const title = item.label.length > 27 ? `${item.label.slice(0, 26)}…` : item.label;
      return `<g transform="translate(${node.position.x},${node.position.y})"><rect width="${nodeWidth}" height="${nodeHeight}" ${shape} fill="#fff" stroke="${stroke}" stroke-width="2"/><text x="12" y="24" font-size="12" font-weight="700" fill="#172033">${escapeXml(title)}</text><text x="12" y="45" font-size="10" fill="#526274">${escapeXml(item.type)}</text></g>`;
    })
    .join('');
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${maxX}" height="${maxY}" viewBox="0 0 ${maxX} ${maxY}"><defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 Z" fill="#778696"/></marker></defs><rect width="100%" height="100%" fill="#f4f6f8"/>${edgeSvg}${nodeSvg}</svg>`;
}

export async function graphSvgToPng(svg: string): Promise<Blob> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    const blob = new Blob([svg], { type: 'image/svg+xml;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    image.onload = () => {
      try {
        const canvas = document.createElement('canvas');
        canvas.width = Math.min(image.naturalWidth || 1600, 4096);
        canvas.height = Math.min(image.naturalHeight || 1000, 4096);
        const context = canvas.getContext('2d');
        if (!context) throw new Error('Canvas 2D недоступен');
        context.fillStyle = '#f4f6f8';
        context.fillRect(0, 0, canvas.width, canvas.height);
        context.drawImage(image, 0, 0, canvas.width, canvas.height);
        canvas.toBlob((png) => {
          URL.revokeObjectURL(url);
          if (png) resolve(png);
          else reject(new Error('PNG не сформирован'));
        }, 'image/png');
      } catch (error) {
        URL.revokeObjectURL(url);
        reject(error instanceof Error ? error : new Error('PNG не сформирован'));
      }
    };
    image.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error('SVG не загружен в canvas'));
    };
    image.src = url;
  });
}
