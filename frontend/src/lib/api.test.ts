import { afterEach, describe, expect, it, vi } from 'vitest';
import { api, requirementToPayload } from './api';
import type { ApiError } from './api';
import type { RequirementInput } from './types';

const input: RequirementInput = {
  uid: 'SYS-002',
  document: '02_system.sdoc',
  nodeType: 'REQUIREMENT',
  type: 'System',
  status: 'Approved',
  priority: 'High',
  verificationMethod: 'Test',
  owner: 'Engineer',
  source: 'SRS',
  tags: ['pressure'],
  title: 'Pressure',
  statement: 'Monitor pressure.',
  rationale: 'Safety',
  acceptanceCriteria: 'Alarm.',
  comment: '',
  relations: [],
  revision: 'rev-3',
};

function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

afterEach(() => vi.unstubAllGlobals());

describe('typed API client contracts', () => {
  it('serializes camelCase UI fields to canonical lower_snake_case', () => {
    expect(requirementToPayload(input)).toMatchObject({
      document: '02_system.sdoc',
      uid: 'SYS-002',
      verification_method: 'Test',
      acceptance_criteria: 'Alarm.',
      revision: 'rev-3',
    });
    expect(requirementToPayload(input)).not.toHaveProperty('verificationMethod');
    expect(requirementToPayload(input)).not.toHaveProperty('node_type');
  });

  it('reads requirement envelopes and sends revision through body and If-Match', async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        jsonResponse({
          items: [{ uid: 'SYS-002', revision: 'rev-3' }],
          total: 1,
          revision: 'rev-3',
        }),
      )
      .mockResolvedValueOnce(jsonResponse({ uid: 'SYS-002', revision: 'rev-4' }));
    vi.stubGlobal('fetch', fetchMock);
    expect((await api.requirements()).items[0]?.uid).toBe('SYS-002');
    expect((await api.updateRequirement('SYS-002', input)).revision).toBe('rev-4');
    const [url, init] = fetchMock.mock.calls[1]!;
    expect(url).toBe('/api/requirements/SYS-002');
    expect(new Headers(init?.headers).get('If-Match')).toBe('rev-3');
    expect(typeof init?.body).toBe('string');
    expect(JSON.parse(typeof init?.body === 'string' ? init.body : '{}')).toMatchObject({
      revision: 'rev-3',
      rationale: 'Safety',
    });
    expect(JSON.parse(typeof init?.body === 'string' ? init.body : '{}')).not.toHaveProperty('uid');
  });

  it('uses exact trace-link and export endpoint contracts', async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        jsonResponse({
          id: 'l1',
          requirement_uid: 'SYS-002',
          target_uuid: 'u1',
          relation: 'satisfied_by',
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({ id: 'j1', format: 'combined-html', status: 'completed', created_files: [] }),
      );
    vi.stubGlobal('fetch', fetchMock);
    await api.createTraceLink({
      requirement_uid: 'SYS-002',
      requirement_mid: 'MID-2',
      model_id: 'm1',
      target_uuid: 'u1',
      target_type: 'Function',
      target_name: 'Evaluate Pressure Threshold',
      relation: 'satisfied_by',
    });
    await api.startExport('combined-html');
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/trace-links');
    const firstBody = fetchMock.mock.calls[0]?.[1]?.body;
    expect(JSON.parse(typeof firstBody === 'string' ? firstBody : '{}')).toMatchObject({
      requirement: { uid: 'SYS-002', mid: 'MID-2' },
      architecture: {
        model_id: 'm1',
        uuid: 'u1',
        type: 'Function',
        name_snapshot: 'Evaluate Pressure Threshold',
      },
      relation: 'satisfied_by',
    });
    expect(fetchMock.mock.calls[1]?.[0]).toBe('/api/exports/combined-html');
  });

  it('preserves structured FastAPI errors for revision conflict UX', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>().mockResolvedValue(
        jsonResponse(
          {
            detail: {
              code: 'REVISION_CONFLICT',
              message: 'Revision changed',
              diagnostics: [{ code: 'STALE', message: 'Reload' }],
            },
          },
          409,
        ),
      ),
    );
    const expected: Partial<ApiError> = {
      name: 'ApiError',
      code: 'REVISION_CONFLICT',
      status: 409,
      message: 'Revision changed',
    };
    await expect(api.requirement('SYS-002')).rejects.toMatchObject(expected);
  });
});
