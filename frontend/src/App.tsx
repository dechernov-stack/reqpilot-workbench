import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { lazy, Suspense } from 'react';
import { createBrowserRouter, RouterProvider } from 'react-router-dom';
import { AppShell } from './components/AppShell';
import { LoadingState } from './components/PageState';

const DashboardPage = lazy(() =>
  import('./pages/DashboardPage').then((module) => ({ default: module.DashboardPage })),
);
const RequirementsPage = lazy(() =>
  import('./pages/RequirementsPage').then((module) => ({ default: module.RequirementsPage })),
);
const ArchitecturePage = lazy(() =>
  import('./pages/ArchitecturePage').then((module) => ({ default: module.ArchitecturePage })),
);
const TraceabilityPage = lazy(() =>
  import('./pages/TraceabilityPage').then((module) => ({ default: module.TraceabilityPage })),
);
const MatricesPage = lazy(() =>
  import('./pages/MatricesPage').then((module) => ({ default: module.MatricesPage })),
);
const ImpactPage = lazy(() =>
  import('./pages/ImpactPage').then((module) => ({ default: module.ImpactPage })),
);
const ExportsPage = lazy(() =>
  import('./pages/ExportsPage').then((module) => ({ default: module.ExportsPage })),
);
const DiagnosticsPage = lazy(() =>
  import('./pages/DiagnosticsPage').then((module) => ({ default: module.DiagnosticsPage })),
);

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 15_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
    mutations: { retry: false },
  },
});

export const router = createBrowserRouter([
  {
    path: '/',
    element: <AppShell />,
    errorElement: <RouteError />,
    children: [
      { index: true, element: <DashboardPage /> },
      { path: 'requirements', element: <RequirementsPage /> },
      { path: 'architecture', element: <ArchitecturePage /> },
      { path: 'traceability', element: <TraceabilityPage /> },
      { path: 'matrices', element: <MatricesPage /> },
      { path: 'impact', element: <ImpactPage /> },
      { path: 'exports', element: <ExportsPage /> },
      { path: 'diagnostics', element: <DiagnosticsPage /> },
      { path: '*', element: <NotFound /> },
    ],
  },
]);

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Suspense
        fallback={
          <div className="min-h-screen bg-canvas p-8">
            <LoadingState label="Загрузка раздела…" />
          </div>
        }
      >
        <RouterProvider router={router} />
      </Suspense>
    </QueryClientProvider>
  );
}

function RouteError() {
  return (
    <div className="grid min-h-screen place-items-center bg-canvas p-8">
      <div className="panel max-w-lg p-8 text-center">
        <p className="text-xs font-semibold uppercase tracking-widest text-danger">UI error</p>
        <h1 className="mt-2 text-2xl font-semibold">Экран не удалось открыть</h1>
        <p className="mt-2 text-sm leading-6 text-steel">
          Обновите страницу. Если ошибка повторяется, откройте «Диагностику» и проверьте backend.
        </p>
        <a className="button-primary mt-5" href="/">
          Вернуться к обзору
        </a>
      </div>
    </div>
  );
}

function NotFound() {
  return (
    <div className="panel p-8 text-center">
      <p className="text-sm font-semibold text-danger">404</p>
      <h1 className="mt-2 text-2xl font-semibold">Раздел не найден</h1>
      <a className="button-primary mt-5" href="/">
        На обзор
      </a>
    </div>
  );
}
