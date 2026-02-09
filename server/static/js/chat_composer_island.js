(function () {
  const scrollTimeline = () => {
    const timeline = document.getElementById("chat-timeline");
    if (!timeline) return;
    timeline.scrollTop = timeline.scrollHeight;
  };

  const mount = (scope) => {
    const form =
      scope && scope.matches && scope.matches("form.composer")
        ? scope
        : scope && scope.querySelector
          ? scope.querySelector("form.composer")
          : document.querySelector("form.composer");
    if (!form) return;
    if (form.dataset.composerMounted === "1") return;
    form.dataset.composerMounted = "1";

    const textarea = form.querySelector("textarea[name='message']");
    if (!textarea) return;

    const clearComposer = () => {
      textarea.value = "";
      textarea.focus();
    };

    form.addEventListener("htmx:afterRequest", (event) => {
      const xhr = event.detail && event.detail.xhr;
      if (!xhr) return;
      if (xhr.status >= 200 && xhr.status < 300) {
        clearComposer();
      }
    });

    textarea.addEventListener("keydown", (event) => {
      if (event.key !== "Enter") return;
      if (event.shiftKey) return;
      if (event.isComposing) return;

      event.preventDefault();
      if (typeof form.requestSubmit === "function") {
        form.requestSubmit();
        return;
      }
      form.submit();
    });
  };

  mount(document);
  scrollTimeline();

  document.body.addEventListener("htmx:load", (event) => {
    mount(event.target);
  });

  document.body.addEventListener("htmx:afterSwap", (event) => {
    const target = event.detail && event.detail.target;
    if (!target) return;
    if (target.id !== "chat-timeline") return;
    requestAnimationFrame(scrollTimeline);
  });
})();
