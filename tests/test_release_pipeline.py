from __future__ import annotations

import unittest

from services.release_pipeline import (
    StubDSPSubmissionAdapter,
    StubPRORegistrationAdapter,
    build_release_bundle,
    generate_split_sheet,
)


class ReleasePipelineServiceTests(unittest.TestCase):
    def test_build_release_bundle_includes_canonical_fields(self) -> None:
        bundle = build_release_bundle(
            release_id="rel-001",
            title="Example Release",
            artist_name="JRT",
            masters=[{"track_id": "trk-001", "path": "masters/trk-001.wav"}],
            stems=[{"track_id": "trk-001", "path": "stems/trk-001-drums.wav"}],
            credits=[{"name": "Artist A", "role": "writer"}],
            rights_metadata={"copyright_owner": "InnovativeArtsInc"},
        )

        self.assertEqual(bundle["identifiers"]["isrc"], "ISRC-TBD")
        self.assertEqual(bundle["identifiers"]["upc"], "UPC-TBD")
        self.assertIn("masters", bundle)
        self.assertIn("stems", bundle)
        self.assertIn("credits", bundle)
        self.assertIn("rights_metadata", bundle)

    def test_generate_split_sheet_returns_signed_reference(self) -> None:
        split_sheet, signed_ref = generate_split_sheet(
            release_id="rel-002",
            ownership_metadata=[
                {"party": "Artist A", "ownership_percent": 50.0},
                {"party": "Producer B", "ownership_percent": 50.0},
            ],
            signer="rights-bot",
            storage_uri="registry://release/split-sheet-rel-002.json",
        )

        self.assertEqual(split_sheet["verification"]["ownership_total_percent"], 100.0)
        self.assertEqual(signed_ref["artifact_type"], "split_sheet")
        self.assertEqual(len(signed_ref["sha256"]), 64)
        self.assertEqual(len(signed_ref["signature"]), 64)

    def test_stub_provider_adapters(self) -> None:
        dsp_adapter = StubDSPSubmissionAdapter()
        pro_adapter = StubPRORegistrationAdapter()
        bundle = {"release_id": "rel-003"}
        split_sheet = {"split_sheet_id": "rel-003-split-sheet"}

        dsp_result = dsp_adapter.submit_release_bundle(bundle)
        pro_result = pro_adapter.register_work(bundle, split_sheet)

        self.assertTrue(dsp_result.accepted)
        self.assertTrue(pro_result.accepted)
        self.assertIn("rel-003", dsp_result.external_reference_id)
        self.assertIn("rel-003", pro_result.external_reference_id)


if __name__ == "__main__":
    unittest.main()
