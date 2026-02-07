(() => {
  const root = document.getElementById("chat-stream-island");
  if (!root) return;

  const form = root.closest(".chat-panel")?.querySelector("form.composer");
  if (!form) return;

  const streamHiddenName = "stream";
  let stream = null;

  root.innerHTML = `
    <label class="flex items-center gap-2 text-sm text-slate-300">
      <input class="h-4 w-4 rounded border-slate-600 bg-slate-900" type="checkbox" data-role="toggle" />
      <span>Enable optional chat stream</span>
    </label>
    <div class="mt-2 text-xs text-slate-500" data-role="status">HTMX-only mode</div>
    <pre class="mt-2 min-h-[2.5rem] whitespace-pre-wrap rounded-md bg-slate-900/70 p-2 font-mono text-xs text-slate-300" data-role="output" aria-live="polite"></pre>
  `;

  const toggle = root.querySelector('[data-role="toggle"]');
  const statusEl = root.querySelector('[data-role="status"]');
  const outputEl = root.querySelector('[data-role="output"]');

  const setStatus = (text) => {
    if (statusEl) statusEl.textContent = text;
  };

  const setStreamField = (enabled) => {
    let streamField = form.querySelector(`input[name="${streamHiddenName}"]`);
    if (enabled) {
      if (!streamField) {
        streamField = document.createElement("input");
        streamField.type = "hidden";
        streamField.name = streamHiddenName;
        form.appendChild(streamField);
      }
      streamField.value = "1";
    } else if (streamField) {
      streamField.remove();
    }
  };

  const clearStream = () => {
    if (stream) {
      stream.close();
      stream = null;
    }
  };

  const appendChunk = (text) => {
    if (!outputEl) return;
    outputEl.textContent += text;
  };

  const startStream = (streamUrl) => {
    if (!("EventSource" in window)) {
      setStatus("SSE unavailable. HTMX-only mode.");
      return;
    }
    clearStream();
    if (outputEl) outputEl.textContent = "";

    stream = new EventSource(streamUrl);
    setStatus("Streaming response...");

    stream.addEventListener("chat_chunk", (event) => {
      try {
        const payload = JSON.parse(event.data);
        appendChunk(payload.chunk || "");
      } catch {
        setStatus("Stream parse error. HTMX-only mode.");
        clearStream();
      }
    });

    stream.addEventListener("chat_complete", () => {
      setStatus("Stream complete.");
      clearStream();
    });

    stream.addEventListener("error", () => {
      setStatus("Stream disconnected. HTMX-only mode.");
      clearStream();
    });
  };

  toggle?.addEventListener("change", () => {
    const enabled = Boolean(toggle.checked);
    setStreamField(enabled);
    if (!enabled) {
      clearStream();
      setStatus("HTMX-only mode");
      if (outputEl) outputEl.textContent = "";
      return;
    }
    setStatus("Stream mode armed. Send a message.");
  });

  form.addEventListener("htmx:afterRequest", (event) => {
    if (!toggle?.checked) return;
    const xhr = event.detail?.xhr;
    if (!xhr) return;
    const streamUrl = xhr.getResponseHeader("X-UI-Stream-Url");
    if (!streamUrl) return;
    startStream(streamUrl);
  });

  window.addEventListener("beforeunload", clearStream);
})();
