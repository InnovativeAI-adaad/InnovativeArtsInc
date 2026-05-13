"""Media generation services for WF-005 orchestration."""

from .adapters import MediaGenerationAdapter, ProviderGenerationResult, StubGenAudioAdapter
from .audio_analysis import AudioMetrics, analyze_audio_file, analyze_pcm_wav, write_analysis_artifact
from .service import ReplayContract, generate_music_for_wf005

__all__ = [
    "AudioMetrics",
    "MediaGenerationAdapter",
    "ProviderGenerationResult",
    "ReplayContract",
    "StubGenAudioAdapter",
    "analyze_audio_file",
    "analyze_pcm_wav",
    "generate_music_for_wf005",
    "write_analysis_artifact",
]
