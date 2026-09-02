import { describe, expect, it, vi } from 'vitest';
import {
  formatBytes,
  formatDuration,
  formatPercent,
  humanize,
  matrixCellIndex,
  matrixCellKey,
  matrixToCsv,
} from './utils';
import type { MatrixData } from './types';

const matrix: MatrixData = {
  rows: [{ id: 'SYS-002', label: 'Pressure; control', type: 'System', status: 'Approved' }],
  columns: [{ id: 'f1', label: 'Evaluate "threshold"', type: 'Function', status: '' }],
  cells: [
    { rowId: 'SYS-002', columnId: 'f1', linked: true, relation: 'satisfied_by', linkIds: ['l1'] },
  ],
  coverage: 100,
  covered: 1,
  total: 1,
};

describe('formatters and matrix export', () => {
  it('formats engineering metrics in Russian locale', () => {
    expect(formatPercent(75)).toContain('75');
    expect(formatDuration(250)).toBe('250 мс');
    expect(formatDuration(1250)).toBe('1.3 с');
    expect(formatDuration(0)).toBe('—');
    expect(formatBytes(512)).toBe('512 Б');
    expect(formatBytes(2048)).toBe('2.0 КБ');
    expect(formatBytes(2 * 1024 ** 2)).toBe('2.0 МБ');
  });

  it('indexes cells by collision-safe compound key', () => {
    const index = matrixCellIndex(matrix);
    expect(index.get(matrixCellKey('SYS-002', 'f1'))?.relation).toBe('satisfied_by');
  });

  it('exports the current matrix to semicolon CSV with escaping', () => {
    const csv = matrixToCsv(matrix);
    expect(csv.split('\n')).toHaveLength(2);
    expect(csv).toContain('"Pressure; control"');
    expect(csv).toContain('"Evaluate ""threshold"""');
    expect(csv).toContain('satisfied_by');
  });

  it('humanizes known and unknown identifiers', () => {
    expect(humanize('broken_uuid')).toBe('UUID не найден');
    expect(humanize('custom_relation')).toBe('custom relation');
  });

  it('does not rely on locale for invalid byte values', () => {
    expect(formatBytes(-1)).toBe('—');
    expect(formatBytes(Number.NaN)).toBe('—');
    vi.useFakeTimers();
    vi.useRealTimers();
  });
});
