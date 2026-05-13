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
from services.release_pipeline.service import build_release_bundle


class MediaConductorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[1]
        self.schema_path = (
            self.repo_root / "projects/jrt/metadata/schema/media_job.schema.json"
        )

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
        return [
            {"ref_type": "decision", "ref": "registry://provenance/decision-1.json"}
        ]

    def _stage_handlers(self, **overrides):
        handlers = {
            "strategy_lock": lambda _: {
                "model_preset": "studio-vocal-v2",
                "temperature": 0.72,
                "creativity_controls": {"profile": "balanced"},
                "proposed_prompt_hash": "sha256:prompt-pack-1",
                "style_fingerprint": "style:track-abc:v2",
                "seed_policy": "reject-seen-seeds-30d",
                "novelty_threshold": 0.74,
            },
            "generation": lambda _: {
                "generated_audio_path": "renders/track-abc.wav",
                "provider_generation_id": "provider-gen-123",
                "model_version": "audio-model-2026-05-01",
                "render_metadata_ref": "registry://renders/track-abc/metadata.json",
            },
            "uniqueness_audit": lambda _: {
                "similarity_decision_refs": [
                    "registry://audit/similarity/job-123-decision.json"
                ]
            },
            "quality_validation": lambda _: {
                "loudness_check_ref": "registry://quality/loudness/job-123.json",
                "clipping_check_ref": "registry://quality/clipping/job-123.json",
                "metadata_check_ref": "registry://quality/metadata/job-123.json",
                "vibe_check_ref": "registry://quality/vibe/job-123.json",
            },
            "rollout_package": lambda _: {
                "release_bundle_artifact_ref": "registry://releases/job-123-bundle.json",
                "release_bundle": build_release_bundle(
                    release_id="job-123",
                    title="Example Release",
                    artist_name="JRT",
                    masters=[
                        {"track_id": "track-abc", "path": "renders/track-abc.wav"}
                    ],
                    stems=[],
                    credits=[{"name": "JRT", "role": "artist"}],
                    rights_metadata={"copyright_owner": "InnovativeArtsInc"},
                ),
            },
        }
        handlers.update(overrides)
        return handlers

    def test_run_transitions_all_stages_and_emits_one_job_file(self) -> None:
        conductor = MediaConductor(
            paths=self.paths, actor="media-pipeline", handlers=self._stage_handlers()
        )

        checkpoint = conductor.run(
            job_id="job-123",
            track_id="track-abc",
            input_assets=self._input_assets(),
            output_assets=self._output_assets(),
            provenance_refs=self._provenance_refs(),
            agent_owner="MediaAgent",
        )

        self.assertEqual(
            checkpoint["media_job_record"]["current_stage"], MEDIA_STAGES[-1]
        )
        self.assertIsNotNone(checkpoint["emitted_media_job_file"])

        jobs = list(self.jobs_dir.glob("*.json"))
        self.assertEqual(len(jobs), 1)

        emitted = json.loads(jobs[0].read_text(encoding="utf-8"))
        self.assertEqual(emitted["job_id"], "job-123")
        self.assertEqual(emitted["status"], "succeeded")
        self.assertIn(
            {
                "ref_type": "release_bundle",
                "ref_id": "job-123-bundle",
                "uri": "projects/jrt/metadata/releases/job-123.release_bundle.json",
            },
            emitted["provenance_refs"],
        )

    def test_resume_from_checkpoint_after_crash(self) -> None:
        fail_once = {"armed": True}

        def crashing_handler(_: dict) -> dict:
            if fail_once["armed"]:
                fail_once["armed"] = False
                raise RuntimeError("simulated crash")
            return {
                "loudness_check_ref": "registry://quality/loudness/job-resume.json",
                "clipping_check_ref": "registry://quality/clipping/job-resume.json",
                "metadata_check_ref": "registry://quality/metadata/job-resume.json",
                "vibe_check_ref": "registry://quality/vibe/job-resume.json",
            }

        conductor = MediaConductor(
            paths=self.paths,
            actor="media-pipeline",
            handlers=self._stage_handlers(quality_validation=crashing_handler),
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
        self.assertNotEqual(
            checkpoint["media_job_record"]["current_stage"], MEDIA_STAGES[-1]
        )

        recovered = conductor.run(
            job_id="job-resume",
            track_id="track-abc",
            input_assets=self._input_assets(),
            output_assets=self._output_assets(),
            provenance_refs=self._provenance_refs(),
            agent_owner="MediaAgent",
        )
        self.assertEqual(
            recovered["media_job_record"]["current_stage"], MEDIA_STAGES[-1]
        )

    def test_invalid_media_job_is_rejected_by_schema_gate(self) -> None:
        conductor = MediaConductor(
            paths=self.paths, actor="media-pipeline", handlers=self._stage_handlers()
        )

        with self.assertRaises(MediaConductorError):
            conductor.run(
                job_id="job-invalid",
                track_id="track-abc",
                input_assets=[],
                output_assets=self._output_assets(),
                provenance_refs=self._provenance_refs(),
                agent_owner="MediaAgent",
            )

    def test_production_mode_requires_concrete_handler_payloads(self) -> None:
        conductor = MediaConductor(paths=self.paths, actor="media-pipeline")

        with self.assertRaisesRegex(MediaConductorError, "strategy_lock"):
            conductor.run(
                job_id="job-missing-handler",
                track_id="track-abc",
                input_assets=self._input_assets(),
                output_assets=self._output_assets(),
                provenance_refs=self._provenance_refs(),
                agent_owner="MediaAgent",
            )

    def test_handler_payload_fields_are_recorded_on_stage_transitions(self) -> None:
        conductor = MediaConductor(
            paths=self.paths, actor="media-pipeline", handlers=self._stage_handlers()
        )

        checkpoint = conductor.run(
            job_id="job-artifacts",
            track_id="track-abc",
            input_assets=self._input_assets(),
            output_assets=self._output_assets(),
            provenance_refs=self._provenance_refs(),
            agent_owner="MediaAgent",
        )

        events = {
            event["to_stage"]: event
            for event in checkpoint["media_job_record"]["transition_log"]
        }
        self.assertEqual(
            events["audio_generated"]["runtime_payload"]["provider_generation_id"],
            "provider-gen-123",
        )
        self.assertEqual(
            events["audio_verified"]["runtime_payload"]["similarity_decision_refs"],
            ["registry://audit/similarity/job-123-decision.json"],
        )
        self.assertEqual(
            events["rollout_packaged"]["runtime_payload"][
                "release_bundle_artifact_ref"
            ],
            "registry://releases/job-123-bundle.json",
        )


class MediaConductorGovernanceTests(unittest.TestCase):
    def setUp(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        schema_path = repo_root / "projects/jrt/metadata/schema/media_job.schema.json"

        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.jobs_dir = root / "projects/jrt/metadata/jobs"
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.paths = MediaConductorPaths(
            repo_root=root,
            jobs_dir=self.jobs_dir,
            schema_path=schema_path,
            checkpoints_dir=self.jobs_dir / "checkpoints",
        )
        self.paths.checkpoints_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_governance_decisions_are_emitted_and_added_to_provenance(self) -> None:
        conductor = MediaConductor(paths=self.paths, actor="media-pipeline")

        checkpoint = conductor.run(
            job_id="job-governance",
            track_id="track-abc",
            input_assets=MediaConductorTests._input_assets(),
            output_assets=MediaConductorTests._output_assets(),
            provenance_refs=MediaConductorTests._provenance_refs(),
            agent_owner="MediaAgent",
        )

        refs = checkpoint["governance_decision_refs"]
        self.assertEqual(len(refs), len(MEDIA_STAGES) - 1)
        self.assertTrue(all(ref["ref_type"] == "governance_decision" for ref in refs))

        decision_files = list(
            (self.paths.repo_root / "projects/jrt/metadata/governance_decisions").glob(
                "govdec-*.json"
            )
        )
        self.assertEqual(len(decision_files), len(MEDIA_STAGES) - 1)
        first = json.loads(decision_files[0].read_text(encoding="utf-8"))
        self.assertEqual(first["decision"], "allowed")
        self.assertIn("artifact_sha256", first)

        jobs = list(self.jobs_dir.glob("*.json"))
        emitted = json.loads(jobs[0].read_text(encoding="utf-8"))
        emitted_governance_refs = [
            ref for ref in emitted["provenance_refs"] if ref["ref_type"] == "governance_decision"
        ]
        self.assertEqual(len(emitted_governance_refs), len(MEDIA_STAGES) - 1)


if __name__ == "__main__":
    unittest.main()
