"""Registry of layers that run on top of the base services.

Adding another harness means writing a Layer subclass and appending it here;
nothing in app.py or the front-end is keyed to Hermes specifically.
"""
from .base import Layer
from .hermes import HermesLayer

LAYER_CLASSES = [HermesLayer]


def build_layers() -> dict:
    """key -> Layer instance, in display order."""
    return {cls.key: cls() for cls in LAYER_CLASSES}


__all__ = ["Layer", "HermesLayer", "LAYER_CLASSES", "build_layers"]
