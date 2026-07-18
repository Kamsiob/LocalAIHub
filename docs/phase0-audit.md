# Phase 0 — Environment Audit

Audit performed on 2026-07-17. Goal: verify the real state of the machine before
building anything, and record findings even where nothing was changed.

## Hardware / platform
- CPU/APU: AMD **Strix Halo** (Ryzen AI Max), integrated **Radeon 8060S** (gfx1151).
- OS: Fedora-based atomic desktop (`/var/home` real home, `/home` symlinked). Wayland session, `DISPLAY=:0` (XWayland present).
- System Python: **3.14.6** only (no 3.11–3.13 present).
- No passwordless sudo. No `/opt/rocm` system install (ROCm ships inside the ComfyUI venv wheels).

## Services — actual state vs. assumption

### Ollama
- **Assumption in plan:** already a `systemctl --user` service.
- **Reality found:** it was a **system** service at `/etc/systemd/system/ollama.service`
  (`User=Kamsiob`, `ExecStart=/usr/local/bin/ollama serve`,
  env `OLLAMA_VULKAN=1 OLLAMA_IGPU_ENABLE=1 OLLAMA_HOST=0.0.0.0:11434`, `Restart=always`).
- **Why it matters:** a system service can't be start/stopped from a user-session GUI
  without root, and there is no passwordless sudo.
- **Action taken (approved):** migrated to a **user** service at
  `~/.config/systemd/user/ollama.service` with the same env vars; disabled the system unit
  (`sudo systemctl disable --now ollama`, one-time) and enabled linger
  (`loginctl enable-linger`). Verified: system unit inactive, user unit active,
  port 11434 → HTTP 200, all models intact, process runs as `Kamsiob`.
- Installed models (disk): `gemma4:26b` (17 GB), `gemma4:31b` (19 GB),
  `qwen3-coder:30b` (18 GB), `nomic-embed-text:latest` (274 MB), `llama3.2:1b` (1.3 GB).
  The first four are the user's "real" models and are not to be touched in testing;
  `llama3.2:1b` is a small non-critical model.

### Open WebUI
- Running and healthy: port 3000 → HTTP 200.
- **Not a hand-written unit** — it's a **Podman Quadlet**: `~/.config/containers/systemd/open-webui.container`
  (image `ghcr.io/open-webui/open-webui:main`, `PublishPort=3000:8080`), rendered by
  `podman-user-generator` into a generated `--user` service.
- Controllable with **no root** via `systemctl --user start/stop open-webui`.
  `is-enabled` reports `generated` (enable/disable is governed by the `.container` file, not a wants-symlink),
  so the GUI should treat start/stop as the control surface, not enable/disable.

### ComfyUI
- Install: `/home/Kamsiob/ComfyUI` (git HEAD `71b73e3b`), venv at `ComfyUI/venv` (Python 3.14).
- `custom_nodes/ComfyUI-GGUF` **present** ✓.
- **torch 2.11.0+rocm7.13** — i.e. **ROCm 7.13**, *not* ROCm 6.3. At import,
  `torch.cuda.is_available() == True`, `torch.version.hip == 7.13`, `device_count == 1`.
  So the GPU is already visible to torch; the "ROCm 6.3 memcpy_and_sync segfault" premise
  in the plan is from an older stack and does not obviously apply here.
- **Real launch pattern** (from `~/ComfyUI/start_comfyui_rocm.sh`, the script the user actually runs):
  ```sh
  cd ~/ComfyUI
  source venv/bin/activate
  unset HSA_OVERRIDE_GFX_VERSION
  export HIP_VISIBLE_DEVICES=0
  export HSA_ENABLE_SDMA=0        # disables SDMA — the actual Strix Halo crash mitigation
  export HSA_USE_SVM=0
  export PYTORCH_ALLOC_CONF="expandable_segments:True,garbage_collection_threshold:0.8,max_split_size_mb:512"
  python3 main.py                # default bind 127.0.0.1:8188
  ```
  The ComfyUI systemd unit (Phase 1) replicates these env vars exactly rather than inventing new ones.
- Was **not running** at audit time (port 8188 closed) — expected, it's launched on demand.

## Consequences for later phases
- GUI service control is all **user-level** now (Ollama, Open WebUI, ComfyUI) → no root needed at runtime.
- ComfyUI GPU env is a solved problem; the unit just needs the env block above. Restart policy will be
  bounded (not infinite) so a genuine crash is visible rather than hidden, per the plan.
- App GUI: PySide6 + QtWebEngine. Since QtWebEngine renders HTML/CSS/JS, the "mockup" can literally *be*
  the UI (rendered in a `QWebEngineView`, wired to Python via `QWebChannel`), which makes matching the
  design exact. PySide6 wheel availability on Python 3.14 is being verified; fallback is a brew Python 3.12 venv.
