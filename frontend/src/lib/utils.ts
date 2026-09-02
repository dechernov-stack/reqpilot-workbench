import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
import type { MatrixData } from './types';

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

export function formatPercent(value: number): string {
  return (
    new Intl.NumberFormat('ru-RU', {
      maximumFractionDigits: 1,
      minimumFractionDigits: value % 1 === 0 ? 0 : 1,
    }).format(value) + '%'
  );
}

export function formatDuration(ms: number): string {
  if (!Number.isFinite(ms) || ms <= 0) return '—';
  if (ms < 1000) return `${Math.round(ms)} мс`;
  return `${(ms / 1000).toFixed(1)} с`;
}

export function formatBytes(value: number): string {
  if (!Number.isFinite(value) || value < 0) return '—';
  if (value < 1024) return `${value} Б`;
  if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} КБ`;
  return `${(value / 1024 ** 2).toFixed(1)} МБ`;
}

export function matrixCellKey(rowId: string, columnId: string): string {
  return `${rowId}\u0000${columnId}`;
}

export function matrixCellIndex(matrix: MatrixData): Map<string, MatrixData['cells'][number]> {
  return new Map(matrix.cells.map((cell) => [matrixCellKey(cell.rowId, cell.columnId), cell]));
}

function csvEscape(value: string): string {
  if (!/[",\n\r;]/.test(value)) return value;
  return `"${value.replaceAll('"', '""')}"`;
}

export function matrixToCsv(matrix: MatrixData): string {
  const cells = matrixCellIndex(matrix);
  const header = ['Объект', ...matrix.columns.map((column) => column.label)];
  const rows = matrix.rows.map((row) => [
    row.label,
    ...matrix.columns.map((column) => {
      const cell = cells.get(matrixCellKey(row.id, column.id));
      return cell?.linked ? cell.relation || 'X' : '';
    }),
  ]);
  return [header, ...rows].map((row) => row.map((value) => csvEscape(value)).join(';')).join('\n');
}

export function downloadText(filename: string, content: string, mediaType: string): void {
  const blob = new Blob([content], { type: `${mediaType};charset=utf-8` });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

export function copyText(value: string): Promise<void> {
  return navigator.clipboard.writeText(value);
}

export function humanize(value: string): string {
  const labels: Record<string, string> = {
    requirement: 'Требование',
    test: 'Тест',
    capella: 'Capella',
    broken: 'Битая ссылка',
    valid: 'Валидно',
    broken_uid: 'UID не найден',
    broken_uuid: 'UUID не найден',
    stale: 'Устаревший снимок',
    satisfied_by: 'Удовлетворяется',
    allocated_to: 'Назначено',
    implemented_by: 'Реализуется',
    verified_by: 'Проверяется',
  };
  return labels[value] ?? value.replaceAll('_', ' ');
}
