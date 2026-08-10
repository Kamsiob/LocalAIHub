# Reviving the Flathub submission — runbook

Everything needed to get Local AI Hub onto Flathub, from exactly where things
stand **now**. Values here are current and specific — follow it top to bottom
with zero recall required.

## Where it stands right now

- The GitHub releases and the AGPLv3 relicense are **done**. Flathub is the only
  thing left.
- The Flathub submission PR **#9414** exists but was **auto-closed by the
  submission-checker bot within minutes**, for one reason: the PR description
  didn't contain Flathub's official checklist. Bot's reason string:
  *"Checklist(s) not completed or missing."*
- The bot's rule (verbatim): *"please post a comment below instead of opening or
  reopening (new) PRs."* It re-runs **hourly**, or immediately on a `/review`
  comment. **Do NOT open a new PR.**
- Nothing on the Flathub side has been touched since the auto-close — on purpose.
  It's waiting on ONE thing: the demo video.

## The one trigger that unblocks everything → the demo video (HUMAN)

A short screencast of Local AI Hub **running as the Flatpak** — launch it, toggle
a service on/off, open the About panel. This is checklist item 2, it is
mandatory, and it can ONLY be attached through **GitHub's web UI by drag-and-drop**
(into the PR description or a comment). **There is no CLI/API way to upload a
video** — so this step is the human's, and everything else waits on it.

Record it against **1.2.0 or later**, not the old 1.1.0 dev build. Two things in
1.2.0 are worth a couple of seconds each on camera because they are the app's
best answer to "why does this need systemd access": toggling a service, and the
"Not installed" card appearing or disappearing on its own when a tool is added
or removed. Skip the Hermes section unless it happens to be on screen — it is
not part of the pitch and its absence is normal for a reviewer's machine.

Test-launch the Flatpak first: `flatpak run io.github.kamsiob.LocalAIHub`
(a local dev build is installed; if it's gone, rebuild per the steps in
`flatpak/PACKAGING-NOTES.md`).

## The official checklist (5 items) and its exact state

Flathub's template lives at `.github/pull_request_template.md` in `flathub/flathub`.
Tick only what's true; the template allows `[X] N/A` **with a reason** for
genuinely-inapplicable items (none here qualify as N/A).

| # | Item | State | Who |
|---|---|---|---|
| 1 | Describe the application briefly | **Ready** — use the blurb below | Claude |
| 2 | Attach a video showcasing the app as a Flatpak | **Needs the video** | **Human** (record + drag-drop) |
| 3 | Flatpak ID follows the Application ID rules | **True** — `io.github.kamsiob.LocalAIHub` ↔ `github.com/kamsiob/LocalAIHub` (exists, 4 components) | tick |
| 4 | Read & followed all Submission requirements + guide, and agree | **Gated** — needs the license-install line added to the manifest first (below). Then truthfully tickable. **Not optional.** | Claude adds line, Human agrees |
| 5 | I am an author/developer/upstream contributor | **True** — you are the author of Local AI Hub | tick |

**Item 1 blurb (paste into the checklist):** Local AI Hub is a free, open-source
control panel for the local AI services running on your own machine — Ollama,
Open WebUI, and ComfyUI. Live status, one-toggle start/stop, and model
management, with no terminal needed for daily use. Fully local; no account, no
telemetry.

## Manifest changes required before ticking item 4

The submission manifest that Flathub actually builds is **not** the copy in this
app repo — it's the one in the **`kamsiob/flathub` fork**, branch
**`io.github.kamsiob.LocalAIHub`**, file **`io.github.kamsiob.LocalAIHub.yaml`**
at the repo root. It currently pins the OLD MIT commit. Two edits:

**1. Repin to the current release** (so the store listing shows AGPLv3, not MIT):

```yaml
    sources:
      - type: git
        url: https://github.com/kamsiob/LocalAIHub.git
        tag: v1.2.0
        commit: d92521a0e03359ca7fe02f8170cdf18d6eff8c87
```

(The copy in this repo, `flatpak/io.github.kamsiob.LocalAIHub.yaml`, is **already**
repinned to exactly this — just copy it over.)

**2. Add the license-install line** to the module's `build-commands` (this is the
item-4 gate — a real requirement: *"License files installed to
`$FLATPAK_DEST/share/licenses/$FLATPAK_ID`"*):

```yaml
      - install -Dm644 LICENSE ${FLATPAK_DEST}/share/licenses/io.github.kamsiob.LocalAIHub/LICENSE
```

The AGPL `LICENSE` is already in the `v1.2.0` tag, so this needs **no new tag**.
After both edits, re-lint: `flatpak run --command=flatpak-builder-lint
org.flatpak.Builder manifest io.github.kamsiob.LocalAIHub.yaml` — the only
remaining error should be `finish-args-systemd1-talk-name` (expected; see below).

## Exact order

1. **[HUMAN]** Record the demo video of the Flatpak. Keep the file handy.
2. **[CLAUDE]** In `kamsiob/flathub` branch `io.github.kamsiob.LocalAIHub`: make the
   two manifest edits above; commit + push. (This updates the closed PR's diff —
   that's expected and fine; it does not reopen it.)
3. **[CLAUDE]** Rewrite PR #9414's **description** using Flathub's official template
   checklist: item 1 filled with the blurb, items 3/4/5 ticked (4 is now true),
   item 2 left as the video slot. Keep the permission justifications already
   written in the old description.
4. **[HUMAN]** Edit the PR description in the web UI and **drag-drop the video into
   item 2**, ticking it. (Alternative: attach the video to a PR *comment* by
   drag-drop, hand Claude the resulting `github.com/user-attachments/...` URL, and
   Claude inserts it into item 2.)
5. **[CLAUDE or HUMAN]** Post a comment on #9414: the checklist is now complete,
   please reopen — optionally include `/review` to trigger the bot immediately.
6. **[BOT / MAINTAINER + HUMAN]** The bot reopens and starts the build. Then the
   review begins — the main topic will be `--talk-name=org.freedesktop.systemd1`.
   Every permission's justification is in `flatpak/PACKAGING-NOTES.md`; answer the
   reviewer from there.

## What 1.2.0 changed for this submission

Nothing in the manifest beyond the pin. Recorded here so the question doesn't
have to be re-derived under review:

- **No new `finish-args`.** The three 1.2.0 features run inside the permissions
  already requested, or don't run at all. Live install detection uses systemd
  signals over the existing `--talk-name=org.freedesktop.systemd1`, plus inotify
  on `~/ComfyUI`, which `--filesystem=~/ComfyUI` already covers. The version
  check uses the existing `--share=network`. The Hermes layer talks to
  127.0.0.1 over that same network permission and controls its unit over the
  same D-Bus name.
- **Two things degrade in the sandbox on purpose, rather than asking for more
  access.** Watching `~/.config/systemd/user` and
  `~/.config/containers/systemd` is not possible without a broader filesystem
  grant, so under Flatpak install detection leans on the D-Bus signals alone.
  Reading the model Hermes is configured against needs `podman`, which the
  sandbox has no route to; the app states that limit in place instead. Neither
  is worth a permission request, and a reviewer asking "why does it need X"
  should be told these were declined deliberately.
- **The app still never self-updates.** 1.2.0 adds a version *check*, and the
  Flatpak build's result explicitly points at the user's app store with no
  download button. Worth mentioning unprompted if update handling comes up.
- **Screenshots.** `assets/screenshot-{dark,light}.png` predate 1.2.0 and show
  no layers section. They are referenced by the MetaInfo, so refresh them
  before the store listing goes live; the listing is not blocked on it, but
  stale shots are a poor first impression.

## Do NOT

- **Do not open a new PR.** Revive the existing **#9414** by fixing it + commenting
  (the bot rejects new/duplicate PRs).
- **Do not pin the v1.0.0 MIT commit** (`67f71f1`) — that would make the store show
  the wrong license. Use **v1.2.0 / d92521a**.

## Key facts (copy-paste)

- App ID: `io.github.kamsiob.LocalAIHub`
- Flathub PR: https://github.com/flathub/flathub/pull/9414  (state: CLOSED)
- Fork + branch: `kamsiob/flathub` @ `io.github.kamsiob.LocalAIHub`
- Tag/commit to pin: `v1.2.0` / `d92521a0e03359ca7fe02f8170cdf18d6eff8c87`
- Expected remaining linter error after fixes: `finish-args-systemd1-talk-name`
  (the systemd permission — justified in `flatpak/PACKAGING-NOTES.md`, resolved by
  a reviewer exception, not by removing it).
