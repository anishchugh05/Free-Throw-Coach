const MOCK_MODE = false;
const $ = (selector) => document.querySelector(selector);
const screenEl = $("#screen");
const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)");
const stages = [
  ["encode", "Preparing your video"],
  ["sam", "Tracking the ball and hoop (SAM 3.1)"],
  ["shots", "Measuring every shot"],
  ["coach", "Writing your coaching (Muse Spark)"],
  ["render", "Rendering the annotated video"],
];
const icon = (name) => '<svg class="icon" aria-hidden="true"><use href="#i-' + name + '"/></svg>';
function el(tag, text, cls) {
  const node = document.createElement(tag);
  if (text != null) node.textContent = String(text);
  if (cls) node.className = cls;
  return node;
}
const finite = Number.isFinite;
const value = (n, suffix = "", signed = false) =>
  finite(n) ? (signed && n > 0 ? "+" : "") + n.toFixed(1) + suffix : "—";
const stamp = (n) =>
  finite(n) ? Math.floor(n / 60) + ":" + String(Math.floor(n % 60)).padStart(2, "0") : "—";
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const ball = $("#heroBall"),
  arc = $("#arcPath");
const replayButton = $("#replay");
let arcPosition = 0,
  arcVelocity = 0,
  arcTarget = 0,
  arcFrame = 0,
  lastFrame = 0;
function paintBall() {
  if (!arcPosition) {
    ball.setAttribute("transform", "translate(228 127) scale(1.4)");
    return;
  }
  const length = arc.getTotalLength();
  const rest = arc.getPointAtLength(length * 0.4);
  const point = arc.getPointAtLength(length * (0.4 + arcPosition * 0.6));
  const x = point.x + (228 - rest.x) * (1 - arcPosition);
  const y = point.y + (127 - rest.y) * (1 - arcPosition);
  ball.setAttribute(
    "transform",
    "translate(" +
      x +
      " " +
      y +
      ") rotate(" +
      arcPosition * 160 +
      ") scale(" +
      (1.4 - arcPosition * 1.23) +
      ")"
  );
}
function finishArc() {
  cancelAnimationFrame(arcFrame);
  arcFrame = 0;
  arcPosition = arcTarget;
  arcVelocity = 0;
  paintBall();
}
function advanceArc(now) {
  const dt = Math.max(0, (now - lastFrame) / 1000);
  lastFrame = now;
  // Exact critically damped spring step. Changing the target preserves current velocity.
  const offset = arcPosition - arcTarget;
  const rate = 6;
  const drift = arcVelocity + rate * offset;
  const decay = Math.exp(-rate * dt);
  arcPosition = arcTarget + (offset + drift * dt) * decay;
  arcVelocity = (arcVelocity - rate * drift * dt) * decay;
  if (Math.abs(arcPosition - arcTarget) < 0.001 && Math.abs(arcVelocity) < 0.01) {
    finishArc();
    return;
  }
  paintBall();
  arcFrame = requestAnimationFrame(advanceArc);
}
replayButton.onclick = () => {
  arcTarget = 1 - arcTarget;
  $("#arcAction").textContent = arcTarget ? "RETURN BALL" : "REPLAY ARC";
  if (reduceMotion.matches) finishArc();
  else if (!arcFrame) {
    lastFrame = performance.now();
    arcFrame = requestAnimationFrame(advanceArc);
  }
};
reduceMotion.addEventListener?.("change", () => {
  if (reduceMotion.matches && arcFrame) finishArc();
});
if ("IntersectionObserver" in window) {
  const observer = new IntersectionObserver((entries) => {
    if (entries[0].isIntersecting) {
      $(".steps").classList.add("revealed");
      observer.disconnect();
    }
  });
  observer.observe($(".steps"));
}
const assetRoot = new URL("../", document.currentScript.src);
let lastReport = null;
let run = 0,
  controller,
  stream,
  recorder,
  previewObjectUrl,
  page = "";
function releaseCamera() {
  if (recorder && recorder.state !== "inactive") recorder.stop();
  recorder = null;
  if (stream) stream.getTracks().forEach((track) => track.stop());
  stream = null;
}
function resetRun() {
  run++;
  if (previewObjectUrl) URL.revokeObjectURL(previewObjectUrl);
  previewObjectUrl = null;
  if (controller) controller.abort();
  controller = new AbortController();
  releaseCamera();
}
function title(kicker, heading, description) {
  screenEl.replaceChildren(el("div", kicker, "kicker"), el("h1", heading));
  if (description) screenEl.append(el("p", description, "desc"));
  const h = screenEl.querySelector("h1");
  h.tabIndex = -1;
  h.focus({ preventScroll: true });
}
const viewOf = (hash) => (hash === "#studio" ? "studio" : hash === "#why" ? "why" : "home");
let currentView = "home";
function route() {
  const view = viewOf(location.hash);
  currentView = view;
  const studio = view === "studio";
  $("#homeView").hidden = view !== "home";
  $("#whyView").hidden = view !== "why";
  $("#studioView").hidden = !studio;
  if (studio && page === "") input();
  if (!studio) {
    resetRun();
    page = "";
    screenEl.replaceChildren();
    requestAnimationFrame(() => {
      const target = ["#how", "#system", "#analysis", "#guide", "#accuracy", "#content"].includes(location.hash)
        ? $(location.hash)
        : null;
      if (target) target.scrollIntoView();
      else window.scrollTo(0, 0);
    });
  } else window.scrollTo(0, 0);
}
function openDemo() {
  if (location.hash !== "#studio") location.hash = "studio";
  begin(null);
}
let navigationTransition;
window.addEventListener("hashchange", () => {
  navigationTransition?.skipTransition();
  const switchesView = currentView !== viewOf(location.hash);
  if (!switchesView || reduceMotion.matches || !document.startViewTransition) {
    route();
    return;
  }
  const transition = document.startViewTransition(route);
  navigationTransition = transition;
  transition.finished.finally(() => {
    if (navigationTransition === transition) navigationTransition = null;
  });
});
reduceMotion.addEventListener?.("change", () => {
  if (reduceMotion.matches) navigationTransition?.skipTransition();
});
window.addEventListener("pagehide", resetRun);
window.addEventListener("pageshow", (event) => {
  if (event.persisted && (page === "camera" || page === "processing")) input();
});
document.querySelector("[data-demo]").onclick = openDemo;
function input() {
  resetRun();
  page = "input";
  title(
    "Studio / Capture",
    "Start a session.",
    "Upload a side-on free-throw clip or record your next set."
  );
  screenEl.insertAdjacentHTML(
    "beforeend",
    '<div class="inputgrid"><div class="panel"><button class="zone" id="drop">' +
      icon("upload") +
      '<strong>Drop your video here</strong><small>or click to choose a file</small></button><input type="file" accept="video/*" id="file" hidden><input type="file" accept="video/*" capture="environment" id="capture" hidden><div class="actions"><button class="btn" id="record">Record in browser</button><button class="btn phoneonly" id="phone">Open phone camera</button></div></div><aside class="panel"><div class="tag">Framing guide</div><h3 style="margin-top:12px">Set up your camera</h3><ul><li>Fix the camera side-on.</li><li>Include the hoop and full ball flight.</li><li>Choose 60 fps if possible.</li></ul><p>Left and right misses cannot be measured in this view.</p><button class="btn" id="demo">' +
      icon("play") +
      " Try the demo session</button></aside></div>"
  );
  if (lastReport) {
    const reopen = el("button", "Reopen last report", "btn");
    $("#demo").after(reopen);
    reopen.onclick = () => {
      resetRun();
      results(lastReport.result, lastReport.id, lastReport.mock, true);
    };
  }
  const drop = $("#drop");
  drop.onclick = () => $("#file").click();
  $("#phone").onclick = () => $("#capture").click();
  for (const id of ["#file", "#capture"])
    $(id).onchange = (e) => {
      if (e.target.files[0]) useFile(e.target.files[0]);
    };
  drop.ondragover = (e) => {
    e.preventDefault();
    drop.classList.add("drag");
  };
  drop.ondragleave = () => drop.classList.remove("drag");
  drop.ondrop = (e) => {
    e.preventDefault();
    drop.classList.remove("drag");
    if (e.dataTransfer.files[0]) useFile(e.dataTransfer.files[0]);
  };
  $("#record").onclick = camera;
  $("#demo").onclick = openDemo;
}
function useFile(file) {
  if (
    !file.size ||
    !(
      file.type.startsWith("video/") ||
      (!file.type && /\.(mp4|mov|m4v|webm|avi|mkv|3gp)$/i.test(file.name))
    )
  ) {
    failure("Choose a non-empty video file to start your session.", input);
    return;
  }
  begin(file);
}
async function camera() {
  resetRun();
  const token = run;
  page = "camera";
  title(
    "Studio / Camera",
    "Frame your shot.",
    "Place your phone side-on and keep the full path inside the guide."
  );
  screenEl.insertAdjacentHTML(
    "beforeend",
    '<div class="panel" style="margin-top:24px"><div class="recordFrame"><video muted playsinline autoplay id="preview"></video><div class="overlay"><svg viewBox="0 0 400 200" preserveAspectRatio="none"><path d="M15 190Q200 -75 342 90" fill="none" stroke="#b7b0ff" stroke-dasharray="5 5"/><rect x="330" y="79" width="35" height="27" fill="none" stroke="#dfd9ff"/></svg><small>FULL ARC · HOOP IN FRAME</small></div></div><p id="cameraStatus" role="status">Opening camera…</p><div class="actions"><button class="btn primary" id="captureAction" disabled>Start recording</button><button class="btn" id="cancel">Back to upload</button></div></div>'
  );
  $("#cancel").onclick = input;
  try {
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder)
      throw Error(
        "Browser recording requires camera support and HTTPS or localhost. You can also upload a clip."
      );
    const media = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: "environment" }, frameRate: { ideal: 60 } },
      audio: false,
    });
    if (token !== run) {
      media.getTracks().forEach((track) => track.stop());
      return;
    }
    stream = media;
    $("#preview").srcObject = stream;
    const mime = ["video/mp4", "video/webm;codecs=vp9", "video/webm"].find((type) =>
      MediaRecorder.isTypeSupported(type)
    );
    recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
    const rec = recorder,
      chunks = [];
    rec.ondataavailable = (e) => {
      if (e.data.size) chunks.push(e.data);
    };
    rec.onerror = () => {
      if (token === run)
        failure("Recording stopped unexpectedly. Check camera access and try again.", camera);
    };
    rec.onstop = () => {
      if (token !== run) return;
      const type = rec.mimeType || chunks[0]?.type || "video/webm";
      useFile(
        new File(chunks, ["session", type.includes("mp4") ? "mp4" : "webm"].join("."), { type })
      );
    };
    const action = $("#captureAction");
    action.disabled = false;
    $("#cameraStatus").textContent = "Camera ready. Check the framing before recording.";
    action.onclick = () => {
      if (rec.state === "recording") {
        action.disabled = true;
        rec.stop();
        return;
      }
      try {
        rec.start(1000);
        action.textContent = "Stop and analyze";
        $("#cameraStatus").textContent = "● Recording your session";
      } catch (e) {
        failure(e.message, camera);
      }
    };
  } catch (e) {
    if (token === run)
      failure(
        e.name === "NotAllowedError"
          ? "Camera access was declined. Allow camera access in your browser or upload a clip."
          : e.message,
        camera
      );
  }
}
function failure(message, retry) {
  resetRun();
  page = "error";
  title("Studio / Session", "Let’s try again.");
  screenEl.insertAdjacentHTML(
    "beforeend",
    '<div class="panel error"><h3>Session interrupted</h3><p id="reason" role="alert"></p><div class="actions"><button class="btn primary" id="retry">Try again</button><button class="btn" id="new">Choose another clip</button></div></div>'
  );
  $("#reason").textContent = message;
  $("#retry").onclick = retry;
  $("#new").onclick = input;
}
function processing(file) {
  page = "processing";
  title(
    "Studio / Analysis",
    "Reading your shot.",
    file ? "Analyzing " + file.name : "Loading the demo session."
  );
  screenEl.insertAdjacentHTML(
    "beforeend",
    '<div class="inputgrid"><div class="panel"><ol class="stages" id="stages"></ol><p class="live" id="statusText" role="status"></p><progress id="progress" class="progress" hidden max="1"></progress></div><div class="panel"><span class="tag">Trajectory lab</span><svg class="waitart" viewBox="0 0 240 100" aria-hidden="true"><path d="M10 85 Q120 -48 230 73" fill="none" stroke="#9b93ff" stroke-dasharray="4 5"/><circle r="6" fill="#9792ff"/><path d="M215 74h23l-5 14h-12z" fill="none" stroke="#aaa8c4"/></svg><h3>Frame by frame</h3><p>A session can take 1–3 minutes. Keep this tab open while the model works.</p><button class="btn" id="leave">Back to upload</button></div></div>'
  );
  $("#leave").onclick = input;
  setStage(null, file ? "Sending your clip…" : "Requesting session…");
}
function setStage(stage, label, progress = null) {
  const current = stages.findIndex((s) => s[0] === stage);
  $("#stages").replaceChildren(
    ...stages.map(([key, name], i) =>
      el(
        "li",
        (i < current ? "✓" : i === current ? "●" : String(i + 1).padStart(2, "0")) + "  " + name,
        i < current ? "done" : i === current ? "active" : ""
      )
    )
  );
  const text = label || stages[current]?.[1] || "Waiting for the job…";
  if ($("#statusText").textContent !== text) $("#statusText").textContent = text;
  const bar = $("#progress");
  bar.hidden = stage !== "render" || !finite(progress);
  if (!bar.hidden) {
    bar.value = progress;
    bar.setAttribute("aria-label", "Rendering video");
  }
}
async function request(url, options = {}) {
  const res = await fetch(url, { ...options, signal: controller.signal, cache: "no-store" });
  const body = await res.json().catch(() => null);
  if (!res.ok)
    throw Error(
      typeof body?.detail === "string"
        ? body.detail
        : "The server returned HTTP " + res.status + ". Check the backend and try again."
    );
  if (!body)
    throw Error("The analysis API did not return JSON. Serve this page from your FastAPI app.");
  return body;
}
async function begin(file, existingId = null) {
  resetRun();
  const token = run;
  let id = existingId;
  processing(file);
  try {
    if (MOCK_MODE) {
      for (const [key, label] of stages) {
        if (token !== run) return;
        setStage(key, label);
        await delay(700);
      }
      if (token === run) results(previewResult(), "preview", true);
      return;
    }
    if (!id) {
      const options = { method: "POST" };
      if (file) {
        options.body = new FormData();
        options.body.append("file", file);
      }
      const job = await request(file ? "/api/upload" : "/api/demo", options);
      if (token !== run) return;
      id = job.id;
      if (typeof id !== "string" || !id) throw Error("The server did not return a job ID.");
    }
    while (token === run) {
      const job = await request("/api/jobs/" + encodeURIComponent(id));
      if (token !== run) return;
      if (job.status === "error") {
        id = null;
        throw Error(job.error || "The model could not finish this clip.");
      }
      if (job.status === "done") {
        if (!job.result) throw Error("The completed job has no result.");
        results(job.result, id, false);
        return;
      }
      if (job.status !== "running") throw Error("The server returned an unknown job status.");
      setStage(job.stage, job.label, job.progress);
      await delay(1500);
    }
  } catch (e) {
    if (token === run)
      failure(e.message || "Could not reach the analysis server.", () => begin(file, id));
  }
}
// A local blob keeps mock replay seekable on static servers without byte-range support.
async function loadPreviewVideo(player, url, token) {
  try {
    const response = await fetch(url, { signal: controller.signal });
    if (!response.ok) throw Error("Could not load the illustrated replay.");
    const blob = await response.blob();
    if (run !== token) return;
    previewObjectUrl = URL.createObjectURL(blob);
    player.src = previewObjectUrl;
  } catch {
    if (run === token) player.src = url;
  }
}
// Keep only this tab’s most recent completed report. Camera footage is never cached here.
function watchReport(saved, checkNow) {
  const status = el("p", null, "report-freshness");
  status.setAttribute("role", "status");
  screenEl.querySelector(".desc").after(status);
  let pending = false;
  const signal = controller.signal;
  async function refresh() {
    if (pending || signal.aborted) return;
    pending = true;
    try {
      const job = await request("/api/jobs/" + encodeURIComponent(saved.id));
      if (signal.aborted) return;
      if (job.status !== "done" || !job.result) throw Error("Report unavailable");
      if (JSON.stringify(saved.result) === JSON.stringify(job.result)) {
        lastReport = saved;
        status.replaceChildren();
      } else {
        // Keep the active replay and keyboard focus intact until the player chooses to switch.
        lastReport = { ...saved, result: job.result };
        const update = el("button", "View updated report", "btn");
        update.onclick = () => {
          resetRun();
          results(job.result, saved.id, false);
        };
        status.replaceChildren("A newer report is ready. ", update);
      }
    } catch {
      if (!signal.aborted)
        status.textContent = "Showing the saved report. The latest version is unavailable.";
    } finally {
      pending = false;
    }
  }
  window.addEventListener("focus", refresh, { signal });
  window.addEventListener("online", refresh, { signal });
  if (checkNow) {
    status.textContent = "Showing the saved report. Checking for updates…";
    refresh();
  }
}
function results(result, id, mock, fromCache = false) {
  lastReport = { id, result, mock };
  page = "results";
  const report = result.report || {},
    shots = Array.isArray(result.shots) ? result.shots : [];
  title(
    mock ? "Studio / Synthetic preview" : "Studio / Session review",
    "Your shot report.",
    "Select a shot to replay the approach to the rim."
  );
  if (!mock) watchReport(lastReport, fromCache);
  const stats = el("div", null, "stats");
  screenEl.append(stats);
  function stat(label, main, sub) {
    const card = el("div", null, "panel stat");
    card.append(el("div", label, "tag"), el("strong", main), el("small", sub));
    stats.append(card);
  }
  stat(
    "Makes",
    (report.makes ?? "—") + " / " + (report.shots ?? "—"),
    finite(report.make_pct) ? report.make_pct + "% made" : "Percentage unavailable"
  );
  stat(
    "Entry angle",
    value(report.entry_angle?.mean, "°"),
    finite(report.entry_angle?.std)
      ? "± " + value(report.entry_angle.std, "° spread")
      : "Spread unavailable"
  );
  stat("Peak height", value(report.apex_in?.mean, "″"), "Above the rim");
  stat("Rim offset", value(report.offset_in?.mean, "″", true), "Positive short · negative long");
  screenEl.insertAdjacentHTML(
    "beforeend",
    '<div class="resultgrid"><div class="panel"><div class="tag">Session film</div><h3>Annotated replay</h3><video class="player" id="player" controls playsinline preload="metadata"></video><p id="playerNote" role="status"></p></div><article class="panel coach" id="coaching"><div class="tag">Muse Spark / Coach verdict</div></article></div><div class="panel"><div class="tag">Flight path</div><h3>Rim crossings</h3><p>Blue circles mark makes. Pink squares mark misses. The shaded band spans ±5.5 inches at the rim.</p><div class="plot-scroll"><div class="plotarea" id="plot"></div></div><div class="plotlabels" id="plotLabels"></div></div><div class="panel tablepanel"><div class="tag">Shot log</div><h3>Shot by shot</h3><div class="tablewrap"><table><thead><tr><th scope="col">Shot</th><th scope="col">Time</th><th scope="col">Result</th><th scope="col">Entry</th><th scope="col">Peak</th><th scope="col">Short / long</th></tr></thead><tbody id="rows"></tbody></table></div></div><div class="actions"><button class="btn primary" id="another">Try another clip</button></div>'
  );
  if (report.shooter && finite(report.shooter.reach_pct?.mean)) {
    const sh = report.shooter,
      panel = el("div", null, "panel routine"),
      grid = el("div", null, "stats routine-stats");
    panel.append(
      el("div", "Shooter tracking / SAM 3.1", "tag"),
      el("h3", "Your routine"),
      el(
        "p",
        "Measured from the box SAM draws around you, shown relative to your own height. These show how repeatable you are, not whether a number is right or wrong."
      ),
      grid
    );
    const card = (label, main, sub) => {
      const c = el("div", null, "panel stat");
      c.append(el("div", label, "tag"), el("strong", main), el("small", sub));
      grid.append(c);
    };
    card(
      "Reach",
      value(sh.reach_pct.mean, "%"),
      finite(sh.reach_pct.std) ? "± " + value(sh.reach_pct.std, "%") + " · above your head" : "Above your head"
    );
    card(
      "Lift tempo",
      sh.tempo_s && finite(sh.tempo_s.mean) ? sh.tempo_s.mean.toFixed(2) + " s" : "—",
      sh.tempo_s && finite(sh.tempo_s.std) ? "± " + sh.tempo_s.std.toFixed(2) + " s · start to full reach" : "Start to full reach"
    );
    card(
      "Stance drift",
      finite(sh.stance_drift_pct?.range) ? value(sh.stance_drift_pct.range, "%") : "—",
      "Spread of where you stand, of your height"
    );
    card(
      "Between shots",
      sh.between_shots_s && finite(sh.between_shots_s.mean) ? sh.between_shots_s.mean.toFixed(1) + " s" : "—",
      sh.between_shots_s && finite(sh.between_shots_s.std) ? "± " + sh.between_shots_s.std.toFixed(1) + " s" : "Routine timing"
    );
    $("#plot").closest(".panel").before(panel);
  }
  if (!mock && typeof id === "string" && shots.length) {
    const panel = el("div", null, "panel ask"),
      log = el("div", null, "ask-log"),
      form = el("form", null, "ask-form"),
      input = el("input"),
      send = el("button", "Ask", "btn primary"),
      chips = el("div", null, "ask-chips"),
      history = [];
    log.setAttribute("aria-live", "polite");
    input.type = "text";
    input.maxLength = 300;
    input.placeholder = "Ask about your session…";
    input.setAttribute("aria-label", "Ask your coach a question");
    send.type = "submit";
    form.append(input, send);
    const misses = shots.filter((s) => !s.made);
    const suggestions = [
      misses.length ? "Why did I miss shot #" + misses[0].i + "?" : "What was my best shot?",
      "What should I drill next?",
      "Was I getting tired?",
    ];
    async function submit(q) {
      q = q.trim();
      if (!q || send.disabled) return;
      send.disabled = true;
      input.value = "";
      chips.hidden = true;
      log.append(el("p", q, "ask-q"));
      const a = el("p", "Thinking…", "ask-a thinking");
      log.append(a);
      log.scrollTop = log.scrollHeight;
      try {
        const res = await request("/api/jobs/" + encodeURIComponent(id) + "/ask", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ question: q, history }),
        });
        a.textContent = res.answer;
        a.classList.remove("thinking");
        history.push({ q, a: res.answer });
      } catch (e) {
        a.textContent = e.message || "The coach couldn't answer just now.";
        a.classList.remove("thinking");
        a.classList.add("ask-err");
      }
      send.disabled = false;
      log.scrollTop = log.scrollHeight;
      input.focus();
    }
    for (const q of suggestions) {
      const b = el("button", q, "chip");
      b.type = "button";
      b.onclick = () => submit(q);
      chips.append(b);
    }
    form.onsubmit = (e) => {
      e.preventDefault();
      submit(input.value);
    };
    panel.append(
      el("div", "Muse Spark / Ask your coach", "tag"),
      el("h3", "Ask about your session"),
      el(
        "p",
        "Answers use only the numbers we measured for this session. Things we can't see, like elbow or wrist, we'll say so."
      ),
      chips,
      log,
      form
    );
    screenEl.querySelector(".resultgrid").after(panel);
  }
  const player = $("#player"),
    note = $("#playerNote");
  // Reserve the final player frame immediately; slow metadata gets a quiet placeholder.
  const skeletonTimer = setTimeout(() => {
    if (player.isConnected && !player.error && player.readyState === 0)
      player.classList.add("loading-frame");
  }, 300);
  function clearSkeleton() {
    clearTimeout(skeletonTimer);
    player.classList.remove("loading-frame");
  }
  player.addEventListener("loadedmetadata", clearSkeleton, { once: true });
  player.addEventListener("error", clearSkeleton, { once: true });
  controller.signal.addEventListener("abort", clearSkeleton, { once: true });
  let seekVersion = 0;
  const token = run;
  if (!mock) {
    // The documented /video route is also the fallback for a missing or external URL.
    const fallback = "/api/jobs/" + encodeURIComponent(id) + "/video";
    let url = new URL(fallback, location.href);
    try {
      const supplied = new URL(result.video || fallback, location.href);
      if (supplied.origin === location.origin) url = supplied;
    } catch {}
    player.src = url.href;
    player.onerror = () => {
      note.textContent = "Annotated video is unavailable. Your shot measurements are below.";
    };
  } else {
    const previewUrl = new URL("img/preview-session.mp4", assetRoot).href;
    if (location.protocol === "file:") player.src = previewUrl;
    else loadPreviewVideo(player, previewUrl, token);
    note.textContent = "Synthetic preview · illustrated session replay.";
  }
  const coach = $("#coaching"),
    c = result.coaching;
  if (c) {
    coach.append(el("h3", c.headline || "Coach notes"));
    if (c.confidence === "low") coach.append(el("p", "Low confidence", "tag"));
    const noteSection = (label, body) => {
      if (body) {
        coach.append(el("div", label, "tag"), el("p", body));
      }
    };
    noteSection("Strength", c.strength);
    if (c.top_issue) {
      const issue = c.top_issue;
      noteSection("One thing to work on", issue.title);
      if (issue.evidence) coach.append(el("p", issue.evidence));
      if (issue.cue) coach.append(el("blockquote", "“" + issue.cue + "”"));
      noteSection("Drill", issue.drill);
    }
    noteSection("Consistency", c.consistency_note);
  } else {
    coach.append(
      el("h3", "Coaching unavailable"),
      el(
        "p",
        result.coaching_error ||
          "The coach report was unavailable for this session. Review your measurements and replay below."
      )
    );
  }
  const rows = $("#rows"),
    plot = $("#plot"),
    labels = $("#plotLabels"),
    rowNodes = new Map();
  let selectedIndex = -1;
  const appleKeys = /Mac|iPad|iPhone/.test(navigator.platform);
  const shotNav = el("div", null, "shot-shortcuts");
  const shotButtons = [-1, 1].map((direction) => {
    const prev = direction < 0;
    const label = prev ? "Previous shot" : "Next shot";
    const shortcut = (appleKeys ? "⌘ ⇧ " : "Ctrl + Shift + ") + (prev ? "←" : "→");
    const button = el("button", label, "btn");
    button.title = label + " (" + shortcut + ")";
    button.setAttribute(
      "aria-keyshortcuts",
      (appleKeys ? "Meta" : "Control") + "+Shift+" + (prev ? "ArrowLeft" : "ArrowRight")
    );
    button.append(el("kbd", shortcut));
    button.disabled = prev || !shots.length;
    button.onclick = () => select(shots[selectedIndex + direction]);
    shotNav.append(button);
    return button;
  });
  if (shots.length) note.after(shotNav);
  window.addEventListener(
    "keydown",
    (event) => {
      if (
        !screenEl.contains(shotNav) ||
        event.defaultPrevented ||
        event.isComposing ||
        event.target.closest?.("input, textarea, select, video, [role=textbox]") ||
        event.target.isContentEditable ||
        !event.shiftKey ||
        event.altKey ||
        event.metaKey !== appleKeys ||
        event.ctrlKey === appleKeys
      )
        return;
      const button =
        event.key === "ArrowLeft"
          ? shotButtons[0]
          : event.key === "ArrowRight"
          ? shotButtons[1]
          : null;
      if (button && !button.disabled) {
        event.preventDefault();
        button.click();
      }
    },
    { signal: controller.signal }
  );
  function select(shot) {
    selectedIndex = shots.indexOf(shot);
    shotButtons[0].disabled = selectedIndex <= 0;
    shotButtons[1].disabled = selectedIndex >= shots.length - 1;
    for (const [s, row] of rowNodes) row.classList.toggle("selected", s === shot);
    if (!finite(shot.rim_t)) {
      note.textContent = "No rim timestamp is available for this shot.";
      return;
    }
    const t = Math.max(0, shot.rim_t - 2.2),
      version = ++seekVersion;
    function playShot() {
      if (token !== run || version !== seekVersion) return;
      player.currentTime = finite(player.duration) ? Math.min(t, player.duration) : t;
      player.play().catch(() => {
        if (token === run && version === seekVersion)
          note.textContent = "Press play to watch the selected shot.";
      });
    }
    if (player.readyState >= 1) playShot();
    else if (!player.error) player.addEventListener("loadedmetadata", playShot, { once: true });
  }
  const extent = shots.reduce(
    (max, s) => (finite(s.short_in) ? Math.max(max, Math.abs(s.short_in)) : max),
    7
  );
  const limit = Math.ceil(extent / 5) * 5,
    position = (n) => 50 + (n / limit) * 50;
  const band = el("div", null, "band");
  band.style.left = position(-5.5) + "%";
  band.style.width = position(5.5) - position(-5.5) + "%";
  plot.append(band);
  labels.append(
    el("span", "−" + limit + "″ LONG"),
    el("span", "RIM CENTER"),
    el("span", "+" + limit + "″ SHORT")
  );
  const plotted = shots.filter((s) => finite(s.short_in));
  if (!plotted.length) {
    plot.append(el("p", "No measured rim crossings."));
    band.hidden = true;
  }
  const plotPoints = [];
  for (const shot of shots) {
    const row = el("tr");
    rowNodes.set(shot, row);
    const btn = el("button", "#" + shot.i, "seek");
    btn.setAttribute("aria-label", "Replay shot " + shot.i);
    const first = el("td");
    first.append(btn);
    row.append(first);
    const outcome = shot.made ? "Make" : "Miss" + (shot.miss_type ? " · " + String(shot.miss_type).replace("_", " ") : "");
    row.append(
      el("td", stamp(shot.t)),
      el("td", outcome, shot.made ? "makeText" : "missText"),
      el("td", value(shot.entry, "°")),
      el("td", value(shot.apex_in, "″")),
      el("td", value(shot.short_in, "″", true))
    );
    row.onclick = () => select(shot);
    rows.append(row);
    if (finite(shot.short_in)) {
      const point = el("button", null, "plotdot" + (shot.made ? "" : " miss"));
      const x = position(shot.short_in);
      plotPoints.push({ point, x });
      point.style.left = x + "%";
      point.title = "Shot " + shot.i + " · " + outcome + " · " + value(shot.short_in, "″", true);
      point.setAttribute("aria-label", point.title);
      point.onclick = () => select(shot);
      plot.append(point);
    }
  }
  // Keep true depth on the horizontal axis. Stack neighboring hit areas in separate lanes.
  plotPoints.sort((a, b) => a.x - b.x);
  function layoutPlot() {
    const width = plot.clientWidth;
    if (!width || !plotPoints.length) return;
    const gap = 4,
      size = plotPoints[0].point.offsetWidth;
    const laneEnds = [];
    for (const { point, x } of plotPoints) {
      const center = (width * x) / 100;
      let lane = laneEnds.findIndex((end) => center - end >= size + gap);
      if (lane === -1) lane = laneEnds.length;
      laneEnds[lane] = center;
      point.style.top = gap + size / 2 + lane * (size + gap) + "px";
    }
    plot.style.height = Math.max(160, laneEnds.length * (size + gap) + gap + 2) + "px";
  }
  layoutPlot();
  if (window.ResizeObserver) {
    const observer = new ResizeObserver(layoutPlot);
    observer.observe(plot);
    controller.signal.addEventListener("abort", () => observer.disconnect(), { once: true });
  } else {
    window.addEventListener("resize", layoutPlot, { signal: controller.signal });
  }
  if (!shots.length) rows.parentElement.after(el("p", "No shots detected in this clip."));
  $("#another").onclick = () => {
    input();
    window.scrollTo(0, 0);
  };
  window.scrollTo(0, 0);
}
// Development only. Generate synthetic measurements and derive the summary from the shots.
function previewResult() {
  const offsets = Array.from({ length: 12 }, (_, i) =>
    i === 3 ? 7.2 : i === 9 ? -8.1 : Math.sin(i * 2.1) * 3.4
  );
  const shots = offsets.map((offset, i) => ({
    i: i + 1,
    t: 1 + i * 3,
    rim_t: 1.8 + i * 3,
    made: Math.abs(offset) <= 5.5,
    miss_type: offset > 5.5 ? "short" : offset < -5.5 ? "long" : null,
    entry: i === 6 ? null : 44 + Math.sin(i) * 4,
    apex_in: i === 6 ? null : 30 + Math.cos(i) * 5,
    short_in: offset,
    fit_ok: i !== 6,
  }));
  function summary(key) {
    const ns = shots.map((s) => s[key]).filter(finite);
    const mean = ns.reduce((s, v) => s + v, 0) / ns.length;
    return { mean, std: Math.sqrt(ns.reduce((s, v) => s + (v - mean) ** 2, 0) / ns.length) };
  }
  const makes = shots.filter((s) => s.made).length;
  return {
    fps: 24,
    video: "/api/jobs/preview/video",
    shots,
    report: {
      shots: shots.length,
      makes,
      make_pct: Math.round((makes / shots.length) * 100),
      entry_angle: summary("entry"),
      apex_in: summary("apex_in"),
      offset_in: summary("short_in"),
      misses: shots
        .filter((s) => !s.made)
        .map((s) => ({ i: s.i, type: s.miss_type, offset_in: s.short_in })),
    },
    coaching: {
      headline: "Bring the depth closer together.",
      strength: "Most shots crossed within the center band.",
      top_issue: {
        title: "Repeat your depth",
        evidence: "The two misses crossed on opposite sides of the depth band.",
        cue: "Aim through the same spot each time.",
        drill: "Shoot five sets of two, keeping the same target at the rim.",
      },
      consistency_note: "One shot has no fitted entry angle or peak height.",
      confidence: "medium",
    },
    coaching_error: null,
  };
}
route();

// ---- Accuracy section (data from /accuracy.json, produced by build_accuracy.py) ----
(async function loadAccuracy() {
  const host = document.getElementById("accuracyBody");
  if (!host) return;
  let data;
  for (const url of ["./accuracy.json", "./static/accuracy.json"]) {
    try {
      const res = await fetch(url, { cache: "no-store" });
      if (res.ok) {
        data = await res.json();
        break;
      }
    } catch {}
  }
  if (!data?.clips?.length) return;
  document.getElementById("accuracy").hidden = false;
  const clips = data.clips;
  const sum = (k) => clips.reduce((s, c) => s + (c[k] || 0), 0);
  const card = (c) => {
    const n = el("article", null, "acc-card"),
      cf = c.confusion || {};
    const head = el("div", null, "acc-head");
    head.append(el("b", c.label), el("span", c.badge || (c.tuned ? "Used while building" : "Held-out clip"), c.tuned ? "badge" : "badge good"));
    const big = el("div", null, "acc-big");
    big.append(el("strong", c.correct + "/" + c.found), el("small", "make/miss calls matched the hand log"));
    const stats = el("ul", null, "acc-stats");
    for (const [k, v] of [
      ["Shots found", c.found + " of " + c.logged],
      ["Extra detections", String(c.extra)],
      ["Makes called right", (cf.make_make || 0) + " of " + ((cf.make_make || 0) + (cf.make_miss || 0))],
      ["Misses called right", (cf.miss_miss || 0) + " of " + ((cf.miss_miss || 0) + (cf.miss_make || 0))],
    ]) {
      const li = el("li");
      li.append(el("span", k), el("b", v));
      stats.append(li);
    }
    n.append(head, big, stats);
    if (c.history && c.history.length) {
      const hist = el("ol", null, "acc-hist");
      for (const h of c.history) {
        const li = el("li");
        li.append(el("span", h.label), el("b", h.correct + "/" + c.found));
        hist.append(li);
      }
      n.append(el("div", "How it improved on this clip", "acc-hist-title"), hist);
    }
    for (const e of c.errors || []) {
      const t = Math.floor(e.t / 60) + ":" + String(e.t % 60).padStart(2, "0");
      const p = el("p", null, "acc-err");
      p.append(el("b", "Wrong call at " + t + ": "), "logged " + e.truth + ", we said " + e.detected + ". " + (e.note || ""));
      n.append(p);
    }
    return n;
  };
  host.replaceChildren(...clips.map(card));
  const total = el("p", null, "acc-total");
  total.textContent =
    sum("correct") + " of " + sum("found") + " calls matched across " + clips.length + " scored clip" + (clips.length > 1 ? "s" : "") + ". We score every clip against a hand-made shot log.";
  host.after(total);
})();
