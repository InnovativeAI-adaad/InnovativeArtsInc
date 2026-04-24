from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pipelines.media_state_machine import MEDIA_STAGES
from services.media_conductor.service import (
    MediaConductor,
    MediaConductorError,
    MediaConductorPaths,
)


class MediaConductorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[1]
        self.schema_path = self.repo_root / "projects/jrt/metadata/schema/media_job.schema.json"

        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.jobs_dir = root / "projects/jrt/metadata/jobs"
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoints_dir = self.jobs_dir / "checkpoints"
        self.checkpoints_dir.mkdir(parents=True, exist_ok=True)
        self.paths = MediaConductorPaths(
            repo_root=root,
            jobs_dir=self.jobs_dir,
            schema_path=self.schema_path,
            checkpoints_dir=self.checkpoints_dir,
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    @staticmethod
    def _input_assets() -> list[dict[str, str]]:
        return [{"asset_type": "prompt", "asset_ref": "registry://prompt/pkg-1.json"}]

    @staticmethod
    def _output_assets() -> list[dict[str, str]]:
        return [{"asset_type": "audio", "asset_ref": "registry://audio/render-1.wav"}]

    @staticmethod
    def _provenance_refs() -> list[dict[str, str]]:
        return [{"ref_type": "decision", "ref": "registry://provenance/decision-1.json"}]

    def test_run_transitions_all_stages_and_emits_one_job_file(self) -> None:
        conductor = MediaConductor(paths=self.paths, actor="media-pipeline")

        checkpoint = conductor.run(
            job_id="job-123",
            track_id="track-abc",
            input_assets=self._input_assets(),
            output_assets=self._output_assets(),
            provenance_refs=self._provenance_refs(),
            agent_owner="MediaAgent",
        )

        self.assertEqual(checkpoint["media_job_record"]["current_stage"], MEDIA_STAGES[-1])
        self.assertIsNotNone(checkpoint["emitted_media_job_file"])

        jobs = list(self.jobs_dir.glob("*.json"))
        self.assertEqual(len(jobs), 1)

        emitted = json.loads(jobs[0].read_text(encoding="utf-8"))
        self.assertEqual(emitted["job_id"], "job-123")
        self.assertEqual(emitted["status"], "succeeded")

    def test_resume_from_checkpoint_after_crash(self) -> None:
        fail_once = {"armed": True}

        def crashing_handler(_: dict) -> dict:
            if fail_once["armed"]:
                fail_once["armed"] = False
                raise RuntimeError("simulated crash")
            return {"quality_gate": "pass"}

        conductor = MediaConductor(
            paths=self.paths,
            actor="media-pipeline",
            handlers={"quality_validation": crashing_handler},
        )

        with self.assertRaises(RuntimeError):
            conductor.run(
                job_id="job-resume",
                track_id="track-abc",
                input_assets=self._input_assets(),
                output_assets=self._output_assets(),
                provenance_refs=self._provenance_refs(),
                agent_owner="MediaAgent",
            )

        checkpoint_path = self.checkpoints_dir / "job-resume.checkpoint.json"
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        self.assertNotEqual(checkpoint["media_job_record"]["current_stage"], MEDIA_STAGES[-1])

        recovered = conductor.run(
            job_id="job-resume",
            track_id="track-abc",
            input_assets=self._input_assets(),
            output_assets=self._output_assets(),
            provenance_refs=self._provenance_refs(),
            agent_owner="MediaAgent",
        )
        self.assertEqual(recovered["media_job_record"]["current_stage"], MEDIA_STAGES[-1])

    def test_invalid_media_job_is_rejected_by_schema_gate(self) -> None:
        conductor = MediaConductor(paths=self.paths, actor="media-pipeline")

        with self.assertRaises(MediaConductorError):
            conductor.run(
                job_id="job-invalid",
                track_id="track-abc",
                input_assets=[],
                output_assets=self._output_assets(),
                provenance_refs=self._provenance_refs(),
                agent_owner="MediaAgent",
            )


if __name__ == "__main__":
    unittest.main()
