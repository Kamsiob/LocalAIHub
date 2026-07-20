"""In-app setup check for the supported configuration.

Verifies the specific, proven-working setup this app targets — Bazzite / Fedora
Atomic on an AMD Strix Halo (gfx1151) iGPU with Ollama + Open WebUI + ComfyUI.
If the distro or chip don't match, the service checks are skipped entirely (they
wouldn't apply). Each check is a plain pass/warn/fail with an explanation; a few
have a safe, known auto-fix.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from .base import host_env
from .comfyui import COMFYUI_ROOT

OLLAMA_USER_UNIT = Path.home() / ".config/systemd/user/ollama.service"
OPENWEBUI_QUADLET = Path.home() / ".config/containers/systemd/open-webui.container"
GGUF_NODE = COMFYUI_ROOT / "custom_nodes" / "ComfyUI-GGUF"
COMFY_VENV_PY = COMFYUI_ROOT / "venv" / "bin" / "python"
GGUF_NIGHTLY_INDEX = "https://rocm.nightlies.amd.com/v2/gfx1151/"


# --------------------------------------------------------------------------- #
# platform detection
# --------------------------------------------------------------------------- #
def _os_release() -> dict:
    out: dict = {}
    try:
        for line in Path("/etc/os-release").read_text().splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                out[k] = v.strip().strip('"')
    except Exception:
        pass
    return out


def _cpu_model() -> str:
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.lower().startswith("model name"):
                return line.split(":", 1)[1].strip()
    except Exception:
        pass
    return ""


def detect_platform() -> dict:
    osr = _os_release()
    idlike = (osr.get("ID_LIKE", "") + " " + osr.get("ID", "")).lower()
    is_fedora = "fedora" in idlike
    is_atomic = bool(osr.get("OSTREE_VERSION")) or os.path.exists("/run/ostree-booted")
    is_bazzite = osr.get("ID") == "bazzite" or osr.get("VARIANT_ID") == "bazzite"
    atomic_fedora = is_fedora and is_atomic

    # GPU: prefer rocminfo, fall back to the CPU model string (Strix Halo APUs).
    gpu_detail = ""
    gfx1151 = False
    rocminfo = shutil.which("rocminfo")
    if rocminfo:
        try:
            out = subprocess.run([rocminfo], capture_output=True, text=True, timeout=15, env=host_env()).stdout
            if "gfx1151" in out:
                gfx1151, gpu_detail = True, "rocminfo reports gfx1151"
        except Exception:
            pass
    cpu = _cpu_model()
    if not gfx1151 and any(k in cpu.upper() for k in ("RYZEN AI MAX", "8060S", "STRIX HALO")):
        gfx1151, gpu_detail = True, f"CPU: {cpu}"
    if not gpu_detail:
        gpu_detail = cpu or "unknown"

    distro = osr.get("PRETTY_NAME") or osr.get("NAME") or "unknown"
    applies = (is_bazzite or atomic_fedora) and gfx1151
    return {
        "bazzite": is_bazzite,
        "atomic_fedora": atomic_fedora,
        "gfx1151": gfx1151,
        "applies": applies,
        "distro": distro,
        "gpu": gpu_detail,
    }


# --------------------------------------------------------------------------- #
# individual checks
# --------------------------------------------------------------------------- #
def _result(cid, label, status, detail, fix=None):
    return {"id": cid, "label": label, "status": status, "detail": detail, "fix": fix}


def _ollama_env() -> str:
    for args in (["--user", "show", "ollama", "-p", "Environment"],
                 ["show", "ollama", "-p", "Environment"]):
        try:
            cp = subprocess.run(["systemctl", *args], capture_output=True, text=True, timeout=10, env=host_env())
            if "Environment=" in cp.stdout:
                return cp.stdout
        except Exception:
            pass
    if OLLAMA_USER_UNIT.exists():
        return OLLAMA_USER_UNIT.read_text()
    return ""


def check_ollama() -> dict:
    env = _ollama_env()
    have_igpu = "OLLAMA_IGPU_ENABLE=1" in env
    have_vulkan = "OLLAMA_VULKAN=1" in env
    if have_igpu and have_vulkan:
        return _result("ollama", "Ollama iGPU acceleration", "pass",
                       "Service sets OLLAMA_IGPU_ENABLE=1 and OLLAMA_VULKAN=1.")
    missing = [n for n, ok in (("OLLAMA_IGPU_ENABLE=1", have_igpu), ("OLLAMA_VULKAN=1", have_vulkan)) if not ok]
    fix = "ollama_env" if OLLAMA_USER_UNIT.exists() else None
    return _result("ollama", "Ollama iGPU acceleration", "fail",
                   f"Missing {', '.join(missing)} — without these Ollama runs on CPU, not the Radeon 8060S."
                   + ("" if fix else " (no user unit found to fix automatically)"), fix)


def check_openwebui() -> list:
    if not OPENWEBUI_QUADLET.exists():
        return [_result("owui_present", "Open WebUI Quadlet present", "fail",
                        f"No {OPENWEBUI_QUADLET.name} in ~/.config/containers/systemd/.")]
    text = OPENWEBUI_QUADLET.read_text()
    checks = [_result("owui_present", "Open WebUI Quadlet present", "pass",
                      "open-webui.container found.")]

    vol = next((l.split("=", 1)[1].strip() for l in text.splitlines()
                if l.strip().startswith("Volume=")), "")
    vol_target = vol.split(":", 1)[0]
    if vol_target.endswith(".volume"):
        checks.append(_result("owui_volume", "Open WebUI volume", "fail",
                              f"Volume references '{vol_target}', a .volume Quadlet file that must exist "
                              "separately. Use a plain named volume (e.g. 'open-webui:/app/backend/data')."))
    elif vol:
        checks.append(_result("owui_volume", "Open WebUI volume", "pass",
                              f"Uses named volume '{vol_target}'."))

    timeout = next((int(l.split("=", 1)[1].strip()) for l in text.splitlines()
                    if l.strip().startswith("TimeoutStartSec=") and l.split("=", 1)[1].strip().isdigit()), 0)
    if timeout >= 300:
        checks.append(_result("owui_timeout", "Open WebUI startup timeout", "pass",
                              f"TimeoutStartSec={timeout} (enough for the first image pull)."))
    else:
        checks.append(_result("owui_timeout", "Open WebUI startup timeout", "fail",
                              "TimeoutStartSec is missing/too low. The first run pulls a large image and can "
                              "exceed the default 90s, so systemd kills it mid-pull. Set TimeoutStartSec=600.",
                              "owui_timeout"))
    return checks


def check_comfyui_rocm() -> dict:
    if not COMFY_VENV_PY.exists():
        return _result("comfy_rocm", "ComfyUI ROCm build", "fail",
                       f"No ComfyUI venv at {COMFY_VENV_PY}.")
    try:
        ver = subprocess.run([str(COMFY_VENV_PY), "-c", "import torch;print(torch.__version__)"],
                             capture_output=True, text=True, timeout=30, env=host_env()).stdout.strip()
    except Exception as exc:  # noqa: BLE001
        return _result("comfy_rocm", "ComfyUI ROCm build", "fail", f"Could not import torch: {exc}")
    if "rocm7" in ver:
        return _result("comfy_rocm", "ComfyUI ROCm build", "pass",
                       f"torch {ver} — the gfx1151 ROCm nightly.")
    if "rocm" in ver:
        return _result("comfy_rocm", "ComfyUI ROCm build", "warn",
                       f"torch {ver} is a standard ROCm build. It crashes on gfx1151 — reinstall from the "
                       f"nightly: pip install --index-url {GGUF_NIGHTLY_INDEX} torch torchaudio torchvision")
    return _result("comfy_rocm", "ComfyUI ROCm build", "warn",
                   f"torch {ver} has no ROCm — ComfyUI will run on CPU.")


def check_gguf_node() -> dict:
    if GGUF_NODE.is_dir():
        return _result("gguf_node", "ComfyUI-GGUF custom node", "pass",
                       "Present — GGUF-format models can load.")
    return _result("gguf_node", "ComfyUI-GGUF custom node", "fail",
                   "Missing — any GGUF-format model won't load in ComfyUI until this node is installed.",
                   "gguf_node")


def run_checks() -> dict:
    plat = detect_platform()
    if not plat["applies"]:
        return {"applies": False, "platform": plat, "checks": []}
    checks = [check_ollama(), *check_openwebui(), check_comfyui_rocm(), check_gguf_node()]
    return {"applies": True, "platform": plat, "checks": checks}


# --------------------------------------------------------------------------- #
# safe, known fixes
# --------------------------------------------------------------------------- #
def apply_fix(fix_id: str) -> dict:
    try:
        if fix_id == "gguf_node":
            GGUF_NODE.parent.mkdir(parents=True, exist_ok=True)
            r = subprocess.run(["git", "clone", "--depth", "1",
                                "https://github.com/city96/ComfyUI-GGUF", str(GGUF_NODE)],
                               capture_output=True, text=True, timeout=120, env=host_env())
            if r.returncode != 0:
                return {"ok": False, "message": r.stderr.strip()[:200] or "git clone failed"}
            return {"ok": True, "message": "Installed ComfyUI-GGUF. Restart ComfyUI to load it."}

        if fix_id == "owui_timeout":
            text = OPENWEBUI_QUADLET.read_text()
            if "TimeoutStartSec=" in text:
                lines = ["TimeoutStartSec=600" if l.strip().startswith("TimeoutStartSec=") else l
                         for l in text.splitlines()]
                text = "\n".join(lines) + "\n"
            else:
                text = text.replace("[Service]", "[Service]\nTimeoutStartSec=600", 1)
            OPENWEBUI_QUADLET.write_text(text)
            subprocess.run(["systemctl", "--user", "daemon-reload"], timeout=15, env=host_env())
            return {"ok": True, "message": "Set TimeoutStartSec=600. Restart Open WebUI to apply."}

        if fix_id == "ollama_env":
            text = OLLAMA_USER_UNIT.read_text()
            add = [v for v in ('Environment="OLLAMA_IGPU_ENABLE=1"', 'Environment="OLLAMA_VULKAN=1"')
                   if v.split('"')[1].split("=")[0] not in text]
            if add and "ExecStart=" in text:
                text = text.replace("ExecStart=", "\n".join(add) + "\nExecStart=", 1)
                OLLAMA_USER_UNIT.write_text(text)
                subprocess.run(["systemctl", "--user", "daemon-reload"], timeout=15, env=host_env())
            return {"ok": True, "message": "Added the iGPU env vars. Restart Ollama to apply."}

        return {"ok": False, "message": f"No automatic fix for '{fix_id}'."}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "message": str(exc)}
