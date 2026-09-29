import React, { useState } from 'react';
import { AuthProfile } from '../api/types';
import { useClearAuthProfile, useUploadAuthProfile } from '../hooks/useProjects';
import { ShieldCheck, ShieldAlert, ShieldOff, Upload, Trash2, X } from 'lucide-react';
import { formatDate } from '../utils/formatters';

interface Props {
  projectId: string;
  profile: AuthProfile | null | undefined;
  isLoading: boolean;
}

/**
 * Shows whether replayed runs will start signed in.
 *
 * The session is captured automatically when a recording stops, so the common
 * path needs no interaction here — this panel exists to say how long it is
 * good for and to let a Playwright storage_state be pasted in for apps that
 * are scripted rather than recorded.
 */
export const SessionCard = ({ projectId, profile, isLoading }: Props) => {
  const [isPasting, setIsPasting] = useState(false);
  const [json, setJson] = useState('');
  const [error, setError] = useState('');
  const upload = useUploadAuthProfile();
  const clear = useClearAuthProfile();

  const handleSave = () => {
    try {
      JSON.parse(json);
    } catch {
      setError('That is not valid JSON.');
      return;
    }
    setError('');
    upload.mutate(
      { projectId, profile: { name: 'Pasted session', storage_state_json: json } },
      { onSuccess: () => { setIsPasting(false); setJson(''); } },
    );
  };

  const tone = !profile
    ? { icon: ShieldOff, wrap: 'bg-canvas border-line', text: 'text-ink-muted', title: 'No saved sign-in' }
    : profile.is_usable
      ? { icon: ShieldCheck, wrap: 'bg-mint-50 border-mint-100', text: 'text-mint-500', title: 'Signed-in session saved' }
      : { icon: ShieldAlert, wrap: 'bg-amber-50 border-amber-100', text: 'text-amber-500', title: 'Session expired' };

  const Icon = tone.icon;

  return (
    <div className="card p-5">
      <div className="flex items-start justify-between gap-3 mb-4">
        <h3 className="text-sm font-semibold text-ink">Authentication</h3>
        {profile && (
          <button
            onClick={() => clear.mutate(projectId)}
            disabled={clear.isPending}
            className="btn-ghost !px-2 !py-1 text-xs"
            title="Forget the stored session"
          >
            <Trash2 className="w-3.5 h-3.5" /> Forget
          </button>
        )}
      </div>

      {isLoading ? (
        <div className="h-20 rounded-xl bg-line/70 animate-pulse" />
      ) : (
        <div className={`rounded-xl border p-4 ${tone.wrap}`}>
          <div className={`flex items-center gap-2 font-semibold text-sm ${tone.text}`}>
            <Icon className="w-4 h-4" />
            {tone.title}
          </div>

          <p className="text-xs text-ink-muted mt-2 leading-relaxed">
            {!profile ? (
              <>
                Runs start as a signed-out visitor. Record a session that includes
                signing in — the cookies are saved automatically, your password is
                never captured.
              </>
            ) : profile.is_usable ? (
              <>
                {profile.cookie_count} cookies from {profile.origins.length || 'no'} origin
                {profile.origins.length === 1 ? '' : 's'}.{' '}
                {profile.expires_at
                  ? <>Valid until <span className="font-medium text-ink-soft">{formatDate(profile.expires_at)}</span>. Runs starting within 5 minutes of that are blocked up front rather than failing halfway.</>
                  : <>Session cookies only — they last until the identity provider ends the session.</>}
              </>
            ) : (
              <>
                Expired {profile.expires_at ? formatDate(profile.expires_at) : ''}. Record the
                flow again to refresh it; runs will fail fast until you do.
              </>
            )}
          </p>
        </div>
      )}

      {isPasting ? (
        <div className="mt-4 space-y-2">
          <label className="label" htmlFor="storage-state">Playwright storage_state JSON</label>
          <textarea
            id="storage-state"
            className="field font-mono text-xs h-28 resize-none"
            placeholder='{"cookies": [...], "origins": [...]}'
            value={json}
            onChange={(e) => setJson(e.target.value)}
          />
          {error && <p className="text-xs text-rose-500">{error}</p>}
          <div className="flex gap-2">
            <button onClick={handleSave} disabled={upload.isPending} className="btn-primary !py-2 text-xs">
              {upload.isPending ? 'Saving…' : 'Save session'}
            </button>
            <button onClick={() => { setIsPasting(false); setError(''); }} className="btn-secondary !py-2 text-xs">
              <X className="w-3.5 h-3.5" /> Cancel
            </button>
          </div>
        </div>
      ) : (
        <button onClick={() => setIsPasting(true)} className="btn-ghost !px-2 mt-3 text-xs">
          <Upload className="w-3.5 h-3.5" /> Paste a storage_state instead
        </button>
      )}
    </div>
  );
};
