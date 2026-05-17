"""Media generation services for WF-005 orchestration."""

from .adapters import MediaGenerationAdapter, ProviderGenerationResult, ReplicateAudioAdapter, StubGenAudioAdapter, SunoAdapter, UdioAdapter
from .audio_analysis import AudioMetrics, analyze_audio_file, analyze_pcm_wav, write_analysis_artifact
from .autonomous_run import run_autonomous_generation_lifecycle
from .ip_lifecycle import (
    IPGuardrailBlockedError,
    audio_fingerprint_for_path,
    decision_provenance_ref,
    run_post_generation_similarity_audit,
    run_pre_generation_uniqueness_gate,
)
from .service import GenerationMode, ReplayContract, generate_music_for_wf005, promote_preview_to_full_render

__all__ = [
    "AudioMetrics",
    "IPGuardrailBlockedError",
    "MediaGenerationAdapter",
    "ProviderGenerationResult",
    "GenerationMode",
    "ReplayContract",
    "ReplicateAudioAdapter",
    "SunoAdapter",
    "UdioAdapter",
    "StubGenAudioAdapter",
    "SunoAdapter",
    "analyze_audio_file",
    "analyze_pcm_wav",
    "generate_music_for_wf005",
    "promote_preview_to_full_render",
    "write_analysis_artifact",
    "run_autonomous_generation_lifecycle",
    "IPGuardrailBlockedError",
    "audio_fingerprint_for_path",
    "decision_provenance_ref",
    "generate_music_for_wf005",
    "promote_preview_to_full_render",
    "run_post_generation_similarity_audit",
    "run_pre_generation_uniqueness_gate",
    "write_analysis_artifact",
]
