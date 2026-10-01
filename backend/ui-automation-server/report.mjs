// Shareable execution report (JSON + self-contained HTML) for one test run.

const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char])

export function buildReport(replay, flow) {
  return {
    runId: replay.id,
    test: { name: flow?.flowName || 'UI test', slug: flow?.testSlug || null, url: flow?.url || '' },
    browser: replay.browser,
    status: replay.status,
    healedSteps: replay.healedSteps ?? 0,
    summary: replay.summary || null,
    steps: replay.results.map((result) => ({
      step: result.index,
      description: result.description || result.action,
      status: result.status,
      tab: result.tab,
      locator: result.locator,
      assertions: result.assertions || [],
      notes: result.notes || [],
      message: result.message,
    })),
  }
}

export function reportHtml(report) {
  const summary = report.summary || { steps: {}, assertions: {}, failures: [] }
  const seconds = summary.durationMs != null ? `${(summary.durationMs / 1000).toFixed(1)}s` : '-'
  const rows = report.steps.map((step) => {
    const checks = step.assertions.map((item) => `<li class="${item.passed ? 'ok' : 'bad'}">${item.passed ? '&#10003;' : '&#10007;'} ${escapeHtml(item.label)}${item.detail ? ` <span>${escapeHtml(item.detail)}</span>` : ''}</li>`).join('')
    const notes = step.notes.map((note) => `<li class="note">${escapeHtml(note)}</li>`).join('')
    return `<tr class="${escapeHtml(step.status)}"><td>${step.step}</td><td>${escapeHtml(step.description)}${step.locator ? `<code>${escapeHtml(step.locator)}</code>` : ''}</td><td><b>${escapeHtml(step.status)}</b></td><td><ul>${checks}${notes}</ul></td></tr>`
  }).join('')
  const failures = (summary.failures || []).map((failure) => `<li><b>Step ${failure.step}:</b> ${escapeHtml(failure.description)}<ul>${failure.reasons.map((reason) => `<li>${escapeHtml(reason)}</li>`).join('')}</ul></li>`).join('')
  return `<!doctype html><html><head><meta charset="utf-8"><title>${escapeHtml(report.test.name)} - execution report</title><style>
body{font:14px Segoe UI,sans-serif;color:#101323;background:#f4f6fb;margin:0;padding:32px}main{max-width:1100px;margin:auto}
h1{margin:0 0 4px}.meta{color:#5b6275;margin-bottom:20px}.cards{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:20px}
.card{background:#fff;border:1px solid #e3e6ef;border-radius:10px;padding:12px 16px;min-width:150px}.card b{display:block;font-size:22px}
.passed-badge{color:#0f5c33}.failed-badge{color:#a13049}table{width:100%;border-collapse:collapse;background:#fff;border:1px solid #e3e6ef}
th,td{padding:8px 10px;border-bottom:1px solid #eef0f5;text-align:left;vertical-align:top}tr.failed td{background:#fff5f6}
code{display:block;color:#3b3f8f;font-size:12px;word-break:break-all}ul{margin:0;padding-left:16px}li.ok{color:#0f5c33}li.bad{color:#a13049}
li span{color:#5b6275}li.note{color:#5b6275;list-style:circle}.failures{background:#fff;border:1px solid #f2b8bd;border-radius:10px;padding:12px 20px;margin-bottom:20px}
</style></head><body><main>
<h1>${escapeHtml(report.test.name)}</h1>
<div class="meta">${escapeHtml(report.test.url)} &middot; ${escapeHtml(report.browser)} &middot; started ${escapeHtml(summary.startedAt || '')} &middot; run ${escapeHtml(report.runId)}</div>
<div class="cards">
<div class="card">Result<b class="${report.status === 'passed' ? 'passed-badge' : 'failed-badge'}">${escapeHtml(String(report.status).toUpperCase())}</b></div>
<div class="card">Steps passed<b>${summary.steps.passed ?? 0} / ${summary.steps.total ?? 0}</b></div>
<div class="card">Steps failed<b>${summary.steps.failed ?? 0}</b></div>
<div class="card">Assertions passed<b>${summary.assertions.passed ?? 0} / ${summary.assertions.total ?? 0}</b></div>
<div class="card">Duration<b>${seconds}</b></div>
${report.healedSteps ? `<div class="card">XPaths refreshed<b>${report.healedSteps}</b></div>` : ''}
</div>
${failures ? `<div class="failures"><h3>Failures</h3><ul>${failures}</ul></div>` : ''}
<table><thead><tr><th>#</th><th>Step</th><th>Status</th><th>Soft assertions</th></tr></thead><tbody>${rows}</tbody></table>
</main></body></html>`
}
