# Getting Started

*Bazzite + AMD Strix Halo — a proven, from-scratch setup*

This guide is proven on one specific setup, from a machine with nothing installed to a full working stack. It targets:

- Bazzite — or a similar immutable Fedora Atomic distro (/usr is read-only)
- An AMD Ryzen AI MAX+ 395 “Strix Halo” with the Radeon 8060S iGPU (gfx1151)

> ⚠️ **Watch out:** If you're on different hardware or a different distro, this guide won't directly apply. The read-only-filesystem workarounds, the iGPU flags, and the gfx1151 ROCm build are all specific to this configuration — the shape may still help, but the exact commands are for this machine.

Pick a track below. If you have an AI assistant, start with Track 1 — it's far faster. Otherwise Track 2 is the complete manual walkthrough.

---

## Track 1 · With an AI assistant

The fastest path is to hand your assistant the hardware and distro context up front. A generic assistant won't know this hardware's quirks unless you tell it directly — the immutable filesystem that blocks the standard installer, the iGPU that's ignored by default, and the ROCm driver gap on this exact chip. Give it all of that at once so it can walk you through, instead of you discovering each issue the hard way, one at a time.

#### Ready-to-paste starter prompt

```text
I'm on Bazzite (an immutable Fedora Atomic distro, KDE, /usr is read-only).
My hardware is an AMD Ryzen AI MAX+ 395 "Strix Halo" with the Radeon 8060S
integrated GPU (gfx1151). I have nothing AI-related installed yet.

Please set up, with GPU acceleration on the iGPU, and verify each actually uses
the GPU rather than falling back to CPU:

  1. Ollama. Do NOT rely on the installer's default systemd service — it creates
     an 'ollama' system user whose home is /usr/share/ollama, which can't be
     created on the read-only /usr, so it silently fails; and it omits the iGPU
     env vars. Instead run Ollama as a systemd *user* service that sets
     OLLAMA_IGPU_ENABLE=1 and OLLAMA_VULKAN=1, stores models under my home, and
     has linger enabled.

  2. Open WebUI as a Podman Quadlet in ~/.config/containers/systemd/, pointed at
     Ollama. Use a plain named volume (NOT a *.volume file reference, which fails
     to generate), and set TimeoutStartSec high (~600) so the first image pull
     doesn't hit systemd's ~90s start timeout.

  3. ComfyUI in a venv, but install PyTorch from the gfx1151 ROCm *nightly*
     (https://rocm.nightlies.amd.com/v2/gfx1151/) — the standard ROCm wheels
     segfault on this chip (a libamdhip64 / memcpy_and_sync crash). Add the
     ComfyUI-GGUF custom node, and launch with HSA_ENABLE_SDMA=0 and
     HSA_OVERRIDE_GFX_VERSION unset.

Explain each step as you go, and after each service confirm it's on the GPU.
```

> ℹ️ **Note:** If your assistant gets stuck, point it at this guide (docs/GETTING_STARTED.md in this repo) for the verified specifics — the exact unit files, env vars, and the gfx1151 nightly index are all here.

---

## Track 2 · Manual setup

### Ollama

Install the binary. This part works — it lands in /usr/local/bin, which is writable on Bazzite:

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

#### Why the installer's service silently fails here

The installer's service step runs `useradd -m -d /usr/share/ollama ollama` — but /usr/share is read-only on Bazzite, so that home directory is never created. You can confirm it: the user exists, yet its home doesn't.

```bash
getent passwd ollama
# -> ollama:x:992:962::/usr/share/ollama:/bin/false   (user exists)
ls -ld /usr/share/ollama
# -> No such file or directory                          (home never created)
```

So the generated service runs as the `ollama` user with a home that doesn't exist on a read-only path — it can't store models, and it never sets the iGPU flags. It looks installed but doesn't work. Disable it:

```bash
sudo systemctl disable --now ollama
```

#### Create a user service that actually works

Run Ollama as your own user (models go in ~/.ollama) with the iGPU flags:

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
```

What the two GPU env vars do — without either, Ollama silently runs on the CPU:
- OLLAMA_IGPU_ENABLE=1 — enables the integrated GPU, which Ollama ignores by default.
- OLLAMA_VULKAN=1 — routes compute through Vulkan, the working path for this iGPU.
(OLLAMA_HOST=0.0.0.0:11434 lets the Open WebUI container reach Ollama.)

#### Enable, start, and keep it running after logout

```bash
systemctl --user daemon-reload
systemctl --user enable --now ollama
sudo loginctl enable-linger "$USER"
```

#### Verify it's on the GPU (not CPU)

```bash
curl 127.0.0.1:11434          # -> "Ollama is running"
ollama pull llama3.2:1b
ollama run llama3.2:1b "hi"
ollama ps                    # PROCESSOR column should show a GPU %, not "100% CPU"
```

### Open WebUI

Run Open WebUI as a Podman Quadlet — a container managed by systemd — rather than a container you start by hand, so it starts on boot and restarts cleanly.

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

Then open http://127.0.0.1:3000 (use 127.0.0.1, not localhost — some browsers mishandle localhost for local servers).

> ⚠️ **Watch out:** Failure point 1 — the Volume line. `Volume=open-webui:/app/backend/data` is a plain named volume that Podman creates automatically. Do NOT write `Volume=open-webui.volume:/...` — the `.volume` suffix makes Quadlet look for a separate open-webui.volume file, and when it isn't there the service never generates. `systemctl --user status open-webui` then shows a confusing “not found” for a unit that was never created.

> ⚠️ **Watch out:** Failure point 2 — the first image pull. The first start pulls a multi-hundred-MB image. Without TimeoutStartSec=600, systemd's default ~90s start timeout fires and kills it mid-pull, leaving the unit failed for no obvious reason. Keep TimeoutStartSec=600, and it helps to pull the image once by hand first: `podman pull ghcr.io/open-webui/open-webui:main`.

> ℹ️ **Note:** Also make sure the first line is exactly `[Unit]`. A stray `Unit]` with the bracket missing silently voids the section.

### ComfyUI

Clone ComfyUI and make a virtualenv:

```bash
git clone https://github.com/comfyanonymous/ComfyUI ~/ComfyUI
cd ~/ComfyUI
python3 -m venv venv
```

#### The ROCm segfault on this chip — and the fix

If you install the standard ROCm PyTorch (download.pytorch.org/whl/rocm6.3), ComfyUI crashes on gfx1151 the moment it touches the GPU. The crash is a segmentation fault inside libamdhip64.so (around memcpy_and_sync) — you'll see something like this and it will exit:

```text
Segmentation fault (core dumped)
# backtrace mentions libamdhip64.so ... memcpy_and_sync
```

That's not something you did wrong — it's a known driver gap on this chip. The fix is to install PyTorch from the gfx1151-specific ROCm nightly:

```bash
venv/bin/pip install --index-url https://rocm.nightlies.amd.com/v2/gfx1151/ \
  torch torchaudio torchvision
```

Then ComfyUI's own dependencies. Its requirements.txt lists torch unpinned, so installing it after the nightly leaves your gfx1151 build in place:

```bash
venv/bin/pip install -r requirements.txt
```

#### The ComfyUI-GGUF custom node (required)

GGUF is a quantized model format; ComfyUI can't load .gguf files without this node's loaders. The main diffusion model below is GGUF, so this is required, not optional:

```bash
git clone https://github.com/city96/ComfyUI-GGUF custom_nodes/ComfyUI-GGUF
venv/bin/pip install -r custom_nodes/ComfyUI-GGUF/requirements.txt
```

#### The three model files (real sizes, exact places)

```bash
# Diffusion model (GGUF) — 20.3 GB  ->  models/diffusion_models/
wget -P models/diffusion_models \
  https://huggingface.co/city96/Qwen-Image-gguf/resolve/main/qwen-image-Q8_0.gguf

# Text encoder — 8.7 GB  ->  models/text_encoders/
wget -P models/text_encoders \
  https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/resolve/main/split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors

# VAE — 242 MB  ->  models/vae/
wget -P models/vae \
  https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/resolve/main/split_files/vae/qwen_image_vae.safetensors
```

#### The launch script

Create the launch wrapper. The environment it sets is not optional — running `python3 main.py` directly (without this env) brings the crash / CPU fallback right back:

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

Why each line matters:
- unset HSA_OVERRIDE_GFX_VERSION — a globally-set gfx override (a common tweak) makes the nightly target the wrong arch and breaks; clear it.
- HSA_ENABLE_SDMA=0 — disables the SDMA path that triggers the crash on Strix Halo. This is the actual mitigation.
- HIP_VISIBLE_DEVICES=0 — selects the iGPU.
- HSA_USE_SVM=0 and PYTORCH_ALLOC_CONF=… — memory settings tuned for this shared-memory APU.

Open http://127.0.0.1:8188. In the startup log you should see `Device: cuda:0 Radeon 8060S Graphics` and `AMD arch: gfx1151` — that's the iGPU in use.

> ℹ️ **Note:** Local AI Hub can run ComfyUI as a systemd user service that sets exactly this same environment, so you don't have to launch the script by hand.

### Troubleshooting

The exact errors hit while building this the first time, so you can pattern-match instead of debugging blind.

#### Ollama looks installed but nothing works

After the installer, the daemon seems present but models won't pull/persist. Check the default service's home:

```bash
ls -ld /usr/share/ollama
# -> No such file or directory
```

The `ollama` user's home was never created on the read-only /usr. Fix: disable that service and use the user service (Ollama section above).

#### Ollama runs on CPU

`ollama ps` shows PROCESSOR as “100% CPU”. The iGPU env vars aren't set — add OLLAMA_IGPU_ENABLE=1 and OLLAMA_VULKAN=1 and restart.

#### Open WebUI: “not found”, unit won't start

`systemctl --user status open-webui` reports the unit as not found / not generated. The Volume line points at a nonexistent `.volume` file. Use a plain named volume (`open-webui:/app/backend/data`).

#### Open WebUI times out on first start

The unit fails after ~90 seconds (a start-timeout / start-limit-hit). The first image pull exceeded systemd's default timeout. Set TimeoutStartSec=600 and/or `podman pull ghcr.io/open-webui/open-webui:main` first.

#### ComfyUI: Segmentation fault (core dumped)

A segfault mentioning libamdhip64.so / memcpy_and_sync as soon as it uses the GPU = the standard ROCm build on gfx1151. Reinstall torch from the gfx1151 nightly index.

#### ComfyUI runs on CPU (very slow)

The log doesn't say `AMD arch: gfx1151` / `Device: cuda:0`. Either you launched `main.py` directly instead of the script (so the env wasn't set), or torch has no ROCm. Use the launch script and confirm the log.

#### A GGUF model doesn't show up / won't load

The ComfyUI-GGUF custom node isn't installed. Clone it into custom_nodes/ and restart ComfyUI.

---

*This guide is generated from `hub/guide.py`; the in-app Getting Started screen renders the same content. Edit the source, then run `python3 scripts/gen_guide.py`.*
