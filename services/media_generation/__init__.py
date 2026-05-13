"""Media generation services for WF-005 orchestration."""

from .adapters import (
    MediaGenerationAdapter,
    ProviderGenerationResult,
    ReplicateAudioAdapter,
    StubGenAudioAdapter,
    SunoAdapter,
    UdioAdapter,
    build_media_generation_adapter,
    build_media_generation_adapter_from_scheduler,
)
from .service import ReplayContract, generate_music_for_wf005

__all__ = [
    "MediaGenerationAdapter",
    "ProviderGenerationResult",
    "ReplayContract",
    "ReplicateAudioAdapter",
    "StubGenAudioAdapter",
    "SunoAdapter",
    "UdioAdapter",
    "build_media_generation_adapter",
    "build_media_generation_adapter_from_scheduler",
    "generate_music_for_wf005",
]
