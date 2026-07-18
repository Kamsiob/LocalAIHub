"""Tiny local preference store — no telemetry, no network, just a JSON file.

Lives at $XDG_CONFIG_HOME/local-ai-hub/config.json (usually ~/.config/...).
Used to persist the light/dark preference between launches.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "local-ai-hub"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULTS: dict = {"theme": None}


def load() -> dict:
    try:
        data = json.loads(CONFIG_FILE.read_text())
        if isinstance(data, dict):
            return {**DEFAULTS, **data}
    except Exception:
        pass
    return dict(DEFAULTS)


def save(patch: dict) -> dict:
    current = load()
    current.update(patch)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(current, indent=2))
    return current


def get(key: str, default=None):
    return load().get(key, default)


def set_(key: str, value) -> dict:
    return save({key: value})
