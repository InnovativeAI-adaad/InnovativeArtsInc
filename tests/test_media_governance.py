from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from services.media_conductor.governance import MediaGovernanceError, authorize_media_stage


class MediaGovernanceTests(unittest.TestCase):
    def test_level_three_public_release_blocks_and_writes_decision_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)

            with self.assertRaises(MediaGovernanceError):
                authorize_media_stage(
                    repo_root=root,
                    job_id="job-public-release",
                    stage="public_release",
                    actor="media-pipeline",
                )

            decision_files = list(
                (root / "projects/jrt/metadata/governance_decisions").glob("govdec-*.json")
            )
            self.assertEqual(len(decision_files), 1)
            artifact = json.loads(decision_files[0].read_text(encoding="utf-8"))
            self.assertEqual(artifact["decision"], "blocked")
            self.assertEqual(artifact["action_id"], "publish_release")
            self.assertTrue(artifact["requires_human_ratification"])
            self.assertTrue(
                any("ratification validation failed" in error for error in artifact["errors"])
            )
            self.assertTrue(
                any("authorization validation failed" in error for error in artifact["errors"])
            )

    def test_provider_backed_generation_allows_with_hash_linked_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)

            decision = authorize_media_stage(
                repo_root=root,
                job_id="job-generation",
                stage="audio_generated",
                actor="media-pipeline",
            )

            self.assertEqual(decision.decision, "allowed")
            artifact = json.loads(decision.artifact_path.read_text(encoding="utf-8"))
            self.assertEqual(artifact["action_id"], "generate_music")
            self.assertTrue(artifact["elevated_action"])
            self.assertEqual(artifact["artifact_sha256"], decision.artifact_sha256)


if __name__ == "__main__":
    unittest.main()
