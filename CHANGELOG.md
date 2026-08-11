# Changelog

All notable changes to (Local) AI Hub are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.3.2] - 2026-08-10

### Changed
- The app is now called **(Local) AI Hub**. Display name only: the application
  ID (`io.github.kamsiob.LocalAIHub`), the desktop entry, the icon name, the
  `local-ai-hub` config directory and the release filenames are all unchanged,
  so nothing about an existing install moves and your saved theme and keys stay
  where they are.
- A pass over the presentation of everything you read, in the app and on the
  repository, for a more consistent house style.
- The About panel described the app as a control panel for AI services, which
  stopped being true in 1.3.0. It now names both halves.

## [1.3.1] - 2026-08-10

### Changed
- The second group is now called **Self-Hosted Apps & Services**, everywhere:
  the app, the README, the in-app guide and the store listing. "Local Apps"
  read as though it meant applications installed on the machine, which is the
  one thing the section is not about.

### Fixed
- The README and store screenshots showed the real services, ports and endpoint
  of the machine they were captured on, a homelab inventory that has no reason
  to be in a public repository. They are now rendered from fixed demo data
  (`tools/shoot_readme.py`), so they show the layout without showing anyone's
  setup, and stay identical whatever is installed on the machine that builds a
  release.

## [1.3.0] - 2026-08-10

### Added
- **Smart address detection.** The app now knows which addresses this machine
  can actually be reached on, loopback always, a private-range LAN address if
  one exists, and a `100.64.0.0/10` address plus its MagicDNS name when
  Tailscale is up, and shows them per service under **Reachable at**, each with
  a plain sentence about where it works. "Open" still uses `127.0.0.1`, which is
  the right answer on this machine. Nothing is invented: an address that isn't
  detected isn't shown. Interfaces are read over the stdlib rather than by
  shelling out to `ip`.
- **Local Apps & Services.** Whatever else you self-host in rootless Podman is
  found generically, with no list of supported names, a container counts when
  Quadlet has stamped it with a `PODMAN_SYSTEMD_UNIT` label and it publishes a
  port. Well-known services get a proper label, anything else is shown by
  container name and port, pods collapse to a single entry, and containers you
  ran by hand stay out. Status is a real liveness check against the address the
  port is published on, and start/stop goes through the same systemd path as the
  AI stack. They appear and disappear live, via the existing watcher.
- **Two groups.** "Local AI" on top, "Local Apps & Services" below, stacked and
  separated by spacing rather than rules. The second group collapses and starts
  collapsed past six services, so a large homelab doesn't bury the AI tools.
  An empty second group is hidden entirely; a build that *cannot* look for them
  says so instead.

### Changed
- The Hermes card folds to a single line, with the same chevron the model lists
  use. Its details are there when you want them and out of the way when you
  don't.

## [1.2.1] - 2026-08-10

### Fixed
- **Every HTTPS request failed in the AppImage and standalone builds on any
  non-Debian system.** Those builds bundle their own OpenSSL, compiled on
  Ubuntu, which has Ubuntu's certificate directory (`/usr/lib/ssl/certs`) baked
  in as its default. That path doesn't exist on Fedora, Bazzite, Arch or
  openSUSE, and no CA bundle shipped inside the build, so the trust store came
  up empty and certificate verification failed for everything: the new version
  check, Ollama model update checks, and Civitai / Hugging Face lookups. The
  builds now locate the host's real trust store at runtime
  (`hub/net.py`). Running from source was never affected, which is why it
  passed testing.
- The version check reported a certificate failure as "Couldn't reach
  github.com", sending you to debug a network that was working fine. TLS
  failures are now named as TLS failures.
- A button with an icon in it rendered at roughly the width of the panel. An
  inline `<svg>` with only a `viewBox` has no intrinsic size, so it laid out at
  the SVG default of 300×150; `.btn-sm svg` is now sized like every other icon.

### Added
- `--self-test-network`, which prints the install method, the trust store in
  use, and the result of one real version check. The bug above could only be
  caught by running the built binary, so the built binary can now report on
  itself.

## [1.2.0] - 2026-08-10

### Added
- **Live install and uninstall detection.** Installing or removing Ollama, Open
  WebUI or ComfyUI is now noticed while the app is open, so the honest "Not
  installed" cards appear and disappear without a restart. Two event sources
  feed it, systemd over D-Bus (`UnitNew`/`UnitRemoved`/`Reloading`/
  `JobRemoved`, filtered to the managed units) and filesystem watches on
  `~/.config/systemd/user`, `~/.config/containers/systemd` and the ComfyUI
  folder. The periodic scan stays on as a safety net.
- **A Hermes Agent layer.** Agent harnesses are shown as their own labelled
  section on top of the base services rather than as a fourth peer, with the
  dependency stated on the card ("Runs on Ollama, running"), the configured
  model and context surfaced, and a clear flag when the harness points at a
  model that isn't installed. Start/stop and restart go over the same systemd
  path as everything else. The pattern is generic, another harness is a
  subclass in `hub/layers/`, not a rewrite.
- **A user-triggered check for a newer version of the app**: in the About panel.
  It contacts GitHub only on a button press, never at launch, never on a
  timer, and says so next to the button. Install-method aware: Flatpak users
  are pointed at their app store (the app never self-updates), AppImage users
  get the releases page and a note about GearLever.

### Changed
- Whether a tool is installed is now decided by something that actually
  disappears when it's uninstalled, the `ollama` binary, the `open-webui`
  quadlet, ComfyUI's `main.py`, instead of the systemd unit's `LoadState`. A
  unit file outlives the thing it starts, so deleting `~/ComfyUI` used to leave
  the app reporting a long-gone ComfyUI as merely "Stopped". Under Flatpak,
  where only `~/ComfyUI` is visible, a marker that can't be read falls back to
  the unit rather than claiming the tool was removed.

### Fixed
- Start/stop failures showed a garbled toast ("failed to sta" / "failed to sto")
  instead of "failed to start" / "failed to stop".
- ComfyUI models with a direct-URL source reported "Update available" forever
  after a successful update, the recorded version headers weren't refreshed.
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

## [1.1.0] - 2026-07-20

### Changed
- **Relicensed from MIT to the GNU Affero General Public License v3.0 (AGPLv3).**
  Commercial use and forking are still allowed, but running a modified version as
  a hosted or networked service now requires publishing the modified source, 
  closing the loophole a permissive license leaves open for closed hosted forks.
  This applies from this release forward; the v1.0.0 release remains under MIT for
  anyone who already has it (a license grant can't be revoked retroactively).

### Added
- A license line in the About panel, "Free & open source · AGPLv3", linking to
  the full license text.

## [1.0.0] - 2026-07-19

First public release: a control panel for a fully local AI stack, Ollama, Open
WebUI, and ComfyUI, built and verified on Bazzite with AMD Strix Halo hardware.

### Added
- **One toggle per service**: start/stop Ollama, Open WebUI, and ComfyUI
  (systemd `--user`), with live status.
- **Honest "Not installed" state**: services that aren't set up on the machine
  show plainly as not installed instead of a misleading "Stopped".
- **Open in browser**: one click to each running web UI, always via `127.0.0.1`.
- **Ollama model manager**: installed models with size, an in-memory vs on-disk
  badge, and a real `ollama pull` update.
- **ComfyUI model manager**: lists models by folder; install from a Hugging Face
  / Civitai / direct link; per-model update once a source is set.
- **Setup Check**: verifies the supported Bazzite + Strix Halo (gfx1151)
  configuration, with safe one-click fixes.
- **Crash-aware**: a service that dies shows "Stopped unexpectedly" with a
  View log button; plus automatic and manual rescan.
- **Built-in Getting Started guide** and an **About & Links** panel.
- **Light and dark themes**: with the choice persisted.
- **Fully local**: no account, no telemetry; the only network use is the model
  update checks and downloads you explicitly click.
- **Distribution**: a portable AppImage and a standalone (no-Python) build, plus
  a Flatpak that controls the host systemd services over D-Bus inside the sandbox.

[1.3.2]: https://github.com/kamsiob/LocalAIHub/releases/tag/v1.3.2
[1.3.1]: https://github.com/kamsiob/LocalAIHub/releases/tag/v1.3.1
[1.3.0]: https://github.com/kamsiob/LocalAIHub/releases/tag/v1.3.0
[1.2.1]: https://github.com/kamsiob/LocalAIHub/releases/tag/v1.2.1
[1.2.0]: https://github.com/kamsiob/LocalAIHub/releases/tag/v1.2.0
[1.1.0]: https://github.com/kamsiob/LocalAIHub/releases/tag/v1.1.0
[1.0.0]: https://github.com/kamsiob/LocalAIHub/releases/tag/v1.0.0
