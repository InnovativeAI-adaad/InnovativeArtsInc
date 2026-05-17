from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from services.media_generation import SunoAdapter, generate_music_for_wf005
from services.media_generation.adapters import normalize_provider_response_payload


class MediaGenerationServiceTests(unittest.TestCase):
    def test_required_outputs_and_artifact_conventions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = generate_music_for_wf005(
                prompt="Cinematic piano with analog bass",
                style_profile="jrt.noir.v1",
                seed=42,
                length=75,
                tempo=108,
                key="D minor",
                uniqueness_report_ref="registry/reports/uniqueness-001.json",
                project_root=root,
            )

            self.assertTrue(result["audio_path"].endswith(".wav"))
            self.assertIn("projects/jrt/audio/generated/", result["audio_path"])
            self.assertIn("provider_generation_id", result)
            self.assertIn("job_id", result)
            self.assertIn("artifacts", result)
            self.assertIn("cost", result)
            self.assertIn("provenance_ref", result)
            self.assertIn("policy_ref", result)
            self.assertIn("render_metadata", result)
            self.assertEqual(
                result["render_metadata"]["provider_generation_id"],
                result["provider_generation_id"],
            )
            self.assertEqual(result["uniqueness_report_ref"], "registry/reports/uniqueness-001.json")
            self.assertEqual(result["policy_ref"], "registry/reports/uniqueness-001.json")
            self.assertEqual(result["render_metadata"]["provider_name"], "stub_genaudio")
            self.assertEqual(result["render_metadata"]["model"], "stub-genaudio-v1")
            self.assertEqual(result["render_metadata"]["model_version"], "1.0.0")
            self.assertIn("request_payload_hash", result["render_metadata"])
            self.assertIn("generation_timestamp", result["render_metadata"])
            self.assertEqual(result["artifact_refs"], result["artifacts"])
            self.assertEqual(result["cost_summary"], result["cost"])

            provenance_log = root / "registry" / "provenance_log.jsonl"
            self.assertTrue(provenance_log.exists())
            row = json.loads(provenance_log.read_text(encoding="utf-8").strip())
            self.assertEqual(row["stage"], "generate_music")
            self.assertEqual(row["workflow"], "WF-005")
            self.assertEqual(row["provider_name"], "stub_genaudio")
            self.assertEqual(row["request_payload_hash"], result["render_metadata"]["request_payload_hash"])

    def test_deterministic_replay_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            params = {
                "prompt": "Sparse western score with steel guitar",
                "style_profile": {"profile": "jrt.frontier.v2"},
                "seed": "9001",
                "length": 64,
                "tempo": 92,
                "key": "E minor",
                "uniqueness_report_ref": "registry/reports/uniqueness-002.json",
                "project_root": root,
            }
            first = generate_music_for_wf005(**params)
            second = generate_music_for_wf005(**params)

            self.assertFalse(first["replayed"])
            self.assertTrue(second["replayed"])
            self.assertEqual(first["replay_key"], second["replay_key"])
            self.assertEqual(first["audio_path"], second["audio_path"])
            self.assertEqual(first["provider_generation_id"], second["provider_generation_id"])
            self.assertEqual(first["job_id"], second["job_id"])

            provenance_rows = [
                json.loads(line)
                for line in (root / "registry" / "provenance_log.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(len(provenance_rows), 1)


    def test_stub_generations_vary_with_seed_and_job_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = generate_music_for_wf005(
                prompt="Minimal synth pulse",
                style_profile="jrt.synth.v1",
                seed=100,
                length=20,
                tempo=120,
                key="A minor",
                uniqueness_report_ref="registry/reports/uniqueness-101.json",
                project_root=root,
            )
            second = generate_music_for_wf005(
                prompt="Minimal synth pulse",
                style_profile="jrt.synth.v1",
                seed=101,
                length=20,
                tempo=120,
                key="A minor",
                uniqueness_report_ref="registry/reports/uniqueness-102.json",
                project_root=root,
            )

            first_digest = hashlib.sha256(Path(first["audio_path"]).read_bytes()).hexdigest()
            second_digest = hashlib.sha256(Path(second["audio_path"]).read_bytes()).hexdigest()

            self.assertNotEqual(first["replay_key"], second["replay_key"])
            self.assertNotEqual(first["provider_generation_id"], second["provider_generation_id"])
            self.assertNotEqual(first_digest, second_digest)

    def test_scheduler_decision_can_select_dry_run_provider_adapter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = generate_music_for_wf005(
                prompt="Anthemic brass and breakbeat",
                style_profile="jrt.trailer.v1",
                seed=73,
                length=30,
                uniqueness_report_ref="registry/reports/uniqueness-003.json",
                scheduler_decision={
                    "selected_provider": "suno",
                    "selected_model": "chirp-v4",
                    "selected_model_version": "v4",
                },
                dry_run=True,
                project_root=root,
            )

            self.assertEqual(result["render_metadata"]["provider_name"], "suno")
            self.assertEqual(result["render_metadata"]["model"], "chirp-v4")
            self.assertEqual(result["render_metadata"]["model_version"], "v4")
            self.assertTrue(result["render_metadata"]["dry_run"])
            self.assertIn("request_payload_hash", result["render_metadata"])

            row = json.loads((root / "registry" / "provenance_log.jsonl").read_text(encoding="utf-8").strip())
            self.assertEqual(row["provider_name"], "suno")
            self.assertEqual(row["model"], "chirp-v4")
            self.assertEqual(row["request_payload_hash"], result["render_metadata"]["request_payload_hash"])

    def test_live_provider_adapter_requires_environment_credentials(self) -> None:
        previous_key = os.environ.pop("SUNO_API_KEY", None)
        try:
            adapter = SunoAdapter(dry_run=False)
            with tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(RuntimeError):
                    adapter.generate(
                        prompt="No credentials",
                        style_profile="jrt.test",
                        seed=1,
                        length=10,
                        output_dir=Path(tmp),
                        replay_key="no-creds",
                    )
        finally:
            if previous_key is not None:
                os.environ["SUNO_API_KEY"] = previous_key

    def test_provider_response_normalization_aliases(self) -> None:
        normalized = normalize_provider_response_payload(
            {"generation_id": "gen-1", "output": ["https://audio.example/file.wav"]}
        )
        self.assertEqual(normalized["id"], "gen-1")
        self.assertEqual(normalized["audio_url"], "https://audio.example/file.wav")

    def test_provider_response_normalization_drops_malformed_audio_fields(self) -> None:
        normalized = normalize_provider_response_payload({"id": "x", "audio": 123, "output": [None]})
        self.assertEqual(normalized["id"], "x")
        self.assertNotIn("audio_base64", normalized)
        self.assertNotIn("audio_url", normalized)


if __name__ == "__main__":
    unittest.main()
