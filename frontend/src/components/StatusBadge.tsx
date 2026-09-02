import { AlertTriangle, CheckCircle2, CircleHelp, XCircle } from 'lucide-react';
import { cn, humanize } from '../lib/utils';

interface StatusBadgeProps {
  status: string;
  label?: string;
  compact?: boolean;
}

const okStatuses = new Set([
  'ok',
  'valid',
  'completed',
  'succeeded',
  'live',
  'approved',
  'pass',
  'ready',
]);
const warnStatuses = new Set([
  'warning',
  'degraded',
  'fixture',
  'draft',
  'stale',
  'running',
  'queued',
]);
const errorStatuses = new Set([
  'error',
  'failed',
  'broken',
  'broken_uid',
  'broken_uuid',
  'broken_requirement',
  'broken_architecture',
  'architecture_unavailable',
  'invalid',
]);

export function StatusBadge({ status, label, compact = false }: StatusBadgeProps) {
  const normalized = status.toLowerCase();
  const tone = okStatuses.has(normalized)
    ? 'ok'
    : warnStatuses.has(normalized)
      ? 'warn'
      : errorStatuses.has(normalized)
        ? 'error'
        : 'neutral';
  const Icon =
    tone === 'ok'
      ? CheckCircle2
      : tone === 'warn'
        ? AlertTriangle
        : tone === 'error'
          ? XCircle
          : CircleHelp;
  return (
    <span
      className={cn(
        'inline-flex max-w-full items-center gap-1.5 rounded border px-2 py-0.5 text-xs font-semibold',
        tone === 'ok' && 'border-emerald-200 bg-emerald-50 text-emerald-800',
        tone === 'warn' && 'border-amber-200 bg-amber-50 text-amber-900',
        tone === 'error' && 'border-red-200 bg-red-50 text-red-800',
        tone === 'neutral' && 'border-slate-200 bg-slate-50 text-slate-700',
        compact && 'px-1.5 py-0',
      )}
      title={humanize(status)}
    >
      <Icon aria-hidden="true" className="h-3.5 w-3.5 shrink-0" />
      <span className="truncate">{label ?? humanize(status || 'unknown')}</span>
    </span>
  );
}
