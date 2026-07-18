# local-ai-hub

A personal hub for seeing local AI models you have downloaded using Ollama. Also take Open Web UI into account + Comfy for image generation models. Built initially for Bazzite (desktop) using the AMD Max+ 395, 64gb chip. Trying to make it so it works with others.

## Requirements

- Python 3.10+
- [git](https://git-scm.com/)

## Setup

```bash
# Clone
git clone https://github.com/Kamsiob/local-ai-hub.git
cd local-ai-hub

# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

# Install dependencies (once a requirements file exists)
pip install -r requirements.txt
```

## Project layout

```
local-ai-hub/
├── README.md
├── .gitignore
└── .claude/            # Claude Code config (settings.local.json is gitignored)
```

## License

No license specified yet — all rights reserved by default.
