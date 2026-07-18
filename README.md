# Local AI Hub

A small, premium desktop control panel for the AI services running locally on
your machine — [Ollama](https://ollama.com), [Open WebUI](https://openwebui.com),
and [ComfyUI](https://github.com/comfyanonymous/ComfyUI). See the models you've
downloaded, start and stop each service, watch live status, and manage your
Ollama models — all from one place.

Built initially for **Bazzite** (desktop) on the **AMD Ryzen AI Max+ 395** (64 GB,
"Strix Halo") with its Radeon 8060S iGPU — but written to work for others too.

Everything stays local. **No accounts, no telemetry, no analytics, nothing
phones home.** The only outbound actions are the three "browse models" buttons
and **model updates** — checking or downloading a model update contacts only
that model's own host (Hugging Face / Civitai / a URL you gave), and only when
you click. Nothing runs in the background.

## Features

- **One toggle per service** — start/stop Ollama, Open WebUI, and ComfyUI as
  `systemd --user` services, with a live status that auto-refreshes.
- **Ollama model manager** — see installed models with on-disk size, a badge for
  which model is currently **loaded in memory** vs. sitting on disk, and an
  **Update** button that runs a real `ollama pull`.
- **ComfyUI model manager & updates** — lists whatever's in your ComfyUI model
  folders (diffusion models, checkpoints, text encoders, VAE, LoRAs), grouped and
  tagged by format. Because ComfyUI files carry no source of their own, you set
  each model's source once — **auto-detect on Civitai** (by file hash), a
  **Hugging Face repo**, or a **direct URL** — and then **Update** checks that
  source for a newer version and downloads it (verified by size + SHA-256, then
  atomically replaced). Provenance is stored locally in
  `~/.config/local-ai-hub/comfy_models.json`. A model whose source can't be
  determined still lists normally, shown as **“no update source.”**
- **Light & dark themes** — a polished pill toggle; your choice persists between
  launches.
- **Browse links** — quick jumps to the Ollama Library, Hugging Face, and Civitai.

## Architecture

- **UI** — a local web front-end (`web/`) rendered in a `QWebEngineView`
  (PySide6 + QtWebEngine), wired to Python over `QWebChannel`.
- **Backend** — `hub/services/` controls each service via `systemctl --user`
  plus HTTP health probes; the Ollama module talks to the local REST API on
  `127.0.0.1:11434` (stdlib only).
- **Services** — systemd user units live in `systemd/` (reference copies).
- **Design source of truth** — `design/reference-mockup.html`.

## Requirements

- Linux with a `systemd --user` session (developed on Bazzite / Fedora Atomic)
- Python 3.10+
- Ollama, Open WebUI, and ComfyUI installed as `systemd --user` units
  (see `docs/phase0-audit.md` for how this repo's environment was set up)

On other machines the service **unit names** and **ports** may differ; they're
defined in `hub/services/*.py` (`unit=` and `health_url=`) and the `systemd/`
reference units, so adapting to a different setup is a small, contained change.

## Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

## Free and open source

Local AI Hub is **free and open source software**. You are welcome to use it,
fork it, modify it, and redistribute it — commercially or not. It is released
under the [MIT License](LICENSE); the only condition is that the copyright and
license notice travel with copies. No accounts, no strings, nothing to sign.
