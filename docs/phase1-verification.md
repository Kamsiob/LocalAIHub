# Phase 1 — ComfyUI service verification

Runtime verification of `comfyui.service` (user unit), captured 2026-07-17.

## GPU is actually used (not CPU fallback)
From `journalctl --user -u comfyui`:
```
Total VRAM 15855 MB, total RAM 31711 MB
pytorch version: 2.11.0+rocm7.13.0a20260426
AMD arch: gfx1151
ROCm version: (7, 13)
Set vram state to: NORMAL_VRAM
Device: cuda:0 Radeon 8060S Graphics : native
```
`Device: ... Radeon 8060S Graphics : native` confirms the Radeon 8060S (gfx1151) is the
compute device — no CPU fallback. The env block (esp. `HSA_ENABLE_SDMA=0`) held; no segfault.

## Lifecycle
| Step | Result |
|------|--------|
| `systemctl --user start comfyui` | `active` |
| port 8188 | HTTP **200** after ~8s |
| `systemctl --user stop comfyui` | `inactive`, port closed |
| `systemctl --user is-failed comfyui` | `inactive` (clean stop, not failed) |
| `systemctl --user start comfyui` (again) | `active`, port **200** after ~6s |

## Restart-loop safety
`Restart=on-failure` with `StartLimitBurst=5` / `StartLimitIntervalSec=300`: a genuine crash
loop stops after 5 attempts in 5 minutes and the unit is left `failed` (visible), rather than
being hidden by infinite restarts. Logs are in the journal (`journalctl --user -u comfyui`).

Baseline after verification: unit registered + enabled-capable but left **stopped** (ComfyUI is
heavy and launched on demand via the app toggle).
