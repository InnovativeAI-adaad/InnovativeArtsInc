from __future__ import annotations

import hashlib
import json
from typing import Any

from services.generation import SceneGenerationContract


def _seed_from_scene_hash(scene_hash: str, salt: str) -> int:
    digest = hashlib.sha256(f"{scene_hash}:{salt}".encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def generate_visual_params(contract: SceneGenerationContract) -> dict[str, Any]:
    palette_seed = _seed_from_scene_hash(contract.scene_hash, "palette")
    camera_motion_seed = _seed_from_scene_hash(contract.scene_hash, "camera_motion")
    cut_timing_seed = _seed_from_scene_hash(contract.scene_hash, "cut_timing")

    request_payload = {
        "scene_hash": contract.scene_hash,
        "palette_seed": palette_seed,
        "camera_motion_seed": camera_motion_seed,
        "cut_timing_seed": cut_timing_seed,
    }
    request_payload_hash = hashlib.sha256(
        json.dumps(request_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    return {
        "visual_request": request_payload,
        "visual_request_payload_hash": request_payload_hash,
    }
