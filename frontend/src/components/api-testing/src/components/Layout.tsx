import { FolderTree, History, Layers, PlayCircle } from 'lucide-react';
import { NavLink, Outlet } from 'react-router';

import { useEnvironments } from '@/hooks/queries';
import { useWorkspace } from '@/hooks/workspace';

const NAV = [
  { to: '/', label: 'Workspace', icon: FolderTree, end: true },
  { to: '/runner', label: 'Runner', icon: PlayCircle, end: false },
  { to: '/runs', label: 'Run history', icon: History, end: false },
  { to: '/environments', label: 'Environments', icon: Layers, end: false },
];

export function Layout() {
  const { environmentId, setEnvironmentId } = useWorkspace();
  const { data: environments } = useEnvironments();
  const known = environments?.some((e) => e.id === environmentId);

  return (
    <div className="flex h-full flex-col">
      <header className="flex h-12 shrink-0 items-center gap-6 border-b border-slate-200 bg-white px-4">
        <div className="flex items-center gap-2 font-semibold">
          <img src="/favicon.svg" alt="" className="size-6" />
          API Testing
        </div>
        <nav className="flex gap-1">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm ${
                  isActive ? 'bg-indigo-50 font-medium text-indigo-700' : 'text-slate-600 hover:bg-slate-100'
                }`
              }
            >
              <Icon className="size-4" /> {label}
            </NavLink>
          ))}
        </nav>
        <label className="ml-auto flex items-center gap-2 text-sm text-slate-500">
          Environment
          <select
            className="input w-48! py-1!"
            value={known ? String(environmentId) : ''}
            onChange={(e) => setEnvironmentId(e.target.value ? Number(e.target.value) : null)}
          >
            <option value="">No environment</option>
            {environments?.map((e) => (
              <option key={e.id} value={e.id}>
                {e.name}
              </option>
            ))}
          </select>
        </label>
      </header>
      <main className="min-h-0 flex-1">
        <Outlet />
      </main>
    </div>
  );
}
