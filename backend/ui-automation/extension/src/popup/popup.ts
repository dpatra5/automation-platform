const statusEl = document.getElementById('status')!;
const statusText = document.getElementById('statusText')!;
const dot = document.getElementById('dot')!;
const controls = document.getElementById('controls')!;
const pauseBtn = document.getElementById('pauseBtn') as HTMLButtonElement;
const stopBtn = document.getElementById('stopBtn') as HTMLButtonElement;
const stepInfo = document.getElementById('stepInfo')!;
const stepCountEl = document.getElementById('stepCount')!;
const elapsedEl = document.getElementById('elapsed')!;
const errorMsg = document.getElementById('errorMsg')!;

interface Status {
  isRecording: boolean;
  isSaving: boolean;
  stepCount: number;
  startedAt: number | null;
  paused: boolean;
}

let startedAt: number | null = null;

function formatElapsed(): string {
  if (!startedAt) return '0:00';
  const total = Math.max(0, Math.floor((Date.now() - startedAt) / 1000));
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`;
}

function updateUI(status: Status) {
  const { isRecording, isSaving, stepCount, paused } = status;
  startedAt = status.startedAt;

  const mode = isSaving ? 'saving' : paused ? 'paused' : isRecording ? 'recording' : 'idle';
  const label = {
    saving: 'Saving recording…',
    paused: 'Paused',
    recording: 'Recording',
    idle: 'Not recording',
  }[mode];

  statusEl.className = `status ${mode}`;
  dot.className = `dot ${mode}`;
  statusText.textContent = label;

  const active = isRecording || isSaving;
  stepInfo.style.display = active ? 'flex' : 'none';
  controls.style.display = active ? 'flex' : 'none';
  stepCountEl.textContent = String(stepCount);
  elapsedEl.textContent = formatElapsed();

  pauseBtn.textContent = paused ? 'Resume' : 'Pause';
  pauseBtn.disabled = isSaving;
  stopBtn.disabled = isSaving || stepCount === 0;
}

function refresh() {
  chrome.runtime.sendMessage({ type: 'GET_STATUS' }, (status: Status) => {
    if (chrome.runtime.lastError || !status) return;
    updateUI(status);
  });
}

refresh();
setInterval(refresh, 1000);
// The elapsed clock ticks independently of the polling round trip.
setInterval(() => { elapsedEl.textContent = formatElapsed(); }, 1000);

pauseBtn.addEventListener('click', () => {
  chrome.runtime.sendMessage({ type: 'TOGGLE_PAUSE' }, () => refresh());
});

stopBtn.addEventListener('click', () => {
  stopBtn.disabled = true;
  stopBtn.textContent = 'Saving…';
  errorMsg.style.display = 'none';

  chrome.runtime.sendMessage({ type: 'STOP_RECORDING' }, (response) => {
    if (response?.success) {
      window.close(); // A dashboard tab opens with the new test case.
      return;
    }
    stopBtn.disabled = false;
    stopBtn.textContent = 'Stop';
    errorMsg.textContent = response?.error || 'Failed to save recording. Try again.';
    errorMsg.style.display = 'block';
  });
});
