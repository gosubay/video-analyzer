/* ───────────────────────────── Video Analyzer — app.js ─────────────────────
   Talks to server.py over plain fetch. Keeps a queue on this side, polls the
   server for progress while a run is going, and draws the three views.
   ───────────────────────────────────────────────────────────────────────── */

const $  = (id) => document.getElementById(id);
const el = (tag, cls, text) => {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
};

// Mirror of core.py's ladder, so the frame estimate updates instantly.
const LADDER = [1, 2, 3, 5, 10, 30, 60];
const TARGET_FRAMES = 30;

const state = {
  mode: "frames",           // "frames" | "video" - which mode new items are added as
  queue: [],
  polling: null,
  results: [],
  lightbox: { frames: [], index: 0 },
  clipboardOffered: "",
};

function setMode(mode) {
  state.mode = mode;
  $("mode-frames").classList.toggle("active", mode === "frames");
  $("mode-video").classList.toggle("active", mode === "video");
  $("url-input").placeholder = mode === "video"
    ? "Paste a YouTube, Instagram, Facebook or TikTok link here…"
    : "Paste a YouTube link here…";
  $("go-left").hidden = mode === "video";
  $("sidebar-foot").hidden = mode === "video";
  if (state.hasPicker) $("pick-file").hidden = mode === "video";
  renderQueue();
}

/* ───────────────────────────── helpers ───────────────────────────── */
async function api(path, payload) {
  const options = payload === undefined
    ? { method: "GET" }
    : { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload) };
  const response = await fetch(path, options);
  const data = await response.json().catch(() => ({ error: "The app did not answer properly." }));
  if (!response.ok) throw new Error(data.error || "Something went wrong.");
  return data;
}

function chooseInterval(duration) {
  const ideal = duration / TARGET_FRAMES;
  return LADDER.find((step) => step >= ideal) ?? 60;
}

function frameEstimate(duration, interval) {
  if (!duration || !interval) return 0;
  return Math.floor((duration - 1e-9) / interval) + 1;
}

function prettyTime(seconds) {
  seconds = Math.round(seconds || 0);
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`
           : `${m}:${String(s).padStart(2, "0")}`;
}

let toastTimer = null;
function toast(message) {
  const node = $("toast");
  node.textContent = message;
  node.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { node.hidden = true; }, 2600);
}

function setMascot(mood) { $("mascot-wrap").dataset.state = mood; }

function setGreeting(title, sub) {
  $("greet-title").textContent = title;
  $("greet-sub").textContent = sub;
}

function showView(name) {
  for (const view of ["setup", "working", "results"]) {
    $(`view-${view}`).hidden = view !== name;
  }
}

/* ───────────────────────────── queue ───────────────────────────── */
function currentInterval() {
  const raw = $("interval-select").value;
  return raw ? Number(raw) : null;
}

function renderQueue() {
  const box = $("queue");
  box.textContent = "";
  const forced = currentInterval();

  state.queue.forEach((item, index) => {
    const isVideoMode = item.mode === "video";
    const row = el("div", "q-item");

    if (item.thumbnail) {
      const img = el("img", "q-thumb");
      img.src = item.thumbnail;
      img.alt = "";
      row.append(img);
    } else {
      row.append(el("div", "q-thumb placeholder", isVideoMode ? "⬇️" : "🎞️"));
    }

    const info = el("div", "q-info");
    info.append(el("div", "q-title", item.title));
    const meta = el("div", "q-meta");
    meta.append(document.createTextNode(item.duration_pretty));
    if (isVideoMode) {
      meta.append(el("span", "sep", "·"));
      meta.append(document.createTextNode("video only, no frames"));
    } else {
      const interval = forced || chooseInterval(item.duration_seconds);
      const frames = frameEstimate(item.duration_seconds, interval);
      meta.append(el("span", "sep", "·"));
      meta.append(document.createTextNode(`${frames} frames`));
      meta.append(el("span", "sep", "·"));
      meta.append(document.createTextNode(`one every ${interval}s`));
    }
    info.append(meta);
    row.append(info);

    const remove = el("button", "q-remove", "✕");
    remove.title = "Take this one out";
    remove.onclick = () => { state.queue.splice(index, 1); renderQueue(); };
    row.append(remove);

    box.append(row);
  });

  const any = state.queue.length > 0;
  $("queue-block").hidden = !any;
  $("go-card").hidden = !any;
  $("tips").hidden = any;
  $("queue-count").textContent = state.queue.length;
  $("start-btn").textContent = state.queue.length > 1
    ? `Let's go — ${state.queue.length} videos ✨`
    : "Let's go ✨";
}

async function addSource(source) {
  const input = $("url-input");
  const errorSlot = $("add-error");
  errorSlot.textContent = "";

  if (!source) return;
  if (state.queue.some((item) => item.source === source)) {
    errorSlot.textContent = "That one is already in the queue.";
    return;
  }

  $("add-btn").disabled = true;
  $("add-btn").textContent = "Looking…";
  try {
    const info = await api("/api/inspect", { source, interval: currentInterval(), mode: state.mode });
    state.queue.push(info);
    input.value = "";
    renderQueue();
    setMascot("idle");
  } catch (error) {
    errorSlot.textContent = error.message;
    setMascot("error");
    setTimeout(() => { if (!$("view-working").hidden === false) setMascot("idle"); }, 2600);
  } finally {
    $("add-btn").disabled = false;
    $("add-btn").textContent = "Add";
  }
}

/* ───────────────────────────── running ───────────────────────────── */
function renderLiveQueue(snapshot) {
  const box = $("queue-live");
  box.textContent = "";

  snapshot.queue.forEach((item) => {
    const row = el("div", `q-item ${item.status}`);
    if (item.thumbnail) {
      const img = el("img", "q-thumb");
      img.src = item.thumbnail;
      img.alt = "";
      row.append(img);
    } else {
      row.append(el("div", "q-thumb placeholder", "🎞️"));
    }

    const info = el("div", "q-info");
    info.append(el("div", "q-title", item.title));
    if (item.error) {
      info.append(el("div", "q-error", item.error));
    } else if (item.mode === "video") {
      info.append(el("div", "q-meta", `${item.duration_pretty || ""} · video only`));
    } else {
      info.append(el("div", "q-meta", `${item.duration_pretty || ""} · ${item.frame_count || "?"} frames`));
    }
    row.append(info);

    const labels = {
      waiting: "waiting", working: "working", done: "done ✓",
      failed: "failed", cancelled: "stopped",
    };
    row.append(el("span", `q-status ${item.status}`, labels[item.status] || item.status));
    box.append(row);
  });
}

function renderProgress(snapshot) {
  const item = snapshot.queue[snapshot.current] || {};
  $("work-title").textContent = item.title || "Working…";
  $("work-of").textContent = snapshot.queue.length > 1
    ? `video ${snapshot.current + 1} of ${snapshot.queue.length}`
    : "";

  const videoMode = item.mode === "video";
  const wantsScript = !!snapshot.transcript;
  // How the bar is divided up depends on which stages this run actually has.
  const span = videoMode
    ? (wantsScript ? { download: 60, extract: 0,  transcribe: 37 }
                   : { download: 90, extract: 0,  transcribe: 0 })
    : (wantsScript ? { download: 35, extract: 35, transcribe: 27 }
                   : { download: 45, extract: 52, transcribe: 0 });

  let percent = 0;
  let stageText = "Getting ready…";

  if (snapshot.stage === "download") {
    percent = snapshot.percent * (span.download / 100);
    stageText = `Downloading the video… ${Math.round(snapshot.percent)}%`;
  } else if (snapshot.stage === "extract") {
    const done = snapshot.frames_done;
    const total = snapshot.frames_total || 1;
    percent = span.download + (done / total) * span.extract;
    stageText = done === 0
      ? `Getting ready to grab ${total} frames…`
      : `Grabbing frames… ${done} of ${total}`;
  } else if (snapshot.stage === "transcribe") {
    percent = span.download + span.extract + (snapshot.percent / 100) * span.transcribe;
    stageText = snapshot.percent < 1
      ? "Warming up the transcriber…"
      : `Listening for the script… ${Math.round(snapshot.percent)}%`;
  } else if (snapshot.stage === "saving") {
    percent = 98;
    stageText = videoMode ? "Saving the video…" : "Writing the manifest…";
  } else if (snapshot.stage === "metadata") {
    percent = 4;
    stageText = "Reading the video details…";
  }

  $("bar-fill").style.width = `${Math.max(2, Math.min(100, percent))}%`;
  $("work-stage").textContent = stageText;

  const dots = $("frame-dots");
  const total = videoMode ? 0 : (snapshot.frames_total || 0);
  if (dots.childElementCount !== total) {
    dots.textContent = "";
    for (let i = 0; i < total; i += 1) dots.append(el("i"));
  }
  [...dots.children].forEach((dot, index) => {
    dot.classList.toggle("on", index < snapshot.frames_done);
  });

  renderLiveQueue(snapshot);
}

async function poll() {
  let snapshot;
  try {
    snapshot = await api("/api/state");
  } catch {
    return;                                   // server briefly busy; try again next tick
  }

  if (snapshot.phase === "working") {
    renderProgress(snapshot);
    return;
  }

  clearInterval(state.polling);
  state.polling = null;

  if (snapshot.phase === "cancelled") {
    setMascot("idle");
    setGreeting("Stopped.", "Nothing was left behind — half-finished folders get cleaned up.");
    showView("setup");
    toast("Stopped");
  } else if (snapshot.phase === "error") {
    setMascot("error");
    setGreeting("That didn't work.", snapshot.error || "Something went wrong.");
    showView("setup");
  } else {
    state.results = snapshot.results;
    renderResults(snapshot);
    const failed = snapshot.queue.filter((q) => q.status === "failed");
    if (failed.length) toast(`${failed.length} didn't work — see the notes above`);
  }

  state.queue = [];
  renderQueue();
  loadHistory();
}

async function start() {
  if (!state.queue.length) return;
  try {
    await api("/api/start", {
      items: state.queue,
      interval: currentInterval(),
      keep_video: $("keep-video").checked,
      transcript: $("want-transcript").checked,
    });
  } catch (error) {
    toast(error.message);
    return;
  }
  setMascot("working");
  setGreeting("On it!", $("want-transcript").checked
    ? "Grabbing your frames and listening for the script. You can stop any time."
    : "Grabbing your frames. You can stop any time.");
  showView("working");
  $("cancel-btn").disabled = false;
  $("cancel-btn").textContent = "Stop";
  state.polling = setInterval(poll, 280);
  poll();
}

/* ───────────────────────────── results ───────────────────────────── */
function confetti() {
  const box = $("confetti");
  const colors = ["#A78BFA", "#6EE7B7", "#FDBA74", "#F9A8D4", "#93C5FD"];
  for (let i = 0; i < 46; i += 1) {
    const bit = el("i");
    bit.style.left = `${Math.random() * 100}%`;
    bit.style.background = colors[i % colors.length];
    bit.style.animationDuration = `${1.7 + Math.random() * 1.5}s`;
    bit.style.animationDelay = `${Math.random() * 0.45}s`;
    box.append(bit);
    setTimeout(() => bit.remove(), 3600);
  }
}

function renderResults(snapshot) {
  const box = $("results");
  box.textContent = "";

  snapshot.results.forEach((result) => {
    const isVideoMode = result.mode === "video";
    const card = el("div", "result-card");

    const head = el("div", "result-head");
    const left = el("div");
    left.append(el("div", "result-title", result.title));
    const meta = el("div", "result-meta");
    if (isVideoMode) {
      meta.append(document.createTextNode("video downloaded"));
      meta.append(el("span", "dot", "•"));
      meta.append(document.createTextNode(result.duration_pretty));
    } else {
      meta.append(document.createTextNode(`${result.frame_count} frames`));
      meta.append(el("span", "dot", "•"));
      meta.append(document.createTextNode(`one every ${result.interval_seconds}s`));
      meta.append(el("span", "dot", "•"));
      meta.append(document.createTextNode(result.duration_pretty));
    }
    if (result.transcript) {
      meta.append(el("span", "dot", "•"));
      meta.append(document.createTextNode("🎙️ script included"));
    } else if (result.transcript_error) {
      meta.append(el("span", "dot", "•"));
      meta.append(document.createTextNode("no script"));
    }
    left.append(meta);
    if (result.transcript_error) {
      left.append(el("div", "result-note", result.transcript_error));
    }
    head.append(left);

    const actions = el("div", "result-actions");

    const openBtn = el("button", "btn btn-soft", "📂 Open folder");
    openBtn.onclick = () => api("/api/open", { path: result.folder })
      .catch((error) => toast(error.message));
    actions.append(openBtn);

    if (result.transcript_txt) {
      const scriptBtn = el("button", "btn btn-soft", "📝 Open script");
      scriptBtn.onclick = () => api("/api/open", { path: result.transcript_txt })
        .catch((error) => toast(error.message));
      actions.append(scriptBtn);
    }

    if (!isVideoMode) {
      const copyBtn = el("button", "btn btn-soft", "📋 Copy for Claude");
      copyBtn.onclick = async () => {
        const text =
          `Frames folder: ${result.folder}\n` +
          `Manifest: ${result.manifest}\n` +
          (result.transcript ? `Transcript: ${result.transcript}\n` : "") +
          `${result.frame_count} frames, one every ${result.interval_seconds}s, ` +
          `from "${result.title}" (${result.duration_pretty})` +
          (result.transcript
            ? ". transcript.json has the spoken words with start and end times "
              + "in seconds, on the same clock as the frames."
            : "");
        try {
          await navigator.clipboard.writeText(text);
        } catch {
          await api("/api/copy", { text });
        }
        toast("Copied — paste it into Claude");
      };
      actions.append(copyBtn);
    }

    head.append(actions);
    card.append(head);

    if (!isVideoMode) {
      const grid = el("div", "grid");
      result.frames.forEach((frame, index) => {
        const shot = el("button", "shot");
        const img = el("img");
        img.src = frame.url;
        img.alt = `Frame at ${frame.label}`;
        img.loading = "lazy";
        shot.append(img, el("span", null, frame.label));
        shot.onclick = () => openLightbox(result.frames, index);
        grid.append(shot);
      });
      card.append(grid);
    }
    box.append(card);
  });

  const total = snapshot.results.reduce((sum, r) => sum + (r.frame_count || 0), 0);
  const videosOnly = snapshot.results.filter((r) => r.mode === "video").length;
  const scripts = snapshot.results.filter((r) => r.transcript).length;
  const scriptBit = scripts ? ` ${scripts} script${scripts > 1 ? "s" : ""} too.` : "";
  setMascot("done");
  if (total) {
    setGreeting("All done! 🎉", `${total} frames saved.${scriptBit} Click any one to see it bigger.`);
  } else if (videosOnly) {
    setGreeting("All done! 🎉", `${videosOnly} video${videosOnly > 1 ? "s" : ""} downloaded.${scriptBit}`);
  } else {
    setGreeting("All done! 🎉", "Nothing came out of that.");
  }
  showView("results");
  if (total) confetti();
}

/* ───────────────────────────── lightbox ───────────────────────────── */
function openLightbox(frames, index) {
  state.lightbox = { frames, index };
  drawLightbox();
  $("lightbox").hidden = false;
}

function drawLightbox() {
  const { frames, index } = state.lightbox;
  const frame = frames[index];
  if (!frame) return;
  $("lb-img").src = frame.url;
  $("lb-caption").textContent = `${frame.label}  ·  ${frame.filename}`;
}

function stepLightbox(delta) {
  const { frames, index } = state.lightbox;
  state.lightbox.index = (index + delta + frames.length) % frames.length;
  drawLightbox();
}

function closeLightbox() { $("lightbox").hidden = true; }

/* ───────────────────────────── history ───────────────────────────── */
async function loadHistory() {
  let items = [];
  try {
    ({ items } = await api("/api/history", {}));
  } catch { return; }

  const box = $("history");
  box.textContent = "";

  if (!items.length) {
    const note = el("p", "empty-note");
    note.innerHTML = "Nothing yet.<br>Your videos will show up here.";
    box.append(note);
    return;
  }

  items.forEach((item) => {
    const row = el("button", "hist-item");
    row.title = "Open this folder";
    row.onclick = () => api("/api/open", { path: item.folder })
      .catch((error) => toast(error.message));

    const title = el("span", "hist-title");
    title.append(el("span", "hist-num", String(item.number)));
    title.append(document.createTextNode(item.title));
    row.append(title);

    const bits = [`${item.frame_count} frames`];
    if (item.duration_pretty) bits.push(item.duration_pretty);
    row.append(el("span", "hist-meta", bits.join(" · ")));

    const del = el("span", "hist-del", "✕");
    del.title = "Delete this folder";
    del.onclick = async (event) => {
      event.stopPropagation();
      if (!confirm(`Delete the whole folder "${item.folder_name}"?\n\nThis cannot be undone.`)) return;
      try {
        await api("/api/delete", { path: item.folder });
        toast("Deleted");
        loadHistory();
      } catch (error) { toast(error.message); }
    };
    row.append(del);

    box.append(row);
  });
}

/* ───────────────────────────── clipboard nudge ───────────────────────────── */
async function offerClipboard() {
  try {
    const { text } = await api("/api/clipboard", { mode: state.mode });
    if (!text || text === state.clipboardOffered) return;
    if (state.queue.some((item) => item.source === text)) return;
    state.clipboardOffered = text;
    $("clip-suggest").hidden = false;
    $("clip-use").onclick = () => {
      $("clip-suggest").hidden = true;
      addSource(text);
    };
  } catch { /* clipboard is optional */ }
}

/* ───────────────────────────── wiring ───────────────────────────── */
function wire() {
  $("mode-frames").onclick = () => setMode("frames");
  $("mode-video").onclick = () => setMode("video");

  $("add-btn").onclick = () => addSource($("url-input").value.trim());
  $("url-input").addEventListener("keydown", (event) => {
    if (event.key === "Enter") addSource($("url-input").value.trim());
  });

  $("pick-file").onclick = async () => {
    try {
      const { path } = await api("/api/pick", {});
      if (path) addSource(path);
    } catch (error) { $("add-error").textContent = error.message; }
  };

  $("interval-select").onchange = renderQueue;
  $("clear-queue").onclick = () => { state.queue = []; renderQueue(); };
  $("start-btn").onclick = start;

  $("cancel-btn").onclick = async () => {
    $("cancel-btn").disabled = true;
    $("cancel-btn").textContent = "Stopping…";
    await api("/api/cancel", {}).catch(() => {});
  };

  $("again-btn").onclick = () => {
    setMascot("idle");
    setGreeting("Hello! Give me a video.",
      "Paste a YouTube link and I'll grab evenly spaced frames with the exact time on every one.");
    showView("setup");
    $("url-input").focus();
    offerClipboard();
  };

  $("refresh-history").onclick = loadHistory;

  $("clip-dismiss").onclick = () => { $("clip-suggest").hidden = true; };

  $("lb-close").onclick = closeLightbox;
  $("lb-prev").onclick = () => stepLightbox(-1);
  $("lb-next").onclick = () => stepLightbox(1);
  $("lightbox").onclick = (event) => { if (event.target === $("lightbox")) closeLightbox(); };

  document.addEventListener("keydown", (event) => {
    if ($("lightbox").hidden) return;
    if (event.key === "Escape") closeLightbox();
    if (event.key === "ArrowLeft") stepLightbox(-1);
    if (event.key === "ArrowRight") stepLightbox(1);
  });
}

async function checkTools() {
  try {
    const health = await api("/api/health", {});
    if (health.missing_tools.length) {
      const warning = $("tool-warning");
      warning.textContent =
        `${health.missing_tools.join(" and ")} is missing, so nothing will work yet. ` +
        `Open a terminal and run:  winget install Gyan.FFmpeg  — then reopen this app.`;
      warning.hidden = false;
      setMascot("error");
    }
    state.hasPicker = health.has_picker;
    if (!health.has_picker) $("pick-file").hidden = true;

    state.canTranscribe = health.can_transcribe !== false;
    if (!state.canTranscribe) {
      $("want-transcript").checked = false;
      $("want-transcript").disabled = true;
      $("transcript-wrap").classList.add("off");
      $("transcript-hint").textContent =
        "Scripts need one extra install. Open a terminal and run:  pip install faster-whisper";
      $("transcript-hint").hidden = false;
    }
  } catch { /* not fatal */ }
}

/* If the page is reopened while the server is mid-run - or just after one -
   pick the view back up instead of pretending nothing happened. */
async function resumeIfBusy() {
  let snapshot;
  try {
    snapshot = await api("/api/state");
  } catch { return false; }

  if (snapshot.phase === "working") {
    setMascot("working");
    setGreeting("On it!", "Grabbing your frames. You can stop any time.");
    showView("working");
    renderProgress(snapshot);
    state.polling = setInterval(poll, 280);
    return true;
  }
  if (snapshot.phase === "done" && snapshot.results.length) {
    state.results = snapshot.results;
    renderResults(snapshot);
    return true;
  }
  return false;
}

async function boot() {
  wire();
  renderQueue();
  await checkTools();
  loadHistory();
  if (await resumeIfBusy()) return;
  offerClipboard();
  $("url-input").focus();
}

boot();
