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
            record = transition_media_job(record, stage, "worker")

        self.assertEqual(record["current_stage"], MEDIA_STAGES[-1])
        self.assertEqual(len(record["transition_log"]), len(MEDIA_STAGES))
        last_event = record["transition_log"][-1]
        self.assertEqual(last_event["status"], MEDIA_STAGES[-1])
        self.assertIn("timestamp", last_event)
        self.assertEqual(last_event["actor"], "worker")

    def test_illegal_jump_fails_closed_without_mutation(self) -> None:
        original = initialize_media_job_record("job-2", "author")
        with self.assertRaises(TransitionValidationError):
            transition_media_job(original, "audio_generated", "worker")

        self.assertEqual(original["current_stage"], "draft_lyrics")
        self.assertEqual(len(original["transition_log"]), 1)


if __name__ == "__main__":
    unittest.main()
