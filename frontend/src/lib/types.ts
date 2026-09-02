export type HealthStatus = 'ok' | 'degraded' | 'error' | 'unknown';
export type CapellaMode = 'disabled' | 'fixture' | 'live';

export interface Relation {
  type: string;
  value: string;
  role: string;
}

export interface Requirement {
  uid: string;
  mid: string;
  document: string;
  nodeType: string;
  type: string;
  status: string;
  priority: string;
  verificationMethod: string;
  owner: string;
  source: string;
  tags: string[];
  title: string;
  statement: string;
  rationale: string;
  acceptanceCriteria: string;
  comment: string;
  relations: Relation[];
  revision: string;
  sectionPath: string[];
  architectureLinkCount: number;
}

export interface RequirementList {
  items: Requirement[];
  total: number;
  revision: string;
}

export type RequirementInput = Omit<
  Requirement,
  'mid' | 'revision' | 'sectionPath' | 'architectureLinkCount'
> & {
  mid?: string;
  revision?: string;
};

export interface ProjectInfo {
  name: string;
  root: string;
  revision: string;
  strictdocStatus: HealthStatus;
  strictdocVersion: string;
  capellaMode: CapellaMode;
  strictdocUrl: string;
  gitBranch: string;
}

export interface CapellaStatus {
  status: HealthStatus;
  mode: CapellaMode;
  modelName: string;
  modelPath: string;
  modelId: string;
  elementCount: number;
  diagramCount: number;
  loadedAt: string;
  durationMs: number;
  errors: string[];
  version: string;
}

export interface CapellaElement {
  uuid: string;
  modelId: string;
  name: string;
  type: string;
  layer: string;
  description: string;
  parentUuid: string;
  path: string[];
  relations: Relation[];
  linkedRequirementUids: string[];
}

export interface Diagram {
  uuid: string;
  name: string;
  type: string;
  representedElementUuids: string[];
}

export type TraceRelation = string;

export interface TraceLink {
  id: string;
  requirementUid: string;
  requirementMid: string;
  modelId: string;
  targetUuid: string;
  relation: TraceRelation;
  targetNameSnapshot: string;
  targetTypeSnapshot: string;
  status: string;
  revision: string;
}

export interface TraceLinkInput {
  requirement_uid: string;
  requirement_mid?: string;
  model_id: string;
  target_uuid: string;
  target_type?: string;
  target_name?: string;
  relation: TraceRelation;
  rationale?: string;
  revision?: string;
}

export interface GraphNode {
  [key: string]: unknown;
  id: string;
  label: string;
  kind: string;
  type: string;
  group: string;
  status: string;
  metadata: Record<string, unknown>;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  relation: string;
  sourceKind: string;
  broken: boolean;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
  truncated: boolean;
  durationMs: number;
}

export interface MatrixItem {
  id: string;
  label: string;
  type: string;
  status: string;
}

export interface MatrixCell {
  rowId: string;
  columnId: string;
  linked: boolean;
  relation: string;
  linkIds: string[];
}

export interface MatrixData {
  rows: MatrixItem[];
  columns: MatrixItem[];
  cells: MatrixCell[];
  coverage: number;
  covered: number;
  total: number;
}

export interface ImpactPath {
  nodes: string[];
  relations: string[];
  summary: string;
}

export interface ImpactGroup {
  name: string;
  items: MatrixItem[];
}

export interface ImpactData {
  root: MatrixItem;
  depth: number;
  groups: ImpactGroup[];
  paths: ImpactPath[];
  brokenLinks: TraceLink[];
}

export interface DashboardData {
  requirements: number;
  capellaElements: number;
  internalRelations: number;
  traceLinks: number;
  testCoverage: number;
  architectureCoverage: number;
  brokenLinks: number;
  indexDurationMs: number;
  gitDirty: boolean;
  gitBranch: string;
  lastExport: string;
  uncoveredRequirements: Requirement[];
  recentErrors: Diagnostic[];
}

export interface Diagnostic {
  id: string;
  source: string;
  severity: string;
  code: string;
  message: string;
  path: string;
  timestamp: string;
}

export interface DiagnosticsData {
  revision: string;
  items: Diagnostic[];
  tools: Record<string, string>;
  gitDirty: boolean;
  staleCache: boolean;
  pdfAvailable: boolean;
  chromeDriver: string;
}

export interface ExportFile {
  id: string;
  name: string;
  path: string;
  sha256: string;
  size: number;
  mediaType: string;
}

export interface ExportJob {
  id: string;
  format: string;
  status: string;
  stdout: string;
  stderr: string;
  durationMs: number;
  createdFiles: ExportFile[];
  error: string;
}

export interface ApiErrorShape {
  code: string;
  message: string;
  diagnostics: Diagnostic[];
  status: number;
}
