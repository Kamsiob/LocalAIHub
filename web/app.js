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
    library: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M4 5.5A1.5 1.5 0 015.5 4H11v16H5.5A1.5 1.5 0 014 18.5v-13z"/><path d="M11 4h7.5A1.5 1.5 0 0120 5.5v13a1.5 1.5 0 01-1.5 1.5H11"/></svg>',
    hugging: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="12" cy="12" r="8"/><path d="M8.5 10h.01M15.5 10h.01M8.5 14.5c1 1 2.2 1.5 3.5 1.5s2.5-.5 3.5-1.5" stroke-linecap="round"/></svg>',
    civitai: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><rect x="3.5" y="5" width="17" height="14" rx="2.5"/><circle cx="8.5" cy="10" r="1.5"/><path d="M4 17l4.5-4 3 2.5L16 11l4 4.5" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    ext: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M14 5h5v5M19 5l-8 8M18 14v4a1 1 0 01-1 1H6a1 1 0 01-1-1V7a1 1 0 011-1h4"/></svg>',
  };

  const SVC_META = {
    ollama:    { name: "Ollama",     sub: "Local LLM runtime · :11434", hasModels: true },
    openwebui: { name: "Open WebUI", sub: "Chat front-end · :3000",      hasModels: false },
    comfyui:   { name: "ComfyUI",    sub: "Image generation · :8188",    hasModels: false },
  };

  // ---- sample data (used only without a backend bridge) -------------------
  const SAMPLE = {
    ollama:    { active: true,  serving: true,  loaded: "qwen3-coder:30b" },
    openwebui: { active: true,  serving: true },
    comfyui:   { active: false, serving: false },
  };
  const SAMPLE_MODELS = [
    { name: "qwen3-coder:30b", size_human: "17.3 GB", loaded: true,  vram_human: "18 GB" },
    { name: "gemma4:31b",      size_human: "18.5 GB", loaded: false, vram_human: "" },
    { name: "gemma4:26b",      size_human: "16.8 GB", loaded: false, vram_human: "" },
    { name: "nomic-embed-text:latest", size_human: "262 MB", loaded: false, vram_human: "" },
  ];

  // ---- backend bridge -----------------------------------------------------
  let backend = null;        // set when QWebChannel connects
  const state = { services: {}, models: [], expanded: { ollama: false } };

  function statusText(svc, s) {
    if (!s || !s.active) return { txt: "Stopped", cls: "" };
    if (!s.serving) return { txt: "Starting…", cls: "is-starting" };
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

  function modelsMarkup(svc) {
    const models = state.models;
    const rows = models.length ? models.map(m => `
      <div class="model">
        <span class="model-name">${m.name}</span>
        <span class="size">${m.size_human || ""}</span>
        <span class="badge ${m.loaded ? "loaded" : ""}"><span class="b-dot"></span>${m.loaded ? "In memory" : "On disk"}</span>
        <button class="btn-sm" data-act="update" data-model="${m.name}">Update</button>
      </div>`).join("") : `<div class="model"><span class="model-name" style="color:var(--text-faint)">No models installed</span></div>`;
    return `
      <div class="models">
        <div class="models-inner">
          <div class="models-head"><span>Installed models</span><span>${models.length} total</span></div>
          ${rows}
        </div>
      </div>`;
  }

  // ---- theme --------------------------------------------------------------
  function applyTheme(theme) {
    document.documentElement.dataset.theme = theme;
  }
  function initTheme() {
    const saved = localStorage.getItem("theme") || "dark";
    applyTheme(saved);
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
    if (tog) tog.classList.add("busy");
    toast(`${SVC_META[svc].name}: ${turnOn ? "starting…" : "stopping…"}`);
    if (backend && backend.set_service) {
      backend.set_service(svc, turnOn);      // real start/stop (async, status refresh follows)
    } else {
      // mock
      state.services[svc] = { active: turnOn, serving: turnOn, loaded: turnOn && svc === "ollama" ? "qwen3-coder:30b" : undefined };
      setTimeout(() => { render(); }, 400);
    }
  }

  function onUpdate(model) {
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

  // ---- event wiring -------------------------------------------------------
  function wire() {
    document.getElementById("brandMark").innerHTML = I.spark;
    document.getElementById("sunIcon").innerHTML = I.sun;
    document.getElementById("moonIcon").innerHTML = I.moon;
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
      state.expanded.ollama = true;
      render();
    }
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
