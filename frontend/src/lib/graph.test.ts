import { describe, expect, it } from 'vitest';
import { graphToSvg, layoutGraph, shortestPath } from './graph';
import type { GraphData } from './types';

const graph: GraphData = {
  nodes: [
    {
      id: 'A',
      label: 'Требование <A>',
      kind: 'requirement',
      type: 'System',
      group: 'requirements',
      status: '',
      metadata: {},
    },
    {
      id: 'B',
      label: 'Function B',
      kind: 'capella',
      type: 'Function',
      group: 'functions',
      status: '',
      metadata: {},
    },
    {
      id: 'C',
      label: 'Test C',
      kind: 'test',
      type: 'TestCase',
      group: 'tests',
      status: '',
      metadata: {},
    },
    {
      id: 'D',
      label: 'Orphan',
      kind: 'broken',
      type: 'Placeholder',
      group: 'broken',
      status: 'broken',
      metadata: {},
    },
  ],
  edges: [
    {
      id: 'e2',
      source: 'A',
      target: 'B',
      relation: 'satisfied_by',
      sourceKind: 'trace',
      broken: false,
    },
    {
      id: 'e1',
      source: 'B',
      target: 'C',
      relation: 'verified_by',
      sourceKind: 'trace',
      broken: false,
    },
    {
      id: 'cycle',
      source: 'C',
      target: 'A',
      relation: 'related',
      sourceKind: 'internal',
      broken: false,
    },
  ],
  truncated: false,
  durationMs: 2,
};

describe('graph business logic', () => {
  it('finds deterministic shortest paths and handles cycles', () => {
    const result = shortestPath(graph, 'A', 'C');
    expect(result).toEqual({ nodeIds: ['A', 'C'], edgeIds: ['cycle'] });
    expect(shortestPath(graph, 'A', 'A')).toEqual({ nodeIds: ['A'], edgeIds: [] });
  });

  it('returns null for invalid or disconnected endpoints', () => {
    expect(shortestPath(graph, '', 'A')).toBeNull();
    expect(shortestPath(graph, 'A', 'D')).toBeNull();
    expect(shortestPath(graph, 'missing', 'D')).toBeNull();
  });

  it('lays out every node and edge in both orientations', () => {
    const horizontal = layoutGraph(graph, 'LR');
    const vertical = layoutGraph(graph, 'TB');
    expect(horizontal.nodes).toHaveLength(4);
    expect(horizontal.edges).toHaveLength(3);
    expect(horizontal.nodes.every((node) => Number.isFinite(node.position.x))).toBe(true);
    expect(vertical.nodes.find((node) => node.id === 'A')?.position).not.toEqual(
      horizontal.nodes.find((node) => node.id === 'A')?.position,
    );
  });

  it('creates standalone escaped SVG with semantic node shapes', () => {
    const svg = graphToSvg(graph);
    expect(svg).toMatch(/^<svg/);
    expect(svg).toContain('Требование &lt;A&gt;');
    expect(svg).toContain('satisfied_by');
    expect(svg).not.toContain('Требование <A>');
  });
});
