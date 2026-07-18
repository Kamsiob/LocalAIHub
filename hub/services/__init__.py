"""Service control modules for local-ai-hub."""
from .base import Service, ServiceStatus
from .ollama import OllamaService, ModelInfo
from .openwebui import OpenWebUIService
from .comfyui import ComfyUIService

SERVICES = {
    "ollama": OllamaService,
    "openwebui": OpenWebUIService,
    "comfyui": ComfyUIService,
}

__all__ = [
    "Service",
    "ServiceStatus",
    "OllamaService",
    "ModelInfo",
    "OpenWebUIService",
    "ComfyUIService",
    "SERVICES",
]
