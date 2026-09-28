/**
 * Talking to the Rewind Chrome extension.
 *
 * A page cannot message an extension service worker directly, so everything
 * goes through the extension's content script, which listens on this window
 * and relays. That means "no reply" is the normal shape of "extension missing",
 * and every call here has to time out rather than hang.
 */

const REPLY_TIMEOUT_MS = 1500;

function ask<T>(request: object, replyType: string, timeoutMs = REPLY_TIMEOUT_MS): Promise<T | null> {
  return new Promise((resolve) => {
    let settled = false;

    const onMessage = (event: MessageEvent) => {
      if (event.source !== window || event.origin !== window.location.origin) return;
      if (event.data?.type !== replyType) return;
      finish(event.data as T);
    };

    const finish = (value: T | null) => {
      if (settled) return;
      settled = true;
      window.removeEventListener('message', onMessage);
      window.clearTimeout(timer);
      resolve(value);
    };

    window.addEventListener('message', onMessage);
    const timer = window.setTimeout(() => finish(null), timeoutMs);
    window.postMessage(request, window.location.origin);
  });
}

/** True when the extension's content script is present in this tab. */
export async function isExtensionPresent(): Promise<boolean> {
  return (await ask<{ type: string }>({ type: 'REWIND_PING' }, 'REWIND_PONG')) !== null;
}

export interface StartResult {
  ok: boolean;
  error: string;
}

export async function startRecording(params: {
  sessionToken: string;
  projectId: string;
  startUrl: string;
}): Promise<StartResult> {
  const reply = await ask<StartResult>(
    { type: 'START_RECORDING_FROM_APP', ...params },
    'REWIND_RECORDING_STARTED',
  );
  if (!reply) return { ok: false, error: 'The extension did not respond.' };
  return { ok: reply.ok, error: reply.error };
}

export const EXTENSION_MISSING_HELP =
  'Rewind extension not detected in this tab. Load it from chrome://extensions ' +
  '(Developer mode → Load unpacked → extension/dist), then reload this page.';
