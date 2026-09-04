# (Local) AI Hub v2.0 Design Brief
## Uninstall, dependency checking, disk visibility, memory release

**Status:** design, not yet implemented. **Target:** v2.0.0 (minor-to-major bump: this is the first release that can delete user data).
**Governing principle:** a missing feature is a mild inconvenience; a wrong deletion is permanent. Where two designs work, this document picks the one that does less.
**House style:** no em dashes in this document or in any user-facing string. American English. Name the limitation, name the cause, give the real alternative.

---

## 0.0 How this document was produced, and what was corrected in review

Eight independent read-only investigations of this machine and this codebase, then a synthesis, then a review pass
against the real system. Every measurement cited was taken on the machine, not assumed.

Two things the research got wrong were caught in review and are corrected in place:

1. **Open WebUI and Future Waqf were recorded as consumers of specific Ollama models.** They are not. Verified: no
   model name appears in either service's quadlet, container environment, or image defaults. Both carry only an
   endpoint. Uncorrected, this would have disabled five of seven models on a false premise. See 3.7 and 5.0.
2. **A declared dependency was treated as a reason to disable the control.** Dependencies warn; only capability
   disables. See 5.0.

One rule was added that the original list did not contain: the preview must never print container environment,
because real containers here hold real secrets in it. See 7.0.

## 0. Scope decision, up front

v2.0 can remove exactly three classes of thing. Everything else is visible, sized where possible, and explicitly not offered.

| Class | What it is | Removal mechanism |
|---|---|---|
| A. Ollama model | A name in `ollama list` | `DELETE /api/delete` |
| B. ComfyUI model file | One file under `~/ComfyUI/models/<category>/` | `os.unlink` of one validated path |
| C. Quadlet single-container service | Exactly one `*.container` file, its generated unit, its container, and its bare-name named volumes | `systemctl --user disable/stop`, unlink quadlet, `daemon-reload`, conditional `podman rm`, `podman volume rm` (data tier only) |

Not offered in v2.0, with reasons in section 4: container images, pods, native installs, anything under `/usr/local`, anything under `/var/mnt`, toolbox and distrobox containers, bind-mount source directories, shared build caches, and the app itself.

On this machine that scope produces a deliberately small result set:

- **All 7** Ollama models are removable, subject to the capability gates. Only `gemma4:26b` carries a
  dependency warning, because Hermes pins it by name. A dependency warns; it does not disable. See 5.0.
- **All** ComfyUI model files under the category roots are removable (ComfyUI is stopped).
- **7 of 11** container services are removable at the software level; Immich's five units and Ollama and ComfyUI are not.

That is the intended shape. A feature that lights up everything would be wrong here.

---

## 1. What already exists and must be built on

### 1.1 Machinery to extend, with the real names

| Existing | File:line | What v2 uses it for |
|---|---|---|
| `Service` base, presence contract | `hub/services/base.py:108` | `install_markers()` (:136), `watch_dirs()` (:140), `_marker_state()` (:150), `is_installed()` (:167), `status()` (:252). A removed tool stays in the registry and reports `present=False`. This is how a card becomes "Not installed" after an uninstall, with zero registry mutation. |
| `ServiceStatus` dataclass | `base.py:90-105` | Already carries `present`, `unit_loaded`, `active`, `serving`, `failed`. Nothing new needed. |
| `run_systemctl` | `base.py:63` | Hardcodes `--user`. The executor uses this and only this for unit control. |
| `containers.discover()` | `hub/services/containers.py:150-200` | Already fully generic: requires a `PODMAN_SYSTEMD_UNIT` label and at least one published port. Supplies the class-C candidate list. |
| `containers.status_for()` | `containers.py:203` | Live probe reused verbatim by the per-step preflight. |
| `containers.SANDBOX_LIMIT` | `containers.py:73` | The `{what, why, options}` record the Flatpak refusal reuses. |
| `addresses.detect()` / `urls_for()` | `hub/addresses.py:96` / `:136` | Enumerates every local IPv4 by ioctl with a 30 s cache. The dependency checker reuses this as its "is this endpoint local" set instead of shelling to `ip`. |
| `comfy_models` manifest | `comfy_models.py:40,105,113,118,122,130` | `set_source` merges, so any new per-file key (a deletion record, a "keep" flag) is an additive change. `forget(path)` (:130) is the existing cleanup hook. |
| `ComfyUIService.list_models()` | `hub/services/comfyui.py:100-115` | Already calls `stat().st_size` per file and returns `size_bytes` / `size_human`. Per-file disk sizing is free. |
| `OllamaService.remove_model()` | `hub/services/ollama.py:208-221` | Written, tested by `tests/smoke_ollama.py:67-68`, wired to nothing. |
| `comfy_models.analyze_install` / `install_model` / `forget` | `comfy_models.py:468` / `:576` / `:130` | Written, wired to nothing. Out of v2.0 scope except `forget`. |
| `Layer` registry | `hub/layers/base.py:25`, `hub/layers/__init__.py:9` | `layer_info()`'s `unavailable: [{what, why, options}]` convention (documented `__init__.py:15-18`, rendered `web/app.js:353-357`) is the honest-limit shape every disabled uninstall reuses. |
| `ChangeWatcher` | `hub/services/watch.py:52,82-98,161` | Invalidates the on-demand disk and dependency memos. Not modified structurally (see 1.3). |
| CSS component set | `web/styles.css` | `.btn-sm.danger` (:586), `.layer-facts` (:469), `.ii-row` (:607), `.m-warn` (:610), `.layer-note.warn`/`.note` (:476/:479), `.modal`/`.sub`/`.modal-foot` (:655+), `.size` (:333), `.dot` (:241), `.chevron` (:248), `.models-head` (:312), `.models-topbar` (:593). Tokens `--err`, `--warn`, `--ok`, `--text-faint`, `--text-muted`, `--surface-2`, `--border`, `--r-card`, `--dur`, `--ease` all exist in both themes. |

### 1.2 Must NOT be duplicated

- **No second presence system.** Absence is `ServiceStatus.present`. Do not add an `installed` boolean, an "uninstalled" set, or a removal journal that the UI reads for presence.
- **No second podman discovery.** `containers.discover()` is the only source of container items. Do not add a parallel `podman ps` call for the uninstall planner; take the same entry dicts.
- **No second address/port table.** `addresses.urls_for(port)` and the entry's own `ports` are authoritative. Note the existing duplication at `web/app.js:208` (`{ollama:11434, openwebui:3000, comfyui:8188, hermes:9119}`) and `SVC_META` (`web/app.js:59-63`); v2.0 does not add a third copy, and does not fix the existing two either (out of scope, see section 11).
- **No second size formatter.** Reuse `_human_size` and the `size_human` string shape (`"2.0 GB"`, `"246 MB"`, one decimal). Do not introduce two-decimal GB.
- **No second modal chassis.** `.modal-backdrop` / `.modal` / `.sub` / `.modal-foot`, built once in `wire()` alongside `buildLogModal()` and `buildSetupModal()`.
- **No second progress idiom.** `.dl-progress` / `.dl-fill` is the app's only progress element and stays reserved for downloads. Uninstall shows real step states, never a bar.
- **No second destructive color.** `--err` already means "this failed". The destructive control is `.btn-sm.danger`, a tinted outline. No filled red button, no red-bordered danger panel.
- **No parallel `SERVICES` registry work.** `hub/services/__init__.py:7` exports a `SERVICES` dict that `app.py:61` does not use. v2.0 leaves both alone.
- **No new icon set.** One new inline SVG (`trash`) in the `I` map, 24x24, stroke-width 1.7, round caps, matching the existing hand-drawn set.

### 1.3 Structural prerequisites, all in `app.py`, all shipped before any destructive code

| # | Change | Why it blocks the feature |
|---|---|---|
| P1 | `Backend._op_lock = threading.Lock()`. `_refresh_async` acquires non-blocking and returns if held. Destructive slots acquire it or report busy. | There are **14** `threading.Thread(target=work, daemon=True).start()` sites in `app.py` and **zero** `Lock()` in the whole tree (verified). The 5 s `QTimer` (`app.py:594-597`) plus the settle loops in `set_service` (:361-363), `restart_service` (:414-416) and `set_app` (:388-390) guarantee overlapping `_collect()` on every start/stop. A preflight that reads state a different thread is about to change is not a preflight. |
| P2 | Hoist the `_last_present` / `_last_failed` read-emit-write triples (`app.py:91-95`, `:97-104`) out of `_collect` into a single-threaded reconcile, and suppress it entirely while `_op_lock` is held. | Today two concurrent collects can both emit "ComfyUI was removed", or resurrect a stale value and emit it again next tick. During an uninstall the executor must narrate its own steps; the filesystem's side effects must not also speak. |
| P3 | Wrap the whole `_collect_apps` per-entry body (currently only `containers.status_for` is guarded, `app.py:176-179`, leaving `primary = entry["ports"][0]` at :180 outside it) and put a `try/except` around the body of `_refresh_async.work`. | An `IndexError` there kills the collect thread silently. In the packaged builds the traceback goes to a stderr nobody reads, and a settle loop dies permanently. |
| P4 | **Keep `Backend._services` a fixed registry.** Do not add or remove entries at runtime. | `app.py:603` hands the live dict to `ChangeWatcher` by reference (`watch.py:52`), which iterates it on the Qt GUI thread inside `_rearm_fs` (`watch.py:109-126`, called unguarded at `:192`), and freezes `_unit_names` at construction (`watch.py:53-58`). Mutating the registry from a worker thread raises `RuntimeError: dictionary changed size during iteration` on the GUI thread and takes the watcher down for the session. The `present=False` design already expresses removal correctly. This is the answer to the codebase probe's first open question: **do not go dynamic.** |
| P5 | Exclude volatile fields from `applyState`'s diff key: `const {machine, ...rest} = payload; const key = JSON.stringify(rest);` | `applyState` (`web/app.js:1159-1182`) short-circuits the whole re-render by stringifying the entire payload. A live byte counter in that payload makes the key differ every 5 s, so `render()` rebuilds `cards.innerHTML` (`web/app.js:142`) every tick. That reintroduces the model-list flicker the comment at `:1160` says was fixed, and makes a destructive button re-created under the pointer between mousedown and mouseup. |
| P6 | `ComfyUIService.is_generating()` returns `None` on error instead of swallowing to `False` (`comfyui.py:129-131`), and `None` is treated as busy. | Fail-open on the one in-use signal the app can actually read is the wrong direction. |

---

## 2. The uninstall user flow, screen by screen

Two deliberate acts to remove software. Three to remove data. The destructive button is disabled until the plan is on screen.

### S0. Card, collapsed
No destructive control anywhere. The `.svc-right` cluster (toggle, chevron, Open, globe) is untouched. Rationale in section 10.

### S1. Card, expanded
The disclosure the card already opens (`.models-inner` for Ollama and ComfyUI, `.layer-body` for layers, a new `.layer-body` for app cards) gains one `.card-foot` row at the bottom: a left-aligned `.cf-why` sentence and a right-aligned `.btn-sm.danger`.

Enabled:
> Removing this stops the service and deletes its unit and container.  **[ Uninstall ]**

Disabled (button absent, not grayed):
> ComfyUI's program files, your models and your generated images are all inside ~/ComfyUI. This app can't tell them apart well enough to remove one and keep the others, so it doesn't offer to uninstall ComfyUI. Individual model files can be removed above.

Model rows carry a `.row-trash` as the last child of `.model`, resting at 0.45 opacity, full on `:hover` and `:focus-visible`. When a whole list is blocked, the trash buttons are omitted and the reason is stated once as a `.layer-note.note` at the top of the list, not repeated as forty tooltips.

**Act 1** is clicking Uninstall or a row trash.

### S2. Preview modal, loading
Opens immediately. Title and subtitle are filled from data already in hand. The facts area shows a single line, and the primary button is `disabled` (the existing `.btn-sm[disabled] { opacity:.5; cursor:default }` at `styles.css:343` makes it visibly inert).

```
Uninstall Open WebUI
Container service · open-webui.service

Working out what this removes...

                              [ Cancel ]  [ Uninstall ]  (disabled)
```

The plan is built on a worker thread holding `_op_lock`. If it cannot be built, the modal states why and offers only Cancel. A destructive action can never be fired before its consequences are on screen; that is the whole reason this is called a preview.

### S3. Preview modal, loaded
Three blocks, in this order.

```
Uninstall Open WebUI
Container service · open-webui.service

  Removes
    Unit                    open-webui.service (generated)
    Quadlet file            ~/.config/containers/systemd/open-webui.container
    Container               open-webui (48.7 MB)

  Left in place
    Image                   ghcr.io/open-webui/open-webui:main (5.16 GB)
    Chat history            volume "open-webui" (1.12 GB)

  [ ] Also delete 1 data volume (1.12 GB)
      Every conversation and setting stored in Open WebUI.

  Your models stay where they are.

                              [ Cancel ]  [ Uninstall ]
```

- **Removes** is the primary manifest. Every row names a literal path or identifier the planner read out of a source it opened.
- **Left in place** is not filler. It is where images, bind-mount sources, backup files and unmeasurable directories are named. For Hermes it reads `~/.hermes (size not available: it belongs to a container user this app can't read)` and `~/.config/containers/systemd/hermes.container.bak-preLAH`.
- The data checkbox is **unchecked by default**. Ticking it (**act 2 of 3**) mints a second token, moves the volume row from "Left in place" into a "Deletes" block, relabels the primary button to **Uninstall and delete data**, and reveals a `.m-warn`:
  > Deletes 1 data volume (1.12 GB). Anything stored in this service goes with it.
- The closing `.layer-note.note` states what survives. For a service uninstall it is always `Your models stay where they are.` because service removal never touches Ollama or ComfyUI models by construction (section 6).
- A generic closing line on every service removal: `Anything outside podman and systemd that points at this service, a reverse proxy or a tailscale serve mapping for example, is not changed.`

**Act 2** (or 3, with data) is clicking the primary button.

### S4. Executing
The modal does not close. The Removes list turns into a step list built from `.ii-row`, each row gaining a right-hand state: `pending` (faint), `working`, `done` (`--ok`), `failed` (`--err`). Cancel becomes a disabled Close.

Steps are real and few, so there is no spinner and no progress bar. `.dl-progress` stays reserved for downloads.

**Escape and backdrop-click are suppressed while executing.** The existing global handler (`web/app.js:1143-1147`) closes the topmost `.modal-backdrop.show` on Escape, and each modal closes on backdrop click (`web/app.js:708`). Both need a guard keyed on an executing flag, otherwise the user can dismiss the modal mid-deletion and lose the only report of what happened.

### S5a. Done
```
  Unit stopped and disabled       done
  Quadlet file deleted            done
  systemd reloaded                done
  Container removed               done

  Removed. The image stays on disk; podman will report it as reclaimable
  once nothing uses it.
                                             [ Close ]
```
Toast, matching the existing toast register: `Open WebUI removed`. A freed-bytes figure appears only when something with a measured size was actually deleted: `Open WebUI removed · 1.12 GB freed`. No exclamation mark, no emoji, no confetti.

### S5b. Halted
```
  Unit stopped and disabled       done
  Quadlet file deleted            done
  systemd reloaded                failed
  Container removed               not attempted

  Stopped here. systemctl --user daemon-reload exited 1.
  Nothing after this step ran.

  To finish by hand:
    systemctl --user daemon-reload
    podman rm hermes
                                             [ Close ]
```
No rollback. Rolling back a deletion is a lie, and re-creating a quadlet file the app just deleted would be a write the user did not ask for. The remaining steps are shown as literal commands. The card shows the true half-state on the next collect, because presence is derived from markers rather than from a removal record (P4).

### Confirmation count
| Path | Deliberate acts |
|---|---|
| Software only | 2: open preview, confirm |
| Software plus data | 3: open preview, tick the data box, confirm the relabeled button |
| Ollama model | 2: row trash, confirm |
| ComfyUI model file | 2: row trash, confirm |

No type-to-confirm anywhere. Reasoning and the rejected alternative are in section 11.

---

## 3. Dependency checking architecture

### 3.1 What it inspects: four tiers, per service

No single source describes the graph. The three highest-value edges on this machine (Hermes to gemma4:26b, Open WebUI to SearXNG, future-waqf to gemma4:26b) are invisible to both the quadlet files and `podman inspect`.

| Tier | Source | Cost | Availability |
|---|---|---|---|
| T1 | Quadlet file text under `~/.config/containers/systemd`, recursive, filtered to exactly `.container` / `.volume` / `.pod` | free | always (host build) |
| T2 | `podman inspect`: `.Config.Env`, `.Mounts`, `.Pod`, `.HostConfig.NetworkMode`, `.HostConfig.ExtraHosts` | ~25 ms per container | always, including stopped containers |
| T3 | A config file inside a declared bind-mount source, read with `podman unshare cat` or a plain read when the user owns it | one subprocess, 20 s timeout | host build only |
| T4 | App-owned state: Open WebUI's `webui.db`, read from a copy | ~50 ms | when the volume is host-readable |

**`podman unshare` is used for reading and never for writing or deleting.** That is a hard line. `podman unshare cat ~/.hermes/config.yaml` is a read of a file the user owns through a uid map; `podman unshare rm -rf` is an unbounded deletion of a tree the app cannot enumerate or verify.

`podman exec` is never used: it returns exit 255 on a stopped container ("can only create exec sessions on running containers"), and `curl` is absent in 3 of the 5 containers tested (future-waqf, searxng, freshrss), so in-container probing is not a general technique.

### 3.2 The `DEP_SOURCES` table

There is no generic way to find a service's config file, so v2.0 carries a small explicit table. Services not in it contribute T1 and T2 edges only, and are listed to the user as unscanned.

| Service | T1 | T2 | T3/T4 | Edges found on this machine |
|---|---|---|---|---|
| hermes | nothing | nothing (`grep -i 'searx\|ollama\|model'` over env returns nothing) | `podman unshare cat` of `<mount for /opt/data>/config.yaml`, `/.env`, `/context_length_cache.yaml` | `gemma4:26b` at `http://100.72.62.1:11434/v1`; SearXNG at `http://100.72.62.1:8888` |
| open-webui | `OLLAMA_BASE_URL=http://host.containers.internal:11434` | confirms env | sqlite copy of `.../volumes/open-webui/_data/webui.db`; `config` table plus `model` table | `gemma4:31b`, `gemma4:26b`, `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M`, `qwen3.6:27b`, `llama3.2:1b`, `nomic-embed-text:latest`; SearXNG at `100.72.62.1:8888` |
| future-waqf | `OLLAMA_URL`, `SEARXNG_URL` on `host.containers.internal` | confirms | plain read of `~/Kamiob Apps/Future Waqf/config.toml` (user-owned) | `gemma4:26b` (TOML only; no env shadows it) |
| immich-\* | `Requires=` / `After=` in `immich-server.container` | `.Pod` non-empty, `NetworkMode=container:<id>` | none | db, redis, ml, all via pod-local `localhost` |
| freshrss, searxng, joplin-webdav, file-share-webdav | none | none | none | none |

Two precedence traps the table encodes per service, because a generic rule gets one of them wrong either way:
- future-waqf's `_pick` is documented and implemented as environment, then config file, then default (`app/config.py:50-54`). So its two URLs resolve from env and its model resolves from the TOML.
- Open WebUI persists env into its `config` table on first boot and the DB wins thereafter. A user who changes the Ollama URL in the web UI never touches the quadlet.

### 3.3 How endpoints resolve

Never string-match hostnames. Resolve each endpoint to `(address, port)` and test membership in a local set built from `addresses.detect()` (which already enumerates every interface IPv4 by ioctl, no `iproute2` dependency), plus `127.0.0.1`, `::1`, `169.254.1.2` (the pasta gateway), and the names `host.containers.internal` / `host.docker.internal`.

This is load-bearing. The same Ollama is reached three ways on this machine: `100.72.62.1:11434` (Hermes), `host.containers.internal:11434` (Open WebUI and future-waqf), `127.0.0.1:11434` (host). A hostname allowlist reports Hermes as having no local dependencies.

`ExtraHosts` proves nothing: future-waqf has `ExtraHosts=[]` and no `AddHost=`, yet `host.containers.internal` resolves to `169.254.1.2` because pasta injects it. Also note `.HostConfig.HostsAdd` is not a field in podman 5.8.4 and errors per container; the correct name is `ExtraHosts`. Every inspect template field is validated once at startup against a live inspect, and a template that errors degrades the whole tier to unavailable rather than to "no dependency".

Inside a pod, `localhost` means a sibling container. When `.Pod` is non-empty, resolve `localhost` against every member of that pod.

### 3.4 When it runs

**Never on the 5 s collect.** The scan is on-demand and memoized for 60 s:
- when a model list is expanded,
- when an uninstall preview opens,
- invalidated by `ChangeWatcher.changed` and by any successful destructive operation.

This matches the existing rule that update checks happen only on demand (`app.py:118-119`).

### 3.5 When information is unavailable

Every failure below was reproduced live. Each one returns an empty or absent result rather than an error the caller notices, which is exactly why an empty result must never render as "no dependency".

| Failure | Reproduced | v2.0 behavior |
|---|---|---|
| EACCES on a 0700 subuid directory (`~/.hermes`, uid 534287) | yes | fall back to `podman unshare cat`; if that fails, mark that service's edge set **unknown** |
| `podman exec` on a stopped container, exit 255 | yes | never used |
| Wrong inspect field name, silent per-container error | yes | fields validated once at startup; tier marked unavailable on mismatch |
| `curl` absent in the container | 3 of 5 | never probe from inside |
| `extra_model_paths.yaml` absent, only `.example` present | yes | do not assume default search paths exist; ComfyUI-GGUF's registered dirs come from parsing `nodes.py:27-33`, which registers `{diffusion_models, unet}` as `unet_gguf` and `{text_encoders, clip}` as `clip_gguf` |
| `hermes.container.bak-preLAH` next to the live quadlet | yes | discovery filters to exact suffixes and never globs `<name>.*` |
| Flatpak build: no podman, no systemctl, host paths invisible | not tested here | the whole feature is refused, see 7.11 |

**Unknown blocks, and says so.** A service whose edge set is unknown disables every Ollama model trash with:
> This app couldn't read Hermes' configuration, so it can't tell which models are in use.

**Unknown-unknowns do not block, and are disclosed.** Services outside `DEP_SOURCES` contribute no edges. Blocking on them would disable everything forever, which is a feature that never works. Instead the confirm dialog states:
> Not checked: FreshRSS, SearXNG, Joplin WebDAV, File Share WebDAV. This app doesn't know how to read their configuration.

This is the deliberate hole. It is the same hole the user has today, made visible. See section 11.

### 3.6 The `.gguf` extension is not the test

Ollama's models are extensionless blobs (`~/.ollama/models/blobs/sha256-<hex>`, GGUF magic confirmed). ComfyUI's are `.gguf` files in registered dirs. The two domains are disjoint and stay separate. Note one Ollama model is literally named `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M`, so name-substring matching on "GGUF" would falsely bind it to the ComfyUI node.

### 3.7 The one fact that dominates the model graph here

`gemma4:26b` has exactly one declared consumer: Hermes, which names it in `config.yaml` inside its container volume.
Open WebUI and Future Waqf were initially recorded as consumers too. They are not. Both carry only an Ollama
*endpoint* (`OLLAMA_BASE_URL`, `FUTURE_WAQF_OLLAMA_URL`), and neither names any model anywhere: not in its quadlet,
not in its container environment, not in its image defaults. Open WebUI's `*_MODEL` variables are HuggingFace
embedding, reranking and whisper models running inside its own container, unrelated to Ollama. Pointing at a
service is a service dependency, not a model dependency, and conflating the two would have disabled five of
seven models on a false premise. Meanwhile Ollama runs with `OLLAMA_MAX_LOADED_MODELS=1` and `OLLAMA_KEEP_ALIVE=60m`, so those three consumers evict each other's model for up to an hour. The blast radius must be reported as a union across services, never per service.

`/api/ps` was empty for the whole investigation. An empty `/api/ps` means "nothing resident right now", not "no dependencies". Treating it as the latter would greenlight removing every model.

---

## 4. The complete removal model per install type

### Type 1: Quadlet single container, bare-name volume only
**Example:** open-webui.

| Step | Verify |
|---|---|
| `systemctl --user disable open-webui.service` | `UnitFileState` no longer enabled |
| `systemctl --user stop open-webui.service` | `ActiveState=inactive` after a bounded settle |
| unlink `~/.config/containers/systemd/open-webui.container` | path gone |
| `systemctl --user daemon-reload` | unit no longer listed |
| `podman rm open-webui` **only if** the container still exists after the stop | not in `podman ps -a` |
| data tier only: `podman volume rm open-webui` | not in `podman volume ls` |

`Restart=always` is set in this quadlet, so **disable precedes stop**. A zero return code from `stop` alone is a false success.

**Left behind on this machine:** `ghcr.io/open-webui/open-webui:main` (5.16 GB, unique, 0 B shared), the `open-webui` volume (1.12 GB) unless the data tier was confirmed, and `~/ystemctl --user status open-webui` (6674 B, a mistyped redirect from 2026-07-16; the planner never sweeps it up, rule 3).

### Type 2: Quadlet single container, path bind mounts
**Examples:** hermes, searxng, joplin-webdav, file-share-webdav, future-waqf.

Same steps as Type 1, minus any volume step: none of these declares a bare-name volume. Every `Volume=` source containing `/` or `%` is disclosed under "Left in place" and is never a delete candidate.

**Left behind, per service, on this machine:**

| Service | Left behind |
|---|---|
| hermes | `~/.hermes` (size not available, uid 534287, mode 0700, holds Playwright browsers via `PLAYWRIGHT_BROWSERS_PATH`), `hermes.container.bak-preLAH` (934 B), `~/hermes-install.sh` (144190 B), both image tags (`v2026.8.3` unique 1.357 GB, orphaned `:latest` unique 1.39 GB, 1.423 GB shared between them), the bind sources `~/Desktop` (76 G), `~/Pictures/Screenshots`, `/var/mnt/backup` |
| searxng | `~/containers/searxng/config/settings.yml` and `/data` (uid 525264, not writable by the user), image `ghcr.io/searxng/searxng:latest` (266 MB) |
| joplin-webdav | `~/webdav-joplin/data` (14 M, ~2000 Joplin notes), `config.yml`, the shared image |
| file-share-webdav | `config.yml`, the shared image, and the four re-exported user directories (`~/Desktop` 76 G, `~/Downloads` 221 M, `~/Documents` 2.7 G, `/var/mnt/storage` 551 G) |
| future-waqf | `~/.config/future-waqf/secrets.env` (mode 600, holds the SQLCipher DB key), `~/.local/share/future-waqf/data/future_waqf.db` (3.84 MB), `/var/mnt/backup/future-waqf` (48 M, 14 dated encrypted copies), the desktop entry and three icon sizes, the tagged image plus 15 dangling build-stage images, and the `tailscale serve` mapping of the tailnet root to `127.0.0.1:8770` |

The `secrets.env` case is the sharpest argument for the bind-source rule: deleting it before the encrypted backups makes 14 backups permanently undecryptable. The file's own comment records that overwriting it has already cost the key once.

**The `tailscale serve` mapping is a real, undisclosed leftover.** v2.0 does not read `tailscale serve status` (a new external dependency) and does not run `tailscale serve reset` (a state change to a host service outside scope). The generic closing line in S3 names the class of thing without claiming to have checked. Flagged in section 12.

### Type 3: Quadlet pod, multiple units. **Not offered.**
**Example:** Immich. Five units (`immich-pod`, `-db`, `-ml`, `-redis`, `-server`) plus two `.volume` units, a directory of seven quadlet files, five containers, two named volumes (`immich-pgdata` 1.092 GB, `immich-modelcache` 823.6 MB), four images, and a library of 533 G on `/var/mnt/storage` (a different device).

Two facts make it unsafe to automate: `~/Immich/thumbs` (18 G) is bind-mounted **over** `/data/thumbs` inside `immich-server`, so `/var/mnt/storage/immich/thumbs` measures 4.0 K and a user inspecting it concludes the thumbnails are already gone; and the infra container has no image at all (`Rootfs=/run/user/1000/libpod/tmp/infra-container`), so there is nothing to `rmi` for it.

Disabled wording:
> Immich runs as a pod of five containers, and its library is on /var/mnt/storage. This app removes single-container services only.

### Type 4: Native clone plus venv plus hand-written unit. **Not offered.**
**Example:** ComfyUI. `~/.config/systemd/user/comfyui.service` (1310 B, currently `disabled/inactive/dead`) starts `~/ComfyUI` (53 G: models 43 G, venv 9.6 G, `.git` 86 M, output 11 M, `user/` holding `comfyui.db` and `comfy.settings.json`).

Program files, model data and generated output share one directory tree. Separating them requires enumerating children, which rule 3 forbids. Removing only the unit would leave 53 G on disk and calling that "uninstall" would be dishonest.

Also left entirely alone and never attributed to ComfyUI: the `strix-halo-comfyui` toolbox container and its 15.1 GB image (the largest on the box, no unit, bind-mounts all of `/var/home/Kamsiob`), the stray `~/ComfyUI-GGUF` clone (484 K, same commit as the live one), the eight `~/.local/bin` scripts the GGUF node's requirements installed with a `#!/usr/bin/python3` shebang, `~/.triton`, `~/.modelscope`, and `~/comfy-models` (31 G, on no search path).

### Type 5: Manual install into root-owned `/usr/local`. **Not offered.**
**Example:** Ollama. `/usr/local/bin/ollama` (38,865,136 B, root:root) and `/usr/local/lib/ollama` (2.1 G, root:root, including dead `cuda_v12`/`cuda_v13` trees on this AMD box). The unit, the `override.conf` drop-in and `~/.ollama` (92 G) are all user-owned, but removing only those leaves a working `ollama` on `PATH` while the app claims it is gone.

The predicate is runtime-derived, not hardcoded: `os.access("/usr/local/bin/ollama", os.W_OK)` is False.

`~/.ollama` also holds `id_ed25519` and `id_ed25519.pub`, the identity used for pushing to ollama.com, not regenerable as the same key. Another reason the whole tree is out of scope.

### Type 6: Toolbox and distrobox containers. **Invisible, by existing design.**
`strix-halo-comfyui` and `fedora` have no `PODMAN_SYSTEMD_UNIT` label, so `discover()` never returns them and there is no card to disable. Worth stating in the doc because the three anonymous volumes on this machine all belong to `fedora`, which is why **`podman volume prune` is never a step**: it has no legitimate target in this artifact set, would reclaim 0 bytes (all three measure 0 B), and would destroy the distrobox's state. Pure downside.

### Type 7: Model artifacts. **Offered.**
Ollama model: `DELETE /api/delete`, target validated against live `list_models()` at plan time and again at preflight. On success, evict `Backend._ollama_updates[name]` (written at `app.py:425/442/462`) so a removed model's cached "Up to date" does not survive.

ComfyUI model file: `os.unlink` of one `ValidatedPath` under `MODELS_DIR/<category>/`. On success, call `comfy_models.forget(path)` (`comfy_models.py:130`), which nothing outside `tools/verify_comfy_updates.py` currently calls. `forget` is called **only** when this app deletes the file, never as a maintenance sweep over stale entries. The manifest currently holds three stale entries (two pointing at now-empty ComfyUI directories, one at a vanished `/tmp/tmpl916lzeq/`); they already render as nothing because `_collect` joins the disk scan to the manifest (`app.py:141-147`), and an unrequested write to clean them up is not this feature's business.

### Type 8: The app itself. **Never.**
Rule 4, section 7.

### Images: out of scope for every type
Reasons, in order of weight:
1. `ghcr.io/hacdias/webdav:latest` is used by two services byte-for-byte. Removing it while uninstalling one breaks the other on next boot with an image-not-found error, silently killing either Joplin sync or phone file access.
2. The reclaim figure is misleading. Hermes' two tags list 2.813 GB and 2.78 GB but share 1.423 GB; future-waqf's tagged image lists 241.4 MB of which only 1.749 MB is unique. A per-line "frees 2.8 GB" would be wrong by roughly half.
3. `podman-auto-update.timer` is enabled and active (next elapse Sat 2026-09-05 00:02:30 EDT) and six containers carry `io.containers.autoupdate=registry`. Removing an image before the quadlet lets the timer re-pull it, producing an uninstall that appears to succeed and silently reverses itself within 24 hours. Ordering fixes that, but leaving images alone fixes it more completely.

Disclosure instead: name the image and its unique size under "Left in place", and state that podman reports it as reclaimable once nothing uses it.

---

## 5. Per-item capability determination

### 5.0 A dependency warns. It never disables.

These are two different questions and merging them produces both false blocks and false comfort.

| Question | Meaning | Consequence |
|---|---|---|
| **Capability** | Can this item be removed completely and safely, at all? | If no, the control is disabled and the reason is stated. The user cannot override it, because the app would not be able to finish the job. |
| **Dependency** | If it is removed, what else stops working? | The control stays enabled. The preview names what breaks, and where a dependent can be repointed instead of broken, it offers that. The user decides. |

The brief writes the rule as: disable only when the app cannot do the job. Never disable because the app has an
opinion about whether the user should want to. A user who knows Hermes is pinned to `gemma4:26b` and wants that model
gone anyway is entitled to do it, having been told exactly what will break.

The one exception that looks like a dependency but is really capability: `DEPS_UNKNOWN`. If Hermes' configuration
cannot be read, the app cannot enumerate consumers at all, so it cannot show the user what would break. That is a
failure to inform, not a decision to protect, and the requirement is explicit that undeterminable dependency
information makes an item risky rather than clear.

### 5.1 The predicate

```python
def removal_state(item) -> tuple[str, str | None]:
    """Returns ("enabled", None) or ("disabled", reason_key)."""
    if in_flatpak():                          return "disabled", "SANDBOX"
    if not containers.available():            return "disabled", "NO_PODMAN"
    if is_self(item):                         return "disabled", "SELF"

    if item.kind == "ollama_model":
        if not ollama_status.active:          return "disabled", "OLLAMA_STOPPED"   # list-level
        if item.name in resident_now():       return "disabled", "IN_MEMORY"
        if deps.unknown_services:             return "disabled", "DEPS_UNKNOWN"
        # A declared consumer does NOT disable. It attaches a warning that the
        # preview shows and the user decides on. See 5.0 for why.
        return "enabled", None

    if item.kind == "comfy_model_file":
        if comfy_status.active and comfy.is_generating() is not False:
                                              return "disabled", "COMFY_BUSY"
        if not validated_under(item.path, MODELS_DIR):
                                              return "disabled", "OUT_OF_TREE"      # defensive
        return "enabled", None

    if item.kind == "service":
        k = install_kind(item)                # derived at runtime, never hardcoded
        if k == "native_root":                return "disabled", "ROOT_OWNED"
        if k == "native_shared_tree":         return "disabled", "SHARED_TREE"
        if k == "quadlet_pod":                return "disabled", "POD_MEMBER"
        if k != "quadlet_single":             return "disabled", "UNKNOWN_INSTALL"
        if quadlet_files_for(item) != 1:      return "disabled", "AMBIGUOUS_QUADLET"
        if any(validate(s.target, ROOTS) is None for s in plan(item).steps):
                                              return "disabled", "PATH_GATE"
        return "enabled", None

    return "disabled", "UNSUPPORTED"
```

`install_kind` is derived, not tabled:

| Result | Derivation |
|---|---|
| `quadlet_single` | exactly one file matching `*.container` under `~/.config/containers/systemd` (recursive) whose generated unit name matches, no `.pod` sibling, `.Pod` empty on inspect |
| `quadlet_pod` | `.Pod` non-empty on inspect, or a `.pod` file in the same quadlet directory |
| `native_root` | unit under `~/.config/systemd/user`, and any `install_markers()` path fails `os.access(path, os.W_OK)` |
| `native_shared_tree` | unit under `~/.config/systemd/user`, and the marker's parent directory also contains the service's model root |
| `unknown_install` | anything else |

### 5.2 The real disabled cases on this machine, with exact wording

| Item | Reason key | Where shown | Exact string |
|---|---|---|---|
| Ollama (service) | `ROOT_OWNED` | `.card-foot .cf-why`, no button | `Ollama isn't installed under your home folder. Its program files are in /usr/local/bin and /usr/local/lib, which need root to change, and this app never asks for root.` |
| ComfyUI (service) | `SHARED_TREE` | `.card-foot .cf-why`, no button | `ComfyUI's program files, your models and your generated images are all inside ~/ComfyUI. This app can't tell them apart well enough to remove one and keep the others, so it doesn't offer to uninstall ComfyUI. Individual model files can be removed above.` |
| Immich, and each of its five units | `POD_MEMBER` | `.card-foot .cf-why`, no button | `Immich runs as a pod of five containers, and its library is on /var/mnt/storage. This app removes single-container services only.` |
| Any model, when Hermes' config cannot be read | `DEPS_UNKNOWN` | `.layer-note.note` at the top of the list, trash buttons omitted | `This app couldn't read Hermes' configuration, so it can't tell which models are in use. Models can't be removed until it can.` |
| Any model while Ollama is stopped | `OLLAMA_STOPPED` | `.layer-note.note`, trash buttons omitted | `Ollama is stopped, so models can't be removed. Start it to manage them.` |
| Any model resident in memory | `IN_MEMORY` | `.row-trash[disabled]` `title`; the row's `.badge.loaded` already reads "In memory" | `This model is in memory right now. Release it first.` |
| ComfyUI model files while a job is queued | `COMFY_BUSY` | `.layer-note.note` at the top of the list | `ComfyUI is running a job. Model files can't be removed until the queue is empty.` |
| Everything, in the Flatpak build | `SANDBOX` | `.card-foot .cf-why` | `Uninstalling isn't available in the sandboxed Flatpak version of (Local) AI Hub. The sandbox has no access to systemd or podman on the host.` |

Defensive cases with no live example here: `AMBIGUOUS_QUADLET`, `UNKNOWN_INSTALL`, `PATH_GATE`, `OUT_OF_TREE`, `SELF`, `NO_PODMAN`. Their strings are written but nothing on this machine triggers them.

### 5.3 The enabled set on this machine

| Item | Enabled | Data tier |
|---|---|---|
| All 7 Ollama models | yes, when Ollama is running, the model is not resident, and Hermes' config could be read | n/a, the model file is the item |
| `~/ComfyUI/models/diffusion_models/qwen-image-Q8_0.gguf` (21,761,817,120 B) | yes, ComfyUI is stopped | n/a |
| `~/ComfyUI/models/unet/Qwen-Image-Edit-2509-Q8_0.gguf` (560,091,857 B) | yes, once `unet` is added to `MODEL_CATEGORIES` (section 11) | n/a |
| open-webui | yes | volume `open-webui`, 1.12 GB |
| hermes | yes | none (no bare-name volumes) |
| freshrss | yes | volumes `freshrss-data` 22.85 MB, `freshrss-ext` 573 B |
| searxng | yes | none |
| joplin-webdav | yes | none |
| file-share-webdav | yes | none |
| future-waqf | yes | none |

Nothing in `~/comfy-models` (31 G) is offered, because it is outside `MODELS_DIR` and on no ComfyUI search path. That is the correct cautious outcome even though it is the largest reclaimable block on the NVMe.

### 5.4 Two rules about how a reason is shown

- **A list-level reason is stated once**, as a `.layer-note.note` at the top of `.models-inner`, with the trash buttons omitted rather than rendered disabled. Forty identical tooltips is not an explanation.
- **`title` is never the only statement of a reason.** It does not exist on touch, and this app ships a 560 px layout on purpose. `.card-foot .cf-why` exists so the reason is visible text next to where the button would be.

---

## 6. The hard line between software removal and data removal

### 6.1 The definitions

| Category | Definition | Examples here |
|---|---|---|
| **Software** | The unit file, the generated unit, the container instance, the quadlet file | `open-webui.service`, `~/.config/containers/systemd/open-webui.container`, container `open-webui` |
| **Data** | A named volume declared as `Volume=<bare-name>:...`, where the source contains no `/` and no `%` | `open-webui`, `freshrss-data`, `freshrss-ext`, `immich-pgdata`, `immich-modelcache` |
| **Neither** | A `Volume=` source containing `/` or `%`. Third-party by construction, never a delete candidate, always disclosed | `%h/.hermes`, `%h/Desktop`, `%h/Pictures/Screenshots`, `/var/mnt/backup`, `%h/webdav-joplin/data`, `/var/mnt/storage` |

That single syntactic test is what prevents the most plausible catastrophic bug in this feature. `hermes.container` declares four `Volume=` lines; a planner that treats "host paths this container mounts" as "this app's data" deletes 76 G of the user's Desktop and, through `file-share-webdav`'s `/data/Storage`, reaches the 533 G Immich library. `%h` and `%t` are systemd specifiers expanded from a small known map; any source carrying an unhandled `%` is refused outright rather than treated as a relative path.

Models are data with their own flow. An "Uninstall Open WebUI" never touches `~/.ollama` or `~/ComfyUI/models`, and the modal says so.

### 6.2 The structural enforcement

`Manifest` carries two lists.

```python
DATA_KINDS = {"podman_volume_rm", "dir_delete_data"}

@dataclass(frozen=True)
class Manifest:
    steps: tuple[Step, ...]        # never contains a DATA_KINDS step
    data_steps: tuple[Step, ...]
    left_in_place: tuple[Residue, ...]
    token: str                     # sha256(canonical_json(steps))
    data_token: str                # sha256(token + canonical_json(data_steps))
```

- `Backend.uninstall_apply(token: str, data_token: str = "")` takes no path and no unit name. The front end has no vocabulary for naming a target.
- The executor asserts `not (DATA_KINDS & {s.kind for s in steps})` at both plan time and execute time. A volume step smuggled into `steps` raises before any op runs.
- `data_steps` execute only when `data_token` is supplied and matches under `hmac.compare_digest`. The second token is minted only when the user ticks the checkbox, so the confirmation for data is a distinct act, not a state the primary token covers.
- Tokens expire after ten minutes and are popped on use, so a stale plan cannot be replayed.

### 6.3 The classifier fails closed

A named volume or an app-owned directory is data unless proven otherwise. Anonymous 64-hex volumes are still data; only the wording changes. Discovery is from the quadlet plus `podman volume inspect` for the mountpoint and size, never from a hardcoded list.

### 6.4 What the UI enforces

| Enforcement | Mechanism |
|---|---|
| Data cannot be removed by accident | checkbox defaults unchecked; the primary token does not cover data |
| The user sees the size before deciding | `podman volume inspect` size shown on the checkbox line; the button stays disabled until the plan loads |
| The consequence is stated in plain terms | `.m-warn` appears only when the box is ticked: `Deletes 1 data volume (1.12 GB). Anything stored in this service goes with it.` |
| The button label carries the consequence | `Uninstall` becomes `Uninstall and delete data` |
| Third-party data is visibly out of reach | the "Left in place" block names every bind source with its size |
| Models are visibly out of reach | `Your models stay where they are.` on every service removal |

---

## 7. Safety rules and the mechanism enforcing each

| # | Rule | Mechanism | Test |
|---|---|---|---|
| 1 | The executor accepts only an opaque token | `uninstall_apply(token, data_token)`; hash re-derived from the stored `Manifest` and compared with `hmac.compare_digest`; ten-minute expiry; popped on use | Build a plan against a scratch root, mutate one stored step's target, apply. Assert `{ok: False, reason: "manifest changed"}` and zero calls on `RecordingOps`. A second test drives the real front end the way `tests/smoke_groups.py` does: read the rendered step rows out of the DOM via `runJavaScript`, assert set equality against `ops.calls`. |
| 2 | Data is a separate tier with its own token | `DATA_KINDS` assertion at plan and execute; `data_token` derived from both lists | Plan a service with a volume; assert `podman_volume_rm` never appears in `steps`; apply with only the primary token, assert no volume removal; apply with both, assert removal. Separate test: hand-build a `Manifest` with a volume step in `steps`, assert it raises before any op. |
| 3 | Every step names the source it was read from; the planner may not enumerate | `Step.why` is a `(source_kind, source_ref)` tuple validated in `__post_init__` against a closed `SOURCE_KINDS` set. A step that cannot cite a literal path from a file it opened cannot be constructed. | Scratch dir with `foo.container`, `foo.container.bak`, `foo.container.d/override.conf`, `bar.container`. Plan `foo`. Assert `{s.target for s in steps} == {scratch/"foo.container"}` by **set equality**, never subset. Plus a grep assertion that the planner module body contains no `glob(`, `rglob(` or `iterdir(`. Live bait: `hermes.container.bak-preLAH` and `ollama.service.d/override.conf`, which holds hand-tuned `OLLAMA_KEEP_ALIVE`, `OLLAMA_MAX_LOADED_MODELS` and `OLLAMA_CONTEXT_LENGTH` the app never wrote. |
| 4 | The app never removes itself | `SELF_PATHS` resolved at startup from four independent identities: `os.environ["APPIMAGE"]` (here `~/Applications/local-ai-hub-1.3.2-x86_64.AppImage`) plus `/proc/self/exe` plus `sys.executable` when frozen plus `app.py`'s ROOT; the desktop entry matched on `StartupWMClass=local-ai-hub` content, not filename (the Flatpak's filename differs); `hub.config.CONFIG_DIR` and `comfy_models.MANIFEST_FILE`; `FLATPAK_ID`. `is_self(p)` refuses if `p` equals, descends from, **or is a parent of** a self path. Re-checked at execute time, not only at plan time. | Point `APPIMAGE` at a scratch file, register a synthetic item whose data dir is that file's parent, assert `plan()` raises `SelfTargetError`. Separately build the manifest before setting `APPIMAGE`, set it, apply, assert refusal and that the scratch file survives. The parent direction is the half people get backwards: deleting `~/Applications` takes the running AppImage with it, leaving the process alive on a deleted inode with nothing left to report the partial state. |
| 5 | Preflight re-reads live state immediately before **each** step | `Step.requires: frozenset` of preconditions; `preflight(step)` re-runs `Service.status()` and `http_probe(health_url)` right before that step. Probes **every** entry in `_ports()`, not `ports[0]`: Hermes publishes 8642 and 9119 on both `127.0.0.1` and `100.72.62.1`, so a loopback-only probe reports dead while a phone on the tailnet is mid-request. Work-in-progress probes reused: `ComfyUIService.is_generating()` (`/queue`) and `/api/ps`. A running generation is a hard stop, not a warning. | Stand up `http.server` on a scratch port, point a synthetic service's `health_url` at it, apply, assert abort with `"still serving"` and zero recorded ops; kill the server, assert it proceeds. Harder second test: inject a probe returning True only on its second call, which fails if the check was hoisted out of the loop. The real lag is documented in the app's own docstring at `comfyui.py:6`: active precedes serving on startup, and the same lag runs in reverse on shutdown. |
| 6 | Only the item's own artifacts, never a neighbor's | `owned_paths(item)` computed from what the item declares (unit name, `install_markers()`, its own labels) and frozen into the `Manifest`; every step target must be a member; before executing, the planner computes every other discovered item's owned set and asserts an empty intersection. Bind sources are excluded by the syntactic test in 6.1. Image removal is out of scope entirely. | Scratch quadlet dir reproducing Hermes' four `Volume=` shapes. Assert the plan's targets contain none of `~/Desktop`, `~/Pictures/Screenshots`, `/var/mnt/backup`. Assert no `image_rm` step exists at all. Assert planning one pod member emits no step owned by another. |
| 7 | Effects go through an injected `Ops` object | Executor never calls `shutil`, `os` or `subprocess` directly. `Ops` exposes `stop_unit`, `disable_unit`, `delete_file`, `delete_tree`, `podman_rm`, `podman_volume_rm`, `daemon_reload`, `ollama_delete`. `RealOps.__init__` refuses to construct when `LAIH_TEST` is set or `pytest` is in `sys.modules`, so a test that forgets to inject cannot reach the real filesystem. Extends the existing `COMFYUI_HOME` redirection idiom (`comfyui.py:27`, `tests/smoke_live_presence.py:21`) with `LAIH_UNINSTALL_ROOT`. | Assert `RealOps()` raises under `LAIH_TEST=1`. Grep the executor module body for `shutil.`, `os.remove`, `os.unlink`, `subprocess.` and assert none. The gap the idiom does not cover: `containers.discover()` shells to real podman (`containers.py:139`), so the fixture puts a fake `podman` on `PATH` answering `ps -a --format json` and `volume ls` from a JSON file. This matters: the existing suite drives the live machine by design, so an uninstall test written in the house style would plan against the user's real Immich. |
| 8 | Verify each step positively; halt immediately; never roll back | Each step is preflight, execute, verify, where verify is a positive assertion (unit inactive; path gone; volume no longer in `podman volume ls`). A zero return code is not verification: `open-webui.container` and `hermes.container` both set `Restart=always`, so `stop` returns 0 and the container comes straight back. Hence disable-before-stop and a settle poll. On failure: stop, no rollback, record `{completed, failed_step, remaining}`. `ignore_errors=True` is banned in the executor (fine in scratch-dir test teardown, as at `tests/smoke_live_presence.py:88`). | `RecordingOps` configured to raise on step 3 of 6: assert exactly 2 calls, `failed_index == 2`, last 3 reported not attempted. Second test: `chmod` a scratch subtree to 0500 and assert `delete_tree` refuses up front with zero calls rather than half-deleting. |
| 9 | Allow-list of resolved write roots, with an explicit deny inside `$HOME` | Allowed: `~/.config/systemd/user`, `~/.config/containers/systemd`, `~/.local/share/applications`, `~/.local/share/icons`, `CONFIG_DIR`, `MODELS_DIR`. Denied first and short-circuiting: `/usr` (read-only on this Fedora Atomic system), `/etc`, `/var/lib`, `/run`, `/var/mnt`, and **`~/.local/share/containers/storage`**. That last one is why "inside `$HOME`" is not a sufficient rule: `podman volume inspect open-webui` reports its mountpoint as `/var/home/Kamsiob/.local/share/containers/storage/volumes/open-webui/_data`, so a `$HOME`-only gate permits `rmtree` straight into podman's storage behind podman's back. Named volumes go through `podman volume rm` or not at all. | Table-driven over ~20 paths asserting on the **reason code**, not the boolean, so a path denied for the wrong reason still fails: `/usr/share/applications/x.desktop`, `/etc/systemd/system/x.service`, the open-webui mountpoint, `~/Desktop`, `/var/mnt/backup`, `~/.config/systemd/user/comfyui.service`, `~/ComfyUI/models/loras/x.safetensors`, `/usr/local/bin/ollama`. |
| 10 | Nothing outside the resolved root is ever touched | `validate(raw, roots) -> ValidatedPath \| None` is the only producer of `ValidatedPath` (frozen: `resolved`, `root`, `dev`, `ino`, `is_dir`). `delete_file`/`delete_tree` open with `if not isinstance(vp, ValidatedPath): raise TypeError`. That runtime check is the difference between validating and making it impossible not to validate. See 7.1 below for the three traps. | Promote the probe script to `tests/smoke_uninstall_paths.py`. Table-driven: unresolved-vs-resolved containment answers differ for a path under home; the sibling-prefix pair is rejected; `resolve(strict=True)` raises for a vanished target. Plus the TOCTOU test in 7.1. |
| L1 | One destructive operation at a time | `Backend._op_lock`, non-blocking acquire, released in `finally`; plus an `flock` on `CONFIG_DIR/uninstall.lock` for two copies of the app. The present-transition alert and the watcher-driven reconcile are suppressed while held (P2). | Two threads calling `uninstall_apply` with valid tokens: assert one proceeds, one returns busy, and the recorded ops show no interleaving. Second test: fire `ChangeWatcher.changed` mid-apply and assert no spurious "X was removed" toast. |
| L2 | The Flatpak build does not plan at all | `uninstall_preview` returns the `SANDBOX_LIMIT` `{what, why, options}` shape and never a token; `uninstall_apply` refuses any token while `FLATPAK_ID` is set, which also covers a token minted before the environment changed. | Set `FLATPAK_ID`, assert preview returns the limit shape with no token, assert apply refuses. |

### 7.0 Rule 12: the preview never prints a container's environment

Not in the original rule list, added after reading real containers. `podman inspect future-waqf` returns
`FUTURE_WAQF_DB_KEY` and `TWELVEDATA_API_KEY` in plain text, and Hermes' quadlet carries `API_SERVER_KEY`. A preview
that dumped "what this container is configured with" would print live secrets into the interface, into any screenshot
of it, and into any log the user pasted for help.

Enforcement: the planner reads container environment only to answer specific questions (does this name a model, does
this name an endpoint) and returns only the answer, never the variable. The manifest carries paths, sizes and unit
names. There is no code path from `Config.Env` to a rendered string. The test asserts that a preview built for
`future-waqf` contains neither key's value.

### 7.1 Rule 10 in detail: the three path traps, all live on this machine

**Trap 1: `/home` is a symlink to `/var/home`.** Verified: `ls -ld /home` gives `/home -> var/home`, and `Path.home()` returns `/home/Kamsiob` while `Path.home().resolve()` returns `/var/home/Kamsiob`. Any check of the form `candidate.resolve().is_relative_to(ROOT)` with an unresolved `ROOT` returns False, and `os.path.commonpath` returns `/`. This is already live in the code: `comfy_models._key()` and `app.py:141` resolve, so manifest keys are `/var/home/...`, but `MODELS_DIR` (`comfyui.py:28`) is never resolved. The idiom to copy is `hub/services/base.py:46`, which resolves both sides.

This trap is dangerous in a specific direction: the naive check is always False, and the natural "fix" is to drop the `resolve()` rather than resolve the root, which opens the gate.

**Trap 2: `startswith` is not containment.** `"/var/home/Kamsiob/ComfyUI-evil".startswith("/var/home/Kamsiob/ComfyUI")` is True. `os.path.commonpath` on the same pair returns `/var/home/Kamsiob`, correctly rejecting it.

**Trap 3: `Path.resolve()` is non-strict.** It cheerfully returns a path for something that does not exist. Delete targets use `resolve(strict=True)` and treat `FileNotFoundError` as "already gone, drop the step", never as an error to power through.

**TOCTOU pinning.** Verified live: after `os.rename` plus `os.symlink`, a path's `(st_dev, st_ino)` changes and `stat(follow_symlinks=False)` reports a symlink, while a directory fd opened before the swap still fstats to the original inode. So: plan time records `(st_dev, st_ino)` via `os.stat(follow_symlinks=False)`; execute time opens the parent with `os.open(parent, O_RDONLY|O_DIRECTORY|O_NOFOLLOW)`, re-stats with `dir_fd=`, compares the pair, and aborts the whole operation on mismatch rather than re-planning. Assert `shutil.rmtree.avoids_symlink_attacks` at import and degrade loudly if False. `shutil.rmtree` already refuses a symlink argument and does not follow symlinked children (confirmed); the residual danger is a symlink component in the **middle** of the path, which resolving before the containment check catches.

**The refuse set inside `validate`:** `resolved == root`; `len(resolved.parts) <= 3` (`/var/home` is 3); `resolved` equal to home or to any immediate XDG child (`Desktop`, `Documents`, `Pictures`, `Downloads`, `.config`, `.local`, `.ssh`); and any mount point, detected as `resolved.stat().st_dev != resolved.parent.stat().st_dev`, which is exactly what `/var/mnt/backup` and `/var/mnt/storage` are.

**Ownership pre-check.** `delete_tree` checks `os.stat(root).st_uid == os.getuid()` and refuses before touching anything. `~/.hermes` is mode 0700 owned by uid 534287 (subuid 524288 + container uid 9999, from `UserNS=keep-id`), so a plain `rmtree` fails partway with `PermissionError` after removing whatever happened to be traversable. Under v2.0's scope this never arises, because `~/.hermes` is a bind source and therefore never a delete candidate, but the guard is the backstop.

---

## 8. Disk visibility

### 8.1 The premise is inverted for the data that matters

`du` cost tracks inode count, not bytes. Measured on this machine:

| Path | Size | Inodes | Wall |
|---|---|---|---|
| `~/.ollama` | 92 G | 43 files | 0.0027 s |
| `~/ComfyUI/models` | 43 G | 39 files | 0.0017 s |
| `~/comfy-models` | 31 G | 11 files | 0.0017 s |
| `~/.local/share/containers` | 31 G | 492,974 files | 1.01 s |
| `/var/mnt/storage/immich` | 533 G | 69,812 files | **51.06 s cold**, 0.33 s warm |

`/var/mnt/storage` is `/dev/sda2` on a USB-attached WDC WD40EDAZ (`ROTA=1`, `TRAN=usb`): about 1,367 inodes/sec against about 584,000/sec on the NVMe, a 427x penalty. So the rule is not "never walk", it is **never walk `/var/mnt`**.

### 8.2 Data sources, by tier

| Tier | Source | Cost | When |
|---|---|---|---|
| **A** (inline, every collect, no cache) | `os.statvfs` per distinct `st_dev` (O(1), reads the superblock, safe even on the USB volume); `GET /api/tags` for per-model Ollama size (6.2 ms); `ComfyUIService.list_models()` per-file `st_size`, already collected | under 10 ms combined | rides the existing 5 s `_collect()` |
| **B** (on demand, memoized 60 s) | `podman system df -v` (0.30 s, gives per-image `SHARED SIZE` / `UNIQUE SIZE` and per-volume size); `podman volume inspect` | 0.3 s | card expanded, uninstall preview opened |
| **C** (never automatic) | any walk under `/var/mnt` | 51 s | not implemented in v2.0 |

**No background cache and no TTL timer.** Tier B memoizes for 60 s in memory on the `Backend` object and is invalidated by `ChangeWatcher.changed` and by any successful destructive operation. A disk cache would need its own invalidation for no benefit.

**Authority notes.** `/api/tags` sums manifest references, so it structurally double-counts shared blobs: it reports 98,493,304,350 B against 98,493,292,993 B on disk, an 11,357 B overcount from one small config blob referenced by two manifests. That is negligible and the API is preferred because it gives the per-model breakdown the UI needs and `hub/services/ollama.py` already calls the endpoint. Similarly, `podman system df` reports about 35 GB against `du`'s 31 GiB because per-image sizes count shared overlay layers repeatedly; use the TOTAL/RECLAIMABLE row for headlines and the SHARED/UNIQUE columns when attributing space to one image.

### 8.3 Per-filesystem free space

Free space is a property of the device, not the tool. Group locations by `os.stat(path).st_dev`.

| Device | Free | Holds |
|---|---|---|
| `/dev/nvme0n1p3` btrfs, mounted `/var/home` | 790,627,053,568 B (736 GiB) | `~/.ollama` 92 G, `~/ComfyUI/models` 43 G, `~/comfy-models` 31 G, `~/.local/share/containers` 31 G |
| `/dev/sda2` ext4, mounted `/var/mnt/storage` | 1,276,497,121,280 B (1.16 TiB) | `/var/mnt/storage/immich` 533 G |

Rendering one global free-space number, or the same number once per tool, would imply that deleting Ollama models frees space for Immich. It does not. The machine line shows only the device holding the model stores; a second device appears in the card of the item that lives on it, not on the machine line.

One btrfs caveat to respect: `btrfs filesystem usage` reports "Free (estimated) 736.33GiB (min: 385.63GiB)" because metadata is DUP. `statvfs` agrees with the 736 GiB figure, so use it, but do not present it as a guarantee.

### 8.4 Progressive display

- **First paint** shows Tier A. Nothing blocks.
- **Card expansion** fires Tier B; the card's `.layer-facts` rows show `...` until it lands, one refresh later at most.
- **The uninstall preview** always waits for Tier B before enabling its button. This is the one place a wait is correct.
- **Nothing is ever walked on a timer.**

### 8.5 Last-used: what is reliable and what is deliberately omitted

| Value | Verdict | Reason |
|---|---|---|
| Container `State.StartedAt` | **Reliable**, shown as "Last started" | Present and correct for both running and stopped containers, ~25 ms per inspect |
| Container `State.FinishedAt` | **Omitted** | `strix-halo-comfyui` reports `Running=false` with `FinishedAt=0001-01-01 00:00:00`, Go's zero value. Suppress the field when it is the zero value rather than rendering year 1 |
| `atime` on `/var/mnt/*` | **Omitted** | Both `/var/mnt/storage` and `/var/mnt/backup` are mounted `noatime`. On one Immich file `atime` is six weeks **older** than `mtime`; library photos show `atime` at the July copy-in despite active browsing. Any derived last-used would confidently tell the user a heavily-used photo library was untouched since July |
| `atime` on `/var/home` | **Omitted** | `relatime`, so it does advance, but it is provably contaminated. A 15.78 GiB blob and a tiny blob share `atime` to the nanosecond (`02:00:07.379007101`); three blobs of 1.23 GiB, 0.255 GiB and near-zero share `17:58:50.128008286`. Files of wildly different sizes cannot be read in the same nanosecond; that is a scanner stamping at open. Pika Backup runs as an active user service and `~/.ollama/models/manifests` carries the same `02:00:07` stamp. A backup run would mark every model "used today" and never flag a stale one, which is the exact failure that makes the feature useless. `relatime` also caps resolution at roughly daily even when clean |
| Ollama `modified_at` | **Shown, relabeled** | It is pull/create time. Label it "Added", never "Last used" |
| Ollama `/api/ps` | **Shown as "In memory" only** | It reports what is resident under a 60 m keep-alive, not what is depended on. Empty here for the whole session |
| Open WebUI chat timestamps | **Omitted in v2.0** | Real data, but positive-only evidence covering 4 of 7 models, newest chat 2026-08-15 while blob `atime` shows Ollama activity on 08-26 and 09-04, and `nomic-embed-text` (RAG embedder, never chatted with) would read as never used. Also requires reading a live WAL sqlite from inside a running container's volume |
| Image `CreatedAt` | **Shown as "Created"** | It is the image build date; `valkey` shows 2026-09-03 for an image pulled 16 hours ago. Never a last-used |

**Net result: v2.0 shows no last-used for any model.** That is a deliberate omission, not an oversight. Absence needs no note in the UI.

### 8.6 One coverage widening

`MODEL_CATEGORIES` (`comfyui.py`) lists `diffusion_models`, `checkpoints`, `text_encoders`, `vae`, `loras`. `~/ComfyUI/models/unet` (535 MB, holding `Qwen-Image-Edit-2509-Q8_0.gguf`) is walked past today. Add `unet` and `clip`, because ComfyUI-GGUF registers exactly `{diffusion_models, unet}` and `{text_encoders, clip}` (`nodes.py:27-33`), and the sizes come from the walk that already runs. This also widens the deletable set by one file; that is the intended consequence and is called out in section 11.

---

## 9. Memory visibility and release

### 9.1 Hardware detection

This is an AMD Strix Halo APU. `MemTotal` 57,192,976 kB (54.54 GiB) plus the 8.00 GiB VRAM carveout is about 62.5 GiB, which is the 64 GB installed. GTT is 29,282,803,712 B (27.27 GiB), exactly `MemTotal/2`, the amdgpu default aperture onto ordinary system pages. **There is one physical pool.**

Detection, primary signal, world-readable, no dependencies:

```
/sys/class/drm/card[0-9]*/device/uma/carveout          -> "4"
/sys/class/drm/card[0-9]*/device/uma/carveout_options  -> "...|4:  (8 GB)|..."
/sys/class/drm/card[0-9]*/device/mem_info_vram_total   -> 8589934592
```

The glob is naturally safe: connector directories such as `card1-DP-1` symlink `device` back to `card1`, which has no `mem_info_*`. Verified: exactly one path returned. `carveout` is `0644 root:root`, readable but not writable by the app, and is **read only, never written**. A careless privileged write would change the user's firmware memory split.

Fallback signal (for kernels without `uma/`): driver is `amdgpu` **and** (`uma/carveout` exists **or** `mem_info_vram_vendor` absent **or** `mem_busy_percent` absent). On this APU both of those attributes are absent while `gpu_busy_percent` is present, and hwmon exposes `in1_label=vddnb`, a northbridge rail that only exists on an APU. This fallback is a hint, not proof: only absence could be confirmed here, not the corresponding presence on a discrete card. See section 12.

### 9.2 Which figures are reliable on this machine, and which are omitted

| Figure | Verdict |
|---|---|
| `MemTotal`, `MemAvailable` from `/proc/meminfo` | **Shown.** The machine line reads `Memory 38 GB available of 62 GB`. "Available", not "free": on Linux "free" is the wrong figure and calling `MemAvailable` free would be inaccurate. Two different verbs across disk and memory is the accurate choice |
| `mem_info_vram_total` as a separate budget | **Omitted on unified hardware.** Adding VRAM to RAM would claim about 90 GiB on a 64 GB machine and let the user start a workload that OOMs the desktop |
| `mem_info_vram_used` as a headline | **Omitted.** It reads 2.25 GiB with nothing loaded (2,654,842,880 B on one read, 2,412,072,960 B minutes later): that is the compositor. A readout sourced straight from it looks broken |
| `mem_info_gtt_total` / `gtt_used` | **Omitted.** GTT bytes are RAM bytes on this hardware |
| `/api/ps` `size_vram`, per model | **Shown, relabeled.** Rendered inside the existing `.badge.loaded` as `In memory · 3.4 GB`, never as "VRAM used, separate from your RAM". The last load put a 16,147 MiB buffer on Vulkan0 while the entire carveout is 8,192 MiB, so those bytes necessarily landed in GTT, which is system RAM |
| Any GPU figure on non-AMD hardware | **Omitted, labeled unknown.** `mem_info_*` is amdgpu-only; NVIDIA and Intel expose no equivalent under `/sys/class/drm`, and `nvidia-smi` is a new external dependency unreachable from a sandbox anyway. Never estimated |
| `gpu_busy_percent` as an in-use guard | **Omitted.** Noisy instantaneous sample (5, then 0 0 0 0 0 within a second) polluted by the compositor |

The three sources report three different totals and none of them add: Ollama's Vulkan/RADV heap equals VRAM + GTT (verified twice by arithmetic against the July logs and today's `available="32.2 GiB" free="32.6 GiB"`), ComfyUI/torch on ROCm reported the GTT figure alone (15,855 MB in the July logs, exactly `MemTotal/2` at the time, against a 32,768 MB carveout), and `/proc/meminfo` sees neither. The app must never present one "VRAM" number sourced from whichever service happens to be up.

### 9.3 The release mechanism

**Ollama.** `ollama stop MODEL` is `cmd.StopHandler` calling `cmd.loadOrUnloadModel`, which posts a generate request with an empty prompt and `KeepAlive 0` (confirmed from the binary's symbols and JSON tags). The HTTP equivalent, stdlib only, matching the existing pattern in `hub/services/ollama.py`:

```
POST http://127.0.0.1:11434/api/generate
Content-Type: application/json
{"model": "<name exactly as returned by /api/ps>", "keep_alive": 0}
```

`keep_alive` is an `api.Duration`: a bare JSON number is seconds, so `0` unloads now. The response carries `done_reason: "unload"`. For an embedding-only model `/api/generate` returns `"%q does not support generate"`, so fall back to `POST /api/chat` with `{"model": ..., "messages": [], "keep_alive": 0}`.

Verification: poll `GET /api/ps` until the model disappears, with a 10 s bound.

**ComfyUI.** `POST /free {"unload_models": true, "free_memory": true}`. This only calls `prompt_queue.set_flag()`; the flag is read by `q.get_flags()` in `main.py` **after** `e.execute()` returns and `task_done()` has run (`main.py:349` then `:387` then `:390`), so an unload can never land underneath a running prompt. `set_flag()` also calls `not_empty.notify()`, so a worker idling in `q.get(timeout=1000.0)` wakes immediately rather than stalling for about 16 minutes.

Verification is best-effort. ComfyUI does not report freed memory. Where `GET /system_stats` is available, compare `devices[0].vram_free` before and after; where it is not, the result line says **asked**, not **freed**.

**Never offered as a release mechanism:** restarting a service. That would kill in-flight work.

### 9.4 The active-use guard

**Ollama's unload is refcount-gated server side.** The scheduler defers the unload until pending requests drain ("waiting for pending requests to complete and unload to occur", `server.(*runnerRef).unload`, "ignoring unload event with no pending requests"). So the risk is not corruption, it is a release that silently has not happened yet.

**But Ollama exposes no in-flight signal at all.** The complete route list is `/api/{blobs,chat,copy,create,delete,embed,embeddings,generate,me,ps,pull,push,show,signout,status,tags,user,version}`. `/api/queue` and `/api/running` return 404; `/api/status` returns only cloud state; `/api/ps` has no refcount, active or in-flight field; `expires_at` is not a substitute because the expiry timer only starts once the runner goes idle. Worse, the real client here is Open WebUI on port 3000, and a user mid-chat there is completely invisible to this app.

Consequence for copy: **the app must never claim it verified idleness.** No string of the form "checked, nothing is running, safe to release" may exist. The action is presented as:
> Unload when the current request finishes.

and after the 10 s poll, if the model is still listed:
> Still in use. It will unload when the current request finishes.

Not a retry, not a failure, and never a suggestion to restart `ollama.service`.

**ComfyUI is the one service where in-use is genuinely knowable.** `GET /queue` returns `queue_running` (from `PromptQueue.currently_running`, populated under mutex) and `queue_pending`; `GET /prompt` returns `exec_info.queue_remaining`. Refuse when `queue_running` is non-empty or `queue_remaining > 0`, purely to set expectations, since the mechanism is already safe.

### 9.5 Types that must refuse

| Type | Reason shown | Why |
|---|---|---|
| Open WebUI | `Open WebUI has no way to release memory on request. The only lever is restarting it, which would end any chat in progress.` | It holds no LLM (it proxies to Ollama) but can hold its own sentence-transformers embedding and reranker models in process, with no unload API and no unauthenticated way to see whether a chat is streaming. 393.6 MB RSS here |
| Every self-hosted app and every generic unit (immich-ml 101.6 MB, hermes 187.5 MB, searxng, freshrss, the webdav pair, future-waqf) | same shape, naming the service | The only lever is stop/restart and there is no in-use signal for any of them |
| The app itself | not offered | rule 4 |

**Memory figures are shown for all of these** (from `podman stats`, on demand, not on the 5 s collect). Only the release action is disabled, with the reason stated. "Restart the service" is never presented as a release-memory action.

---

## 10. UI placement

### 10.1 Machine summary

One text line between `</header>` (`web/index.html:30`) and `<section class="group" id="groupAI">` (`:32`). Not in `.header-actions` (already five controls, wraps full-width at 560 px). Not in the footer (disk is what you check before a download, not after scrolling past the models).

```html
<div class="mach-line" id="machine" hidden>
  <span class="mach-item" title="Free space on the filesystem holding your models">
    <span class="dot"></span>Disk <b>412 GB free</b> of 1.8 TB
  </span>
  <span class="mach-sep">·</span>
  <span class="mach-item">
    <span class="dot"></span>Memory <b>38 GB available</b> of 62 GB
  </span>
</div>
```

Two facts only, `·`-separated, matching `.svc-sub` ("container · :8080") and `.footer-note`. `.dot` is the existing status dot, `display:none` unless the item is low, which is the only color this line ever earns.

The header gives back its own margin so nothing is pushed down. `:has()` is already in this stylesheet (`.btn-sm:has(svg)`, `styles.css:349`), so this is established syntax:

```css
.app-header:has(+ .mach-line:not([hidden])) { margin-bottom: 13px; }
.mach-line {
  display: flex; align-items: center; flex-wrap: wrap; gap: 4px 10px;
  padding: 0 4px; margin: 0 0 20px;
  font-size: 12.5px; color: var(--text-faint);
  font-variant-numeric: tabular-nums;
}
.mach-item { display: inline-flex; align-items: center; gap: 7px; }
.mach-item b { color: var(--text-muted); font-weight: 600; }
.mach-sep { color: var(--text-faint); }
.mach-item .dot { display: none; }
.mach-item.low .dot { display: block; background: var(--warn);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--warn) 22%, transparent); }
.mach-item.low b { color: var(--text); }
```

Net added height versus v1.3.2: 13 + 18 + 20 minus 26, about **+25 px**, and exactly **0** when hidden. Both themes work because every value is a token.

**Degradation.** Free known plus total known gives both. Free known, total unknown gives `Disk 412 GB free`. Free unknown drops the item entirely, because a capacity with no free figure answers nothing. The `·` is emitted only between rendered items, so there is never a dangling separator. Neither item survives means `hidden` on `#machine`, and the `:has()` rule restores v1 spacing byte for byte.

No third fact. GPU memory is the same pool on this hardware, and a two-item line becoming three is where the rule-of-three tell starts.

### 10.2 Per-item sizes: no new elements

| Where | Existing slot | Change |
|---|---|---|
| Ollama model row | `.size` (`styles.css:333`: `min-width:62px; text-align:right; tabular-nums`) | none. An unknown size already renders as an empty span that holds the column |
| Ollama in-memory figure | `.badge.loaded` | text becomes `In memory · 3.4 GB` (`vram_human` already exists in the sample data and is currently unrendered) |
| Ollama card total | `.models-head` right span (`web/app.js:449`, currently `${models.length} total`) | becomes `${models.length} models · 9.9 GB`. Zero models reads `0 models`, with no size segment |
| ComfyUI card total | `.models-topbar` right side, currently empty | `<span class="size">21.4 GB</span>` |
| App card | `.svc-sub`, built by `[a.kind, ':'+a.port].filter(Boolean).join(" · ")` (`web/app.js:287-289`) | append the size as one more segment; an unknown size drops out for free |
| AI service card row | nothing | nothing. Adding a third line to the three most important cards for the least important fact would change the page's rhythm |

### 10.3 Uninstall entry points

**The trash never enters `.svc-right`.** On a running ComfyUI card that cluster is already `[View log] [Open] [globe] [chevron] [toggle]`, and at 560 px `.card-row` wraps with `.svc-right { margin-left: auto }` (`styles.css:426-427`). Putting delete one 12 px gap from the control the user presses most, on a row that reflows on a phone, is a mis-tap that deletes a model.

```css
/* One destructive control per card, at the bottom of what the card already
   opens, never beside the toggle. */
.card-foot { display: flex; align-items: center; justify-content: space-between;
  gap: 12px; margin-top: 12px; padding: 12px 2px 2px;
  border-top: 1px solid var(--border); }
.card-foot .cf-why { font-size: 12px; color: var(--text-faint); line-height: 1.55; }

.row-trash { width: 30px; height: 30px; flex: none; border-radius: 9px;
  border: 1px solid transparent; background: none; color: var(--text-faint);
  display: grid; place-items: center; cursor: pointer; opacity: .45;
  transition: opacity var(--dur) var(--ease), color var(--dur) var(--ease),
              border-color var(--dur) var(--ease); }
.row-trash svg { width: 15px; height: 15px; }
.model:hover .row-trash, .row-trash:focus-visible { opacity: 1; }
.row-trash:hover { color: var(--err);
  border-color: color-mix(in srgb, var(--err) 45%, transparent); }
.row-trash[disabled] { opacity: .3; cursor: not-allowed; }
```

The 30 px box, 9 px radius and 1 px border match `.chevron` (`styles.css:248-254`) and `.addr-copy` (`:412-415`) exactly. Resting at 0.45 rather than 0 is deliberate: a hover-only destructive control is undiscoverable on touch, and this app ships a phone-width layout on purpose. Every trash carries `aria-label="Uninstall <name>"` and a matching `title`.

App cards have no disclosure today (`renderApps()` builds a `.card-row` plus an optional `.addr-panel` and nothing else, `web/app.js:281-302`). They gain the same `.chevron` with `data-act="appexpand"` and, on open, a `.layer-body` containing `.layer-facts` rows of `.ii-row` plus the `.card-foot`. That also answers the cost question: the `podman system df -v` read happens on expansion, not on the 5 s poll.

### 10.4 The modal

Built once in `wire()` beside `buildLogModal()` and `buildSetupModal()`, assembled entirely from existing classes: `.modal-backdrop`, `.modal`, `.sub`, `.layer-facts`, `.ii-row`, `.m-warn`, `.layer-note.note`, `.modal-foot`, `.btn-ghost`, `.btn-sm.danger`.

New CSS, exhaustively:

```css
.rm-modal   { width: min(520px, 94vw); }   /* alongside .sc-modal 560, .log-modal 660 */
.modal-foot { gap: 10px; }                 /* promoted from the inline style at web/app.js:702 */
.ii-row b.ok  { color: var(--ok); }
.ii-row b.err { color: var(--err); }
```

Plus `.mach-line` / `.mach-item` / `.mach-sep`, the `:has()` margin rule, `.card-foot` / `.cf-why`, `.row-trash`, and one new `trash` entry in the `I` icon map (24x24, `stroke-width="1.7"`, round caps, matching the existing hand-drawn set). **No new token, no new gradient, no new shadow, no new radius, no new uppercase treatment, no new panel style.**

### 10.5 Event wiring

Three delegated `[data-act]` listeners already exist (`#cards` at `web/app.js:1079-1096`, `#apps` at `:1098-1106`, `#layers` at `:1116-1137`). Two new verbs, matching the existing vocabulary (`toggle`, `expand`, `lexpand`, `apptoggle`, `clog`, `addr`, `copy`):

- `uninstall`, added to all three, carrying `data-scope` in `{model, comfy, service, layer, app}` plus the existing identifier attribute (`data-model`, `data-path`, `data-unit`, or the card's `data-svc`).
- `appexpand`, in `#apps` only.

Note `get_log` (`app.py:480-489`) resolves keys against `Backend._services` only, so a discovered container app asking for its log gets the literal string "(unknown service)". v2.0 does not fix that; it is unrelated and out of scope.

### 10.6 Responsive

Adding a 30 px `.row-trash` plus its gap takes 42 px out of `.model-name`, the only shrinkable child. At 560 px the name still has roughly 200 px, which works, but relief goes in the media query that already exists at `styles.css:422`:

```css
@media (max-width: 560px) {
  .model { gap: 8px; }
  .size  { min-width: 0; }
}
```

Do **not** add `flex-wrap` to `.model`: a wrapping row changes height as data arrives and would make the list jump under the finger.

### 10.7 Anti-slop tripwires for this feature

Ruled out explicitly, against `design/ANTI-SLOP.md`: stat banner rows and metric tiles; a usage meter or progress bar for disk (`.dl-fill` is the app's only progress element and the only gradient outside the 42 px brand mark); percentage-driven color ramps; a new uppercase `STORAGE` label (uppercase exists at exactly one size and role in this app, and the machine line is a footnote, not a section, so it gets no label); a third shadow, a tinted panel or a colored left border; emoji anywhere; a red-bordered "Danger Zone" panel; a count-up animation on a size.

Copy tripwires: no em dash in any new string; no "Are you sure?"; no reassurance ("Don't worry, your models are safe"); no "at a glance"; no exclamation mark; no "Freed up 4.1 GB!". And no "cannot be undone" doubled with "irreversible": for a model the true cost is the download, so state that instead.

The model-delete confirmation, in the house voice:

```
Delete qwen3.6:35b-a3b?
Ollama model

  Frees                   22 GB
  Disk after              434 GB free

  Ollama will need to download the model again before it can run.

  Not checked: FreshRSS, SearXNG, Joplin WebDAV, File Share WebDAV.
  This app doesn't know how to read their configuration.

                              [ Cancel ]  [ Delete model ]
```

Initial focus goes to Cancel, never to the destructive button, so a stray Enter cannot delete. Escape and backdrop click resolve to Cancel (and are suppressed while executing, 2.S4).

---

## 11. Decisions made independently, with reasoning

| # | Decision | Alternative rejected | Reasoning |
|---|---|---|---|
| D1 | Scope limited to three item classes (section 0) | Uninstall everything the app can see | The generic feature would offer removal for Immich (five units, 533 G on another device) and for the toolbox container that bind-mounts all of `$HOME`. Doing less is the whole brief |
| D2 | `Backend._services` stays a fixed registry | Make it dynamic so removed services disappear | `ChangeWatcher` holds the dict by reference and iterates it on the GUI thread with no try (`watch.py:96`, called from `:192`); its `_unit_names` is frozen at construction. Going dynamic is a two-file change but a real architectural reversal, and the `present=False` design already models removal correctly |
| D3 | Container images are never removed | Remove the image, gated on a live reference count | The reference count is easy; the honest reclaim figure is not (`podman system df -v` shows future-waqf's tagged image as 241.4 MB of which 1.749 MB is unique), and a shared image exists here. Disclosure plus `podman image prune` as the named alternative is strictly safer and not much less useful |
| D4 | Bind-mount sources are excluded by a syntactic test (`/` or `%` in the source), not by a path blacklist | Blacklist `~/Desktop`, `~/Documents`, `/var/mnt`, and so on | A blacklist is a list someone forgets to extend. The syntactic test is a property of the declaration and covers paths nobody anticipated |
| D5 | `podman unshare` is used for reading, never for writing or deleting | Use `podman unshare rm -rf ~/.hermes` so uninstall is complete | The app cannot enumerate or verify a tree it cannot read. An unbounded recursive delete of an opaque directory is precisely the operation this brief exists to prevent. The cost is a leftover folder, which is a mild inconvenience |
| D6 | ComfyUI service uninstall is disabled | Delete `~/ComfyUI` and put `models/`, `user/`, `output/` in the data tier | Software and data are one tree, and separating them requires enumerating children, which rule 3 forbids. Removing only the unit would leave 53 G and calling that "uninstall" would be dishonest |
| D7 | Ollama service uninstall is disabled; the app never prompts for root | Prompt for `sudo` / `pkexec` to remove `/usr/local` | Adding a privilege escalation path to a local control panel to delete files is a much larger security surface than the feature is worth, and this app's existing promise is that it never asks for root |
| D8 | Data removal is opt-in via an unchecked box plus a relabeled button; no type-to-confirm | Require typing the service name for data deletion | Two designs were genuinely available. Type-to-confirm is standard and stronger. Rejected because the data step is already opt-in and defaulted off, because the strongest protection is structural (a bind path cannot be deleted at all), and because the app's voice does not shout. Reconsider if the data tier ever reaches something as irreplaceable as `immich-pgdata`, which is exactly why Immich is out of scope |
| D9 | Unknown dependency reads **block**; unscanned services **disclose** | Fail closed on everything unknown | Fail-closed on unknown-unknowns disables all seven model trashes forever, producing a feature that never works. Blocking on failed reads of known sources, and naming the unscanned set in the dialog, is the honest middle. This is the weakest point in the design and is stated as such |
| D10 | Dependency findings block rather than warn | Show a warning and let the user proceed | Removing `gemma4:26b` silently breaks three services, and the union is discoverable only by reading three file formats. A user who has already been shown the consequence still cannot see Open WebUI's in-flight state, so proceed-anyway has no safe moment |
| D11 | No last-used for models, anywhere | Derive it from `atime`, or from Open WebUI's chat history | `atime` is frozen by `noatime` on `/var/mnt` and provably contaminated by a batch scanner on `/var/home` (identical nanosecond stamps across files of wildly different sizes; Pika Backup active). Open WebUI's history covers 4 of 7 models and would mark the RAG embedder as never used. A recency column that is wrong is worse than no column |
| D12 | No background cache and no TTL timer for disk | Cache `podman system df` with a 60 s TTL, refreshed in the background | The only figures the main screen needs are Tier A, which cost under 10 ms. Everything else is on demand. Background refresh would exist purely to keep a number warm that nobody is looking at, and would need its own invalidation |
| D13 | Immich's 533 G is never displayed | Show it from a cached user-initiated walk | Walking it costs 51 s cold and spins up an external USB drive. It cannot be refreshed. A number the app cannot keep current is worse than an absence |
| D14 | `~/comfy-models` (31 G) is not made deletable, and is not surfaced as reclaimable | Add it to the ComfyUI view with a reclaim action | It holds the only copies of `qwen_image_vae.safetensors` and `qwen_2.5_vl_7b_fp8_scaled.safetensors` on the machine, while `~/ComfyUI/models/vae` and `text_encoders` are empty. Deleting it would make the existing workflows unrunnable rather than merely unchanged. Whether it is a staged upgrade or abandoned is the user's call, section 12 |
| D15 | `unet` and `clip` are added to `MODEL_CATEGORIES` | Leave the list as is | The GGUF node registers exactly those directories, and 560 MB is currently invisible. Consequence acknowledged: it widens the deletable set by one file |
| D16 | `forget(path)` is called only when this app deletes the file | Sweep stale manifest entries at startup | Three stale entries exist. They already render as nothing because `_collect` joins the disk scan to the manifest. An unrequested write to tidy them is not this feature's business |
| D17 | `Backend._ollama_updates[name]` is evicted on delete | Leave it | Otherwise a removed model's cached "Up to date" survives and reappears if the model is re-pulled |
| D18 | Escape and backdrop click are suppressed during execution | Let the existing global handlers apply throughout | Dismissing mid-deletion hides the only report of what happened. This is a deliberate deviation from `web/app.js:1143-1147` and `:708` and needs an explicit guard |
| D19 | `hub/services/__init__.py:7`'s unused `SERVICES` and `containers.AI_UNITS`'s hardcoded set are left alone | Reconcile them into one registry | Correct cleanup, unrelated to this feature, and v2.0 adds no service so nothing forces it |
| D20 | The duplicated port map (`web/app.js:208`, `SVC_META`) is left alone | Have the backend emit `reachable` per service | Same reasoning as D19 |
| D21 | Memory release is offered for Ollama and ComfyUI only | Offer it for every service by restarting the container | Restarting destroys in-flight work with no warning and no way to detect it beforehand. "Restart" is never presented as a release action |
| D22 | Release copy never claims idleness was verified | "Checked, nothing is running" | Ollama exposes no in-flight signal and the real client is Open WebUI on another port. That sentence would be a fabrication |
| D23 | The service uninstall carries a generic closing line about external references rather than reading `tailscale serve status` | Read it and disclose the mapping | A new external dependency for one machine's configuration. The generic line is honest without claiming to have checked. Flagged in section 12 |
| D24 | Toasts state no freed-bytes figure unless something with a measured size was deleted | Always show a reclaim total | Overstating a saving is the same dishonesty as a cleanup app's inflated numbers |

### Where the investigations disagree or a finding is uncertain

- **`podman unshare` allowlist.** The artifacts probe declined to run `podman unshare du -sh ~/.hermes` as outside its read-only allowlist; the dependency probe ran `podman unshare cat` successfully on files in the same directory. Both are reads. The design resolves this by allowing `cat` and disallowing `du` (which is an unbounded walk of an opaque tree) and `rm` (D5).
- **`~/.hermes` size is unknown and stays unknown.** The one unresolved number in the manifest. It could be several GB because `PLAYWRIGHT_BROWSERS_PATH` points inside it. A `du` reporting 0 would be wrong, not empty, so the UI says "size not available" and names the cause.
- **ComfyUI/torch sees GTT, not the carveout.** This rests on arithmetic across two logs from 2026-07-17 (torch reported 15,855 MB, exactly `MemTotal/2` at the time, against a 32,768 MB carveout). The match is exact but was not re-measured, because ComfyUI is stopped and starting it is a state change. Re-confirm from `GET /system_stats` (`devices[0].vram_total`) next time ComfyUI is legitimately running.
- **The Ollama unload was designed but never executed**, and `/api/ps` was empty for the whole session, so the before/after transition is unproven on this machine. First real test should use `llama3.2:1b` (1.3 GB), not a 22 GB model.
- **The discrete-card fallback signal is half-verified.** Absence of `mem_info_vram_vendor` and `mem_busy_percent` on this APU was confirmed; their presence on a discrete card was not, because only an APU was available. Treat `uma/carveout` as primary and the absence rules as a hint.
- **Sysfs readability under Flatpak is untested.** The manifest grants `--device=dri` but nothing for `/sys`. Flatpak normally bind-mounts `/sys` read-only so this should work, but the app is not currently installed as a Flatpak (`flatpak info io.github.kamsiob.LocalAIHub` reports not installed). Since the whole uninstall feature is refused under Flatpak anyway, the exposure is limited to the memory readout, which must fall back to `/proc/meminfo` only.
- **The disk probe and the safety/UI probes disagree on whether `du` is expensive.** Both are right in their own domain: `du` on the model directories is 1.7 to 2.7 ms because they hold dozens of files; `du` on `/var/mnt/storage/immich` is 51 s because it holds 69,812 on a USB spinning disk. The design uses API sizes where they exist and never walks `/var/mnt`.
- **`podman system df` and `du` disagree by about 4 GiB** on `~/.local/share/containers` (35 GB versus 31 GiB) because podman counts shared overlay layers repeatedly. The design uses podman's TOTAL/RECLAIMABLE row for headlines and the SHARED/UNIQUE columns for attribution, and never mixes the two.

---

## 12. Open questions that need the user's decision

1. **Is `~/comfy-models` (31 G) a deliberate staging area for a Qwen-Image-2512 upgrade, or abandoned?** It is on no ComfyUI search path (no `extra_model_paths.yaml`, no symlinks, no unit flag) and holds the only copies of `qwen_image_vae.safetensors` and `qwen_2.5_vl_7b_fp8_scaled.safetensors` on the machine, while `~/ComfyUI/models/vae` and `text_encoders` are empty. That means the installed ComfyUI is currently missing a VAE and a text encoder. This is a repair question before it is a design question. v2.0's default is to leave it invisible.

2. **Is `~/ACE-Step-1.5` (60 G) in scope for anything?** No unit, no container, no reference from any listed service, and the second-largest tree in `$HOME` after `~/.ollama`. Including it in an "AI artifacts" sweep would delete 60 G of an unrelated project; excluding it means the app's numbers will never match what a disk-usage tool shows, which erodes trust in them. v2.0 excludes it and says nothing about it.

3. **Should `~/.config/containers/systemd/hermes.container.bak-preLAH` be flagged for removal now, independently of uninstall?** It pins the orphaned `:latest` image with `AutoUpdate=registry` and a different port set. It is inert only because the quadlet generator ignores unknown suffixes; renamed back to `*.container` it would define a second `ContainerName=hermes` colliding with the live unit. v2.0 lists it under "Left in place" and does nothing else.

4. **Low-space threshold for the `.low` warn dot on the machine line: a percentage (under 10%) or an absolute figure (under 20 GB, roughly one large model)?** The absolute figure is more meaningful for this app's purpose but needs a number chosen.

5. **Should the About panel carry an uninstall disclosure the way `app_update.DISCLOSURE` carries the update one?** The app already makes a specific, checkable promise about never updating itself. The parallel promises (it never uninstalls itself; it never removes data without a second confirmation; it never asks for root; it never removes container images) would fit the voice and give the tests something user-visible to assert against.

6. **Should the app read `tailscale serve status` so it can disclose a mapping like future-waqf's?** It is read-only and cheap, but it is a new external dependency for one machine's configuration, and the app still would not offer to undo it. D23 says no; this reverses cheaply if you want it.

7. **Is per-model deletion for ComfyUI wanted at all in v2.0, or only for Ollama?** The ComfyUI side deletes a file that may be a 21.76 GB re-download over a slow link, and unlike Ollama there is no registry to re-pull from for a Civitai or direct-URL source unless the manifest recorded one. Keeping ComfyUI file deletion out of v2.0 would be the more cautious ship.

8. **What is the recovery story after a halted partial uninstall?** The design records completed and remaining steps and shows them as literal commands. Whether that also needs a retry button, and whether the record must survive an app restart, changes what the executor has to persist.

9. **Should the "Not checked" disclosure (D9) name the services, or state the limitation without a list?** Naming them is more honest and also longer, and the list grows with every container the user adds.