import React from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import { LayoutDashboard, History, PlayCircle, BookOpen } from 'lucide-react';

const NAV_ITEMS = [
  { to: '/', icon: LayoutDashboard, label: 'Projects', end: true },
  { to: '/history', icon: History, label: 'Run history', end: false },
];

export const Layout = () => {
  return (
    <div className="flex h-screen overflow-hidden bg-canvas">
      <aside className="w-60 shrink-0 bg-surface border-r border-line flex flex-col">
        <div className="h-16 flex items-center gap-2.5 px-5 border-b border-line">
          <span className="w-8 h-8 rounded-xl bg-primary-500 grid place-items-center">
            <PlayCircle className="w-4.5 h-4.5 text-white" />
          </span>
          <span className="font-bold text-[17px] tracking-tight text-ink">Rewind</span>
        </div>

        <nav className="flex-1 p-3 space-y-1">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-semibold transition-colors ${
                  isActive
                    ? 'bg-primary-50 text-primary-600'
                    : 'text-ink-muted hover:text-ink hover:bg-canvas'
                }`
              }
            >
              <item.icon className="w-[18px] h-[18px]" />
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="p-3 border-t border-line">
          <div className="rounded-xl bg-lilac-50 p-3.5">
            <div className="flex items-center gap-2 text-lilac-500 font-semibold text-xs mb-1.5">
              <BookOpen className="w-4 h-4" />
              How it works
            </div>
            <p className="text-[11.5px] leading-relaxed text-ink-muted">
              Record a flow with the Chrome extension, or build one by hand,
              then replay it. Chrome opens and drives every step while
              evidence is captured.
            </p>
          </div>
        </div>
      </aside>

      <main className="flex-1 overflow-y-auto">
        <div className="p-8 max-w-6xl mx-auto w-full">
          <Outlet />
        </div>
      </main>
    </div>
  );
};
