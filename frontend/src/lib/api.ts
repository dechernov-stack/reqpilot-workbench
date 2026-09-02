import {
  asArray,
  asRecord,
  normalizeCapellaElement,
  normalizeCapellaElements,
  normalizeCapellaStatus,
  normalizeDashboard,
  normalizeDiagnostics,
  normalizeDiagrams,
  normalizeExportJob,
  normalizeGraph,
  normalizeImpact,
  normalizeMatrix,
  normalizeProject,
  normalizeRequirement,
  normalizeRequirementList,
  normalizeTraceLink,
  normalizeTraceLinks,
  pick,
  textValue,
} from './normalize';
import type {
  ApiErrorShape,
  CapellaElement,
  CapellaStatus,
  DashboardData,
  DiagnosticsData,
  Diagram,
  ExportJob,
  GraphData,
  ImpactData,
  MatrixData,
  ProjectInfo,
  Requirement,
  RequirementInput,
  RequirementList,
  TraceLink,
  TraceLinkInput,
} from './types';

const API_ROOT = '/api';

export class ApiError extends Error implements ApiErrorShape {
  readonly code: string;
  readonly diagnostics: ApiErrorShape['diagnostics'];
  readonly status: number;

  constructor(shape: ApiErrorShape) {
    super(shape.message);
    this.name = 'ApiError';
    this.code = shape.code;
    this.diagnostics = shape.diagnostics;
    this.status = shape.status;
  }
}

function normalizeErrorBody(value: unknown, status: number): ApiErrorShape {
  const body = asRecord(value);
  const detail = asRecord(body.detail);
  const source = Object.keys(detail).length > 0 ? detail : body;
  const diagnostics = asArray(source.diagnostics).map((item, index) => {
    const diagnostic = asRecord(item);
    return {
      id: textValue(diagnostic.id, `api-error-${index}`),
      source: textValue(diagnostic.source, 'api'),
      severity: textValue(diagnostic.severity, 'error'),
      code: textValue(diagnostic.code),
      message: textValue(pick(diagnostic, 'message', 'detail')),
      path: textValue(diagnostic.path),
      timestamp: textValue(diagnostic.timestamp),
    };
  });
  return {
    code: textValue(source.code, `HTTP_${status}`),
    message: textValue(
      pick(source, 'message', 'detail', 'error'),
      `Сервер вернул ошибку ${status}`,
    ),
    diagnostics,
    status,
  };
}

async function apiFetch(path: string, init?: RequestInit): Promise<unknown> {
  const headers = new Headers(init?.headers);
  if (init?.body !== undefined && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }
  headers.set('Accept', 'application/json');
  let response: Response;
  try {
    response = await fetch(`${API_ROOT}${path}`, { ...init, headers });
  } catch (error) {
    throw new ApiError({
      code: 'NETWORK_ERROR',
      message: error instanceof Error ? error.message : 'Backend недоступен',
      diagnostics: [],
      status: 0,
    });
  }

  const contentType = response.headers.get('content-type') ?? '';
  const payload: unknown =
    response.status === 204
      ? null
      : contentType.includes('json')
        ? await response.json()
        : await response.text();

  if (!response.ok) throw new ApiError(normalizeErrorBody(payload, response.status));
  return payload;
}

function params(values: Record<string, string | number | boolean | undefined>): string {
  const result = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => {
    if (value !== undefined && value !== '') result.set(key, String(value));
  });
  const query = result.toString();
  return query ? `?${query}` : '';
}

export function requirementToUpdatePayload(input: RequirementInput): Record<string, unknown> {
  return {
    type: input.type,
    status: input.status,
    priority: input.priority,
    verification_method: input.verificationMethod,
    owner: input.owner,
    source: input.source,
    tags: input.tags,
    title: input.title,
    statement: input.statement,
    rationale: input.rationale,
    acceptance_criteria: input.acceptanceCriteria,
    comment: input.comment,
    relations: input.relations,
    ...(input.revision ? { revision: input.revision } : {}),
  };
}

export function requirementToPayload(input: RequirementInput): Record<string, unknown> {
  return {
    document: input.document,
    uid: input.uid,
    ...requirementToUpdatePayload(input),
  };
}

export const api = {
  health: async (): Promise<{ status: string; strictdocVersion: string; revision: string }> => {
    const record = asRecord(await apiFetch('/health'));
    return {
      status: textValue(record.status, 'unknown'),
      strictdocVersion: textValue(pick(record, 'strictdoc_version', 'strictdocVersion')),
      revision: textValue(record.revision),
    };
  },

  project: async (): Promise<ProjectInfo> => normalizeProject(await apiFetch('/project')),
  diagnostics: async (): Promise<DiagnosticsData> =>
    normalizeDiagnostics(await apiFetch('/diagnostics')),
  reload: async (): Promise<unknown> => apiFetch('/reload', { method: 'POST' }),

  requirements: async (
    filters: { text?: string; type?: string; status?: string } = {},
  ): Promise<RequirementList> =>
    normalizeRequirementList(await apiFetch(`/requirements${params(filters)}`)),
  requirement: async (uid: string): Promise<Requirement> =>
    normalizeRequirement(await apiFetch(`/requirements/${encodeURIComponent(uid)}`)),
  createRequirement: async (input: RequirementInput): Promise<Requirement> =>
    normalizeRequirement(
      await apiFetch('/requirements', {
        method: 'POST',
        body: JSON.stringify(requirementToPayload(input)),
      }),
    ),
  updateRequirement: async (uid: string, input: RequirementInput): Promise<Requirement> =>
    normalizeRequirement(
      await apiFetch(`/requirements/${encodeURIComponent(uid)}`, {
        method: 'PUT',
        ...(input.revision ? { headers: { 'If-Match': input.revision } } : {}),
        body: JSON.stringify(requirementToUpdatePayload(input)),
      }),
    ),
  deleteRequirement: async (uid: string, revision: string): Promise<void> => {
    await apiFetch(`/requirements/${encodeURIComponent(uid)}${params({ revision })}`, {
      method: 'DELETE',
      ...(revision ? { headers: { 'If-Match': revision } } : {}),
    });
  },
  validateRequirements: async (): Promise<unknown> =>
    apiFetch('/requirements/validate', { method: 'POST' }),

  capellaStatus: async (): Promise<CapellaStatus> =>
    normalizeCapellaStatus(await apiFetch('/capella/status')),
  reloadCapella: async (): Promise<CapellaStatus> =>
    normalizeCapellaStatus(await apiFetch('/capella/reload', { method: 'POST' })),
  capellaElements: async (
    filters: {
      layer?: string;
      type?: string;
      text?: string;
      parent_uuid?: string;
      related_to?: string;
    } = {},
  ): Promise<CapellaElement[]> =>
    normalizeCapellaElements(await apiFetch(`/capella/elements${params(filters)}`)),
  capellaElement: async (uuid: string): Promise<CapellaElement> =>
    normalizeCapellaElement(await apiFetch(`/capella/elements/${encodeURIComponent(uuid)}`)),
  diagrams: async (): Promise<Diagram[]> => normalizeDiagrams(await apiFetch('/capella/diagrams')),
  diagramSvg: async (uuid: string): Promise<string> => {
    const payload = await apiFetch(`/capella/diagrams/${encodeURIComponent(uuid)}/svg`);
    if (typeof payload === 'string') return payload;
    const record = asRecord(payload);
    return textValue(pick(record, 'svg', 'content'));
  },

  traceLinks: async (): Promise<TraceLink[]> => normalizeTraceLinks(await apiFetch('/trace-links')),
  createTraceLink: async (input: TraceLinkInput): Promise<TraceLink> =>
    normalizeTraceLink(
      await apiFetch('/trace-links', {
        method: 'POST',
        body: JSON.stringify({
          requirement: {
            uid: input.requirement_uid,
            mid: input.requirement_mid ?? input.requirement_uid,
          },
          architecture: {
            model_id: input.model_id,
            uuid: input.target_uuid,
            type: input.target_type ?? 'Element',
            name_snapshot: input.target_name ?? input.target_uuid,
          },
          relation: input.relation,
          rationale: input.rationale ?? '',
          ...(input.revision ? { revision: input.revision } : {}),
        }),
      }),
    ),
  updateTraceLink: async (id: string, input: TraceLinkInput): Promise<TraceLink> =>
    normalizeTraceLink(
      await apiFetch(`/trace-links/${encodeURIComponent(id)}`, {
        method: 'PUT',
        ...(input.revision ? { headers: { 'If-Match': input.revision } } : {}),
        body: JSON.stringify({
          requirement: {
            uid: input.requirement_uid,
            mid: input.requirement_mid ?? input.requirement_uid,
          },
          architecture: {
            model_id: input.model_id,
            uuid: input.target_uuid,
            type: input.target_type ?? 'Element',
            name_snapshot: input.target_name ?? input.target_uuid,
          },
          relation: input.relation,
          rationale: input.rationale ?? '',
          revision: input.revision,
        }),
      }),
    ),
  deleteTraceLink: async (id: string, revision?: string): Promise<void> => {
    await apiFetch(`/trace-links/${encodeURIComponent(id)}${params({ revision })}`, {
      method: 'DELETE',
    });
  },
  validateTraceLinks: async (): Promise<unknown> =>
    apiFetch('/trace-links/validate', { method: 'POST' }),
  refreshTraceLinkSnapshots: async (): Promise<unknown> =>
    apiFetch('/trace-links/refresh-snapshots', { method: 'POST' }),

  dashboard: async (): Promise<DashboardData> => normalizeDashboard(await apiFetch('/dashboard')),
  graph: async (filters: {
    focus?: string;
    depth?: number;
    source?: string;
    type?: string;
    relation?: string;
    text?: string;
  }): Promise<GraphData> =>
    normalizeGraph(
      await apiFetch(
        `/graph${params({
          focus: filters.focus,
          depth: filters.depth,
          sources: filters.source,
          types: filters.type,
          relations: filters.relation,
          text: filters.text,
        })}`,
      ),
    ),
  matrix: async (
    kind:
      | 'requirements-tests'
      | 'requirements-functions'
      | 'requirements-components'
      | 'functions-components',
    filters: { text?: string } = {},
  ): Promise<MatrixData> => normalizeMatrix(await apiFetch(`/matrices/${kind}${params(filters)}`)),
  impactRequirement: async (uid: string, depth = 3): Promise<ImpactData> =>
    normalizeImpact(
      await apiFetch(`/impact/requirement/${encodeURIComponent(uid)}${params({ depth })}`),
    ),
  impactCapella: async (uuid: string, depth = 3): Promise<ImpactData> =>
    normalizeImpact(
      await apiFetch(`/impact/capella/${encodeURIComponent(uuid)}${params({ depth })}`),
    ),

  startExport: async (
    format: 'html' | 'pdf' | 'excel' | 'json' | 'reqif' | 'combined-html',
  ): Promise<ExportJob> => {
    const path =
      format === 'combined-html' ? '/exports/combined-html' : `/exports/strictdoc/${format}`;
    return normalizeExportJob(await apiFetch(path, { method: 'POST' }));
  },
  exportJob: async (id: string): Promise<ExportJob> =>
    normalizeExportJob(await apiFetch(`/exports/jobs/${encodeURIComponent(id)}`)),
  exportFileUrl: (id: string): string => `${API_ROOT}/exports/files/${encodeURIComponent(id)}`,
};
