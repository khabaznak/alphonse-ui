(() => {
  const root = document.querySelector('[data-island="presence"]');
  if (!root) return;

  const statusEl = root.querySelector('[data-role="status"]');
  const logEl = root.querySelector('[data-role="log"]');
  const pauseBtn = root.querySelector('[data-role="pause"]');
  const resumeBtn = root.querySelector('[data-role="resume"]');

  let source = null;

  const appendLine = (text) => {
    if (!logEl) return;
    const line = document.createElement('div');
    line.textContent = text;
    logEl.appendChild(line);
    logEl.scrollTop = logEl.scrollHeight;
  };

  const setStatus = (text) => {
    if (statusEl) statusEl.textContent = text;
  };

  const connect = () => {
    if (!('EventSource' in window)) {
      setStatus('Streaming not supported in this browser.');
      return;
    }

    source = new EventSource('/stream/presence');
    source.addEventListener('presence', (event) => {
      try {
        const payload = JSON.parse(event.data);
        appendLine(`[presence] ${payload.timestamp}`);
      } catch {
        appendLine('[presence] received');
      }
    });

    source.addEventListener('error', () => {
      setStatus('Stream disconnected.');
    });

    setStatus('Stream connected.');
  };

  const disconnect = () => {
    if (source) {
      source.close();
      source = null;
      setStatus('Stream paused.');
    }
  };

  if (pauseBtn) pauseBtn.addEventListener('click', (event) => {
    event.preventDefault();
    disconnect();
  });

  if (resumeBtn) resumeBtn.addEventListener('click', (event) => {
    event.preventDefault();
    if (!source) connect();
  });

  connect();

  window.addEventListener('beforeunload', () => {
    if (source) source.close();
  });
})();
