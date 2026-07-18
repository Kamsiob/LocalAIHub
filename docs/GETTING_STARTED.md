# Getting Started — Bazzite + AMD Strix Halo

A from-scratch setup guide for the **exact configuration this project targets**:

- **Distro:** Bazzite (Fedora Atomic base, KDE/Kinoite) — immutable, `/usr` is read-only
- **Hardware:** AMD Ryzen AI MAX+ 395 "Strix Halo", Radeon 8060S iGPU (**gfx1151**)
- **Goal:** Ollama + Open WebUI + ComfyUI, all GPU-accelerated on the iGPU

Every command and file below is copied from a working machine with this exact
setup — not reconstructed from general docs. If your distro or chip differ, this
guide may not apply (and the in-app **Setup Check** will tell you so).

There are two tracks. Pick one.

---

## Track A — You have an AI coding assistant (Claude, etc.)

This is the fastest path. The catch: a general assistant **doesn't know this
hardware's quirks** (the read-only filesystem, the iGPU flags Ollama needs, the
gfx1151-specific ROCm build ComfyUI needs) unless you tell it up front. So lead
with the context.

Paste this as your starter prompt, then let it drive:

```
I'm on Bazzite (Fedora Atomic base, KDE, immutable filesystem — /usr is
read-only). Hardware is an AMD Ryzen AI MAX+ 395 "Strix Halo" with the Radeon
8060S integrated GPU (gfx1151). I have nothing AI-related installed yet.

Please set up, with GPU acceleration on the iGPU, and verify each works:
  1. Ollama — as a systemd *user* service (NOT the installer's default system
     service, whose dedicated 'ollama' user home lives under read-only /usr and
     which omits the iGPU env vars). It must set OLLAMA_IGPU_ENABLE=1 and
     OLLAMA_VULKAN=1, store models under my home, and survive logout (linger).
  2. Open WebUI — as a Podman Quadlet (~/.config/containers/systemd/), pointed at
     Ollama. Watch for two gotchas: use a plain named volume (not a *.volume
     file reference), and set TimeoutStartSec high (~600) so the first image
     pull doesn't hit the default 90s start timeout.
  3. ComfyUI — in a venv, but install PyTorch from the gfx1151 ROCm *nightly*
     index (https://rocm.nightlies.amd.com/v2/gfx1151/), because the standard
     ROCm wheels crash on this chip. Add the ComfyUI-GGUF custom node. Use a
     launch wrapper that sets HSA_ENABLE_SDMA=0 (the Strix Halo crash
     mitigation) and unsets HSA_OVERRIDE_GFX_VERSION.

Explain what you're doing as you go, and confirm each service actually uses the
Radeon 8060S rather than falling back to CPU.
```

Then, optionally, clone this repo and run **Local AI Hub** to manage it all
(see the main [README](../README.md)), and use its **Setup Check** to confirm
everything is configured correctly.

---

## Track B — Manual setup (no assistant)

Full walkthrough. Run these in order. You'll need `sudo` for a few one-time
steps. Podman, git, python3, and wget ship with Bazzite already.

### 1. Ollama

Install the binary (this part works fine — it lands in `/usr/local/bin`, which on
Bazzite is writable):

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

**Why the default service fails here:** the installer also creates a *system*
service that runs as a dedicated `ollama` user whose home is `/usr/share/ollama`
— which is under the **read-only `/usr`** tree, so the daemon can't store models
there. It also doesn't set the integrated-GPU flags, so even when it runs it
falls back to CPU. Both problems disappear if you run Ollama as **your own user**
instead. Turn off the installer's service:

```bash
sudo systemctl disable --now ollama
```

Create a user service that runs as you (models go in `~/.ollama`) with the iGPU
flags:

```bash
mkdir -p ~/.config/systemd/user
cat > ~/.config/systemd/user/ollama.service <<'EOF'
[Unit]
Description=Ollama Service (user)
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=/usr/local/bin/ollama serve
Environment="OLLAMA_VULKAN=1"
Environment="OLLAMA_IGPU_ENABLE=1"
Environment="OLLAMA_HOST=0.0.0.0:11434"
Restart=always
RestartSec=3

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now ollama
sudo loginctl enable-linger "$USER"   # keep it running after logout
```

Verify and pull a model:

```bash
curl 127.0.0.1:11434            # -> "Ollama is running"
ollama pull qwen3-coder:30b     # or any model you want
```

`OLLAMA_IGPU_ENABLE=1` + `OLLAMA_VULKAN=1` are what put inference on the Radeon
8060S. Without them Ollama silently uses the CPU.

### 2. Open WebUI (Podman Quadlet)

Open WebUI runs as a container, managed by systemd via a Quadlet file.

```bash
mkdir -p ~/.config/containers/systemd
cat > ~/.config/containers/systemd/open-webui.container <<'EOF'
[Unit]
Description=Open WebUI Container
After=network-online.target

[Container]
Image=ghcr.io/open-webui/open-webui:main
ContainerName=open-webui
PublishPort=3000:8080
Volume=open-webui:/app/backend/data
AddHost=host.containers.internal:host-gateway
Environment=OLLAMA_BASE_URL=http://host.containers.internal:11434

[Service]
Restart=always
TimeoutStartSec=600

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user start open-webui
```

Open it at **http://127.0.0.1:3000** (use `127.0.0.1`, not `localhost` — some
browsers mishandle `localhost` for local servers).

**Two failure points that cost real time — get them right up front:**

1. **The volume line.** `Volume=open-webui:/app/backend/data` uses a *named
   volume* that Podman creates automatically. Do **not** write
   `Volume=open-webui.volume:/app/backend/data` — the `.volume` suffix makes
   Quadlet look for a separate `open-webui.volume` file, and if it doesn't
   exist the generated service silently fails to start.
2. **The startup timeout.** The very first start pulls a multi-hundred-MB image.
   Without `TimeoutStartSec=600`, systemd's default ~90s start timeout fires and
   kills the container mid-pull, leaving the unit "failed" for no obvious reason.
   Keep `TimeoutStartSec=600`.

(Also make sure the first line is exactly `[Unit]` — a stray `Unit]` with the
bracket missing silently voids the whole section.)

### 3. ComfyUI

Clone it and make a virtualenv:

```bash
git clone https://github.com/comfyanonymous/ComfyUI ~/ComfyUI
cd ~/ComfyUI
python3 -m venv venv
```

**Install PyTorch from the gfx1151 ROCm nightly — this is the critical step.**
The standard ROCm wheels (`download.pytorch.org/whl/rocm6.3`) **crash on this
chip** (a Strix Halo driver gap surfaces as a `libamdhip64` / `memcpy_and_sync`
segfault). AMD publishes a nightly built specifically for gfx1151:

```bash
venv/bin/pip install --index-url https://rocm.nightlies.amd.com/v2/gfx1151/ \
  torch torchaudio torchvision
```

Then ComfyUI's own dependencies. `requirements.txt` lists `torch` unpinned, so
installing it *after* the nightly leaves your gfx1151 build in place:

```bash
venv/bin/pip install -r requirements.txt
```

Add the **ComfyUI-GGUF** custom node (required for any GGUF-format model):

```bash
git clone https://github.com/city96/ComfyUI-GGUF custom_nodes/ComfyUI-GGUF
venv/bin/pip install -r custom_nodes/ComfyUI-GGUF/requirements.txt
```

Download the three model files needed to run Qwen-Image, into their folders
(sizes are real — budget the download time and disk):

```bash
# Diffusion model (GGUF) — ~20.3 GB  -> models/diffusion_models/
wget -P models/diffusion_models \
  https://huggingface.co/city96/Qwen-Image-gguf/resolve/main/qwen-image-Q8_0.gguf

# Text encoder — ~8.7 GB  -> models/text_encoders/
wget -P models/text_encoders \
  https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/resolve/main/split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors

# VAE — ~242 MB  -> models/vae/
wget -P models/vae \
  https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/resolve/main/split_files/vae/qwen_image_vae.safetensors
```

Create the launch wrapper. The environment here is not optional — `HSA_ENABLE_SDMA=0`
is the Strix Halo crash mitigation, and unsetting `HSA_OVERRIDE_GFX_VERSION`
prevents a common global override from breaking the nightly build:

```bash
cat > ~/ComfyUI/start_comfyui_rocm.sh <<'EOF'
#!/bin/bash
cd ~/ComfyUI
source venv/bin/activate
unset HSA_OVERRIDE_GFX_VERSION
export HIP_VISIBLE_DEVICES=0
export HSA_ENABLE_SDMA=0
export HSA_USE_SVM=0
export PYTORCH_ALLOC_CONF="expandable_segments:True,garbage_collection_threshold:0.8,max_split_size_mb:512"
python3 main.py
EOF
chmod +x ~/ComfyUI/start_comfyui_rocm.sh

~/ComfyUI/start_comfyui_rocm.sh
```

Open it at **http://127.0.0.1:8188**. In the startup log you should see
`Device: cuda:0 Radeon 8060S Graphics` and `AMD arch: gfx1151` — that's the iGPU
being used. If it says CPU, the torch build is wrong (re-check the nightly step).

*(Local AI Hub can run ComfyUI as a systemd user service instead of this script —
it replicates exactly this environment. See the main README.)*

---

## Verify the whole stack

| Service | Check | Expected |
|---|---|---|
| Ollama | `curl 127.0.0.1:11434` | `Ollama is running` |
| Open WebUI | open `http://127.0.0.1:3000` | login page loads |
| ComfyUI | open `http://127.0.0.1:8188` | the graph UI loads |

Then clone **[Local AI Hub](../README.md)**, run it, and hit **Setup Check** — it
confirms all of the above (iGPU flags, the Quadlet volume/timeout, the gfx1151
ROCm build, the GGUF node) in one panel.
