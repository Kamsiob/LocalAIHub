"""Service control modules for local-ai-hub."""
from .base import Service, ServiceStatus
from .ollama import OllamaService, ModelInfo
from .openwebui import OpenWebUIService

# Registry grows as each service module lands (comfyui next).
SERVICES = {
    "ollama": OllamaService,
    "openwebui": OpenWebUIService,
}

__all__ = [
    "Service",
    "ServiceStatus",
    "OllamaService",
    "ModelInfo",
    "OpenWebUIService",
    "SERVICES",
]
