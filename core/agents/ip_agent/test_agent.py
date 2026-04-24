from __future__ import annotations

import unittest
from unittest.mock import patch

from core.agents.ip_agent import agent


class IPAgentTelemetryTests(unittest.TestCase):
    @patch("core.agents.ip_agent.agent.append_stage_metric")
    @patch("core.agents.ip_agent.agent.append_provenance_entries")
    def test_run_records_success_metric(self, mock_append_entries, mock_append_metric) -> None:
        mock_append_entries.return_value = [{"artifact_hash": "abc123"}]

        result = agent.run(
            {
                "job_id": "job-1",
                "track_id": "track-1",
                "output_files": ["registry/provenance_log.jsonl"],
            }
        )

        self.assertTrue(result["ok"])
        mock_append_metric.assert_called_once()
        metric_call = mock_append_metric.call_args.kwargs
        self.assertEqual(metric_call["job_id"], "job-1")
        self.assertEqual(metric_call["stage"], "ip_agent.run")
        self.assertEqual(metric_call["result"], "success")
        self.assertEqual(metric_call["fitness_score"], 1.0)

    @patch("core.agents.ip_agent.agent.append_stage_metric")
    @patch("core.agents.ip_agent.agent.append_provenance_entries")
    def test_run_records_failure_metric_on_exception(self, mock_append_entries, mock_append_metric) -> None:
        mock_append_entries.side_effect = RuntimeError("boom")

        result = agent.run(
            {
                "job_id": "job-2",
                "track_id": "track-2",
                "output_files": ["registry/provenance_log.jsonl"],
            }
        )

        self.assertFalse(result["ok"])
        self.assertIn("Provenance append failed", result["error"])
        mock_append_metric.assert_called_once()
        metric_call = mock_append_metric.call_args.kwargs
        self.assertEqual(metric_call["job_id"], "job-2")
        self.assertEqual(metric_call["stage"], "ip_agent.run")
        self.assertEqual(metric_call["result"], "failure:append_provenance_exception")
        self.assertEqual(metric_call["fitness_score"], 0.0)


if __name__ == "__main__":
    unittest.main()
