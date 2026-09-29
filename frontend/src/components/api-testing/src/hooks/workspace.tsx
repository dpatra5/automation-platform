import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';

const ENV_KEY = 'apit.environmentId';
const SESSION_KEY = 'apit.sessionVariables';

interface WorkspaceState {
  environmentId: number | null;
  setEnvironmentId: (id: number | null) => void;
  /** Values extracted by ad-hoc sends, reused by later sends (like a manual run). */
  sessionVariables: Record<string, string>;
  mergeSessionVariables: (values: Record<string, string>) => void;
  clearSessionVariables: () => void;
}

const Context = createContext<WorkspaceState | null>(null);

function readSession(): Record<string, string> {
  try {
    const parsed: unknown = JSON.parse(sessionStorage.getItem(SESSION_KEY) ?? '{}');
    return parsed && typeof parsed === 'object' ? (parsed as Record<string, string>) : {};
  } catch {
    return {};
  }
}

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [environmentId, setEnv] = useState<number | null>(() => {
    const raw = localStorage.getItem(ENV_KEY);
    return raw ? Number(raw) : null;
  });
  const [sessionVariables, setSessionVariables] = useState<Record<string, string>>(readSession);

  const setEnvironmentId = useCallback((id: number | null) => {
    setEnv(id);
    if (id === null) localStorage.removeItem(ENV_KEY);
    else localStorage.setItem(ENV_KEY, String(id));
  }, []);

  const persist = (next: Record<string, string>) => {
    sessionStorage.setItem(SESSION_KEY, JSON.stringify(next));
    return next;
  };
  const mergeSessionVariables = useCallback(
    (values: Record<string, string>) => setSessionVariables((prev) => persist({ ...prev, ...values })),
    [],
  );
  const clearSessionVariables = useCallback(() => setSessionVariables(persist({})), []);

  const value = useMemo(
    () => ({ environmentId, setEnvironmentId, sessionVariables, mergeSessionVariables, clearSessionVariables }),
    [environmentId, setEnvironmentId, sessionVariables, mergeSessionVariables, clearSessionVariables],
  );
  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function useWorkspace(): WorkspaceState {
  const ctx = useContext(Context);
  if (!ctx) throw new Error('useWorkspace must be used inside WorkspaceProvider');
  return ctx;
}
