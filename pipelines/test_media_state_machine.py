from __future__ import annotations

import unittest

from pipelines.media_state_machine import (
    MEDIA_STAGES,
    TransitionValidationError,
    initialize_media_job_record,
    transition_media_job,
)


class MediaStateMachineTests(unittest.TestCase):
    @staticmethod
    def _strategized_payload() -> dict:
        return {
            "model_preset": "v4-quality",
            "temperature": 0.65,
            "creativity_controls": {"style_push": 0.4},
            "seed_policy": "deterministic",
            "novelty_threshold": 0.7,
        }

    @staticmethod
    def _lock_payload() -> dict:
        return {
            "proposed_prompt_hash": "sha256:abc123",
            "style_fingerprint": "style:v1:electro-pop:bright",
            "anti_dup_seed_policy": "reject-seen-seeds-30d",
            "novelty_threshold": 0.7,
        }

    def test_happy_path_transitions_and_log_fields(self) -> None:
        record = initialize_media_job_record("job-1", "author")

        for stage in MEDIA_STAGES[1:]:
            runtime_payload = None
            if stage == "generation_strategized":
                runtime_payload = self._strategized_payload()
            if stage == "generation_strategy_locked":
                runtime_payload = self._lock_payload()
            record = transition_media_job(record, stage, "worker", runtime_payload=runtime_payload)

        self.assertEqual(record["current_stage"], MEDIA_STAGES[-1])
        self.assertEqual(len(record["transition_log"]), len(MEDIA_STAGES))
        last_event = record["transition_log"][-1]
        self.assertEqual(last_event["status"], MEDIA_STAGES[-1])
        self.assertIn("timestamp", last_event)
        self.assertEqual(last_event["actor"], "worker")

    def test_generation_strategized_to_generation_strategy_locked_succeeds(self) -> None:
        record = initialize_media_job_record("job-2", "author")
        record = transition_media_job(record, "refined_lyrics", "worker")
        record = transition_media_job(record, "prompt_packaged", "worker")

        record = transition_media_job(
            record,
            "generation_strategized",
            "worker",
            runtime_payload=self._strategized_payload(),
        )
        record = transition_media_job(
            record,
            "generation_strategy_locked",
            "worker",
            runtime_payload=self._lock_payload(),
        )

        self.assertEqual(record["current_stage"], "generation_strategy_locked")

    def test_prompt_packaged_direct_to_audio_generated_is_rejected(self) -> None:
        record = initialize_media_job_record("job-3", "author")
        record = transition_media_job(record, "refined_lyrics", "worker")
        record = transition_media_job(record, "prompt_packaged", "worker")

        with self.assertRaises(TransitionValidationError):
            transition_media_job(record, "audio_generated", "worker")

        self.assertEqual(record["current_stage"], "prompt_packaged")

    def test_generation_strategy_locked_missing_required_payload_fails_closed(self) -> None:
        record = initialize_media_job_record("job-4", "author")
        record = transition_media_job(record, "refined_lyrics", "worker")
        record = transition_media_job(record, "prompt_packaged", "worker")
        record = transition_media_job(
            record,
            "generation_strategized",
            "worker",
            runtime_payload=self._strategized_payload(),
        )

        with self.assertRaises(TransitionValidationError):
            transition_media_job(
                record,
                "generation_strategy_locked",
                "worker",
                runtime_payload={"proposed_prompt_hash": "sha256:abc123"},
            )

        self.assertEqual(record["current_stage"], "generation_strategized")

    def test_compat_generation_strategized_direct_to_audio_generated_allowed(self) -> None:
        record = initialize_media_job_record("job-5", "author")
        record = transition_media_job(record, "refined_lyrics", "worker")
        record = transition_media_job(record, "prompt_packaged", "worker")
        record = transition_media_job(
            record,
            "generation_strategized",
            "worker",
            runtime_payload=self._strategized_payload(),
        )

        record = transition_media_job(record, "audio_generated", "worker")
        self.assertEqual(record["current_stage"], "audio_generated")


    def test_level_3_transition_metadata_is_attached(self) -> None:
        record = initialize_media_job_record("job-6", "author")

        for stage in MEDIA_STAGES[1:]:
            runtime_payload = None
            if stage == "generation_strategized":
                runtime_payload = self._strategized_payload()
            if stage == "generation_strategy_locked":
                runtime_payload = self._lock_payload()
            record = transition_media_job(record, stage, "worker", runtime_payload=runtime_payload)

        provenance_event = next(event for event in record["transition_log"] if event["to_stage"] == "provenance_written")
        rollout_event = next(event for event in record["transition_log"] if event["to_stage"] == "rollout_packaged")

        self.assertEqual(provenance_event["transition_metadata"]["ratification_scope"], "publish_release")
        self.assertEqual(rollout_event["transition_metadata"]["ratification_scope"], "deploy_production")
        self.assertTrue(rollout_event["transition_metadata"]["can_invoke_level_3"])


if __name__ == "__main__":
    unittest.main()
