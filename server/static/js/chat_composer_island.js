(function () {
  const scrollTimeline = () => {
    const timeline = document.getElementById("chat-timeline");
    if (!timeline) return;
    timeline.scrollTop = timeline.scrollHeight;
  };

  const refreshTimeline = () => {
    if (window.htmx) {
      window.htmx.ajax("GET", "/chat/timeline", {
        target: "#chat-timeline",
        swap: "innerHTML",
      });
      return;
    }
    fetch("/chat/timeline", { credentials: "same-origin" })
      .then((response) => {
        if (!response.ok) throw new Error("Timeline refresh failed");
        return response.text();
      })
      .then((html) => {
        const timeline = document.getElementById("chat-timeline");
        if (!timeline) return;
        timeline.innerHTML = html;
        scrollTimeline();
      })
      .catch(() => {});
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

    const voiceRoot = form.querySelector(".voice-controls");
    if (!voiceRoot) return;
    if (voiceRoot.dataset.voiceMounted === "1") return;
    voiceRoot.dataset.voiceMounted = "1";

    const voiceButton = voiceRoot.querySelector("[data-role='voice-toggle']");
    const voiceStatus = voiceRoot.querySelector("[data-role='voice-status']");
    const voiceError = voiceRoot.querySelector("[data-role='voice-error']");
    const audioModeToggle = voiceRoot.querySelector("input[name='audio_mode_local']");
    if (!voiceButton || !voiceStatus || !voiceError || !audioModeToggle) return;

    const setStatus = (status) => {
      voiceStatus.textContent = status;
    };

    const setError = (message) => {
      if (!message) {
        voiceError.textContent = "";
        voiceError.classList.add("hidden");
        return;
      }
      voiceError.textContent = message;
      voiceError.classList.remove("hidden");
    };

    const supportsMediaRecorder =
      typeof window.MediaRecorder !== "undefined" &&
      navigator.mediaDevices &&
      typeof navigator.mediaDevices.getUserMedia === "function";

    if (!supportsMediaRecorder) {
      voiceButton.disabled = true;
      setStatus("Waiting (mic unavailable)");
      setError("This browser does not support microphone recording.");
      return;
    }

    let mediaRecorder = null;
    let mediaStream = null;
    let chunks = [];
    let isRecording = false;
    let isUploading = false;

    const preferredMimeType = () => {
      const candidates = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"];
      for (const candidate of candidates) {
        if (window.MediaRecorder.isTypeSupported(candidate)) return candidate;
      }
      return "";
    };

    const fileNameForMime = (mimeType) => {
      if ((mimeType || "").includes("ogg")) return `voice-${Date.now()}.ogg`;
      if ((mimeType || "").includes("mp4")) return `voice-${Date.now()}.mp4`;
      if ((mimeType || "").includes("wav")) return `voice-${Date.now()}.wav`;
      return `voice-${Date.now()}.webm`;
    };

    const stopTracks = () => {
      if (!mediaStream) return;
      mediaStream.getTracks().forEach((track) => track.stop());
      mediaStream = null;
    };

    const uploadAudio = async (blob, mimeType) => {
      const correlationId = `ui-${Date.now()}`;
      const formData = new FormData();
      formData.append("audio", blob, fileNameForMime(mimeType));
      formData.append("audio_mode", audioModeToggle.checked ? "local_audio" : "none");
      formData.append("correlation_id", correlationId);
      formData.append("provider", "webui");
      formData.append("channel", "webui");

      const response = await fetch("/chat/voice", {
        method: "POST",
        body: formData,
        credentials: "same-origin",
      });
      if (!response.ok) {
        let reason = "Audio upload failed.";
        try {
          const payload = await response.json();
          if (payload && typeof payload.error === "string") {
            reason = `Audio upload failed: ${payload.error}`;
          }
        } catch (_) {}
        throw new Error(reason);
      }
    };

    const beginRecording = async () => {
      if (isUploading || isRecording) return;
      setError("");
      try {
        mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      } catch (_) {
        setError("Microphone access was denied.");
        setStatus("Waiting");
        return;
      }

      chunks = [];
      const mimeType = preferredMimeType();
      mediaRecorder = mimeType
        ? new window.MediaRecorder(mediaStream, { mimeType })
        : new window.MediaRecorder(mediaStream);

      mediaRecorder.addEventListener("dataavailable", (event) => {
        if (event.data && event.data.size > 0) {
          chunks.push(event.data);
        }
      });

      mediaRecorder.addEventListener("stop", async () => {
        isRecording = false;
        voiceButton.textContent = "🎙️ Hablar";
        stopTracks();
        const blob = new Blob(chunks, { type: mediaRecorder && mediaRecorder.mimeType ? mediaRecorder.mimeType : "audio/webm" });
        chunks = [];
        if (!blob.size) {
          setStatus("Waiting");
          setError("No audio was captured.");
          return;
        }

        isUploading = true;
        voiceButton.disabled = true;
        setStatus("Uploading");
        try {
          await uploadAudio(blob, blob.type);
          setStatus("Waiting");
          setError("");
          refreshTimeline();
        } catch (error) {
          setStatus("Waiting");
          setError(error instanceof Error ? error.message : "Audio upload failed.");
        } finally {
          isUploading = false;
          voiceButton.disabled = false;
        }
      });

      mediaRecorder.start();
      isRecording = true;
      voiceButton.textContent = "⏹️ Detener";
      setStatus("Recording");
    };

    const stopRecording = () => {
      if (!mediaRecorder || mediaRecorder.state !== "recording") return;
      mediaRecorder.stop();
    };

    voiceButton.addEventListener("click", () => {
      if (isUploading) return;
      if (isRecording) {
        stopRecording();
        return;
      }
      beginRecording();
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
