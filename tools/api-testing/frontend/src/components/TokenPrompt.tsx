import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';

import { onUnauthorized, tokenStore } from '@/lib/api';
import { Button, Modal } from './ui';

export function TokenPrompt() {
  const [open, setOpen] = useState(false);
  const [token, setToken] = useState('');
  const client = useQueryClient();

  useEffect(() => onUnauthorized(() => setOpen(true)), []);

  if (!open) return null;
  const save = () => {
    tokenStore.set(token.trim());
    setOpen(false);
    setToken('');
    void client.invalidateQueries();
  };
  return (
    <Modal
      title="API token required"
      onClose={() => setOpen(false)}
      footer={
        <Button variant="primary" disabled={!token.trim()} onClick={save}>
          Save token
        </Button>
      }
    >
      <p className="mb-3 text-sm text-slate-600">
        This server requires the token configured in <code>APIT_TOKEN</code>. It is kept only for this browser tab.
      </p>
      <input
        className="input"
        type="password"
        autoFocus
        value={token}
        onChange={(e) => setToken(e.target.value)}
        onKeyDown={(e) => e.key === 'Enter' && token.trim() && save()}
        placeholder="Token"
      />
    </Modal>
  );
}
