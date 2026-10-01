// One long-lived "test browser" per engine with its own saved profile, so sign-ins survive between runs.
// Each run opens its own tabs here and closes only those tabs when it finishes.
import fs from 'node:fs/promises'
import path from 'node:path'
import { chromium, firefox, webkit } from 'playwright'

const engines = { chromium, firefox, webkit }
const contexts = new Map()

export const sharedBrowserEnabled = () => process.env.UI_AUTOMATION_SHARED_BROWSER !== 'false'

export function getSharedContext(name, { dataDirectory, headless, initScript, executablePath }) {
  if (!contexts.has(name)) {
    const launching = (async () => {
      const profile = path.join(dataDirectory, 'browser-profiles', name)
      await fs.mkdir(profile, { recursive: true })
      const context = await engines[name].launchPersistentContext(profile, {
        headless,
        ...(headless ? {} : { viewport: null }),
        ...(name === 'chromium' && executablePath ? { executablePath } : {}),
      })
      if (initScript) await context.addInitScript({ content: initScript })
      context.on('close', () => contexts.delete(name))
      return context
    })()
    contexts.set(name, launching)
    launching.catch(() => contexts.delete(name))
  }
  return contexts.get(name)
}

export async function sharedBrowserStatus() {
  const status = {}
  for (const [name, launching] of contexts) {
    const context = await launching.catch(() => null)
    if (context) status[name] = { open: true, tabs: context.pages().length }
  }
  return status
}

// Adds cookies saved with the recording only where the test browser has none, so a newer sign-in is never overwritten.
export async function seedCookies(context, storageState) {
  const saved = storageState?.cookies || []
  if (!saved.length) return 0
  const key = (cookie) => `${cookie.name}|${cookie.domain}|${cookie.path}`
  const existing = new Set((await context.cookies()).map(key))
  const now = Date.now() / 1000
  const missing = saved.filter((cookie) => !existing.has(key(cookie)) && (cookie.expires === -1 || cookie.expires > now))
  if (missing.length) await context.addCookies(missing).catch(() => {})
  return missing.length
}

export async function closeSharedBrowsers() {
  const open = [...contexts.values()]
  contexts.clear()
  await Promise.all(open.map((launching) => launching.then((context) => context.close(), () => {}).catch(() => {})))
}
