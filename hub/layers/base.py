"""Layers: things that run *on top of* a base engine.

The dashboard's original three entries are peers — Ollama runs models, Open WebUI
talks to it, ComfyUI is its own world. An agent harness is not a peer. Hermes
does not run a model; it drives one that Ollama is running, and it is useless the
moment Ollama stops. Showing it as a fourth card alongside the others would state
the opposite of what is true.

So a Layer is a Service with two additions: the key of the service it sits on
(`depends_on`), and a slot for whatever layer-specific state it can report
(`layer_info`). Everything else — start, stop, status, presence, the D-Bus path
that keeps it working under Flatpak — is inherited unchanged, which is the point:
adding a second harness later means writing a subclass, not a second system.

`layer_info` returns free-form dict per layer, plus one shared convention: an
`unavailable` list of {what, why, options} for anything the layer genuinely
cannot report from where the app is running. The UI renders those as plain
statements of the limit rather than blank fields or invented values.
"""
from __future__ import annotations

from ..services.base import Service


class Layer(Service):
    """A harness or framework running on top of one of the base services."""

    # Overridden by subclasses; `key` is what the front-end addresses it by.
    key: str = ""
    depends_on: str = ""
    tagline: str = ""

    def layer_info(self) -> dict:
        """Layer-specific state: model, endpoints, sub-process health, limits."""
        return {}

    def to_dict(self) -> dict:
        """The shape the front-end consumes for one layer."""
        st = self.status()
        return {
            "key": self.key,
            "name": self.display_name,
            "tagline": self.tagline,
            "depends_on": self.depends_on,
            "active": st.active,
            "serving": st.serving,
            "failed": st.failed,
            "present": st.present,
            "info": self.layer_info(),
        }
