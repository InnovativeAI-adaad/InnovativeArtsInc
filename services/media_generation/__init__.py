"""Media generation services for WF-005 orchestration."""

from services.generation import SceneGenerationContract

from .adapters import (
    MediaGenerationAdapter,
    ProviderGenerationResult,
    ReplicateAudioAdapter,
    StubGenAudioAdapter,
    SunoAdapter,
)
from .audio_analysis import AudioMetrics, analyze_audio_file, analyze_pcm_wav, write_analysis_artifact
from .autonomous_run import run_autonomous_generation_lifecycle
from .ip_lifecycle import (
    IPGuardrailBlockedError,
    audio_fingerprint_for_path,
    decision_provenance_ref,
    run_post_generation_similarity_audit,
    run_pre_generation_uniqueness_gate,
)
from .service import generate_music_for_wf005

__all__ = [
    "AudioMetrics",
    "IPGuardrailBlockedError",
    "MediaGenerationAdapter",
    "ProviderGenerationResult",
    "ReplicateAudioAdapter",
    "SceneGenerationContract",
    "StubGenAudioAdapter",
    "SunoAdapter",
    "analyze_audio_file",
    "analyze_pcm_wav",
    "audio_fingerprint_for_path",
    "decision_provenance_ref",
    "generate_music_for_wf005",
    "run_autonomous_generation_lifecycle",
    "run_post_generation_similarity_audit",
    "run_pre_generation_uniqueness_gate",
    "write_analysis_artifact",
]
