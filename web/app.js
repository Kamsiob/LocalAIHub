/* local-ai-hub — frontend logic
   Renders service cards, handles theme + interactions, and talks to the Python
   backend over QWebChannel when hosted in the app. When opened as a plain page
   (no bridge — e.g. the design mockup), it falls back to static sample data so
   the layout can be reviewed on its own. */

(() => {
  "use strict";

  // ---- inline icons -------------------------------------------------------
  const I = {
    spark: '<svg viewBox="0 0 24 24" fill="none"><path d="M12 3l1.8 4.9L18.7 9l-4.9 1.8L12 15.7 10.2 10.8 5.3 9l4.9-1.1L12 3z" fill="#fff"/><circle cx="18.5" cy="17.5" r="1.6" fill="#fff"/><circle cx="6" cy="16" r="1.1" fill="#fff"/></svg>',
    ollama: '<svg viewBox="0 0 24 24" fill="none"><rect x="4" y="4" width="16" height="4.2" rx="1.6" fill="currentColor" opacity=".95"/><rect x="4" y="9.9" width="16" height="4.2" rx="1.6" fill="currentColor" opacity=".75"/><rect x="4" y="15.8" width="16" height="4.2" rx="1.6" fill="currentColor" opacity=".55"/></svg>',
    openwebui: '<svg viewBox="0 0 24 24" fill="none"><path d="M4 6.5A2.5 2.5 0 016.5 4h11A2.5 2.5 0 0120 6.5v7A2.5 2.5 0 0117.5 16H9l-4 3.5V16H6.5A2.5 2.5 0 014 13.5v-7z" fill="currentColor"/></svg>',
    comfyui: '<svg viewBox="0 0 24 24" fill="none"><path d="M14.7 3.3l6 6-9.9 9.9-3.6.7.7-3.6L14.7 3.3z" fill="currentColor"/><circle cx="5" cy="19" r="1.6" fill="currentColor"/><path d="M16.2 5.8l2 2" stroke="rgba(255,255,255,.6)" stroke-width="1.3"/></svg>',
    sun: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="12" cy="12" r="4"/><path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6l1.4 1.4M17 17l1.4 1.4M18.4 5.6L17 7M7 17l-1.4 1.4"/></svg>',
    moon: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M20 14.5A8 8 0 019.5 4 8 8 0 1020 14.5z"/></svg>',
    chevron: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6"/></svg>',
    refresh: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 11-2.64-6.36M21 4v5h-5"/></svg>',
    plus: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>',
    external2: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M14 5h5v5M19 5l-8 8M18 14v4a1 1 0 01-1 1H6a1 1 0 01-1-1V7a1 1 0 011-1h4"/></svg>',
    warn: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M12 9v4M12 17h.01M10.3 3.9L2 18a2 2 0 001.7 3h16.6a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0z"/></svg>',
    library: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M4 5.5A1.5 1.5 0 015.5 4H11v16H5.5A1.5 1.5 0 014 18.5v-13z"/><path d="M11 4h7.5A1.5 1.5 0 0120 5.5v13a1.5 1.5 0 01-1.5 1.5H11"/></svg>',
    hugging: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="12" cy="12" r="8"/><path d="M8.5 10h.01M15.5 10h.01M8.5 14.5c1 1 2.2 1.5 3.5 1.5s2.5-.5 3.5-1.5" stroke-linecap="round"/></svg>',
    civitai: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><rect x="3.5" y="5" width="17" height="14" rx="2.5"/><circle cx="8.5" cy="10" r="1.5"/><path d="M4 17l4.5-4 3 2.5L16 11l4 4.5" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    ext: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M14 5h5v5M19 5l-8 8M18 14v4a1 1 0 01-1 1H6a1 1 0 01-1-1V7a1 1 0 011-1h4"/></svg>',
  };

  const SVC_META = {
    ollama:    { name: "Ollama",     sub: "Local LLM runtime · :11434", hasModels: true },
    openwebui: { name: "Open WebUI", sub: "Chat front-end · :3000",      hasModels: false, webPort: 3000 },
    comfyui:   { name: "ComfyUI",    sub: "Image generation · :8188",    hasModels: true,  webPort: 8188 },
  };

  // STANDING RULE: links to anything running locally use the literal loopback
  // address 127.0.0.1 with the port — never the word "localhost", which some
  // browsers mishandle for plain local servers and silently fail to load.
  function localServiceUrl(port) { return "http://127.0.0.1:" + port; }

  // ---- sample data (illustrative only; used when there is no backend, e.g.
  // the standalone design mockup). Deliberately generic public model names —
  // the app never assumes anyone's actual models; live data comes from the API. -
  const SAMPLE = {
    ollama:    { active: true,  serving: true,  loaded: "llama3.2:3b" },
    openwebui: { active: true,  serving: true },
    comfyui:   { active: true,  serving: true,  generating: false },
  };
  const SAMPLE_MODELS = [
    { name: "llama3.2:3b", size_human: "2.0 GB", loaded: true,  vram_human: "3.4 GB" },
    { name: "mistral:7b",  size_human: "4.1 GB", loaded: false, vram_human: "" },
    { name: "phi3:mini",   size_human: "2.2 GB", loaded: false, vram_human: "" },
    { name: "gemma2:2b",   size_human: "1.6 GB", loaded: false, vram_human: "" },
  ];
  const SAMPLE_COMFY = [
    { category_label: "Diffusion models", name: "flux1-dev-Q8_0.gguf",       size_human: "12.5 GB", format: "GGUF",        source: "huggingface", update: { available: true,  detail: "Update available" } },
    { category_label: "Checkpoints",      name: "sd_xl_base_1.0.safetensors", size_human: "6.5 GB", format: "safetensors", source: "civitai",     update: { available: false, detail: "Up to date" } },
    { category_label: "Text encoders",    name: "clip_l.safetensors",         size_human: "246 MB", format: "safetensors", source: "huggingface", update: null },
    { category_label: "VAE",              name: "sdxl_vae.safetensors",       size_human: "320 MB", format: "safetensors", source: null,          update: null, untracked: true },
    { category_label: "LoRAs",            name: "add-detail-xl.safetensors",  size_human: "144 MB", format: "safetensors", source: null,          update: null },
  ];

  // ---- backend bridge -----------------------------------------------------
  let backend = null;        // set when QWebChannel connects
  const state = { services: {}, models: [], comfyModels: [], expanded: { ollama: false, comfyui: false } };

  function statusText(svc, s) {
    if (s && s.failed) return { txt: "Stopped unexpectedly", cls: "is-failed" };
    if (!s || !s.active) return { txt: "Stopped", cls: "" };
    if (!s.serving) return { txt: "Starting…", cls: "is-starting" };
    if (svc === "comfyui" && s.generating) return { txt: "Generating…", cls: "is-on is-starting" };
    if (svc === "ollama" && s.loaded) return { txt: `Running · ${s.loaded} in memory`, cls: "is-on" };
    return { txt: "Running", cls: "is-on" };
  }

  // ---- rendering ----------------------------------------------------------
  function render() {
    const cards = document.getElementById("cards");
    cards.innerHTML = "";
    for (const svc of ["ollama", "openwebui", "comfyui"]) {
      const meta = SVC_META[svc];
      const s = state.services[svc] || { active: false, serving: false };
      const st = statusText(svc, s);
      const on = st.cls === "is-on";
      const card = document.createElement("div");
      card.className = `card ${st.cls}` + (state.expanded[svc] ? " expanded" : "");
      card.dataset.svc = svc;

      card.innerHTML = `
        <div class="card-row">
          <div class="icon-sq">${I[svc]}</div>
          <div class="svc-meta">
            <div class="svc-name">${meta.name}</div>
            <div class="svc-status"><span class="dot"></span>${st.txt}</div>
          </div>
          <div class="svc-right">
            ${s.failed ? `<button class="btn-sm danger" data-act="clog" data-svc="${svc}">${I.warn}View log</button>` : ""}
            ${(meta.webPort && s.serving) ? `<button class="btn-open" data-act="open" data-port="${meta.webPort}" title="Open http://127.0.0.1:${meta.webPort}">Open ${I.external2}</button>` : ""}
            ${meta.hasModels ? `<div class="chevron" data-act="expand">${I.chevron}</div>` : ""}
            <div class="toggle" data-act="toggle" role="switch" aria-checked="${on}"><span class="knob"></span></div>
          </div>
        </div>
        ${meta.hasModels ? modelsMarkup(svc) : ""}
      `;
      cards.appendChild(card);

      if (meta.hasModels) {
        const wrap = card.querySelector(".models");
        if (wrap) wrap.style.maxHeight = state.expanded[svc] ? wrap.scrollHeight + "px" : "0";
      }
    }
  }

  function esc(s) { return String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }

  function modelsMarkup(svc) {
    return svc === "comfyui" ? comfyModelsMarkup() : ollamaModelsMarkup();
  }

  // Ollama: installed models with in-memory vs on-disk state + Update.
  function ollamaModelsMarkup() {
    const models = state.models;
    const rows = models.length ? models.map(m => `
      <div class="model">
        <span class="model-name">${esc(m.name)}</span>
        <span class="size">${esc(m.size_human || "")}</span>
        <span class="badge ${m.loaded ? "loaded" : ""}"><span class="b-dot"></span>${m.loaded ? "In memory" : "On disk"}</span>
        <button class="btn-sm" data-act="update" data-model="${esc(m.name)}">Update</button>
      </div>`).join("") : `<div class="model"><span class="model-name" style="color:var(--text-faint)">No models installed</span></div>`;
    return `
      <div class="models">
        <div class="models-inner">
          <div class="models-head"><span>Installed models</span><span>${models.length} total</span></div>
          ${rows}
        </div>
      </div>`;
  }

  // ComfyUI: whatever files are on disk, grouped by folder, with a format tag.
  // No in-memory/idle state (ComfyUI has none) and no Update (no registry).
  function comfyModelsMarkup() {
    const models = state.comfyModels || [];
    const topbar = `<div class="models-topbar">
      <span class="models-topbar-label">Installed models${models.length ? " · " + models.length : ""}</span>
      <button class="btn-sm" data-act="cinstall">${I.plus}Install a model</button>
    </div>`;
    if (!models.length) {
      return `<div class="models"><div class="models-inner">
        ${topbar}
        <div class="model"><span class="model-name" style="color:var(--text-faint)">No model files yet — use “Install a model”, or drop files into ComfyUI/models</span></div>
      </div></div>`;
    }
    const order = ["Diffusion models", "Checkpoints", "Text encoders", "VAE", "LoRAs"];
    const groups = {};
    models.forEach(m => (groups[m.category_label] = groups[m.category_label] || []).push(m));
    let body = topbar;
    order.forEach(label => {
      const items = groups[label];
      if (!items || !items.length) return;
      body += `<div class="models-head"><span>${esc(label)}</span><span>${items.length}</span></div>`;
      body += items.map(m => `
        <div class="model">
          <span class="model-name" title="${esc(m.name)}">${esc(m.name)}</span>
          <span class="size">${esc(m.size_human || "")}</span>
          <span class="badge">${esc(m.format || "")}</span>
          ${comfyAction(m)}
        </div>`).join("");
    });
    return `<div class="models"><div class="models-inner">${body}</div></div>`;
  }

  // The per-row update control, mirroring Ollama's Update but source-aware:
  // no source -> Set source; source set + unchecked -> Check; then Update / Up to date.
  function comfyAction(m) {
    const p = esc(m.path || "");
    const nm = esc(m.name || "");
    if (m.source) {
      if (m.update && m.update.available === true) {
        return `<button class="btn-sm accent" data-act="cupdate" data-path="${p}">Update</button>`;
      }
      if (m.update && m.update.available === false) {
        return `<span class="cu-uptodate" title="${esc((m.update && m.update.detail) || "")}">Up to date</span>`;
      }
      return `<button class="btn-sm" data-act="ccheck" data-path="${p}">Check</button>`;
    }
    // No source. If we already tried and found nothing, say so plainly (but keep
    // it clickable so a manual source can still be set); otherwise offer to set one.
    if (m.untracked) {
      return `<button class="cu-untracked" data-act="csource" data-path="${p}" data-name="${nm}"
        title="No update source found — click to link a Hugging Face repo or URL">No update source</button>`;
    }
    return `<button class="btn-sm" data-act="csource" data-path="${p}" data-name="${nm}">Set source</button>`;
  }

  // ---- theme --------------------------------------------------------------
  function applyTheme(theme) {
    document.documentElement.dataset.theme = theme;
    const sun = document.getElementById("sunIcon");
    const moon = document.getElementById("moonIcon");
    if (sun && moon) {
      sun.classList.toggle("active", theme === "light");
      moon.classList.toggle("active", theme === "dark");
    }
  }
  function initTheme() {
    // Saved preference wins; otherwise follow the OS setting on first run.
    let theme = localStorage.getItem("theme");
    if (!theme) {
      const prefersLight = window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches;
      theme = prefersLight ? "light" : "dark";
    }
    applyTheme(theme);
  }
  function toggleTheme() {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    applyTheme(next);
    localStorage.setItem("theme", next);
    if (backend && backend.set_theme) backend.set_theme(next);   // persist server-side too
  }

  // ---- toast --------------------------------------------------------------
  let toastTimer = null;
  function toast(msg) {
    const t = document.getElementById("toast");
    t.textContent = msg;
    t.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => t.classList.remove("show"), 2600);
  }

  // ---- actions ------------------------------------------------------------
  function onToggle(svc) {
    const s = state.services[svc] || {};
    const turnOn = !s.active;
    const card = document.querySelector(`.card[data-svc="${svc}"]`);
    const tog = card && card.querySelector(".toggle");
    if (backend && !backend.set_service) { toast("Controls arrive in the next step"); return; }
    if (tog) tog.classList.add("busy");
    toast(`${SVC_META[svc].name}: ${turnOn ? "starting…" : "stopping…"}`);
    if (backend && backend.set_service) {
      backend.set_service(svc, turnOn);      // real start/stop (async, status refresh follows)
    } else {
      // standalone mockup only (no backend at all)
      state.services[svc] = { active: turnOn, serving: turnOn, loaded: turnOn && svc === "ollama" ? "llama3.2:3b" : undefined };
      setTimeout(() => { render(); }, 400);
    }
  }

  function onUpdate(model) {
    if (backend && !backend.pull_model) { toast("Update wiring arrives in the next step"); return; }
    toast(`Pulling update for ${model}…`);
    if (backend && backend.pull_model) backend.pull_model(model);
  }

  function onExpand(svc) {
    state.expanded[svc] = !state.expanded[svc];
    render();
  }

  function openUrl(url) {
    if (backend && backend.open_url) backend.open_url(url);
    else window.open(url, "_blank");
  }

  // ---- ComfyUI model update actions --------------------------------------
  function onComfyCheck(path) {
    if (!path) return;
    if (backend && backend.comfy_check) { toast("Checking for update…"); backend.comfy_check(path); }
    else toast("Not connected to backend");
  }
  function onComfyUpdate(path) {
    if (!path) return;
    if (backend && backend.comfy_update) { toast("Starting update…"); backend.comfy_update(path); }
    else toast("Not connected to backend");
  }

  let modalPath = null;
  function buildModal() {
    const bd = document.createElement("div");
    bd.className = "modal-backdrop";
    bd.id = "sourceModal";
    bd.innerHTML = `
      <div class="modal">
        <h3>Set model source</h3>
        <div class="sub" id="smName"></div>
        <div class="method">
          <div class="m-title">Auto-detect on Civitai</div>
          <button class="btn-sm" id="smCivitai">Identify by file hash</button>
          <div class="m-hint">Hashes the file and asks Civitai. Works for models hosted on Civitai; large files take a moment.</div>
        </div>
        <div class="method">
          <div class="m-title">Hugging Face repo</div>
          <div class="m-row"><input id="smHf" placeholder="org/name or huggingface.co URL" /><button class="btn-sm" id="smHfBtn">Link</button></div>
          <div class="m-hint">Finds this filename inside the repo (e.g. Comfy-Org/Qwen-Image-Edit_ComfyUI).</div>
        </div>
        <div class="method">
          <div class="m-title">Direct URL</div>
          <div class="m-row"><input id="smUrl" placeholder="https://…/model.safetensors" /><button class="btn-sm" id="smUrlBtn">Link</button></div>
          <div class="m-hint">Re-downloads from this URL when it changes.</div>
        </div>
        <div class="modal-foot"><button class="btn-ghost" id="smClose">Close</button></div>
      </div>`;
    document.body.appendChild(bd);
    bd.addEventListener("click", e => { if (e.target === bd) closeModal(); });
    bd.querySelector("#smClose").addEventListener("click", closeModal);
    bd.querySelector("#smCivitai").addEventListener("click", () => {
      if (backend && backend.comfy_identify) { toast("Identifying on Civitai…"); backend.comfy_identify(modalPath); }
      closeModal();
    });
    bd.querySelector("#smHfBtn").addEventListener("click", () => {
      const v = bd.querySelector("#smHf").value.trim();
      if (v && backend && backend.comfy_set_hf) { toast("Linking to Hugging Face…"); backend.comfy_set_hf(modalPath, v); }
      closeModal();
    });
    bd.querySelector("#smUrlBtn").addEventListener("click", () => {
      const v = bd.querySelector("#smUrl").value.trim();
      if (v && backend && backend.comfy_set_url) { toast("Linking URL…"); backend.comfy_set_url(modalPath, v); }
      closeModal();
    });
  }
  function openSourceModal(path, name) {
    modalPath = path;
    const bd = document.getElementById("sourceModal");
    bd.querySelector("#smName").textContent = name || path || "";
    bd.querySelector("#smHf").value = "";
    bd.querySelector("#smUrl").value = "";
    bd.classList.add("show");
  }
  function closeModal() {
    const bd = document.getElementById("sourceModal");
    if (bd) bd.classList.remove("show");
    modalPath = null;
  }

  const COMFY_FOLDERS = [
    ["diffusion_models", "Diffusion models"], ["checkpoints", "Checkpoints"],
    ["text_encoders", "Text encoders"], ["vae", "VAE"], ["loras", "LoRAs"],
  ];
  function buildInstallModal() {
    const bd = document.createElement("div");
    bd.className = "modal-backdrop";
    bd.id = "installModal";
    const opts = COMFY_FOLDERS.map(([v, l]) => `<option value="${v}">${l}</option>`).join("");
    bd.innerHTML = `
      <div class="modal">
        <h3>Install a ComfyUI model</h3>
        <div class="sub">Paste a Hugging Face, Civitai, or direct link. The app downloads it, verifies it, and files it in the right folder.</div>
        <div class="m-row"><input id="inLink" placeholder="https://huggingface.co/…  or  https://civitai.com/models/…" /><button class="btn-sm" id="inAnalyze">Analyze</button></div>
        <div class="m-hint" id="inMsg"></div>
        <div id="inDetails" style="display:none">
          <div class="install-info" id="inInfo"></div>
          <div class="m-title" style="margin-top:14px">Destination folder</div>
          <div class="m-row"><select id="inFolder" class="select">${opts}</select></div>
          <div class="m-hint" id="inFolderHint"></div>
        </div>
        <div class="modal-foot" style="gap:10px">
          <button class="btn-ghost" id="inClose">Cancel</button>
          <button class="btn-sm accent" id="inGo" style="display:none">Download &amp; install</button>
        </div>
      </div>`;
    document.body.appendChild(bd);
    const close = () => { bd.classList.remove("show"); };
    bd.addEventListener("click", e => { if (e.target === bd) close(); });
    bd.querySelector("#inClose").addEventListener("click", close);
    bd.querySelector("#inAnalyze").addEventListener("click", () => {
      const link = bd.querySelector("#inLink").value.trim();
      const msg = bd.querySelector("#inMsg");
      if (!link) { msg.textContent = "Paste a link first."; return; }
      if (!backend || !backend.comfy_analyze_install) { msg.textContent = "Available when running in the app."; return; }
      msg.textContent = "Analyzing…";
      bd.querySelector("#inDetails").style.display = "none";
      bd.querySelector("#inGo").style.display = "none";
      backend.comfy_analyze_install(link, res => {
        let r; try { r = JSON.parse(res); } catch (e) { r = { ok: false, error: "bad response" }; }
        if (!r.ok) { msg.textContent = "Couldn't read that link: " + (r.error || "unknown"); return; }
        msg.textContent = "";
        bd.querySelector("#inInfo").innerHTML =
          `<div class="ii-row"><span>File</span><b>${esc(r.filename)}</b></div>` +
          `<div class="ii-row"><span>Source</span><b>${esc(r.source)}${r.size_human ? " · " + esc(r.size_human) : ""}</b></div>`;
        const sel = bd.querySelector("#inFolder");
        const hint = bd.querySelector("#inFolderHint");
        if (r.category) {
          sel.value = r.category;
          hint.textContent = "Suggested folder (" + r.category_reason + "). Change it if that's wrong.";
        } else {
          hint.textContent = "Couldn't determine the folder from the link — please choose one.";
        }
        bd.querySelector("#inDetails").style.display = "block";
        bd.querySelector("#inGo").style.display = "inline-flex";
      });
    });
    bd.querySelector("#inGo").addEventListener("click", () => {
      const link = bd.querySelector("#inLink").value.trim();
      const folder = bd.querySelector("#inFolder").value;
      if (backend && backend.comfy_install) { toast("Downloading model…"); backend.comfy_install(link, folder); }
      close();
    });
  }
  function openInstallModal() {
    const bd = document.getElementById("installModal");
    bd.querySelector("#inLink").value = "";
    bd.querySelector("#inMsg").textContent = "";
    bd.querySelector("#inDetails").style.display = "none";
    bd.querySelector("#inGo").style.display = "none";
    bd.classList.add("show");
  }

  function buildLogModal() {
    const bd = document.createElement("div");
    bd.className = "modal-backdrop";
    bd.id = "logModal";
    bd.innerHTML = `
      <div class="modal log-modal">
        <h3 id="lmTitle">Service log</h3>
        <div class="sub">The last lines from this service's journal.</div>
        <pre class="log-pre" id="lmBody">Loading…</pre>
        <div class="modal-foot"><button class="btn-ghost" id="lmClose">Close</button></div>
      </div>`;
    document.body.appendChild(bd);
    bd.addEventListener("click", e => { if (e.target === bd) bd.classList.remove("show"); });
    bd.querySelector("#lmClose").addEventListener("click", () => bd.classList.remove("show"));
  }
  function openLogModal(svc) {
    const bd = document.getElementById("logModal");
    bd.querySelector("#lmTitle").textContent = (SVC_META[svc] ? SVC_META[svc].name : svc) + " — recent log";
    const body = bd.querySelector("#lmBody");
    body.textContent = "Loading…";
    bd.classList.add("show");
    if (backend && backend.get_log) {
      backend.get_log(svc, t => {
        body.textContent = t || "(no output)";
        body.scrollTop = body.scrollHeight;   // newest lines (the crash) first
      });
    } else {
      body.textContent = "(log is available when running in the app)";
    }
  }

  // ---- event wiring -------------------------------------------------------
  function onRescan() {
    const b = document.getElementById("rescanBtn");
    if (b) { b.classList.add("spinning"); setTimeout(() => b.classList.remove("spinning"), 900); }
    toast("Rescanning for models…");
    if (backend && backend.request_refresh) backend.request_refresh();
    else render();
  }

  function wire() {
    buildModal();
    buildLogModal();
    buildInstallModal();
    document.getElementById("brandMark").innerHTML = I.spark;
    document.getElementById("sunIcon").innerHTML = I.sun;
    document.getElementById("moonIcon").innerHTML = I.moon;
    const rescanBtn = document.getElementById("rescanBtn");
    rescanBtn.innerHTML = I.refresh;
    rescanBtn.addEventListener("click", onRescan);
    document.getElementById("themeToggle").addEventListener("click", toggleTheme);

    document.getElementById("cards").addEventListener("click", (e) => {
      const el = e.target.closest("[data-act]");
      if (!el) return;
      const card = e.target.closest(".card");
      const svc = card && card.dataset.svc;
      const act = el.dataset.act;
      if (act === "toggle") onToggle(svc);
      else if (act === "expand") onExpand(svc);
      else if (act === "update") onUpdate(el.dataset.model);
      else if (act === "csource") openSourceModal(el.dataset.path, el.dataset.name);
      else if (act === "ccheck") onComfyCheck(el.dataset.path);
      else if (act === "cupdate") onComfyUpdate(el.dataset.path);
      else if (act === "open") openUrl(localServiceUrl(el.dataset.port));
      else if (act === "clog") openLogModal(el.dataset.svc);
      else if (act === "cinstall") openInstallModal();
    });

    document.querySelectorAll(".browse-link").forEach(a => {
      a.innerHTML = `${I[a.dataset.icon]}<span>${a.textContent.trim()}</span>${I.ext}`;
      a.addEventListener("click", (e) => { e.preventDefault(); openUrl(a.dataset.url); });
    });
  }

  // ---- data intake from backend ------------------------------------------
  function applyState(payload) {
    // payload: { services: {svc:{active,serving,loaded}}, models: [...] }
    if (payload.services) state.services = payload.services;
    if (payload.models) state.models = payload.models;
    if (payload.comfyui_models) state.comfyModels = payload.comfyui_models;
    render();
  }
  window.__applyState = applyState;   // backend pushes here

  // ---- boot ---------------------------------------------------------------
  function boot() {
    initTheme();
    wire();
    if (typeof QWebChannel !== "undefined" && window.qt && window.qt.webChannelTransport) {
      new QWebChannel(window.qt.webChannelTransport, (channel) => {
        backend = channel.objects.backend;
        if (backend.state_changed) backend.state_changed.connect((json) => applyState(JSON.parse(json)));
        if (backend.notify) backend.notify.connect((msg) => toast(msg));
        if (backend.get_theme) backend.get_theme(function (t) { if (t) { applyTheme(t); localStorage.setItem("theme", t); } });
        if (backend.request_refresh) backend.request_refresh();
      });
    } else {
      // standalone / mockup: use sample data
      state.services = JSON.parse(JSON.stringify(SAMPLE));
      state.models = SAMPLE_MODELS;
      state.comfyModels = SAMPLE_COMFY;
      state.expanded.ollama = true;
      state.expanded.comfyui = true;
      render();
    }
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
