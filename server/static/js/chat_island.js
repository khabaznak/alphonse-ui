(() => {
  const root = document.querySelector('[data-island="chat"]');
  if (!root) return;

  const statusEl = root.querySelector('[data-role="status"]');
  const logEl = root.querySelector('[data-role="log"]');
  const form = root.querySelector('[data-role="form"]');

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

  const connectStream = () => {
    if (!('EventSource' in window)) {
      setStatus('Streaming not supported in this browser.');
      return null;
    }

    const source = new EventSource('/stream/chat');
    source.addEventListener('chat', (event) => {
      try {
        const payload = JSON.parse(event.data);
        appendLine(`[stream] ${payload.timestamp}`);
      } catch {
        appendLine('[stream] received');
      }
    });

    source.addEventListener('error', () => {
      setStatus('Stream disconnected.');
    });

    setStatus('Stream connected.');
    return source;
  };

  let stream = connectStream();

  if (form) {
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const textarea = form.querySelector('textarea[name="message"]');
      const value = textarea ? textarea.value.trim() : '';
      if (!value) {
        appendLine('[local] (empty message)');
        return;
      }

      appendLine(`[local] ${value}`);
      if (textarea) textarea.value = '';

      try {
        const response = await fetch('/chat/send', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: value }),
        });
        if (response.ok) {
          const payload = await response.json();
          appendLine(`[ack] ${payload.received_at}`);
        } else {
          appendLine('[ack] failed to send');
        }
      } catch {
        appendLine('[ack] network error');
      }
    });
  }

  window.addEventListener('beforeunload', () => {
    if (stream) stream.close();
  });
})();
