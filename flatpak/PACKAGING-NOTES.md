# Flathub submission — status & notes

The GitHub release (AppImage + standalone) is the live, finished distribution.
The Flathub listing is **pending review** — an open PR that real reviewers approve
over a multi-day back-and-forth. It is not "published" until they merge it.

- **Flathub PR:** https://github.com/flathub/flathub/pull/9414
- **App ID:** `io.github.kamsiob.LocalAIHub`
- **Source:** https://github.com/kamsiob/LocalAIHub — tag `v1.0.0`, commit pinned
- **Runtime:** `org.kde.Platform//6.10` + `io.qt.PySide.BaseApp//6.10` (Qt6 +
  QtWebEngine shared from the runtime; no bundled second Qt)

## How service management works under the sandbox (implemented)

Local AI Hub manages the user's **host** systemd services. A Flatpak sandbox has
no `systemctl`/`journalctl`, so the service layer (`hub/services/_systemd_dbus.py`)
talks to the host user systemd manager over the session bus
(`org.freedesktop.systemd1`) via QtDBus. This path is used only when `FLATPAK_ID`
is set; native and AppImage builds keep the `systemctl` CLI and full journal logs,
unchanged.

- Start / stop / status: **work** over D-Bus (validated against real host systemd).
- **Crash detection is fully preserved** — "stopped unexpectedly" and its alert are
  derived from the unit's `ActiveState`/`Result`, read over D-Bus, not from the
  journal. Only the log *detail* view degrades.
- Log detail: unavailable in the sandbox (no host journal access). Instead of
  hiding the button, the Flatpak shows an honest note pointing to the AppImage.

## Permissions (final) — justifications for the PR

| finish-arg | Why it's the minimum |
|---|---|
| `--socket=wayland`, `--socket=fallback-x11`, `--share=ipc`, `--device=dri` | QtWebEngine desktop GUI; `--device=dri` for rendering only. |
| `--talk-name=org.freedesktop.systemd1` | Start/stop/query the user's Ollama, Open WebUI, ComfyUI services. One well-known bus name, talk-only — not unfiltered `--socket=session-bus`, not `--talk-name=org.freedesktop.Flatpak`. |
| `--share=network` | User-initiated model work only (Ollama REST on 127.0.0.1:11434, clicked downloads). No telemetry. |
| `--filesystem=~/ComfyUI` | Scan/update ComfyUI model folders. Restricted to that tree, not `home`/`host`. |

Not requested: `--filesystem=host`, unfiltered session bus, `org.freedesktop.Flatpak`, `--device=all`.

## Linter status

`flatpak-builder-lint` (manifest + built app) is clean except:

- **`finish-args-systemd1-talk-name`** (error) — *expected.* This is the permission
  the whole app depends on; it needs a reviewer to approve an exception. Justified
  in the PR. Nothing to "fix" without removing the app's core function.
- **`runtime-update-available-to-org.kde.Platform-6.11`** (warning) — the PySide
  BaseApp maxes at 6.10, so 6.10 is the newest usable pairing. Revisit when a 6.11
  BaseApp exists.
- Screenshots: `appstream-external-screenshot-url` appears in a local build; Flathub
  mirrors screenshots during publish, so this is handled by the pipeline.

## What a reviewer is most likely to raise

1. **`--talk-name=org.freedesktop.systemd1`** — the main conversation, as expected.
   The justification: this app is explicitly a host service manager; the permission
   is the narrowest form (one name, talk-only) that lets it do its job, and the
   broad escape hatches were deliberately avoided. Be ready to explain that
   start/stop/status all go through this one bus name.
2. **`--filesystem=~/ComfyUI`** — they may ask why filesystem access at all. Answer:
   to list installed ComfyUI models and write model updates into place; it's scoped
   to the ComfyUI tree, not `home`.
3. **`--share=network`** — they may ask what it's for. Answer: only user-clicked
   model checks/downloads and the local Ollama API; no background or telemetry use.
4. Possibly the **degraded log view** under Flatpak — the honest in-app note covers
   it; they may just want to confirm nothing silently fails.

## What needs you (the human)

- **Approve the build / respond in the PR thread.** First-time submissions usually
  need a Flathub maintainer to kick off the build, then a back-and-forth. Watch
  https://github.com/flathub/flathub/pull/9414 and answer the permission questions
  (the justifications above are your script).
- **App-ID ownership** is satisfied automatically: `io.github.kamsiob.LocalAIHub`
  maps to `github.com/kamsiob/LocalAIHub`, which you own — no website/DNS step and
  no kamsiob.com dependency (which was the reason for the GitHub-form ID).
- **Screenshots** must stay reachable at the raw URLs on `main`
  (`assets/screenshot-{dark,light}.png`).
- **A local dev build** of the Flatpak is installed on this machine
  (`flatpak run io.github.kamsiob.LocalAIHub`) for testing; remove it any time with
  `flatpak uninstall io.github.kamsiob.LocalAIHub`. It is not the Flathub build.
