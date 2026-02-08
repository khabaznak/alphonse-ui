(function () {
  const form = document.querySelector("form.composer");
  if (!form) return;

  const textarea = form.querySelector("textarea[name='message']");
  if (!textarea) return;

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
})();
