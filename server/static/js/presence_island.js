(() => {
  let activeStream = null;

  const POLL_TRIGGER = "load, every 20s";

  const closeActiveStream = () => {
    if (activeStream) {
      activeStream.close();
      activeStream = null;
    }
  };

  const enablePollingFallback = (root) => {
    root.setAttribute("hx-get", "/ui/presence");
    root.setAttribute("hx-trigger", POLL_TRIGGER);
    root.setAttribute("hx-swap", "innerHTML");
    if (window.htmx) {
      window.htmx.process(root);
    }
  };

  const useSingleLoad = (root) => {
    root.setAttribute("hx-get", "/ui/presence");
    root.setAttribute("hx-trigger", "load");
    root.setAttribute("hx-swap", "innerHTML");
    if (window.htmx) {
      window.htmx.process(root);
    }
  };

  const renderPresence = (root, payload) => {
    const presence = payload.presence || {};
    const status = presence.status || "unknown";
    const note = presence.note || "No note";
    const timestamp = payload.timestamp || "";

    root.innerHTML = `
      <div class="space-y-2">
        <div>
          <div class="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500">Status</div>
          <div class="text-sm text-slate-200">${status}</div>
        </div>
        <div>
          <div class="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500">Note</div>
          <div class="text-sm text-slate-300">${note}</div>
        </div>
        <div>
          <div class="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500">As of</div>
          <div class="text-sm text-slate-400">${timestamp}</div>
        </div>
      </div>
    `;
  };

  const mount = (scope) => {
    const root =
      scope && scope.id === "presence-island"
        ? scope
        : scope && scope.querySelector
          ? scope.querySelector("#presence-island")
          : document.getElementById("presence-island");
    if (!root) return;
    if (root.dataset.presenceIslandMounted === "1") return;
    root.dataset.presenceIslandMounted = "1";

    closeActiveStream();

    if (!("EventSource" in window)) {
      enablePollingFallback(root);
      return;
    }

    useSingleLoad(root);

    activeStream = new EventSource("/stream/presence");
    const stream = activeStream;

    stream.addEventListener("presence", (event) => {
      try {
        const payload = JSON.parse(event.data);
        renderPresence(root, payload);
      } catch {
        enablePollingFallback(root);
        closeActiveStream();
      }
    });

    stream.addEventListener("error", () => {
      enablePollingFallback(root);
      closeActiveStream();
    });
  };

  mount(document);

  document.body.addEventListener("htmx:load", (event) => {
    mount(event.target);
  });

  document.body.addEventListener("htmx:beforeSwap", (event) => {
    const target = event.detail && event.detail.target;
    if (target && target.id === "main-panel") {
      closeActiveStream();
    }
  });

  window.addEventListener("beforeunload", () => {
    closeActiveStream();
  });
})();
