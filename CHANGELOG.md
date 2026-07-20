# Changelog

All notable changes to Local AI Hub are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- Start/stop failures showed a garbled toast ("failed to sta" / "failed to sto")
  instead of "failed to start" / "failed to stop".
- ComfyUI models with a direct-URL source reported "Update available" forever
  after a successful update — the recorded version headers weren't refreshed.
- The Open WebUI startup-timeout check misread a valid `TimeoutStartSec` written
  with a unit suffix (e.g. `10min`) as missing/too low.
- The Ollama iGPU-env fix reported success without changing anything when the
  variable was present but set to `0`.
- A service toggle could stay dimmed and stuck if the start/stop no-oped and the
  refreshed state was identical (the dedup skipped the re-render).
- Malformed guide/setup data could throw an uncaught error and leave the panel on
  "Loading…"; the Setup summary icon and count are now guarded too.

### Added
- Pressing Escape closes any open overlay or modal (Getting Started, About,
  Setup, Log, Source).
- Clicking a "Not installed" service's toggle now explains it with a toast
  instead of doing nothing.

## [1.1.0] — 2026-07-20

### Changed
- **Relicensed from MIT to the GNU Affero General Public License v3.0 (AGPLv3).**
  Commercial use and forking are still allowed, but running a modified version as
  a hosted or networked service now requires publishing the modified source —
  closing the loophole a permissive license leaves open for closed hosted forks.
  This applies from this release forward; the v1.0.0 release remains under MIT for
  anyone who already has it (a license grant can't be revoked retroactively).

### Added
- A license line in the About panel — "Free & open source · AGPLv3" — linking to
  the full license text.

## [1.0.0] — 2026-07-19

First public release: a control panel for a fully local AI stack — Ollama, Open
WebUI, and ComfyUI — built and verified on Bazzite with AMD Strix Halo hardware.

### Added
- **One toggle per service** — start/stop Ollama, Open WebUI, and ComfyUI
  (systemd `--user`), with live status.
- **Honest "Not installed" state** — services that aren't set up on the machine
  show plainly as not installed instead of a misleading "Stopped".
- **Open in browser** — one click to each running web UI, always via `127.0.0.1`.
- **Ollama model manager** — installed models with size, an in-memory vs on-disk
  badge, and a real `ollama pull` update.
- **ComfyUI model manager** — lists models by folder; install from a Hugging Face
  / Civitai / direct link; per-model update once a source is set.
- **Setup Check** — verifies the supported Bazzite + Strix Halo (gfx1151)
  configuration, with safe one-click fixes.
- **Crash-aware** — a service that dies shows "Stopped unexpectedly" with a
  View log button; plus automatic and manual rescan.
- **Built-in Getting Started guide** and an **About & Links** panel.
- **Light and dark themes**, with the choice persisted.
- **Fully local** — no account, no telemetry; the only network use is the model
  update checks and downloads you explicitly click.
- **Distribution** — a portable AppImage and a standalone (no-Python) build, plus
  a Flatpak that controls the host systemd services over D-Bus inside the sandbox.

[1.1.0]: https://github.com/kamsiob/LocalAIHub/releases/tag/v1.1.0
[1.0.0]: https://github.com/kamsiob/LocalAIHub/releases/tag/v1.0.0
