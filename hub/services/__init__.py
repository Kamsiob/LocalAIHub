"""Service control modules for local-ai-hub."""
from .base import Service, ServiceStatus
from .ollama import OllamaService, ModelInfo

# Registry grows as each service module lands (openwebui, comfyui).
SERVICES = {
    "ollama": OllamaService,
}

__all__ = [
    "Service",
    "ServiceStatus",
    "OllamaService",
    "ModelInfo",
    "SERVICES",
]
