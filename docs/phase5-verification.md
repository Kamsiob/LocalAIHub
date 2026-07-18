# Phase 5 — skeptical end-to-end verification

Driven by `tools/verify_phase5.py`: it launches the **real** app with a live
event loop, clicks the actual DOM controls (same handlers a user triggers), and
after each one checks the **real system state** — not just the UI. Browser opens
are intercepted so verification spawns no stray tabs.

## Result: 10 / 10 checks passed

| Control exercised | What was checked against reality | Result |
|---|---|---|
| ComfyUI toggle (start) | `systemctl --user is-active comfyui` → `active` | PASS |
| — toast feedback | `#toast` gains `show` class on toggle (notify signal delivered) | PASS |
| ComfyUI toggle (stop) | unit → `inactive` | PASS |
| Ollama expand | real `.model` rows rendered (5) | PASS |
| Load model into memory | `GET /api/ps` actually lists `llama3.2:1b` | PASS |
| — UI reflects it | `.badge.loaded` appears after the 5s auto-refresh | PASS |
| — status line | header reads "Running · llama3.2:1b in memory" | PASS |
| Theme toggle | preference written to `~/.config/local-ai-hub/config.json` | PASS |
| Browse link | `open_url` invoked with `https://ollama.com/library` | PASS |

The final screenshot (light theme, since the run toggled it) showed the running
app on live data: Ollama with the loaded model badged **In memory**, the other
four **On disk**, Open WebUI running, ComfyUI stopped.

## Honest notes / caveats
- **Headless rendering.** Verification runs the app on the `offscreen` Qt
  platform with software rendering (`--disable-gpu`) and captures via
  `QWebEngineView.grab()`. This is faithful to layout, color, and state, but it
  is not the GPU-composited on-screen path. The breathing-glow animation and
  hover states are CSS and render identically on screen; they just can't be
  shown in a still capture. Launched normally (`python app.py`) the same page
  runs on the live Wayland session.
- **Browse links** were verified by intercepting `QDesktopServices.openUrl` to
  avoid opening real browser tabs during an unattended run. Opened normally they
  hand the URL to the system default browser.
- **Model update** uses a real streaming `ollama pull`; it was exercised end to
  end in Phase 4 against a throwaway model (`all-minilm`), never a real one.
- Theme was reset to `dark` after the run (the test had flipped it to light).
