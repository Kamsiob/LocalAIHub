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
| Version | 2.0.0 |
| Latest tag | `v2.0.0` |
| Distribution | GitHub release: AppImage plus standalone tarball |
| License | AGPLv3 |
| Installed copy | `~/Applications/local-ai-hub-2.0.0-x86_64.AppImage` |
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
| Front end | `web/app.js` | `applyState()` then `render()`, `renderLayers()`, `renderApps()`, `renderMachine()`. Event delegation per container. |
| Operation lock | `app.py`, `Backend._run_exclusive` | The single mutual-exclusion point. Every mutating slot goes through it, and the 5 second refresh skips its tick rather than queueing behind it. Nothing destructive may be added that does not use it. |
| Removal | `hub/removal.py` | Planner and fail-stop executor. `validate_path` is the only sanctioned way to turn a string into something deletable. `Manifest.compute_token` binds an execution to the exact plan that was previewed. |
| Dependencies | `hub/deps.py` | What breaks if something is removed, read from real quadlets, container environments and harness config. Returns facts, never values, because container environments hold secrets. |
| Disk | `hub/sizes.py` | Cached, background-computed. `_walk_size` refuses any path on a different filesystem from home, which is what keeps the slow external disk out. |
| Memory | `hub/memory.py` | Unified versus discrete detection, and the Ollama unload path. |
| Design tokens | `web/styles.css` | One stylesheet for both themes. Cards, the two group headers, the disclosure panels, the modals. |

## Rules that v2.0 added, and why they are not negotiable

- **Nothing is deleted that was not shown in a preview and confirmed.** Planning
  and executing are separate. The executor re-plans and compares tokens, so a
  system that changed between preview and confirmation refuses rather than
  proceeds.
- **Software and data never share a confirmation.** Named volumes are data, are
  excluded by default, and need their own tick box that names the volume.
- **A shared artifact is never removed** as part of removing one of its users. A
  failed podman probe must never read as evidence that nothing shares it.
- **Paths are validated, never constructed and deleted.** `validate_path`
  resolves, checks containment under an allowed root, refuses the root itself,
  and treats a symlink as a link rather than following it. Both sides of any
  self-protection comparison go through `_norm`, because `/home` is a symlink to
  `/var/home` here and an unnormalized comparison silently matches nothing.
- **Stop at the first failure.** Report what was and was not done.
- **The preview never prints a container's environment.** Real containers on this
  machine hold API keys and database passwords there.
- **Throwaway subjects only.** `tools/testbed.sh` creates and destroys everything
  the removal tests touch. Nothing real is ever a test target.

## House rules

- No em dashes in anything a user reads: app text, README, guide, release notes.
  Code comments and docstrings are exempt. American English spellings.
- Match the existing design language exactly. `design/ANTI-SLOP.md` records the
  tells to avoid and the voice to match.
- Honest limits are a feature. Name the limitation, name the cause, give the real
  alternative.
- Keep exactly one copy of the app installed, always the newest.
- Commit incrementally with clear messages.
- Flathub is no longer a distribution target. The `flatpak/` files stay but are
  not extended. The GitHub release and the AppImage are the only path, which
  makes verifying a built artifact more important, not less.

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

## Where v2.0 landed, and what is deliberately not there

| Item | Removal | Why |
|---|---|---|
| Open WebUI, Hermes, and every discovered quadlet service | offered | One quadlet file names the container and its volumes, so the plan can be exact |
| Ollama models | offered | Re-pullable by name; blocked while resident in memory |
| Ollama | not offered | Program files root owned in `/usr/local`, outside `$HOME` |
| ComfyUI | not offered | Program, models and generated images share one folder |
| Immich, or any pod | not offered | Several containers; removing one member leaves the rest half configured |
| ComfyUI model files | not offered in 2.0 | Often no recorded source to fetch again |
| Container images | never | Shared downloads; removing one is not needed to remove a service |
| `~/.config/<name>`, `~/.cache/<name>`, launcher entries | never | Matched only by name, which is not proof of ownership. Reported instead |

An adversarial review of the removal code before release produced 42 confirmed
findings, 16 of them data loss. The largest was the config and cache sweep,
which matched on a container name: a container called `containers` would have
deleted `~/.config/containers` and every quadlet on the machine. It is gone.
Anything similar proposed in future should be treated the same way: if the app
cannot prove ownership, it reports rather than deletes.

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
- The `ollama` binary is at `/usr/local/bin/ollama`, which resolves to
  `/var/usrlocal/bin/ollama`, is owned by root and is outside `$HOME`. This is
  why Ollama cannot be uninstalled by the app.
- `ghcr.io/hacdias/webdav:latest` backs two containers, which makes the shared
  image case real here rather than hypothetical.
- `~/comfy-models` holds about 31 GiB that ComfyUI cannot load: there is no
  active `extra_model_paths.yaml` and no symlink, and `~/ComfyUI/models/vae` and
  `text_encoders` are empty. Reported to the user, deliberately untouched.
- `du` on the model trees is fast because they hold few, large files. The tree
  that is slow is the photo library on the external USB disk: 533 GiB across
  about 70,000 files, 51 seconds cold. Never walk it.
