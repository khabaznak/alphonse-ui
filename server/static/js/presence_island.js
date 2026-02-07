(() => {
  const root = document.getElementById("presence-island");
  if (!root) return;

  const POLL_TRIGGER = "load, every 20s";

  const enablePollingFallback = () => {
    root.setAttribute("hx-get", "/ui/presence");
    root.setAttribute("hx-trigger", POLL_TRIGGER);
    root.setAttribute("hx-swap", "innerHTML");
    if (window.htmx) {
      window.htmx.process(root);
    }
  };

  const useSingleLoad = () => {
    root.setAttribute("hx-get", "/ui/presence");
    root.setAttribute("hx-trigger", "load");
    root.setAttribute("hx-swap", "innerHTML");
    if (window.htmx) {
      window.htmx.process(root);
    }
  };

  const renderPresence = (payload) => {
    const presence = payload.presence || {};
    const status = presence.status || "unknown";
    const note = presence.note || "No note";
    const timestamp = payload.timestamp || "";

    root.innerHTML = `
      <div class="presence">
        <div class="presence-row">
          <div class="presence-label">Status</div>
          <div class="presence-value">${status}</div>
        </div>
        <div class="presence-row">
          <div class="presence-label">Note</div>
          <div class="presence-value">${note}</div>
        </div>
        <div class="presence-row">
          <div class="presence-label">As of</div>
          <div class="presence-value">${timestamp}</div>
        </div>
      </div>
    `;
  };

  if (!("EventSource" in window)) {
    enablePollingFallback();
    return;
  }

  useSingleLoad();

  const stream = new EventSource("/stream/presence");

  stream.addEventListener("presence", (event) => {
    try {
      const payload = JSON.parse(event.data);
      renderPresence(payload);
    } catch {
      enablePollingFallback();
      stream.close();
    }
  });

  stream.addEventListener("error", () => {
    enablePollingFallback();
    stream.close();
  });

  window.addEventListener("beforeunload", () => {
    stream.close();
  });
})();
