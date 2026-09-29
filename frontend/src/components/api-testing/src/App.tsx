import { createBrowserRouter, RouterProvider } from 'react-router';

import { Layout } from '@/components/Layout';
import { TokenPrompt } from '@/components/TokenPrompt';
import { Empty } from '@/components/ui';
import { EnvironmentsPage } from '@/pages/EnvironmentsPage';
import { RunDetailPage } from '@/pages/RunDetailPage';
import { RunnerPage } from '@/pages/RunnerPage';
import { RunsPage } from '@/pages/RunsPage';
import { WorkspacePage } from '@/pages/WorkspacePage';

const router = createBrowserRouter([
  {
    path: '/',
    element: <Layout />,
    children: [
      { index: true, element: <WorkspacePage /> },
      { path: 'runner', element: <RunnerPage /> },
      { path: 'runs', element: <RunsPage /> },
      { path: 'runs/:runId', element: <RunDetailPage /> },
      { path: 'environments', element: <EnvironmentsPage /> },
      { path: '*', element: <Empty title="Page not found" /> },
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
