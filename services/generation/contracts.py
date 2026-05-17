from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SceneGenerationContract:
    replay_key: str
    seed: int | str
    job_id: str
    prompt: str
    style_profile: str | dict[str, Any]
    duration: int
    tempo: int | None = None
    key: str | None = None

    def core_fields(self) -> dict[str, Any]:
        return {
            "replay_key": self.replay_key,
            "seed": self.seed,
            "job_id": self.job_id,
            "prompt": self.prompt,
            "style_profile": self.style_profile,
            "duration": self.duration,
            "tempo": self.tempo,
            "key": self.key,
        }

    @property
    def scene_hash(self) -> str:
        canonical = json.dumps(self.core_fields(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def as_payload(self) -> dict[str, Any]:
        payload = self.core_fields().copy()
        payload["scene_hash"] = self.scene_hash
        return payload
