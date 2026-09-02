import type {
  CapellaElement,
  CapellaStatus,
  DashboardData,
  Diagnostic,
  DiagnosticsData,
  Diagram,
  ExportFile,
  ExportJob,
  GraphData,
  GraphEdge,
  GraphNode,
  ImpactData,
  ImpactGroup,
  ImpactPath,
  MatrixCell,
  MatrixData,
  MatrixItem,
  ProjectInfo,
  Relation,
  Requirement,
  RequirementList,
  TraceLink,
} from './types';

type UnknownRecord = Record<string, unknown>;

export function asRecord(value: unknown): UnknownRecord {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
    ? (value as UnknownRecord)
    : {};
}

export function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

export function pick(record: UnknownRecord, ...keys: string[]): unknown {
  for (const key of keys) {
    if (record[key] !== undefined && record[key] !== null) return record[key];
  }
  return undefined;
}

export function textValue(value: unknown, fallback = ''): string {
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  return fallback;
}

export function numberValue(value: unknown, fallback = 0): number {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string') {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return fallback;
}

export function booleanValue(value: unknown, fallback = false): boolean {
  if (typeof value === 'boolean') return value;
  if (value === 'true' || value === 1) return true;
  if (value === 'false' || value === 0) return false;
  return fallback;
}

export function stringArray(value: unknown): string[] {
  if (Array.isArray(value)) return value.map((item) => textValue(item)).filter(Boolean);
  if (typeof value === 'string') {
    return value
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean);
  }
  return [];
}

export function normalizeRelation(value: unknown): Relation {
  const record = asRecord(value);
  return {
    type: textValue(pick(record, 'type', 'TYPE')),
    value: textValue(pick(record, 'value', 'VALUE', 'uid', 'target')),
    role: textValue(pick(record, 'role', 'ROLE', 'relation')),
  };
}

export function normalizeRequirement(value: unknown): Requirement {
  const record = asRecord(value);
  return {
    uid: textValue(pick(record, 'uid', 'UID')),
    mid: textValue(pick(record, 'mid', 'MID')),
    document: textValue(pick(record, 'document', 'document_path', 'DOCUMENT')),
    nodeType: textValue(pick(record, 'node_type', 'nodeType', '_NODE_TYPE'), 'REQUIREMENT'),
    type: textValue(pick(record, 'type', 'TYPE'), 'Requirement'),
    status: textValue(pick(record, 'status', 'STATUS'), 'Draft'),
    priority: textValue(pick(record, 'priority', 'PRIORITY'), 'Medium'),
    verificationMethod: textValue(
      pick(record, 'verification_method', 'verificationMethod', 'VERIFICATION_METHOD'),
    ),
    owner: textValue(pick(record, 'owner', 'OWNER')),
    source: textValue(pick(record, 'source', 'SOURCE')),
    tags: stringArray(pick(record, 'tags', 'TAGS')),
    title: textValue(pick(record, 'title', 'TITLE')),
    statement: textValue(pick(record, 'statement', 'STATEMENT')),
    rationale: textValue(pick(record, 'rationale', 'RATIONALE')),
    acceptanceCriteria: textValue(
      pick(record, 'acceptance_criteria', 'acceptanceCriteria', 'ACCEPTANCE_CRITERIA'),
    ),
    comment: textValue(pick(record, 'comment', 'COMMENT')),
    relations: asArray(pick(record, 'relations', 'RELATIONS')).map(normalizeRelation),
    revision: textValue(pick(record, 'revision', 'etag', '_revision')),
    sectionPath: stringArray(pick(record, 'section_path', 'sectionPath', 'sections')),
    architectureLinkCount: numberValue(
      pick(record, 'architecture_link_count', 'architectureLinkCount', 'trace_link_count'),
    ),
  };
}

export function normalizeRequirementList(value: unknown): RequirementList {
  if (Array.isArray(value)) {
    const items = value.map(normalizeRequirement);
    return { items, total: items.length, revision: items[0]?.revision ?? '' };
  }
  const record = asRecord(value);
  const items = asArray(pick(record, 'items', 'requirements', 'data')).map(normalizeRequirement);
  return {
    items,
    total: numberValue(record.total, items.length),
    revision: textValue(pick(record, 'revision', 'etag')),
  };
}

export function normalizeProject(value: unknown): ProjectInfo {
  const record = asRecord(value);
  const strictdoc = asRecord(record.strictdoc);
  const capella = asRecord(record.capella);
  const git = asRecord(record.git);
  const rawMode = textValue(pick(record, 'capella_mode', 'capellaMode', 'mode') ?? capella.mode);
  const capellaMode = ['disabled', 'fixture', 'live'].includes(rawMode) ? rawMode : 'disabled';
  return {
    name: textValue(
      pick(record, 'name', 'project_name', 'title'),
      'ReqPilot Engineering Workbench',
    ),
    root: textValue(pick(record, 'root', 'project_root') ?? strictdoc.root),
    revision: textValue(pick(record, 'revision') ?? strictdoc.revision),
    strictdocStatus: textValue(
      pick(record, 'strictdoc_status') ?? strictdoc.status,
      'unknown',
    ) as ProjectInfo['strictdocStatus'],
    strictdocVersion: textValue(pick(record, 'strictdoc_version') ?? strictdoc.version),
    capellaMode: capellaMode as ProjectInfo['capellaMode'],
    strictdocUrl: textValue(pick(record, 'strictdoc_url') ?? strictdoc.url),
    gitBranch: textValue(pick(record, 'git_branch') ?? git.branch),
  };
}

export function normalizeCapellaStatus(value: unknown): CapellaStatus {
  const record = asRecord(value);
  const rawMode = textValue(pick(record, 'mode', 'capella_mode'), 'disabled');
  const mode = ['disabled', 'fixture', 'live'].includes(rawMode) ? rawMode : 'disabled';
  return {
    status: textValue(
      pick(record, 'status', 'state'),
      mode === 'disabled' ? 'unknown' : 'ok',
    ) as CapellaStatus['status'],
    mode: mode as CapellaStatus['mode'],
    modelName: textValue(pick(record, 'model_name', 'modelName', 'name')),
    modelPath: textValue(pick(record, 'model_path', 'modelPath', 'path')),
    modelId: textValue(pick(record, 'model_id', 'modelId')),
    elementCount: numberValue(pick(record, 'element_count', 'elementCount', 'elements')),
    diagramCount: numberValue(pick(record, 'diagram_count', 'diagramCount', 'diagrams')),
    loadedAt: textValue(pick(record, 'loaded_at', 'loadedAt')),
    durationMs: numberValue(pick(record, 'duration_ms', 'durationMs', 'indexed_duration_ms')),
    errors: stringArray(record.errors),
    version: textValue(pick(record, 'version', 'capellambse_version')),
  };
}

export function normalizeCapellaElement(value: unknown): CapellaElement {
  const record = asRecord(value);
  const related = stringArray(pick(record, 'related_element_uuids', 'relatedElementUuids'));
  return {
    uuid: textValue(pick(record, 'uuid', 'id')),
    modelId: textValue(pick(record, 'model_id', 'modelId')),
    name: textValue(pick(record, 'name', 'label'), 'Без имени'),
    type: textValue(pick(record, 'type', 'element_type', 'elementType'), 'Element'),
    layer: textValue(pick(record, 'layer', 'architecture_layer', 'architectureLayer')),
    description: textValue(pick(record, 'description', 'summary')),
    parentUuid: textValue(pick(record, 'parent_uuid', 'parentUuid', 'parent')),
    path: stringArray(pick(record, 'path', 'breadcrumbs')),
    relations: [
      ...asArray(record.relations).map(normalizeRelation),
      ...related.map((uuid) => ({
        type: 'Architecture',
        value: uuid,
        role: 'related_to',
      })),
    ],
    linkedRequirementUids: stringArray(
      pick(record, 'linked_requirement_uids', 'linkedRequirementUids', 'requirements'),
    ),
  };
}

export function normalizeCapellaElements(value: unknown): CapellaElement[] {
  if (Array.isArray(value)) return value.map(normalizeCapellaElement);
  const record = asRecord(value);
  return asArray(pick(record, 'items', 'elements', 'data')).map(normalizeCapellaElement);
}

export function normalizeDiagram(value: unknown): Diagram {
  const record = asRecord(value);
  return {
    uuid: textValue(pick(record, 'uuid', 'id')),
    name: textValue(pick(record, 'name', 'label'), 'Диаграмма'),
    type: textValue(pick(record, 'type', 'diagram_type', 'diagramType')),
    representedElementUuids: stringArray(
      pick(record, 'represented_element_uuids', 'representedElementUuids', 'elements'),
    ),
  };
}

export function normalizeDiagrams(value: unknown): Diagram[] {
  if (Array.isArray(value)) return value.map(normalizeDiagram);
  const record = asRecord(value);
  return asArray(pick(record, 'items', 'diagrams', 'data')).map(normalizeDiagram);
}

export function normalizeTraceLink(value: unknown): TraceLink {
  const record = asRecord(value);
  const requirement = asRecord(record.requirement);
  const architecture = asRecord(record.architecture);
  const rawStatus = textValue(record.status, 'valid');
  const normalizedStatus =
    rawStatus === 'broken_requirement'
      ? 'broken_uid'
      : rawStatus === 'broken_architecture'
        ? 'broken_uuid'
        : rawStatus;
  return {
    id: textValue(pick(record, 'id', 'link_id', 'linkId')),
    requirementUid: textValue(
      pick(record, 'requirement_uid', 'requirementUid', 'uid') ?? requirement.uid,
    ),
    requirementMid: textValue(
      pick(record, 'requirement_mid', 'requirementMid', 'mid') ?? requirement.mid,
    ),
    modelId: textValue(pick(record, 'model_id', 'modelId') ?? architecture.model_id),
    targetUuid: textValue(pick(record, 'target_uuid', 'targetUuid', 'uuid') ?? architecture.uuid),
    relation: textValue(pick(record, 'relation', 'role'), 'satisfied_by'),
    targetNameSnapshot: textValue(
      pick(record, 'target_name_snapshot', 'targetNameSnapshot', 'target_name') ??
        architecture.name_snapshot,
    ),
    targetTypeSnapshot: textValue(
      pick(record, 'target_type_snapshot', 'targetTypeSnapshot', 'target_type') ??
        architecture.type,
    ),
    status: normalizedStatus,
    revision: textValue(record.revision),
  };
}

export function normalizeTraceLinks(value: unknown): TraceLink[] {
  if (Array.isArray(value)) return value.map(normalizeTraceLink);
  const record = asRecord(value);
  const revision = textValue(record.revision);
  return asArray(pick(record, 'items', 'links', 'data')).map((item) => {
    const link = normalizeTraceLink(item);
    return link.revision || !revision ? link : { ...link, revision };
  });
}

export function normalizeGraph(value: unknown): GraphData {
  const record = asRecord(value);
  const nodes: GraphNode[] = asArray(record.nodes).map((item) => {
    const node = asRecord(item);
    const data = asRecord(node.data);
    const source = textValue(pick(node, 'source') ?? data.source);
    const rawKind = textValue(pick(node, 'kind') ?? data.kind);
    const type = textValue(pick(node, 'type') ?? data.type);
    const kind =
      rawKind ||
      (source === 'capella'
        ? 'capella'
        : source === 'placeholder'
          ? 'broken'
          : type === 'TestCase'
            ? 'test'
            : 'requirement');
    return {
      id: textValue(pick(node, 'id', 'uid', 'uuid')),
      label: textValue(pick(node, 'label', 'name', 'title') ?? data.label, 'Без имени'),
      kind,
      type,
      group: textValue(pick(node, 'group', 'layer') ?? data.group),
      status: booleanValue(pick(node, 'broken') ?? data.broken)
        ? 'broken'
        : textValue(pick(node, 'status') ?? data.status),
      metadata: asRecord(pick(node, 'metadata', 'data')),
    };
  });
  const edges: GraphEdge[] = asArray(record.edges).map((item, index) => {
    const edge = asRecord(item);
    const data = asRecord(edge.data);
    const source = textValue(edge.source);
    const target = textValue(edge.target);
    const relation = textValue(pick(edge, 'relation', 'type', 'label') ?? data.relation);
    return {
      id: textValue(edge.id, `${source}:${relation}:${target}:${index}`),
      source,
      target,
      relation,
      sourceKind: textValue(pick(edge, 'source_kind', 'sourceKind', 'origin') ?? data.sourceKind),
      broken: booleanValue(pick(edge, 'broken') ?? data.broken),
    };
  });
  return {
    nodes,
    edges,
    truncated: booleanValue(record.truncated),
    durationMs: numberValue(pick(record, 'duration_ms', 'durationMs')),
  };
}

function normalizeMatrixItem(value: unknown): MatrixItem {
  const record = asRecord(value);
  return {
    id: textValue(pick(record, 'id', 'uid', 'uuid')),
    label: textValue(pick(record, 'label', 'name', 'title', 'uid'), 'Без имени'),
    type: textValue(record.type),
    status: textValue(record.status),
  };
}

export function normalizeMatrix(value: unknown): MatrixData {
  const record = asRecord(value);
  const rows = asArray(pick(record, 'rows', 'requirements', 'functions')).map(normalizeMatrixItem);
  const columns = asArray(pick(record, 'columns', 'tests', 'components')).map(normalizeMatrixItem);
  const rawCells = asArray(pick(record, 'cells', 'links', 'entries'));
  const cells: MatrixCell[] = rawCells.map((item) => {
    const cell = asRecord(item);
    return {
      rowId: textValue(pick(cell, 'row_id', 'rowId', 'source')),
      columnId: textValue(pick(cell, 'column_id', 'columnId', 'target')),
      linked: booleanValue(pick(cell, 'linked', 'value'), true),
      relation: textValue(pick(cell, 'relation', 'role')) || stringArray(cell.relations).join(', '),
      linkIds: stringArray(pick(cell, 'link_ids', 'linkIds', 'ids')),
    };
  });
  const coverageRecord = asRecord(record.coverage);
  const total = numberValue(
    pick(record, 'total') ?? coverageRecord.total ?? coverageRecord.denominator,
    rows.length,
  );
  const covered = numberValue(
    pick(record, 'covered') ?? coverageRecord.covered ?? coverageRecord.numerator,
    new Set(cells.filter((cell) => cell.linked).map((cell) => cell.rowId)).size,
  );
  const directCoverage = record.coverage;
  const coverageRaw = numberValue(
    pick(record, 'coverage_percent') ??
      (typeof directCoverage === 'number' || typeof directCoverage === 'string'
        ? directCoverage
        : coverageRecord.percent),
    total === 0 ? 0 : (covered / total) * 100,
  );
  return {
    rows,
    columns,
    cells,
    coverage: coverageRaw <= 1 && total > 1 ? coverageRaw * 100 : coverageRaw,
    covered,
    total,
  };
}

function normalizeDiagnostic(value: unknown, index: number): Diagnostic {
  const record = asRecord(value);
  return {
    id: textValue(record.id, `diagnostic-${index}`),
    source: textValue(pick(record, 'source', 'component'), 'system'),
    severity: textValue(pick(record, 'severity', 'level'), 'info'),
    code: textValue(record.code),
    message: textValue(pick(record, 'message', 'detail', 'error')),
    path: textValue(pick(record, 'path', 'file')),
    timestamp: textValue(pick(record, 'timestamp', 'created_at', 'createdAt')),
  };
}

export function normalizeDiagnostics(value: unknown): DiagnosticsData {
  const record = asRecord(value);
  const strictdoc = asRecord(record.strictdoc);
  const itemSource = pick(record, 'items', 'diagnostics', 'errors') ?? strictdoc.diagnostics;
  const toolsRecord = {
    ...asRecord(pick(record, 'tools', 'versions')),
    ...(strictdoc.version ? { strictdoc: strictdoc.version } : {}),
  };
  return {
    revision: textValue(record.revision),
    items: asArray(itemSource).map(normalizeDiagnostic),
    tools: Object.fromEntries(
      Object.entries(toolsRecord).map(([key, item]) => [key, textValue(item)]),
    ),
    gitDirty: booleanValue(pick(record, 'git_dirty', 'gitDirty')),
    staleCache: booleanValue(pick(record, 'stale_cache', 'staleCache')),
    pdfAvailable: booleanValue(pick(record, 'pdf_available', 'pdfAvailable')),
    chromeDriver: textValue(pick(record, 'chromedriver', 'chrome_driver', 'chromeDriver')),
  };
}

export function normalizeDashboard(value: unknown): DashboardData {
  const record = asRecord(value);
  const coveragePercent = (input: unknown): number => {
    const coverage = asRecord(input);
    return numberValue(coverage.percent, numberValue(input));
  };
  const uncoveredIds = [
    ...stringArray(pick(record, 'uncovered_test_requirements')),
    ...stringArray(pick(record, 'uncovered_architecture_requirements')),
  ];
  const uncoveredRaw = asArray(pick(record, 'uncovered_requirements', 'uncoveredRequirements'));
  const recentRaw = asArray(pick(record, 'recent_errors', 'recentErrors'));
  const gitStatus = textValue(pick(record, 'git_status', 'gitStatus'));
  return {
    requirements: numberValue(pick(record, 'requirements', 'requirement_count')),
    capellaElements: numberValue(pick(record, 'capella_elements', 'capellaElements')),
    internalRelations: numberValue(pick(record, 'internal_relations', 'internalRelations')),
    traceLinks: numberValue(pick(record, 'trace_links', 'traceLinks')),
    testCoverage: coveragePercent(pick(record, 'test_coverage', 'testCoverage')),
    architectureCoverage: coveragePercent(
      pick(record, 'architecture_coverage', 'architectureCoverage'),
    ),
    brokenLinks: numberValue(pick(record, 'broken_links', 'brokenLinks')),
    indexDurationMs: numberValue(
      pick(record, 'index_duration_ms', 'indexDurationMs', 'indexing_duration_ms'),
    ),
    gitDirty:
      booleanValue(pick(record, 'git_dirty', 'gitDirty')) ||
      gitStatus.toLowerCase().includes('dirty'),
    gitBranch: textValue(pick(record, 'git_branch', 'gitBranch'), gitStatus),
    lastExport: textValue(pick(record, 'last_export', 'lastExport')),
    uncoveredRequirements: [
      ...uncoveredRaw.map(normalizeRequirement),
      ...uncoveredIds.map((uid) => normalizeRequirement({ uid, title: uid })),
    ].filter(
      (item, index, items) => items.findIndex((candidate) => candidate.uid === item.uid) === index,
    ),
    recentErrors: recentRaw.map((item, index) =>
      typeof item === 'string'
        ? normalizeDiagnostic({ message: item, severity: 'error' }, index)
        : normalizeDiagnostic(item, index),
    ),
  };
}

function normalizeImpactItem(value: unknown): MatrixItem {
  const direct = normalizeMatrixItem(value);
  if (direct.id) return direct;
  const node = normalizeGraph({ nodes: [value], edges: [] }).nodes[0];
  return node ? { id: node.id, label: node.label, type: node.type, status: node.status } : direct;
}

export function normalizeImpact(value: unknown): ImpactData {
  const record = asRecord(value);
  const root = normalizeImpactItem(pick(record, 'root', 'subject', 'focus'));
  const groups: ImpactGroup[] = Array.isArray(record.groups)
    ? record.groups.map((item) => {
        const group = asRecord(item);
        return {
          name: textValue(pick(group, 'name', 'type', 'label', 'key')),
          items: asArray(pick(group, 'items', 'nodes')).map(normalizeImpactItem),
        };
      })
    : Object.entries(asRecord(record.groups)).map(([name, items]) => ({
        name,
        items: asArray(items).map(normalizeImpactItem),
      }));
  const paths: ImpactPath[] = asArray(record.paths).map((item) => {
    const path = asRecord(item);
    return {
      nodes: stringArray(path.nodes ?? path.node_ids),
      relations: stringArray(path.relations ?? path.edge_ids),
      summary: textValue(
        path.summary,
        `Кратчайший путь: ${numberValue(path.length, stringArray(path.node_ids).length - 1)} рёбер`,
      ),
    };
  });
  return {
    root,
    depth: numberValue(record.depth, 3),
    groups,
    paths,
    brokenLinks: asArray(pick(record, 'broken_links', 'brokenLinks')).map((item) =>
      typeof item === 'string'
        ? normalizeTraceLink({ id: item, status: 'broken_uuid', target_uuid: item })
        : normalizeTraceLink(item),
    ),
  };
}

function normalizeExportFile(value: unknown): ExportFile {
  const record = asRecord(value);
  return {
    id: textValue(record.id),
    name: textValue(record.name),
    path: textValue(record.path),
    sha256: textValue(record.sha256),
    size: numberValue(record.size),
    mediaType: textValue(pick(record, 'media_type', 'mediaType'), 'application/octet-stream'),
  };
}

export function normalizeExportJob(value: unknown): ExportJob {
  const record = asRecord(value);
  return {
    id: textValue(pick(record, 'id', 'job_id', 'jobId')),
    format: textValue(record.format),
    status: textValue(record.status, 'queued'),
    stdout: textValue(record.stdout),
    stderr: textValue(record.stderr),
    durationMs: numberValue(pick(record, 'duration_ms', 'durationMs')),
    createdFiles: asArray(pick(record, 'created_files', 'createdFiles', 'files')).map(
      normalizeExportFile,
    ),
    error: textValue(record.error),
  };
}
