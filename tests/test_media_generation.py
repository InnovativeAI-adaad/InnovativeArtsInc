from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from services.media_generation import GenerationMode, SunoAdapter, generate_music_for_wf005, promote_preview_to_full_render
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
            self.assertEqual(row["stage"], "generate_scene_media")
            self.assertEqual(row["workflow"], "WF-005")
            self.assertEqual(row["provider_name"], "stub_genaudio")
            self.assertEqual(row["audio_request_payload_hash"], result["render_metadata"]["request_payload_hash"])
            self.assertEqual(row["visual_request_payload_hash"], result["visual_request_payload_hash"])
            self.assertIn("scene_hash", result["scene_contract"])


    def test_preview_outputs_are_capped_and_low_cost(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            preview = generate_music_for_wf005(
                prompt="Cinematic piano with analog bass",
                style_profile="jrt.noir.v1",
                seed=42,
                length=75,
                tempo=108,
                key="D minor",
                generation_mode=GenerationMode.PREVIEW,
                uniqueness_report_ref="registry/reports/uniqueness-preview.json",
                project_root=root,
            )
            full = generate_music_for_wf005(
                prompt="Cinematic piano with analog bass",
                style_profile="jrt.noir.v1",
                seed=42,
                length=75,
                tempo=108,
                key="D minor",
                generation_mode=GenerationMode.FULL,
                uniqueness_report_ref="registry/reports/uniqueness-full.json",
                project_root=root,
            )

            self.assertIn("/preview/", preview["audio_path"])
            self.assertLess(Path(preview["audio_path"]).stat().st_size, Path(full["audio_path"]).stat().st_size)
            self.assertEqual(preview["render_metadata"]["sample_rate_hz"], 16000)
            self.assertEqual(preview["render_metadata"]["visual_quality_tier"], "low")
            self.assertLess(preview["render_metadata"]["render_settings"]["length"], 75)

    def test_promote_preview_to_full_preserves_lineage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            preview = generate_music_for_wf005(
                prompt="Sparse western score with steel guitar",
                style_profile={"profile": "jrt.frontier.v2"},
                seed="9001",
                length=64,
                tempo=92,
                key="E minor",
                generation_mode=GenerationMode.PREVIEW,
                uniqueness_report_ref="registry/reports/uniqueness-002-preview.json",
                project_root=root,
            )

            promoted = promote_preview_to_full_render(
                preview_replay_key=preview["replay_key"],
                uniqueness_report_ref="registry/reports/uniqueness-002-full.json",
                project_root=root,
            )

            self.assertEqual(promoted["generation_mode"], "full")
            self.assertEqual(promoted["promoted_from_replay_key"], preview["replay_key"])
            self.assertIn("preview_render_record", promoted)
            self.assertIn("/generated/", promoted["audio_path"])
            self.assertNotEqual(preview["replay_key"], promoted["replay_key"])

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



    def test_provenance_dedupe_skips_invalid_jsonl_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            params = {
                "prompt": "Ambient pulses with distant choir",
                "style_profile": "jrt.noir.v1",
                "seed": 808,
                "length": 24,
                "tempo": 104,
                "key": "C minor",
                "uniqueness_report_ref": "registry/reports/uniqueness-provenance-001.json",
                "project_root": root,
            }

            first = generate_music_for_wf005(**params)
            provenance_log = root / "registry" / "provenance_log.jsonl"
            valid_line = provenance_log.read_text(encoding="utf-8").strip()
            provenance_log.write_text("{not json}\n" + valid_line + "\n", encoding="utf-8")

            second = generate_music_for_wf005(**params)

            self.assertTrue(second["replayed"])
            self.assertEqual(first["replay_key"], second["replay_key"])
            rows = [
                json.loads(line)
                for line in provenance_log.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.startswith("{not json}")
            ]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["replay_key"], first["replay_key"])

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

    def test_contract_and_visual_fingerprints_are_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base_params = {
                "prompt": "Neon noir pulse with choir textures",
                "style_profile": {"profile": "jrt.noir.v2"},
                "seed": 333,
                "length": 28,
                "tempo": 110,
                "key": "F minor",
                "job_id": "job-contract-1",
                "uniqueness_report_ref": "registry/reports/uniqueness-201.json",
                "project_root": root,
            }
            first = generate_music_for_wf005(**base_params)
            second = generate_music_for_wf005(**base_params)

            self.assertEqual(first["scene_contract"]["scene_hash"], second["scene_contract"]["scene_hash"])
            self.assertEqual(first["render_metadata"]["request_payload_hash"], second["render_metadata"]["request_payload_hash"])
            self.assertEqual(first["visual_request_payload_hash"], second["visual_request_payload_hash"])

            changed = generate_music_for_wf005(**{**base_params, "seed": 334, "job_id": "job-contract-2"})
            self.assertNotEqual(first["scene_contract"]["scene_hash"], changed["scene_contract"]["scene_hash"])
            self.assertNotEqual(first["render_metadata"]["request_payload_hash"], changed["render_metadata"]["request_payload_hash"])
            self.assertNotEqual(first["visual_request_payload_hash"], changed["visual_request_payload_hash"])

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
    def test_brand_profile_is_deterministic_for_same_seed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "registry" / "style_memory").mkdir(parents=True, exist_ok=True)
            source = Path("registry/style_memory/noir_baseline.json")
            (root / "registry" / "style_memory" / "noir_baseline.json").write_text(source.read_text(encoding="utf-8"))

            params = {
                "prompt": "Slow-burn noir cue",
                "style_profile": "jrt.noir.v1",
                "seed": 11,
                "length": 25,
                "brand_profile_id": "noir_baseline",
                "uniqueness_report_ref": "registry/reports/uniqueness-bp-001.json",
                "project_root": root,
            }
            first = generate_music_for_wf005(**params)
            second = generate_music_for_wf005(**params)
            self.assertEqual(first["replay_key"], second["replay_key"])
            self.assertEqual(first["brand_profile_hash"], second["brand_profile_hash"])
            self.assertEqual(first["provider_generation_id"], second["provider_generation_id"])

    def test_changing_brand_profile_changes_output_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "registry" / "style_memory").mkdir(parents=True, exist_ok=True)
            for profile in ("noir_baseline", "neon_pulse"):
                source = Path(f"registry/style_memory/{profile}.json")
                (root / "registry" / "style_memory" / f"{profile}.json").write_text(source.read_text(encoding="utf-8"))

            first = generate_music_for_wf005(
                prompt="Pulse-driven hybrid cue",
                style_profile="jrt.hybrid.v1",
                seed=333,
                length=18,
                brand_profile_id="noir_baseline",
                uniqueness_report_ref="registry/reports/uniqueness-bp-101.json",
                project_root=root,
            )
            second = generate_music_for_wf005(
                prompt="Pulse-driven hybrid cue",
                style_profile="jrt.hybrid.v1",
                seed=333,
                length=18,
                brand_profile_id="neon_pulse",
                uniqueness_report_ref="registry/reports/uniqueness-bp-102.json",
                project_root=root,
            )
            self.assertNotEqual(first["brand_profile_hash"], second["brand_profile_hash"])
            self.assertNotEqual(first["replay_key"], second["replay_key"])
            self.assertNotEqual(first["provider_generation_id"], second["provider_generation_id"])

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
