from __future__ import annotations

import unittest
from unittest.mock import patch

from core.agents.ip_agent import agent


class IPAgentTelemetryTests(unittest.TestCase):
    @patch("core.agents.ip_agent.agent.append_stage_metric")
    @patch("core.agents.ip_agent.agent.append_provenance_entries")
    @patch("core.agents.ip_agent.agent.run_similarity_audit")
    def test_run_records_success_metric(
        self,
        mock_similarity_audit,
        mock_append_entries,
        mock_append_metric,
    ) -> None:
        mock_similarity_audit.return_value = {
            "decision": "pass",
            "max_similarity": 0.12,
            "audit_artifact_path": "registry/similarity_audits/job-1.json",
            "audit_artifact": {},
        }
        mock_append_entries.return_value = [{"artifact_hash": "abc123"}]

        result = agent.run(
            {
                "job_id": "job-1",
                "track_id": "track-1",
                "output_files": ["registry/provenance_log.jsonl"],
                "render_metadata": {"prompt": "sunrise"},
            }
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["stage_result_code"], "success")
        self.assertIn("registry/similarity_audits/job-1.json", result["provenance_refs"])
        mock_append_metric.assert_called_once()
        metric_call = mock_append_metric.call_args.kwargs
        self.assertEqual(metric_call["job_id"], "job-1")
        self.assertEqual(metric_call["stage"], "ip_agent.run")
        self.assertEqual(metric_call["result"], "success")
        self.assertEqual(metric_call["fitness_score"], 1.0)

    @patch("core.agents.ip_agent.agent.append_stage_metric")
    @patch("core.agents.ip_agent.agent.append_provenance_entries")
    @patch("core.agents.ip_agent.agent.run_similarity_audit")
    def test_run_records_failure_metric_on_exception(
        self,
        mock_similarity_audit,
        mock_append_entries,
        mock_append_metric,
    ) -> None:
        mock_similarity_audit.side_effect = RuntimeError("boom")

        result = agent.run(
            {
                "job_id": "job-2",
                "track_id": "track-2",
                "output_files": ["registry/provenance_log.jsonl"],
                "render_metadata": {"prompt": "night sky"},
            }
        )

        self.assertFalse(result["ok"])
        self.assertIn("Similarity audit/provenance append failed", result["error"])
        self.assertEqual(result["stage_result_code"], "failure:similarity_audit_exception")
        mock_append_entries.assert_not_called()
        mock_append_metric.assert_called_once()
        metric_call = mock_append_metric.call_args.kwargs
        self.assertEqual(metric_call["job_id"], "job-2")
        self.assertEqual(metric_call["stage"], "ip_agent.run")
        self.assertEqual(metric_call["result"], "failure:similarity_audit_exception")
        self.assertEqual(metric_call["fitness_score"], 0.0)

    @patch("core.agents.ip_agent.agent.append_stage_metric")
    @patch("core.agents.ip_agent.agent.append_provenance_entries")
    @patch("core.agents.ip_agent.agent.run_similarity_audit")
    def test_run_blocks_on_similarity_decision(
        self,
        mock_similarity_audit,
        mock_append_entries,
        mock_append_metric,
    ) -> None:
        mock_similarity_audit.return_value = {
            "decision": "block",
            "max_similarity": 0.97,
            "audit_artifact_path": "registry/similarity_audits/job-3.json",
            "audit_artifact": {},
        }
        mock_append_entries.return_value = [{"artifact_hash": "abc123"}]

        result = agent.run(
            {
                "job_id": "job-3",
                "track_id": "track-3",
                "output_files": ["registry/provenance_log.jsonl"],
                "render_metadata": {"prompt": "city at dusk"},
            }
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["stage_result_code"], "failure:similarity_blocked")
        self.assertEqual(result["similarity_audit"]["decision"], "block")

        metric_call = mock_append_metric.call_args.kwargs
        self.assertEqual(metric_call["result"], "failure:similarity_blocked")
        self.assertEqual(metric_call["fitness_score"], 0.0)


    @patch("core.agents.ip_agent.agent.append_stage_metric")
    @patch("core.agents.ip_agent.agent.append_provenance_entries")
    def test_run_emits_uniqueness_audit_metric_when_fields_provided(self, mock_append_entries, mock_append_metric) -> None:
        mock_append_entries.return_value = [{"artifact_hash": "abc123"}]

        result = agent.run(
            {
                "job_id": "job-3",
                "track_id": "track-3",
                "output_files": ["registry/provenance_log.jsonl"],
                "uniqueness_validation_time_ms": 245,
                "novelty_index": 0.87,
                "similarity_guardrail_pass": True,
            }
        )

        self.assertTrue(result["ok"])
        self.assertEqual(mock_append_metric.call_count, 2)

        uniqueness_call = mock_append_metric.call_args_list[0].kwargs
        self.assertEqual(uniqueness_call["job_id"], "job-3")
        self.assertEqual(uniqueness_call["stage"], "ip_agent.uniqueness_audit")
        self.assertEqual(uniqueness_call["duration_ms"], 245)
        self.assertEqual(uniqueness_call["result"], "success")
        self.assertEqual(uniqueness_call["fitness_score"], 0.87)
        self.assertEqual(uniqueness_call["uniqueness_validation_time_ms"], 245)
        self.assertEqual(uniqueness_call["novelty_index"], 0.87)
        self.assertTrue(uniqueness_call["similarity_guardrail_pass"])

        run_stage_call = mock_append_metric.call_args_list[1].kwargs
        self.assertEqual(run_stage_call["stage"], "ip_agent.run")


if __name__ == "__main__":
    unittest.main()
