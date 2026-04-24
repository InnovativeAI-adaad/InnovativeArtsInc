from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from services.media_generation import generate_music_for_wf005


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
            self.assertIn("render_metadata", result)
            self.assertEqual(
                result["render_metadata"]["provider_generation_id"],
                result["provider_generation_id"],
            )
            self.assertEqual(result["uniqueness_report_ref"], "registry/reports/uniqueness-001.json")

            provenance_log = root / "registry" / "provenance_log.jsonl"
            self.assertTrue(provenance_log.exists())
            row = json.loads(provenance_log.read_text(encoding="utf-8").strip())
            self.assertEqual(row["stage"], "generate_music")
            self.assertEqual(row["workflow"], "WF-005")

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

            provenance_rows = [
                json.loads(line)
                for line in (root / "registry" / "provenance_log.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(len(provenance_rows), 1)


if __name__ == "__main__":
    unittest.main()
