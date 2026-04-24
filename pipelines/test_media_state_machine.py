from __future__ import annotations

import unittest

from pipelines.media_state_machine import (
    MEDIA_STAGES,
    TransitionValidationError,
    initialize_media_job_record,
    transition_media_job,
)


class MediaStateMachineTests(unittest.TestCase):
    def test_happy_path_transitions_and_log_fields(self) -> None:
        record = initialize_media_job_record("job-1", "author")

        for stage in MEDIA_STAGES[1:]:
            runtime_payload = None
            if stage == "generation_strategized":
                runtime_payload = {
                    "model_preset": "v4-quality",
                    "temperature": 0.65,
                    "creativity_controls": {"style_push": 0.4},
                    "seed_policy": "deterministic",
                    "novelty_threshold": 0.7,
                }
            record = transition_media_job(record, stage, "worker", runtime_payload=runtime_payload)

        self.assertEqual(record["current_stage"], MEDIA_STAGES[-1])
        self.assertEqual(len(record["transition_log"]), len(MEDIA_STAGES))
        last_event = record["transition_log"][-1]
        self.assertEqual(last_event["status"], MEDIA_STAGES[-1])
        self.assertIn("timestamp", last_event)
        self.assertEqual(last_event["actor"], "worker")

    def test_prompt_packaged_to_generation_strategized_succeeds(self) -> None:
        record = initialize_media_job_record("job-2", "author")
        record = transition_media_job(record, "refined_lyrics", "worker")
        record = transition_media_job(record, "prompt_packaged", "worker")

        record = transition_media_job(
            record,
            "generation_strategized",
            "worker",
            runtime_payload={
                "model_preset": "v4-quality",
                "temperature": 0.5,
                "creativity_controls": {"variation": "medium"},
                "seed_policy": "semi_random",
                "novelty_threshold": 0.6,
            },
        )

        self.assertEqual(record["current_stage"], "generation_strategized")

    def test_prompt_packaged_direct_to_audio_generated_is_rejected(self) -> None:
        record = initialize_media_job_record("job-3", "author")
        record = transition_media_job(record, "refined_lyrics", "worker")
        record = transition_media_job(record, "prompt_packaged", "worker")

        with self.assertRaises(TransitionValidationError):
            transition_media_job(record, "audio_generated", "worker")

        self.assertEqual(record["current_stage"], "prompt_packaged")

    def test_generation_strategized_requires_runtime_payload_fields(self) -> None:
        record = initialize_media_job_record("job-4", "author")
        record = transition_media_job(record, "refined_lyrics", "worker")
        record = transition_media_job(record, "prompt_packaged", "worker")

        with self.assertRaises(TransitionValidationError):
            transition_media_job(
                record,
                "generation_strategized",
                "worker",
                runtime_payload={"model_preset": "v4-quality"},
            )

        self.assertEqual(record["current_stage"], "prompt_packaged")


if __name__ == "__main__":
    unittest.main()
