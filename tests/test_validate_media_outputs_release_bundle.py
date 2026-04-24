from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pipelines.validate_media_outputs import check_release_bundle_structure


class ReleaseBundleValidationTests(unittest.TestCase):
    def test_release_bundle_structure_check_passes_for_valid_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle_path = root / "bundle.json"
            bundle_path.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0.0",
                        "release_id": "rel-001",
                        "title": "Example Release",
                        "artist_name": "JRT",
                        "created_at": "2026-04-24T00:00:00Z",
                        "identifiers": {"isrc": "ISRC-TBD", "upc": "UPC-TBD"},
                        "masters": [{"track_id": "trk-001", "path": "masters/trk-001.wav"}],
                        "stems": [{"track_id": "trk-001", "path": "stems/trk-001-drums.wav"}],
                        "credits": [{"name": "Artist A", "role": "writer"}],
                        "rights_metadata": {"copyright_owner": "InnovativeArtsInc"},
                        "artifacts": {
                            "bundle_sha256": "abc",
                            "split_sheet_refs": [
                                {
                                    "artifact_type": "split_sheet",
                                    "artifact_id": "rel-001-split-sheet",
                                    "storage_uri": "registry://split-sheets/rel-001.json",
                                    "sha256": "f" * 64,
                                    "signature": "a" * 64,
                                    "signer": "rights-bot",
                                    "signed_at": "2026-04-24T00:00:00Z",
                                }
                            ],
                        },
                    }
                ),
                encoding="utf-8",
            )

            track = {"assets": {"release_bundle": str(bundle_path)}}
            rules = {"release_bundle_validation": {"enabled": True, "required": True}}
            result = check_release_bundle_structure(track, rules, root)

            self.assertTrue(result.passed)


if __name__ == "__main__":
    unittest.main()
