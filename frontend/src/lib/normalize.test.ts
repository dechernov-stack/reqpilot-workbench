import { describe, expect, it } from 'vitest';
import {
  normalizeCapellaElement,
  normalizeCapellaStatus,
  normalizeDashboard,
  normalizeDiagnostics,
  normalizeExportJob,
  normalizeGraph,
  normalizeImpact,
  normalizeMatrix,
  normalizeProject,
  normalizeRequirement,
  normalizeRequirementList,
  normalizeTraceLink,
} from './normalize';

describe('API normalizers', () => {
  it('normalizes canonical lower_snake_case requirement without losing unicode or relations', () => {
    const result = normalizeRequirement({
      uid: 'SYS-002',
      mid: 'MID-0002',
      document: '02_system.sdoc',
      node_type: 'REQUIREMENT',
      type: 'System',
      status: 'Approved',
      priority: 'High',
      verification_method: 'Test',
      owner: 'Системный инженер',
      tags: ['pressure', 'safety'],
      title: 'Контроль давления',
      statement: 'Система должна контролировать давление.',
      rationale: 'Строка 1\nСтрока 2 — кириллица',
      acceptance_criteria: 'Порог обнаружен за 100 мс.',
      relations: [{ type: 'Parent', value: 'STK-001', role: 'Refines' }],
      architecture_link_count: 2,
      section_path: ['Функции', 'Контроль'],
      revision: 'rev-7',
    });
    expect(result).toMatchObject({
      uid: 'SYS-002',
      mid: 'MID-0002',
      verificationMethod: 'Test',
      owner: 'Системный инженер',
      rationale: 'Строка 1\nСтрока 2 — кириллица',
      architectureLinkCount: 2,
      revision: 'rev-7',
    });
    expect(result.relations).toEqual([{ type: 'Parent', value: 'STK-001', role: 'Refines' }]);
    expect(result.sectionPath).toEqual(['Функции', 'Контроль']);
  });

  it('accepts StrictDoc uppercase fields and direct arrays', () => {
    const list = normalizeRequirementList([
      { UID: 'TC-001', MID: 'm1', TYPE: 'TestCase', TITLE: 'Проверка', TAGS: 'test, smoke' },
    ]);
    expect(list.total).toBe(1);
    expect(list.items[0]).toMatchObject({
      uid: 'TC-001',
      mid: 'm1',
      type: 'TestCase',
      tags: ['test', 'smoke'],
    });
  });

  it('accepts requirement envelopes', () => {
    const list = normalizeRequirementList({
      items: [{ uid: 'SYS-001', title: 'A' }],
      total: '12',
      revision: 'abc',
    });
    expect(list).toMatchObject({ total: 12, revision: 'abc' });
    expect(list.items[0]?.uid).toBe('SYS-001');
  });

  it('normalizes nested project and Capella status', () => {
    expect(
      normalizeProject({
        project_name: 'Pump',
        strictdoc: { status: 'ok', version: '0.29.0', revision: 'r1' },
        capella: { mode: 'fixture' },
        git: { branch: 'main' },
      }),
    ).toMatchObject({
      name: 'Pump',
      strictdocStatus: 'ok',
      strictdocVersion: '0.29.0',
      capellaMode: 'fixture',
      gitBranch: 'main',
      revision: 'r1',
    });
    expect(
      normalizeCapellaStatus({
        status: 'ok',
        mode: 'live',
        model_name: 'Station',
        element_count: 100,
        diagram_count: 3,
        duration_ms: 19,
      }),
    ).toMatchObject({
      mode: 'live',
      modelName: 'Station',
      elementCount: 100,
      diagramCount: 3,
      durationMs: 19,
    });
  });

  it('normalizes Capella elements and trace links', () => {
    expect(
      normalizeCapellaElement({
        id: 'uuid-1',
        model_id: 'm',
        label: 'Evaluate Pressure Threshold',
        element_type: 'Function',
        breadcrumbs: ['OA', 'Function'],
        requirements: ['SYS-002'],
      }),
    ).toMatchObject({
      uuid: 'uuid-1',
      modelId: 'm',
      name: 'Evaluate Pressure Threshold',
      type: 'Function',
      path: ['OA', 'Function'],
      linkedRequirementUids: ['SYS-002'],
    });
    expect(
      normalizeTraceLink({
        id: 'TL-0001',
        requirement: { uid: 'SYS-002', mid: 'm2' },
        architecture: {
          model_id: 'm',
          uuid: 'uuid-1',
          type: 'Function',
          name_snapshot: 'Evaluate Pressure Threshold',
        },
        relation: 'satisfied_by',
        status: 'broken_architecture',
      }),
    ).toMatchObject({
      id: 'TL-0001',
      requirementUid: 'SYS-002',
      targetUuid: 'uuid-1',
      relation: 'satisfied_by',
      targetTypeSnapshot: 'Function',
      status: 'broken_uuid',
    });
  });

  it('normalizes graph nodes, nested data and broken edges', () => {
    const graph = normalizeGraph({
      nodes: [
        { id: 'SYS-002', data: { label: 'Pressure', kind: 'requirement', type: 'System' } },
        { uuid: 'u1', name: 'Function', kind: 'capella' },
      ],
      edges: [
        { source: 'SYS-002', target: 'u1', data: { relation: 'satisfied_by', broken: true } },
      ],
      truncated: true,
      duration_ms: 7,
    });
    expect(graph.nodes.map((node) => node.id)).toEqual(['SYS-002', 'u1']);
    expect(graph.edges[0]).toMatchObject({ relation: 'satisfied_by', broken: true });
    expect(graph).toMatchObject({ truncated: true, durationMs: 7 });
  });

  it('calculates matrix defaults and reads explicit coverage', () => {
    const calculated = normalizeMatrix({
      rows: [
        { uid: 'SYS-001', title: 'A' },
        { uid: 'SYS-002', title: 'B' },
      ],
      columns: [{ uuid: 'u1', name: 'F' }],
      cells: [{ row_id: 'SYS-002', column_id: 'u1', relations: ['satisfied_by'] }],
      coverage: { numerator: 1, denominator: 2, percent: 50 },
    });
    expect(calculated).toMatchObject({ covered: 1, total: 2, coverage: 50 });
    expect(calculated.cells[0]?.linked).toBe(true);
    expect(
      normalizeMatrix({
        rows: [{ id: 'a' }],
        columns: [{ id: 'b' }],
        coverage: { percent: 0.75, covered: 1, total: 1 },
      }).coverage,
    ).toBe(0.75);
  });

  it('normalizes dashboard and diagnostics', () => {
    const dashboard = normalizeDashboard({
      requirements: 24,
      capella_elements: 42,
      test_coverage: { numerator: 8, denominator: 10, percent: 80 },
      architecture_coverage: { numerator: 1, denominator: 2, percent: 50 },
      broken_links: 2,
      uncovered_test_requirements: ['SYS-003'],
      recent_errors: ['Ошибка'],
    });
    expect(dashboard).toMatchObject({
      requirements: 24,
      capellaElements: 42,
      testCoverage: 80,
      brokenLinks: 2,
      architectureCoverage: 50,
    });
    expect(dashboard.uncoveredRequirements[0]?.uid).toBe('SYS-003');
    const diagnostics = normalizeDiagnostics({
      revision: 'r2',
      diagnostics: [{ source: 'strictdoc', severity: 'error', detail: 'bad' }],
      versions: { strictdoc: '0.29.0' },
      git_dirty: true,
      pdf_available: false,
    });
    expect(diagnostics.items[0]?.message).toBe('bad');
    expect(diagnostics).toMatchObject({
      gitDirty: true,
      pdfAvailable: false,
      tools: { strictdoc: '0.29.0' },
    });
  });

  it('normalizes impact paths, groups and export jobs', () => {
    const impact = normalizeImpact({
      focus: { id: 'SYS-002', label: 'Pressure', source: 'strictdoc', type: 'System' },
      depth: 3,
      groups: [
        {
          key: 'functions',
          label: 'Функции',
          nodes: [{ id: 'u1', label: 'Evaluate', source: 'capella', type: 'Function' }],
        },
      ],
      paths: [{ node_ids: ['SYS-002', 'u1'], edge_ids: ['TL-0001'], length: 1 }],
      broken_links: ['TL-0999'],
    });
    expect(impact.groups[0]).toMatchObject({
      name: 'Функции',
      items: [{ id: 'u1', label: 'Evaluate' }],
    });
    expect(impact.paths[0]?.nodes).toEqual(['SYS-002', 'u1']);
    const job = normalizeExportJob({
      job_id: 'j1',
      format: 'html',
      status: 'completed',
      duration_ms: 25,
      created_files: [
        { id: 'f1', name: 'index.html', sha256: 'abc', size: 10, media_type: 'text/html' },
      ],
    });
    expect(job).toMatchObject({ id: 'j1', status: 'completed', durationMs: 25 });
    expect(job.createdFiles[0]).toMatchObject({ mediaType: 'text/html', name: 'index.html' });
  });
});
