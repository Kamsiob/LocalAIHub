# Handoff

State of (Local) AI Hub for whoever picks it up next, human or model. Current and
specific, so no recall is required.

> This file did not exist before v2.0 work began, although several briefs
> referred to it. It was created then, from the actual repository and machine
> state, and is updated as work proceeds.

## What the app is

A desktop control panel for the services running on one Linux machine, in two
groups:

- **Local AI**: Ollama, Open WebUI, ComfyUI, plus agent harnesses layered on top
  of them (currently Hermes Agent).
- **Self-Hosted Apps & Services**: every other rootless Podman service, found
  generically rather than from a supported-names list.

PySide6 and QtWebEngine host a local web front end (`web/`) wired to Python over
QWebChannel. Stdlib only on the Python side.

## Current release

| Item | Value |
|---|---|
| Version | 1.3.2 |
| Latest tag | `v1.3.2` |
| Distribution | GitHub release: AppImage plus standalone tarball |
| License | AGPLv3 |
| Installed copy | `~/Applications/local-ai-hub-1.3.2-x86_64.AppImage` |
| Launcher | `~/.local/share/applications/local-ai-hub.desktop`, `Name=(Local) AI Hub` |

Exactly one copy of the app is kept installed at any time, and it is always the
newest build. Verify with:

    find ~ /opt -iname "*local-ai-hub*.AppImage"

## Architecture, and what to build on rather than duplicate

| Area | Where | What it already does |
|---|---|---|
| Service control | `hub/services/base.py` | `Service` class: start, stop, restart, status over `systemctl --user`, and the same operations over D-Bus when sandboxed. `install_markers()` and `is_installed()` decide presence from an on-disk marker that actually disappears on uninstall, not from the unit's `LoadState`. |
| Change detection | `hub/services/watch.py` | `ChangeWatcher`: systemd D-Bus signals (`UnitNew`, `UnitRemoved`, `Reloading`, `JobRemoved`, filtered to managed units) plus inotify on the unit, quadlet, and ComfyUI directories. Debounced. The 5 second poll remains as a safety net. |
| Generic discovery | `hub/services/containers.py` | Finds self-hosted services by asking Podman. A container counts when Quadlet stamped it with a `PODMAN_SYSTEMD_UNIT` label and it publishes a port. Pods collapse to one entry via the infra container. Liveness is probed at the address the port is actually published on. |
| Ollama | `hub/services/ollama.py` | REST API: model list, loaded models, pull, update check, and `remove_model()`. |
| ComfyUI | `hub/services/comfyui.py`, `comfy_models.py` | Filesystem model scan by category, plus provenance and update tracking. |
| Layers | `hub/layers/` | A `Layer` is a `Service` plus the key of the service it depends on. Adding a harness is a subclass plus one line in `LAYER_CLASSES`. |
| Addresses | `hub/addresses.py` | Loopback, LAN, and Tailscale addresses, read through an ioctl over the stdlib rather than by shelling out to `ip`. |
| Networking | `hub/net.py` | Shared TLS context that finds the host trust store. Required because the bundled OpenSSL in a built artifact looks for certificates in the build distribution's directory. |
| Version check | `hub/app_update.py` | Strictly user triggered. Nothing runs unless the button is pressed. |
| Backend bridge | `app.py` | `Backend._collect()` assembles the whole state dict on a background thread every 5 seconds and pushes JSON over QWebChannel. Slots are the only surface the front end can call. |
| Front end | `web/app.js` | `applyState()` then `render()`, `renderLayers()`, `renderApps()`. Event delegation per container. |
| Design tokens | `web/styles.css` | One stylesheet for both themes. Cards, the two group headers, the disclosure panels, the modals. |

## House rules

- No em dashes in anything a user reads: app text, README, guide, release notes.
  Code comments and docstrings are exempt. American English spellings.
- Match the existing design language exactly. `design/ANTI-SLOP.md` records the
  tells to avoid and the voice to match.
- Honest limits are a feature. Name the limitation, name the cause, give the real
  alternative.
- Keep exactly one copy of the app installed, always the newest.
- Commit incrementally with clear messages.

## Distribution

The GitHub release is the only distribution path. Flathub is no longer a target.
Flatpak files remain in `flatpak/` but are not extended.

Build with `scripts/build-release.sh`, which builds inside an `ubuntu:22.04`
container so the result runs on a low glibc baseline. Verify a built artifact
before publishing:

    ./local-ai-hub-<version>-x86_64.AppImage --self-test-network

That prints the install method, the trust store in use, and the result of one
real version check. It exists because a whole class of bug is invisible from
source and only the built binary can prove it is fixed.

## Verified facts about this machine

Useful context, not assumptions the code should rely on. The code discovers all
of this at runtime.

- Bazzite, Fedora Atomic base, KDE on Wayland. `/usr` is read only.
- AMD Ryzen AI MAX+ 395 "Strix Halo", Radeon 8060S iGPU (gfx1151), with unified
  memory shared between CPU and GPU.
- Ollama and ComfyUI run as systemd user units. Open WebUI, Hermes, and the
  self-hosted services run as rootless Podman Quadlets.
- Hermes is pinned to `docker.io/nousresearch/hermes-agent:v2026.8.3`.
  `~/.hermes` is mode 0700 owned by the container's mapped uid, so the host user
  cannot read its config directly.
