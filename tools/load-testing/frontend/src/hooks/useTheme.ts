import { useCallback, useEffect, useState } from 'react';

export type Theme = 'light' | 'dark' | 'system';
const KEY = 'lt.theme';

function readTheme(): Theme {
  const v = localStorage.getItem(KEY);
  return v === 'light' || v === 'dark' ? v : 'system';
}

function apply(theme: Theme) {
  const dark =
    theme === 'dark' ||
    (theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
  document.documentElement.classList.toggle('dark', dark);
}

export const applyStoredTheme = () => apply(readTheme());

export function useTheme() {
  const [theme, setThemeState] = useState<Theme>(readTheme);

  useEffect(() => {
    apply(theme);
    if (theme !== 'system') return;
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const onChange = () => apply('system');
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, [theme]);

  const setTheme = useCallback((next: Theme) => {
    if (next === 'system') localStorage.removeItem(KEY);
    else localStorage.setItem(KEY, next);
    setThemeState(next);
  }, []);

  return { theme, setTheme };
}
