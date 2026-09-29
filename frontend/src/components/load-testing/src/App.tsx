import { lazy, Suspense, type ReactNode } from 'react';
import { createBrowserRouter, RouterProvider } from 'react-router';

import { AppLayout } from '@/components/layout/AppLayout';
import { PageLoader } from '@/components/ui/Spinner';
import { TokenPrompt } from '@/components/TokenPrompt';

const DashboardPage = lazy(() =>
  import('@/pages/DashboardPage').then((m) => ({ default: m.DashboardPage })),
);
const RunsPage = lazy(() => import('@/pages/RunsPage').then((m) => ({ default: m.RunsPage })));
const NewRunPage = lazy(() =>
  import('@/pages/NewRunPage').then((m) => ({ default: m.NewRunPage })),
);
const RunDetailPage = lazy(() =>
  import('@/pages/RunDetailPage').then((m) => ({ default: m.RunDetailPage })),
);
const DemoServerPage = lazy(() =>
  import('@/pages/DemoServerPage').then((m) => ({ default: m.DemoServerPage })),
);
const NotFoundPage = lazy(() =>
  import('@/pages/NotFoundPage').then((m) => ({ default: m.NotFoundPage })),
);
const ScansPage = lazy(() => import('@/pages/ScansPage').then((m) => ({ default: m.ScansPage })));
const ScanDetailPage = lazy(() =>
  import('@/pages/ScanDetailPage').then((m) => ({ default: m.ScanDetailPage })),
);

const page = (node: ReactNode) => <Suspense fallback={<PageLoader />}>{node}</Suspense>;

const router = createBrowserRouter([
  {
    path: '/',
    element: <AppLayout />,
    children: [
      { index: true, element: page(<DashboardPage />) },
      { path: 'runs', element: page(<RunsPage />) },
      { path: 'runs/new', element: page(<NewRunPage />) },
      { path: 'runs/:runId', element: page(<RunDetailPage />) },
      { path: 'demo-server', element: page(<DemoServerPage />) },
      { path: 'scans', element: page(<ScansPage />) },
      { path: 'scans/:scanId', element: page(<ScanDetailPage />) },
      { path: '*', element: page(<NotFoundPage />) },
    ],
  },
]);

export function App() {
  return (
    <>
      <RouterProvider router={router} />
      <TokenPrompt />
    </>
  );
}
