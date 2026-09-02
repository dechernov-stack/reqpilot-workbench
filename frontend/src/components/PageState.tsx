import { AlertCircle, Inbox, LoaderCircle, RefreshCw } from 'lucide-react';

export function LoadingState({ label = 'Загрузка данных…' }: { label?: string }) {
  return (
    <div className="state-panel" role="status" aria-live="polite">
      <LoaderCircle aria-hidden="true" className="h-6 w-6 animate-spin text-cyan" />
      <span>{label}</span>
    </div>
  );
}

export function EmptyState({
  title = 'Нет данных',
  description,
  action,
}: {
  title?: string;
  description?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="state-panel">
      <Inbox aria-hidden="true" className="h-7 w-7 text-slate-400" />
      <div className="text-center">
        <p className="font-semibold text-ink">{title}</p>
        {description ? <p className="mt-1 max-w-lg text-sm text-steel">{description}</p> : null}
      </div>
      {action}
    </div>
  );
}

export function ErrorState({
  error,
  onRetry,
  title = 'Не удалось получить данные',
}: {
  error: unknown;
  onRetry?: () => void;
  title?: string;
}) {
  const message = error instanceof Error ? error.message : 'Неизвестная ошибка';
  return (
    <div className="state-panel border-red-200 bg-red-50" role="alert">
      <AlertCircle aria-hidden="true" className="h-7 w-7 text-danger" />
      <div className="text-center">
        <p className="font-semibold text-red-900">{title}</p>
        <p className="mt-1 max-w-xl text-sm text-red-800">{message}</p>
      </div>
      {onRetry ? (
        <button className="button-secondary" type="button" onClick={onRetry}>
          <RefreshCw aria-hidden="true" className="h-4 w-4" />
          Повторить
        </button>
      ) : null}
    </div>
  );
}
