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
    shield: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l7 3v5c0 4.5-3 7.6-7 9-4-1.4-7-4.5-7-9V6l7-3z"/><path d="M9 12l2 2 4-4"/></svg>',
    book: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 5.5A1.5 1.5 0 015.5 4H12v15H5.5A1.5 1.5 0 004 20.5v-15z"/><path d="M20 5.5A1.5 1.5 0 0018.5 4H12v15h6.5a1.5 1.5 0 011.5 1.5v-15z"/></svg>',
    copy: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a2 2 0 012-2h10"/></svg>',
    check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12l5 5L20 6"/></svg>',
    xmark: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>',
    library: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M4 5.5A1.5 1.5 0 015.5 4H11v16H5.5A1.5 1.5 0 014 18.5v-13z"/><path d="M11 4h7.5A1.5 1.5 0 0120 5.5v13a1.5 1.5 0 01-1.5 1.5H11"/></svg>',
    hugging: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="12" cy="12" r="8"/><path d="M8.5 10h.01M15.5 10h.01M8.5 14.5c1 1 2.2 1.5 3.5 1.5s2.5-.5 3.5-1.5" stroke-linecap="round"/></svg>',
    civitai: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><rect x="3.5" y="5" width="17" height="14" rx="2.5"/><circle cx="8.5" cy="10" r="1.5"/><path d="M4 17l4.5-4 3 2.5L16 11l4 4.5" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    ext: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M14 5h5v5M19 5l-8 8M18 14v4a1 1 0 01-1 1H6a1 1 0 01-1-1V7a1 1 0 011-1h4"/></svg>',
    info: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 7.5h.01"/></svg>',
    youtube: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M23 12s0-3.2-.4-4.7a2.5 2.5 0 00-1.77-1.77C19.34 5.1 12 5.1 12 5.1s-7.34 0-8.83.43A2.5 2.5 0 001.4 7.3C1 8.8 1 12 1 12s0 3.2.4 4.7a2.5 2.5 0 001.77 1.77C4.66 18.9 12 18.9 12 18.9s7.34 0 8.83-.43a2.5 2.5 0 001.77-1.77C23 15.2 23 12 23 12zM9.75 15.02V8.98L15.5 12l-5.75 3.02z"/></svg>',
    github: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.48 2 2 6.48 2 12c0 4.42 2.87 8.17 6.84 9.5.5.09.68-.22.68-.48 0-.24-.01-.87-.01-1.7-2.78.6-3.37-1.34-3.37-1.34-.45-1.16-1.11-1.47-1.11-1.47-.91-.62.07-.6.07-.6 1 .07 1.53 1.03 1.53 1.03.89 1.52 2.34 1.08 2.91.83.09-.65.35-1.08.63-1.33-2.22-.25-4.55-1.11-4.55-4.94 0-1.09.39-1.98 1.03-2.68-.1-.25-.45-1.27.1-2.65 0 0 .84-.27 2.75 1.02.8-.22 1.65-.33 2.5-.34.85 0 1.7.12 2.5.34 1.91-1.29 2.75-1.02 2.75-1.02.55 1.38.2 2.4.1 2.65.64.7 1.03 1.59 1.03 2.68 0 3.84-2.34 4.68-4.57 4.93.36.31.68.92.68 1.85 0 1.34-.01 2.42-.01 2.75 0 .27.18.58.69.48A10.01 10.01 0 0022 12c0-5.52-4.48-10-10-10z"/></svg>',
    globe: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M3 12h18"/><path d="M12 3a15 15 0 010 18M12 3a15 15 0 000 18"/></svg>',
    telegram: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M21.94 4.63l-3.3 15.56c-.25 1.1-.9 1.37-1.83.85l-5.05-3.72-2.44 2.35c-.27.27-.5.5-1.02.5l.36-5.16L17.5 6.9c.4-.36-.09-.56-.62-.2L6.9 13.06l-4.9-1.53c-1.07-.33-1.09-1.07.22-1.58l19.14-7.38c.89-.33 1.67.2 1.38 1.6z"/></svg>',
    coffee: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 8h13v5a4 4 0 01-4 4H8a4 4 0 01-4-4V8z"/><path d="M17 9h1.5a2.5 2.5 0 010 5H17"/><path d="M7 2.6c-.4.6-.4 1.4 0 2M11 2.6c-.4.6-.4 1.4 0 2M14.5 20.5h-11"/></svg>',
    mail: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="5" width="18" height="14" rx="2.5"/><path d="M4 7l8 5 8-5"/></svg>',
  };

  // The user's finalized links (used by the About & Links panel).
  const LINKS = {
    youtube:  "https://youtube.com/@kamsiob",
    github:   "https://github.com/kamsiob",
    website:  "https://kamsiob.com",
    bmc:      "https://buymeacoffee.com/kamsiob",
    telegram: "https://t.me/+g5LKm9rUnNcxMjk5",
    email:    "hello@kamsiob.com",
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
    { name: "llama3.2:3b", size_human: "2.0 GB", loaded: true,  vram_human: "3.4 GB", update: { available: false, detail: "Up to date" } },
    { name: "mistral:7b",  size_human: "4.1 GB", loaded: false, vram_human: "", update: { available: true, detail: "Update available" } },
    { name: "phi3:mini",   size_human: "2.2 GB", loaded: false, vram_human: "", update: null },
    { name: "gemma2:2b",   size_human: "1.6 GB", loaded: false, vram_human: "", update: { available: false, detail: "Up to date" } },
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
    if (s && s.present === false) return { txt: "Not installed", cls: "is-absent" };
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
      const absent = s.present === false;
      const card = document.createElement("div");
      card.className = `card ${st.cls}` + (state.expanded[svc] && !absent ? " expanded" : "");
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
            ${(meta.hasModels && !absent) ? `<div class="chevron" data-act="expand">${I.chevron}</div>` : ""}
            ${absent
              ? `<div class="toggle disabled" role="switch" aria-checked="false" aria-disabled="true" title="${meta.name} isn't installed on this machine"><span class="knob"></span></div>`
              : `<div class="toggle" data-act="toggle" role="switch" aria-checked="${on}"><span class="knob"></span></div>`}
          </div>
        </div>
        ${(meta.hasModels && !absent) ? modelsMarkup(svc) : ""}
      `;
      cards.appendChild(card);

      if (meta.hasModels && !absent) {
        const wrap = card.querySelector(".models");
        // Set the height instantly (no transition) on every render so a data
        // refresh never re-animates an already-open list into a flicker.
        if (wrap) wrap.style.maxHeight = state.expanded[svc] ? "none" : "0";
      }
    }
  }

  function esc(s) { return String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }

  // Ollama update control: Update only when one is available, else Up to date;
  // Check when we haven't looked yet (or couldn't determine).
  function ollamaAction(m) {
    const nm = esc(m.name);
    if (m.update && m.update.available === true) {
      return `<button class="btn-sm accent" data-act="update" data-model="${nm}">Update</button>`;
    }
    if (m.update && m.update.available === false) {
      return `<span class="cu-uptodate" title="${esc((m.update && m.update.detail) || "")}">Up to date</span>`;
    }
    return `<button class="btn-sm" data-act="ocheck" data-model="${nm}" title="${esc((m.update && m.update.detail) || "Check the registry for an update")}">Check</button>`;
  }

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
        ${ollamaAction(m)}
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
    </div>`;
    if (!models.length) {
      return `<div class="models"><div class="models-inner">
        ${topbar}
        <div class="model"><span class="model-name" style="color:var(--text-faint)">No model files found under ComfyUI/models</span></div>
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
    if (s.present === false) { toast(`${SVC_META[svc].name} isn't installed on this machine`); return; }
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
        <div class="method">
          <div class="m-title">Civitai API key <span style="font-weight:400;color:var(--text-faint)">(optional)</span></div>
          <div class="m-row"><input id="smKey" type="password" placeholder="for gated Civitai downloads" /><button class="btn-sm" id="smKeyBtn">Save</button></div>
          <div class="m-hint">Some Civitai downloads require a key. Get one at civitai.com → Account → API Keys.</div>
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
    bd.querySelector("#smKeyBtn").addEventListener("click", () => {
      const v = bd.querySelector("#smKey").value;
      if (backend && backend.set_civitai_key) backend.set_civitai_key(v);
      bd.querySelector("#smKey").value = "";
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

  function buildSetupModal() {
    const bd = document.createElement("div");
    bd.className = "modal-backdrop";
    bd.id = "setupModal";
    bd.innerHTML = `
      <div class="modal sc-modal">
        <h3>Setup check</h3>
        <div class="sub">Verifies the supported setup: Bazzite / Fedora Atomic on an AMD Strix Halo (gfx1151) iGPU.</div>
        <div id="scBody">Checking…</div>
        <div class="modal-foot" style="gap:10px">
          <button class="btn-ghost" id="scClose">Close</button>
          <button class="btn-sm" id="scRerun">Re-run</button>
        </div>
      </div>`;
    document.body.appendChild(bd);
    bd.addEventListener("click", e => { if (e.target === bd) bd.classList.remove("show"); });
    bd.querySelector("#scClose").addEventListener("click", () => bd.classList.remove("show"));
    bd.querySelector("#scRerun").addEventListener("click", runSetupCheck);
    bd.querySelector("#scBody").addEventListener("click", e => {
      const b = e.target.closest("[data-fix]");
      if (!b) return;
      if (backend && backend.apply_setup_fix) {
        b.textContent = "Fixing…"; b.disabled = true;
        toast("Applying fix…");
        backend.apply_setup_fix(b.dataset.fix);
      }
    });
  }
  function runSetupCheck() {
    const body = document.getElementById("scBody");
    body.textContent = "Checking…";
    if (backend && backend.run_setup_check) {
      backend.run_setup_check(res => { try { renderSetup(JSON.parse(res)); } catch (e) { body.textContent = "Check failed."; } });
    } else {
      body.innerHTML = `<div class="m-hint">Setup check runs inside the app (needs the backend).</div>`;
    }
  }
  function openSetupModal() {
    document.getElementById("setupModal").classList.add("show");
    runSetupCheck();
  }
  const SC_ICON = { pass: I.check, warn: I.warn, fail: I.xmark };
  function renderSetup(data) {
    const body = document.getElementById("scBody");
    if (data.error) { body.innerHTML = `<div class="m-warn" style="display:flex">${I.warn}<span>${esc(data.error)}</span></div>`; return; }
    const p = data.platform || {};
    if (!data.applies) {
      body.innerHTML = `
        <div class="sc-plat">Detected: <b>${esc(p.distro || "unknown")}</b> · <b>${esc(p.gpu || "unknown")}</b></div>
        <div class="m-hint" style="margin-top:12px">These checks apply only to Bazzite / Fedora Atomic on an AMD Strix Halo (gfx1151) iGPU. This machine doesn't match, so they're skipped — they wouldn't apply here.</div>`;
      return;
    }
    const rows = (data.checks || []).map(c => `
      <div class="sc-row">
        <span class="sc-status ${c.status}">${SC_ICON[c.status] || ""}</span>
        <div class="sc-text"><div class="sc-label">${esc(c.label)}</div><div class="sc-detail">${esc(c.detail)}</div></div>
        ${c.fix ? `<button class="btn-sm" data-fix="${esc(c.fix)}">Fix</button>` : ""}
      </div>`).join("");
    const pass = data.checks.filter(c => c.status === "pass").length;
    body.innerHTML = `
      <div class="sc-plat">${I.check2 || ""}<b>${esc(p.distro)}</b> · ${esc(p.gpu)} <span class="sc-summary">${pass}/${data.checks.length} OK</span></div>
      <div class="sc-list">${rows}</div>`;
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
    toast("Rescanning + checking for updates…");
    if (backend) {
      if (backend.request_refresh) backend.request_refresh();
      if (backend.check_ollama_updates) backend.check_ollama_updates();   // check every model
    } else {
      render();
    }
  }

  // ---- Getting Started screen (native, from Backend.get_guide) -----------
  let guideData = null;
  let guideTrack = null;
  function buildGuideScreen() {
    const el = document.createElement("div");
    el.className = "guide-screen";
    el.id = "guideScreen";
    el.innerHTML = `
      <div class="guide-head">
        <div><div class="guide-title">Getting Started</div><div class="guide-sub" id="guideSub"></div></div>
        <button class="btn-ghost" id="guideClose">Close</button>
      </div>
      <div class="guide-tabs" id="guideTabs"></div>
      <div class="guide-body" id="guideBody">Loading…</div>`;
    document.body.appendChild(el);
    el.querySelector("#guideClose").addEventListener("click", () => el.classList.remove("show"));
    el.addEventListener("click", (e) => {
      const cp = e.target.closest(".gb-copy"); if (cp) return copyCode(cp);
      const tab = e.target.closest("[data-track]"); if (tab) return setGuideTrack(tab.dataset.track);
      const head = e.target.closest(".guide-sec-head"); if (head) head.parentElement.classList.toggle("open");
    });
  }
  function openGuide() {
    document.getElementById("guideScreen").classList.add("show");
    if (guideData) return renderGuide();
    if (backend && backend.get_guide) {
      backend.get_guide(res => { try { guideData = JSON.parse(res); renderGuide(); } catch (e) { document.getElementById("guideBody").textContent = "Could not load the guide."; } });
    } else {
      document.getElementById("guideTabs").innerHTML = "";
      document.getElementById("guideBody").innerHTML = `<div class="m-hint">The Getting Started guide loads inside the app.</div>`;
    }
  }
  function setGuideTrack(id) { guideTrack = id; renderGuide(); document.getElementById("guideBody").scrollTop = 0; }
  function renderGuide() {
    const d = guideData;
    document.getElementById("guideSub").textContent = d.subtitle || "";
    if (!guideTrack) guideTrack = d.tracks[0].id;
    document.getElementById("guideTabs").innerHTML = d.tracks.map(t =>
      `<button class="guide-tab ${t.id === guideTrack ? "active" : ""}" data-track="${esc(t.id)}">${esc(t.label)}</button>`).join("");
    const track = d.tracks.find(t => t.id === guideTrack) || d.tracks[0];
    let html = `<div class="guide-intro">${d.intro.map(renderGuideBlock).join("")}</div>`;
    if (track.blocks) html += `<div class="guide-track">${track.blocks.map(renderGuideBlock).join("")}</div>`;
    if (track.sections) html += track.sections.map((s, i) => `
      <div class="guide-sec ${i === 0 ? "open" : ""}">
        <div class="guide-sec-head"><span>${esc(s.title)}</span><span class="guide-chev">${I.chevron}</span></div>
        <div class="guide-sec-body">${s.blocks.map(renderGuideBlock).join("")}</div>
      </div>`).join("");
    document.getElementById("guideBody").innerHTML = html;
  }
  function renderGuideBlock(b) {
    if (b.type === "p") return `<div class="gb-p">${guideText(b.text)}</div>`;
    if (b.type === "h") return `<h4 class="gb-h">${esc(b.text)}</h4>`;
    if (b.type === "warn") return `<div class="gb-callout warn">${I.warn}<div>${guideText(b.text)}</div></div>`;
    if (b.type === "note") return `<div class="gb-callout note">${I.book}<div>${guideText(b.text)}</div></div>`;
    if (b.type === "code") return `<div class="gb-code"><button class="gb-copy" title="Copy">${I.copy}</button><pre><code>${esc(b.code)}</code></pre></div>`;
    return "";
  }
  function guideText(t) {
    const lines = esc(t).split("\n");
    if (lines.some(l => l.trim().startsWith("•"))) {
      return "<ul class='gb-ul'>" + lines.map(l => l.trim().startsWith("•")
        ? `<li>${l.trim().slice(1).trim()}</li>`
        : (l.trim() ? `<li class="gb-noli">${l}</li>` : "")).join("") + "</ul>";
    }
    return lines.join("<br>");
  }
  function copyCode(btn) {
    const code = btn.parentElement.querySelector("code");
    copyText(code ? code.textContent : "");
    const prev = btn.innerHTML;
    btn.innerHTML = I.check;
    btn.classList.add("copied");
    setTimeout(() => { btn.innerHTML = prev; btn.classList.remove("copied"); }, 1200);
  }
  function copyText(text) {
    try {
      const ta = document.createElement("textarea");
      ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0";
      document.body.appendChild(ta); ta.focus(); ta.select();
      document.execCommand("copy"); document.body.removeChild(ta);
    } catch (e) { if (navigator.clipboard) navigator.clipboard.writeText(text); }
  }

  // ---- About & Links panel (same full-screen pattern as Getting Started) --
  function linkChip(key, icon, title, sub) {
    return `<a class="link-chip" data-act="open" data-url="${LINKS[key]}">
      <span class="lc-icon">${icon}</span>
      <span class="lc-text"><span class="lc-title">${title}</span><span class="lc-sub">${sub}</span></span>
      <span class="lc-ext">${I.ext}</span></a>`;
  }
  function buildAboutScreen() {
    const el = document.createElement("div");
    el.className = "guide-screen";   // reuse the Getting Started shell for an exact visual match
    el.id = "aboutScreen";
    el.innerHTML = `
      <div class="guide-head">
        <div><div class="guide-title">About &amp; Links</div><div class="guide-sub">Local AI Hub · made by Kamsiob</div></div>
        <button class="btn-ghost" id="aboutClose">Close</button>
      </div>
      <div class="guide-body">
        <div class="about-lead">Local AI Hub is a free, open-source control panel for the AI services running on your own machine — <b>local-only, no accounts, no telemetry</b>.</div>
        <div class="about-note">Follow along, get help, or just say hello through the links below.</div>

        <div class="about-section-label">Links</div>
        <div class="link-grid">
          ${linkChip("youtube",  I.youtube,  "YouTube",  "@kamsiob")}
          ${linkChip("github",   I.github,   "GitHub",   "github.com/kamsiob")}
          ${linkChip("website",  I.globe,    "Website",  "kamsiob.com")}
          ${linkChip("telegram", I.telegram, "Telegram", "Kamsiob Lab")}
        </div>

        <div class="about-section-label">Support</div>
        <a class="support-btn" data-act="open" data-url="${LINKS.bmc}">
          <span class="sb-icon">${I.coffee}</span>
          <span class="sb-text"><span class="sb-title">Buy me a coffee</span><span class="sb-sub">Support the project — entirely optional, always appreciated</span></span>
          <span class="sb-ext">${I.ext}</span>
        </a>

        <div class="about-section-label">Feedback</div>
        <a class="email-link" data-act="open" data-url="mailto:${LINKS.email}">${I.mail}<span>Questions or suggestions? <b>${LINKS.email}</b></span></a>
      </div>`;
    document.body.appendChild(el);
    el.querySelector("#aboutClose").addEventListener("click", () => el.classList.remove("show"));
    el.addEventListener("click", (e) => {
      const a = e.target.closest("[data-act='open']");
      if (a) { e.preventDefault(); openUrl(a.dataset.url); }
    });
  }
  function openAbout() { document.getElementById("aboutScreen").classList.add("show"); }

  function buildProgressBar() {
    const el = document.createElement("div");
    el.className = "dl-progress";
    el.id = "dlProgress";
    el.innerHTML = `<div class="dl-fill" id="dlFill"></div><div class="dl-label" id="dlLabel"></div>`;
    document.body.appendChild(el);
  }
  let dlHideTimer = null;
  function updateProgress(d) {
    const el = document.getElementById("dlProgress");
    const fill = document.getElementById("dlFill");
    const label = document.getElementById("dlLabel");
    if (!el) return;
    if (!d.active) {
      fill.style.width = "100%";
      clearTimeout(dlHideTimer);
      dlHideTimer = setTimeout(() => { el.classList.remove("show"); setTimeout(() => { fill.style.width = "0%"; }, 350); }, 500);
      return;
    }
    clearTimeout(dlHideTimer);
    el.classList.add("show");
    const frac = d.fraction || 0;
    const pct = Math.round(frac * 100);
    fill.style.width = (frac > 0 ? pct : 4) + "%";
    let txt = d.label || "Working";
    if (frac > 0 && frac < 1) txt += ` · ${pct}%`;
    else if (d.stage && d.stage !== "starting") txt += ` · ${d.stage}`;
    else txt += " · starting…";
    label.textContent = txt;
  }

  function wire() {
    buildModal();
    buildLogModal();
    buildSetupModal();
    buildGuideScreen();
    buildAboutScreen();
    buildProgressBar();
    document.getElementById("brandMark").innerHTML = I.spark;
    document.getElementById("sunIcon").innerHTML = I.sun;
    document.getElementById("moonIcon").innerHTML = I.moon;
    const guideBtn = document.getElementById("guideBtn");
    guideBtn.querySelector(".gb-icon").innerHTML = I.book;
    guideBtn.addEventListener("click", openGuide);
    const aboutBtn = document.getElementById("aboutBtn");
    aboutBtn.querySelector(".gb-icon").innerHTML = I.info;
    aboutBtn.addEventListener("click", openAbout);
    const setupBtn = document.getElementById("setupBtn");
    setupBtn.innerHTML = I.shield;
    setupBtn.addEventListener("click", openSetupModal);
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
      else if (act === "ocheck") { if (backend && backend.check_ollama_update) { toast("Checking for update…"); backend.check_ollama_update(el.dataset.model); } }
      else if (act === "csource") openSourceModal(el.dataset.path, el.dataset.name);
      else if (act === "ccheck") onComfyCheck(el.dataset.path);
      else if (act === "cupdate") onComfyUpdate(el.dataset.path);
      else if (act === "open") openUrl(localServiceUrl(el.dataset.port));
      else if (act === "clog") openLogModal(el.dataset.svc);
    });

    document.querySelectorAll(".browse-link").forEach(a => {
      a.innerHTML = `${I[a.dataset.icon]}<span>${a.textContent.trim()}</span>${I.ext}`;
      a.addEventListener("click", (e) => { e.preventDefault(); openUrl(a.dataset.url); });
    });
    document.querySelectorAll(".foot-link").forEach(a => {
      a.addEventListener("click", (e) => { e.preventDefault(); openUrl(a.dataset.url); });
    });
  }

  // ---- data intake from backend ------------------------------------------
  let lastPayloadKey = "";
  function applyState(payload) {
    // Skip the re-render entirely when nothing changed — the periodic refresh
    // fires every few seconds, and re-rendering unchanged data is what caused
    // the open model list to flicker.
    const key = JSON.stringify(payload);
    if (key === lastPayloadKey) return;
    lastPayloadKey = key;
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
        if (backend.download_progress) backend.download_progress.connect((json) => {
          try { updateProgress(JSON.parse(json)); } catch (e) {}
        });
        if (backend.setup_result) backend.setup_result.connect((json) => {
          if (document.getElementById("setupModal").classList.contains("show")) {
            try { renderSetup(JSON.parse(json)); } catch (e) {}
          }
        });
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
