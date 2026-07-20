# Flathub submission — status & notes

This directory holds the Flatpak packaging for Local AI Hub. The GitHub release
(AppImage + standalone) is the live, finished distribution. **Flathub is a
work in progress** — it isn't published until real reviewers approve it over a
multi-day back-and-forth. This file records exactly where things stand.

## Application ID

`com.kamsiob.LocalAIHub` — reverse-DNS of `kamsiob.com`, which you control. This
is the correct form. Flathub verifies ownership; see "What needs you" below.

## The honest complication: this app manages the host

Local AI Hub exists to start/stop/query the user's **host** systemd services
(Ollama, Open WebUI, ComfyUI) and read their logs. Today it does that by running
`systemctl --user` and `journalctl --user` as subprocesses.

**Inside a Flatpak sandbox those binaries do not exist, and no permission adds
them.** So the current subprocess approach cannot work under Flatpak, even with
finish-args. This is the "core feature can't work in the sandbox" case flagged
up front rather than shipped broken. There are two realistic ways forward:

1. **systemd over D-Bus (tight, Flathub-preferred).** Rewrite the service layer
   to call the host user systemd manager over the session bus
   (`org.freedesktop.systemd1`: `StartUnit` / `StopUnit` / `RestartUnit`, and
   unit properties `ActiveState` / `SubState` / `LoadState` for status). PySide6
   ships QtDBus, so no new dependency. Permission: a single scoped
   `--talk-name=org.freedesktop.systemd1`.
   - Start / stop / status: **work.**
   - Log viewing ("View log" after a crash): **degraded.** The host journal
     isn't reachable from the sandbox this way, so that button would either be
     hidden in the Flatpak or point the user to `journalctl` in a terminal.
   - Cost: real code, and it only runs when `FLATPAK_ID` is set (native/AppImage
     builds keep the `systemctl` CLI path unchanged).

2. **Run host commands via the portal (broad).**
   `--talk-name=org.freedesktop.Flatpak` + `flatpak-spawn --host systemctl …`.
   Everything works unchanged, including logs — but this is effectively a
   sandbox escape (run arbitrary host commands), which Flathub reviewers
   scrutinize hard and often reject unless the app is explicitly a host manager.

**Recommendation: option 1.** It's the tight, defensible approach that matches
what reviewers expect, at the cost of the D-Bus rewrite and degraded log
viewing. This is a decision for the human — it changes the app's architecture
and the sandbox tightness — so the Flathub PR is intentionally **not** opened
until it's made. The manifest here is written for option 1.

## Permission justifications (for the PR description)

Every finish-arg in `com.kamsiob.LocalAIHub.yaml`, and why it's the minimum:

| Permission | Why it's needed |
|---|---|
| `--socket=wayland`, `--socket=fallback-x11`, `--share=ipc`, `--device=dri` | It's a QtWebEngine desktop GUI. `--device=dri` is for rendering; there is no camera/other-device access. |
| `--talk-name=org.freedesktop.systemd1` | The app's entire purpose: start/stop/query the user's Ollama, Open WebUI and ComfyUI systemd services. Scoped to that one well-known bus name — **not** `--socket=session-bus` (unfiltered) and **not** `org.freedesktop.Flatpak` (host escape). |
| `--share=network` | User-initiated model work only: query Ollama's local REST API (127.0.0.1:11434) and download/update models the user explicitly clicks. No background traffic, no telemetry. |
| `--filesystem=~/ComfyUI` | Scan the ComfyUI model folders and write downloaded model updates into place. Restricted to the ComfyUI tree — not `--filesystem=home`. |

Not requested (worth stating in the PR so reviewers see restraint): no
`--filesystem=host`, no unfiltered `--socket=session-bus`, no
`--talk-name=org.freedesktop.Flatpak`, no `--device=all`, no `--share=network`
for anything other than user-clicked model actions.

## PySide6 dependency

PySide6 (Qt6 + QtWebEngine) is large. On Flathub it's installed from pinned
wheels: generate `pyside6.yaml` with
[`flatpak-pip-generator`](https://github.com/flatpak/flatpak-builder-tools):

```
python flatpak-pip-generator --runtime org.freedesktop.Sdk//24.08 PySide6==6.11.1
```

That produces the `pyside6.yaml` the manifest includes, with every wheel pinned
by sha256 (Flathub builds are offline, so URLs+hashes are required).

## What's left before the PR can be opened

1. **Decide the systemd approach** (option 1 vs 2 above) — the blocker.
2. If option 1: implement the QtDBus service backend (guarded by `FLATPAK_ID`),
   and decide the log-viewing fallback.
3. Generate `pyside6.yaml` (needs `flatpak-builder` + the freedesktop SDK, ~1 GB
   of runtime downloads).
4. `flatpak-builder --install` and run once to confirm it starts and can toggle
   a service over D-Bus.
5. `flatpak run org.flatpak.Builder --lint` (manifest + appstream) clean.
6. Fork `flathub/flathub`, add the manifest on a branch, open the PR against the
   `new-pr` base with the justifications above.

## What needs you (the human), not me

- **App-ID ownership.** For `com.kamsiob.LocalAIHub`, Flathub will want proof you
  own `kamsiob.com`. After the PR is filed you verify on flathub.org by either
  logging in with the GitHub account tied to the project, or placing a token
  file they give you at a `/.well-known/…` path on `kamsiob.com`. Exact steps
  come from the reviewer/flathub.org — keep access to the domain's web root and
  DNS handy.
- **Screenshots.** The metainfo points at the two PNGs in `assets/` on the `main`
  branch (dark + light). They must stay reachable at those raw URLs.
- **The systemd decision** in "What's left" #1.
