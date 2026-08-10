"""Single source of truth for the Getting Started guide.

Both the repo's docs/GETTING_STARTED.md (via scripts/gen_guide.py) and the
in-app Getting Started screen (via Backend.get_guide -> QWebChannel) are
generated from GUIDE below, so they can't drift apart.

Every command and file body here is copied from a working Bazzite + AMD Strix
Halo (gfx1151) machine — not reconstructed from general docs.

Block types: p (paragraph), h (subheading), code {code,lang}, warn, note.
"""

OLLAMA_UNIT = """[Unit]
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
WantedBy=default.target"""

OPENWEBUI_QUADLET = """[Unit]
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
WantedBy=default.target"""

# Generic on purpose: a version tag rather than :latest, both a loopback and a
# LAN/remote publish, and a placeholder key. Nobody's real secret belongs in a
# guide that ships inside the app.
HERMES_QUADLET = """[Unit]
Description=Hermes Agent
After=network-online.target
Wants=network-online.target

[Container]
Image=docker.io/nousresearch/hermes-agent:v2026.8.3
ContainerName=hermes
UserNS=keep-id
Exec=gateway run

# Loopback so this machine can reach it; add a second pair on a LAN or
# Tailscale address if you want it from other devices.
PublishPort=127.0.0.1:8642:8642
PublishPort=127.0.0.1:9119:9119

Volume=%h/.hermes:/opt/data

Environment=API_SERVER_ENABLED=true
Environment=API_SERVER_KEY=<your-own-generated-key>
Environment=HERMES_DASHBOARD=1

[Service]
Restart=always
TimeoutStartSec=900

[Install]
WantedBy=default.target"""

COMFY_LAUNCH = """#!/bin/bash
cd ~/ComfyUI
source venv/bin/activate
unset HSA_OVERRIDE_GFX_VERSION
export HIP_VISIBLE_DEVICES=0
export HSA_ENABLE_SDMA=0
export HSA_USE_SVM=0
export PYTORCH_ALLOC_CONF="expandable_segments:True,garbage_collection_threshold:0.8,max_split_size_mb:512"
python3 main.py"""

STARTER_PROMPT = """I'm on Bazzite (an immutable Fedora Atomic distro, KDE, /usr is read-only).
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

Explain each step as you go, and after each service confirm it's on the GPU."""

GUIDE = {
    "title": "Getting Started",
    "subtitle": "Bazzite + AMD Strix Halo — a proven, from-scratch setup",
    "intro": [
        {"type": "p", "text": "This guide is proven on one specific setup, from a machine with nothing installed to a full working stack. It targets:"},
        {"type": "p", "text": "• Bazzite — or a similar immutable Fedora Atomic distro (/usr is read-only)\n• An AMD Ryzen AI MAX+ 395 “Strix Halo” with the Radeon 8060S iGPU (gfx1151)"},
        {"type": "warn", "text": "If you're on different hardware or a different distro, this guide won't directly apply. The read-only-filesystem workarounds, the iGPU flags, and the gfx1151 ROCm build are all specific to this configuration — the shape may still help, but the exact commands are for this machine."},
        {"type": "p", "text": "Pick a track below. If you have an AI assistant, start with Track 1 — it's far faster. Otherwise Track 2 is the complete manual walkthrough."},
    ],
    "tracks": [
        {
            "id": "assistant",
            "label": "1 · With an AI assistant",
            "blocks": [
                {"type": "p", "text": "The fastest path is to hand your assistant the hardware and distro context up front. A generic assistant won't know this hardware's quirks unless you tell it directly — the immutable filesystem that blocks the standard installer, the iGPU that's ignored by default, and the ROCm driver gap on this exact chip. Give it all of that at once so it can walk you through, instead of you discovering each issue the hard way, one at a time."},
                {"type": "h", "text": "Ready-to-paste starter prompt"},
                {"type": "code", "lang": "text", "code": STARTER_PROMPT},
                {"type": "note", "text": "If your assistant gets stuck, point it at this guide (docs/GETTING_STARTED.md in this repo) for the verified specifics — the exact unit files, env vars, and the gfx1151 nightly index are all here."},
            ],
        },
        {
            "id": "manual",
            "label": "2 · Manual setup",
            "sections": [
                {
                    "id": "ollama",
                    "title": "Ollama",
                    "blocks": [
                        {"type": "p", "text": "Install the binary. This part works — it lands in /usr/local/bin, which is writable on Bazzite:"},
                        {"type": "code", "lang": "bash", "code": "curl -fsSL https://ollama.com/install.sh | sh"},
                        {"type": "h", "text": "Why the installer's service silently fails here"},
                        {"type": "p", "text": "The installer's service step runs `useradd -m -d /usr/share/ollama ollama` — but /usr/share is read-only on Bazzite, so that home directory is never created. You can confirm it: the user exists, yet its home doesn't."},
                        {"type": "code", "lang": "bash", "code": "getent passwd ollama\n# -> ollama:x:992:962::/usr/share/ollama:/bin/false   (user exists)\nls -ld /usr/share/ollama\n# -> No such file or directory                          (home never created)"},
                        {"type": "p", "text": "So the generated service runs as the `ollama` user with a home that doesn't exist on a read-only path — it can't store models, and it never sets the iGPU flags. It looks installed but doesn't work. Disable it:"},
                        {"type": "code", "lang": "bash", "code": "sudo systemctl disable --now ollama"},
                        {"type": "h", "text": "Create a user service that actually works"},
                        {"type": "p", "text": "Run Ollama as your own user (models go in ~/.ollama) with the iGPU flags:"},
                        {"type": "code", "lang": "bash", "code": "mkdir -p ~/.config/systemd/user\ncat > ~/.config/systemd/user/ollama.service <<'EOF'\n" + OLLAMA_UNIT + "\nEOF"},
                        {"type": "p", "text": "What the two GPU env vars do — without either, Ollama silently runs on the CPU:\n• OLLAMA_IGPU_ENABLE=1 — enables the integrated GPU, which Ollama ignores by default.\n• OLLAMA_VULKAN=1 — routes compute through Vulkan, the working path for this iGPU.\n(OLLAMA_HOST=0.0.0.0:11434 lets the Open WebUI container reach Ollama.)"},
                        {"type": "h", "text": "Enable, start, and keep it running after logout"},
                        {"type": "code", "lang": "bash", "code": "systemctl --user daemon-reload\nsystemctl --user enable --now ollama\nsudo loginctl enable-linger \"$USER\""},
                        {"type": "h", "text": "Verify it's on the GPU (not CPU)"},
                        {"type": "code", "lang": "bash", "code": "curl 127.0.0.1:11434          # -> \"Ollama is running\"\nollama pull llama3.2:1b\nollama run llama3.2:1b \"hi\"\nollama ps                    # PROCESSOR column should show a GPU %, not \"100% CPU\""},
                    ],
                },
                {
                    "id": "openwebui",
                    "title": "Open WebUI",
                    "blocks": [
                        {"type": "p", "text": "Run Open WebUI as a Podman Quadlet — a container managed by systemd — rather than a container you start by hand, so it starts on boot and restarts cleanly."},
                        {"type": "code", "lang": "bash", "code": "mkdir -p ~/.config/containers/systemd\ncat > ~/.config/containers/systemd/open-webui.container <<'EOF'\n" + OPENWEBUI_QUADLET + "\nEOF\n\nsystemctl --user daemon-reload\nsystemctl --user start open-webui"},
                        {"type": "p", "text": "Then open http://127.0.0.1:3000 (use 127.0.0.1, not localhost — some browsers mishandle localhost for local servers)."},
                        {"type": "warn", "text": "Failure point 1 — the Volume line. `Volume=open-webui:/app/backend/data` is a plain named volume that Podman creates automatically. Do NOT write `Volume=open-webui.volume:/...` — the `.volume` suffix makes Quadlet look for a separate open-webui.volume file, and when it isn't there the service never generates. `systemctl --user status open-webui` then shows a confusing “not found” for a unit that was never created."},
                        {"type": "warn", "text": "Failure point 2 — the first image pull. The first start pulls a multi-hundred-MB image. Without TimeoutStartSec=600, systemd's default ~90s start timeout fires and kills it mid-pull, leaving the unit failed for no obvious reason. Keep TimeoutStartSec=600, and it helps to pull the image once by hand first: `podman pull ghcr.io/open-webui/open-webui:main`."},
                        {"type": "note", "text": "Also make sure the first line is exactly `[Unit]`. A stray `Unit]` with the bracket missing silently voids the section."},
                    ],
                },
                {
                    "id": "comfyui",
                    "title": "ComfyUI",
                    "blocks": [
                        {"type": "p", "text": "Clone ComfyUI and make a virtualenv:"},
                        {"type": "code", "lang": "bash", "code": "git clone https://github.com/comfyanonymous/ComfyUI ~/ComfyUI\ncd ~/ComfyUI\npython3 -m venv venv"},
                        {"type": "h", "text": "The ROCm segfault on this chip — and the fix"},
                        {"type": "p", "text": "If you install the standard ROCm PyTorch (download.pytorch.org/whl/rocm6.3), ComfyUI crashes on gfx1151 the moment it touches the GPU. The crash is a segmentation fault inside libamdhip64.so (around memcpy_and_sync) — you'll see something like this and it will exit:"},
                        {"type": "code", "lang": "text", "code": "Segmentation fault (core dumped)\n# backtrace mentions libamdhip64.so ... memcpy_and_sync"},
                        {"type": "p", "text": "That's not something you did wrong — it's a known driver gap on this chip. The fix is to install PyTorch from the gfx1151-specific ROCm nightly:"},
                        {"type": "code", "lang": "bash", "code": "venv/bin/pip install --index-url https://rocm.nightlies.amd.com/v2/gfx1151/ \\\n  torch torchaudio torchvision"},
                        {"type": "p", "text": "Then ComfyUI's own dependencies. Its requirements.txt lists torch unpinned, so installing it after the nightly leaves your gfx1151 build in place:"},
                        {"type": "code", "lang": "bash", "code": "venv/bin/pip install -r requirements.txt"},
                        {"type": "h", "text": "The ComfyUI-GGUF custom node (required)"},
                        {"type": "p", "text": "GGUF is a quantized model format; ComfyUI can't load .gguf files without this node's loaders. The main diffusion model below is GGUF, so this is required, not optional:"},
                        {"type": "code", "lang": "bash", "code": "git clone https://github.com/city96/ComfyUI-GGUF custom_nodes/ComfyUI-GGUF\nvenv/bin/pip install -r custom_nodes/ComfyUI-GGUF/requirements.txt"},
                        {"type": "h", "text": "The three model files (real sizes, exact places)"},
                        {"type": "code", "lang": "bash", "code": "# Diffusion model (GGUF) — 20.3 GB  ->  models/diffusion_models/\nwget -P models/diffusion_models \\\n  https://huggingface.co/city96/Qwen-Image-gguf/resolve/main/qwen-image-Q8_0.gguf\n\n# Text encoder — 8.7 GB  ->  models/text_encoders/\nwget -P models/text_encoders \\\n  https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/resolve/main/split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors\n\n# VAE — 242 MB  ->  models/vae/\nwget -P models/vae \\\n  https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/resolve/main/split_files/vae/qwen_image_vae.safetensors"},
                        {"type": "h", "text": "The launch script"},
                        {"type": "p", "text": "Create the launch wrapper. The environment it sets is not optional — running `python3 main.py` directly (without this env) brings the crash / CPU fallback right back:"},
                        {"type": "code", "lang": "bash", "code": "cat > ~/ComfyUI/start_comfyui_rocm.sh <<'EOF'\n" + COMFY_LAUNCH + "\nEOF\nchmod +x ~/ComfyUI/start_comfyui_rocm.sh\n\n~/ComfyUI/start_comfyui_rocm.sh"},
                        {"type": "p", "text": "Why each line matters:\n• unset HSA_OVERRIDE_GFX_VERSION — a globally-set gfx override (a common tweak) makes the nightly target the wrong arch and breaks; clear it.\n• HSA_ENABLE_SDMA=0 — disables the SDMA path that triggers the crash on Strix Halo. This is the actual mitigation.\n• HIP_VISIBLE_DEVICES=0 — selects the iGPU.\n• HSA_USE_SVM=0 and PYTORCH_ALLOC_CONF=… — memory settings tuned for this shared-memory APU."},
                        {"type": "p", "text": "Open http://127.0.0.1:8188. In the startup log you should see `Device: cuda:0 Radeon 8060S Graphics` and `AMD arch: gfx1151` — that's the iGPU in use."},
                        {"type": "note", "text": "Local AI Hub can run ComfyUI as a systemd user service that sets exactly this same environment, so you don't have to launch the script by hand."},
                    ],
                },
                {
                    "id": "layers",
                    "title": "Agent layers (optional)",
                    "blocks": [
                        {"type": "p", "text": "Everything above is the base stack: Ollama is the engine that runs models, Open WebUI is an interface onto it, ComfyUI is its own image-generation world. An agent harness is a different kind of thing — it doesn't run a model, it drives one that Ollama is already running, which means it's dead in the water whenever Ollama is stopped."},
                        {"type": "p", "text": "Local AI Hub shows harnesses in their own section below the services, with the dependency stated on the card, so the difference is visible rather than something you have to remember. Hermes Agent is the one it knows about today."},
                        {"type": "h", "text": "Hermes Agent as a rootless quadlet"},
                        {"type": "p", "text": "Hermes runs as a container. As a Podman quadlet it becomes an ordinary systemd --user unit, which is what lets the app start and stop it the same way as everything else:"},
                        {"type": "code", "lang": "ini", "code": HERMES_QUADLET},
                        {"type": "code", "lang": "bash", "code": "systemctl --user daemon-reload\nsystemctl --user start hermes"},
                        {"type": "h", "text": "Pin the image"},
                        {"type": "p", "text": "A `:latest` tag with `AutoUpdate=registry` means the version you're running can change on a restart, without you asking. Pin a real version tag instead and move it deliberately when you want to."},
                        {"type": "h", "text": "Publish on 127.0.0.1 as well as any remote address"},
                        {"type": "p", "text": "If Hermes is only published on a remote address (a Tailscale IP, say), nothing answers on loopback and the app's Open button has nowhere local to go. Publishing both keeps remote access working and gives the local machine a loopback route."},
                        {"type": "warn", "text": "Hermes asks for a sign-in whenever a `dashboard.basic_auth` block is set in its config.yaml — including on loopback. That's a config choice, not a bind rule: keeping it means the Open button lands on a login page, and removing it would drop authentication for remote access too. The app tells you which of the two you're in rather than guessing."},
                        {"type": "note", "text": "Hermes keeps the model and context it's pointed at inside its own container volume, which is readable only by the container's user. The app reads it through podman, so that one detail is unavailable in the sandboxed Flatpak build — it says so in place instead of showing a blank."},
                    ],
                },
                {
                    "id": "apps",
                    "title": "Your other self-hosted services",
                    "blocks": [
                        {"type": "p", "text": "Below the AI stack, Local AI Hub lists whatever else you self-host, under \"Self-Hosted Apps & Services\". You don't configure this and there's no list of supported apps — it asks Podman what's actually running."},
                        {"type": "h", "text": "What shows up, and what doesn't"},
                        {"type": "p", "text": "A container appears when two things are true: Podman Quadlet generated it (which is what gives it a systemd unit the app can start and stop), and it publishes at least one port. That second rule is why a toolbox or a container you started by hand with `podman run` stays out — there's nothing to open and nothing to check for life."},
                        {"type": "p", "text": "A pod shows as one entry, not one per container. Immich is five containers behind a single port; five cards for one app would be noise."},
                        {"type": "note", "text": "Recognised services get a proper name and category. Anything the app doesn't recognise is shown by its container name and port rather than guessed at — honest and usually what you called it anyway."},
                        {"type": "h", "text": "Running status means running, not \"exists\""},
                        {"type": "p", "text": "The status dot comes from an actual request to the address the port is published on, the same treatment the AI services get. A container can be up while the thing inside it is broken, and the app will say so rather than show a green light."},
                    ],
                },
                {
                    "id": "addresses",
                    "title": "Which address works from where",
                    "blocks": [
                        {"type": "p", "text": "127.0.0.1 means \"this computer\". It's the right address for the Open button and completely useless typed into your phone — which is the single most common confusion with self-hosted services."},
                        {"type": "p", "text": "Each service with a web interface has a globe button that folds out every address it's reachable at, with a sentence about where each one works:"},
                        {"type": "p", "text": "• 127.0.0.1 — only on this computer.\n• A 192.168.x.x / 10.x.x.x / 172.16-31.x.x address — other devices on the same network. Use this one on your phone at home.\n• A 100.x address or a MagicDNS name — your devices anywhere, over Tailscale. This one keeps working away from home."},
                        {"type": "p", "text": "The app detects these rather than asking you to configure anything, and shows only what genuinely exists. No LAN address detected means none is shown."},
                        {"type": "warn", "text": "A service reachable on your LAN is reachable by everything else on that network. That is what makes it useful from the sofa and what makes it worth thinking about on a network you don't control. Tailscale is the private option: only your own devices, wherever they are."},
                    ],
                },
                {
                    "id": "troubleshooting",
                    "title": "Troubleshooting",
                    "blocks": [
                        {"type": "p", "text": "The exact errors hit while building this the first time, so you can pattern-match instead of debugging blind."},
                        {"type": "h", "text": "Ollama looks installed but nothing works"},
                        {"type": "p", "text": "After the installer, the daemon seems present but models won't pull/persist. Check the default service's home:"},
                        {"type": "code", "lang": "bash", "code": "ls -ld /usr/share/ollama\n# -> No such file or directory"},
                        {"type": "p", "text": "The `ollama` user's home was never created on the read-only /usr. Fix: disable that service and use the user service (Ollama section above)."},
                        {"type": "h", "text": "Ollama runs on CPU"},
                        {"type": "p", "text": "`ollama ps` shows PROCESSOR as “100% CPU”. The iGPU env vars aren't set — add OLLAMA_IGPU_ENABLE=1 and OLLAMA_VULKAN=1 and restart."},
                        {"type": "h", "text": "Open WebUI: “not found”, unit won't start"},
                        {"type": "p", "text": "`systemctl --user status open-webui` reports the unit as not found / not generated. The Volume line points at a nonexistent `.volume` file. Use a plain named volume (`open-webui:/app/backend/data`)."},
                        {"type": "h", "text": "Open WebUI times out on first start"},
                        {"type": "p", "text": "The unit fails after ~90 seconds (a start-timeout / start-limit-hit). The first image pull exceeded systemd's default timeout. Set TimeoutStartSec=600 and/or `podman pull ghcr.io/open-webui/open-webui:main` first."},
                        {"type": "h", "text": "ComfyUI: Segmentation fault (core dumped)"},
                        {"type": "p", "text": "A segfault mentioning libamdhip64.so / memcpy_and_sync as soon as it uses the GPU = the standard ROCm build on gfx1151. Reinstall torch from the gfx1151 nightly index."},
                        {"type": "h", "text": "ComfyUI runs on CPU (very slow)"},
                        {"type": "p", "text": "The log doesn't say `AMD arch: gfx1151` / `Device: cuda:0`. Either you launched `main.py` directly instead of the script (so the env wasn't set), or torch has no ROCm. Use the launch script and confirm the log."},
                        {"type": "h", "text": "A GGUF model doesn't show up / won't load"},
                        {"type": "p", "text": "The ComfyUI-GGUF custom node isn't installed. Clone it into custom_nodes/ and restart ComfyUI."},
                    ],
                },
            ],
        },
    ],
}
