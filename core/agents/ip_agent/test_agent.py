from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
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


class IPAgentSimilarityPolicyTests(unittest.TestCase):
    def _policy_file(
        self,
        revise: float = 0.75,
        block: float = 0.9,
        version: str = "1.0.0",
        methods: dict | None = None,
        decision_policy: str = "max_similarity",
        method_weights: dict[str, float] | None = None,
        required_methods: dict[str, bool] | None = None,
    ) -> str:
        temp_dir = tempfile.mkdtemp(prefix="ip-policy-")
        path = Path(temp_dir) / "policy.json"
        policy_methods = methods or {
            "metadata": {
                "version": "1.0.0",
                "model_id": "jaccard-v1",
                "required_for_release_intent": True,
            },
            "fingerprint": {
                "version": "1.0.0",
                "model_id": "fingerprint-v1",
                "required_for_release_intent": True,
            },
            "embedding": {
                "version": "1.0.0",
                "model_id": "embedding-v1",
                "required_for_release_intent": True,
            },
        }
        if required_methods:
            for method_name, is_required in required_methods.items():
                if method_name in policy_methods:
                    policy_methods[method_name]["required_for_release_intent"] = is_required
        path.write_text(
            json.dumps(
                {
                    "version": version,
                    "decision_policy": decision_policy,
                    "method_weights": method_weights or {},
                    "confidence_floor": 0.3,
                    "thresholds": {"revise": revise, "block": block},
                    "methods": policy_methods,
                }
            ),
            encoding="utf-8",
        )
        return str(path)

    def _provenance_file(self, lines: list[dict]) -> str:
        fd, path_str = tempfile.mkstemp(prefix="ip-prov-", suffix=".jsonl")
        Path(path_str).write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")
        return path_str

    def test_run_similarity_audit_boundary_values(self) -> None:
        policy_path = self._policy_file(revise=0.5, block=1.0)
        provenance = self._provenance_file(
            [
                {
                    "job_id": "prior-1",
                    "track_id": "track-prior-1",
                    "render_metadata": {"prompt": "shared"},
                    "audio_fingerprint": [1.0, 0.0],
                    "embedding": [1.0, 0.0],
                }
            ]
        )

        pass_result = agent.run_similarity_audit(
            {
                "job_id": "job-pass",
                "similarity_policy_path": policy_path,
                "provenance_log_path": provenance,
                "render_metadata": {"prompt": "different"},
                "audio_fingerprint": [0.0, 1.0],
                "embedding": [0.0, 1.0],
            }
        )
        self.assertEqual(pass_result["decision"], "pass")

        revise_result = agent.run_similarity_audit(
            {
                "job_id": "job-revise",
                "similarity_policy_path": policy_path,
                "provenance_log_path": provenance,
                "render_metadata": {"prompt": "shared", "extra": "field"},
                "audio_fingerprint": [0.0, 1.0],
                "embedding": [0.0, 1.0],
            }
        )
        self.assertEqual(revise_result["decision"], "revise")
        self.assertAlmostEqual(revise_result["max_similarity"], 0.5, places=6)

        block_result = agent.run_similarity_audit(
            {
                "job_id": "job-block",
                "similarity_policy_path": policy_path,
                "provenance_log_path": provenance,
                "render_metadata": {"prompt": "shared"},
                "audio_fingerprint": [1.0, 0.0],
                "embedding": [1.0, 0.0],
            }
        )
        self.assertEqual(block_result["decision"], "block")
        self.assertAlmostEqual(block_result["max_similarity"], 1.0, places=6)

    def test_run_similarity_audit_required_methods_all_pass_release_intent_enforcement(self) -> None:
        policy_path = self._policy_file(
            revise=0.5,
            block=0.9,
            decision_policy="required_methods_all_pass",
            required_methods={"metadata": True, "fingerprint": False, "embedding": False},
        )
        provenance = self._provenance_file(
            [
                {
                    "job_id": "prior-1",
                    "track_id": "track-prior-1",
                    "render_metadata": {"prompt": "different"},
                    "audio_fingerprint": [1.0, 0.0],
                    "embedding": [0.0, 1.0],
                }
            ]
        )

        result = agent.run_similarity_audit(
            {
                "job_id": "job-required-pass",
                "release_intent": True,
                "similarity_policy_path": policy_path,
                "provenance_log_path": provenance,
                "render_metadata": {"prompt": "unique"},
                "audio_fingerprint": [1.0, 0.0],
                "embedding": [0.0, 1.0],
            }
        )
        self.assertEqual(result["decision"], "pass")
        self.assertAlmostEqual(result["max_similarity"], 1.0, places=6)
        self.assertEqual(result["audit_artifact"]["decision_rationale"]["policy_mode"], "required_methods_all_pass")
        self.assertEqual(result["audit_artifact"]["decision_rationale"]["required_method_breaches"], [])

    def test_run_similarity_audit_weighted_mean_mode(self) -> None:
        policy_path = self._policy_file(
            revise=0.5,
            block=0.9,
            decision_policy="weighted_mean",
            method_weights={"metadata": 0.2, "fingerprint": 0.4, "embedding": 0.4},
        )
        provenance = self._provenance_file(
            [
                {
                    "job_id": "prior-1",
                    "track_id": "track-prior-1",
                    "render_metadata": {"prompt": "same"},
                    "audio_fingerprint": [1.0, 0.0],
                    "embedding": [1.0, 0.0],
                }
            ]
        )

        result = agent.run_similarity_audit(
            {
                "job_id": "job-weighted",
                "similarity_policy_path": policy_path,
                "provenance_log_path": provenance,
                "render_metadata": {"prompt": "same"},
                "audio_fingerprint": [0.0, 1.0],
                "embedding": [0.0, 1.0],
            }
        )
        self.assertEqual(result["decision"], "pass")
        self.assertAlmostEqual(result["max_similarity"], 0.2, places=6)
        self.assertEqual(result["audit_artifact"]["decision_rationale"]["policy_mode"], "weighted_mean")
        self.assertEqual(len(result["audit_artifact"]["decision_rationale"]["contributing_methods"]), 3)

    def test_run_similarity_audit_unknown_policy_defaults_to_max_similarity(self) -> None:
        policy_path = self._policy_file(revise=0.5, block=0.9, decision_policy="unknown_mode")
        provenance = self._provenance_file(
            [
                {
                    "job_id": "prior-1",
                    "track_id": "track-prior-1",
                    "render_metadata": {"prompt": "same"},
                    "audio_fingerprint": [0.0, 1.0],
                    "embedding": [0.0, 1.0],
                }
            ]
        )

        result = agent.run_similarity_audit(
            {
                "job_id": "job-fallback",
                "similarity_policy_path": policy_path,
                "provenance_log_path": provenance,
                "render_metadata": {"prompt": "same"},
                "audio_fingerprint": [0.0, 1.0],
                "embedding": [0.0, 1.0],
            }
        )
        self.assertEqual(result["decision"], "block")
        self.assertAlmostEqual(result["max_similarity"], 1.0, places=6)
        self.assertTrue(result["audit_artifact"]["decision_rationale"]["fallback_to_max_similarity"])

    @patch("core.agents.ip_agent.agent.append_stage_metric")
    @patch("core.agents.ip_agent.agent.append_provenance_entries")
    def test_run_fails_on_policy_version_drift(self, mock_append_entries, mock_append_metric) -> None:
        mock_append_entries.return_value = [{"artifact_hash": "abc123"}]
        policy_path = self._policy_file(version="2.0.0")

        result = agent.run(
            {
                "job_id": "job-drift",
                "track_id": "track-drift",
                "output_files": ["registry/provenance_log.jsonl"],
                "render_metadata": {"prompt": "x"},
                "similarity_policy_path": policy_path,
                "expected_similarity_policy_version": "1.0.0",
            }
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["stage_result_code"], "failure:similarity_audit_exception")
        self.assertIn("policy version drift", result["error"])
        mock_append_entries.assert_not_called()
        self.assertEqual(mock_append_metric.call_count, 1)

    @patch("core.agents.ip_agent.agent.append_stage_metric")
    @patch("core.agents.ip_agent.agent.append_provenance_entries")
    def test_run_fails_closed_for_missing_release_intent_inputs(self, mock_append_entries, mock_append_metric) -> None:
        mock_append_entries.return_value = [{"artifact_hash": "abc123"}]
        policy_path = self._policy_file(version="1.0.0")

        result = agent.run(
            {
                "job_id": "job-release",
                "track_id": "track-release",
                "output_files": ["registry/provenance_log.jsonl"],
                "release_intent": True,
                "render_metadata": {"prompt": "x"},
                "similarity_policy_path": policy_path,
            }
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["stage_result_code"], "failure:similarity_audit_exception")
        self.assertIn("Missing required similarity inputs", result["error"])
        mock_append_entries.assert_not_called()
        self.assertEqual(mock_append_metric.call_count, 1)

    def test_build_strategies_respects_configured_method_subset(self) -> None:
        policy_path = self._policy_file(
            methods={
                "embedding": {
                    "version": "9.9.9",
                    "model_id": "embedding-v99",
                    "required_for_release_intent": False,
                }
            }
        )
        policy = agent._load_similarity_policy({"similarity_policy_path": policy_path})

        strategies = agent._build_strategies(policy)

        self.assertEqual(len(strategies), 1)
        self.assertEqual(strategies[0].method, "embedding")
        self.assertEqual(strategies[0].version, "9.9.9")
        self.assertEqual(strategies[0].model_id, "embedding-v99")

    def test_load_similarity_policy_accepts_valid_weighted_policy(self) -> None:
        policy_path = self._policy_file(
            decision_policy="weighted_mean",
            method_weights={"metadata": 0.2, "embedding": 0.8, "fingerprint": 0.0},
        )

        policy = agent._load_similarity_policy({"similarity_policy_path": policy_path})

        self.assertEqual(policy.decision_policy, "weighted_mean")
        self.assertEqual(policy.method_weights, {"metadata": 0.2, "embedding": 0.8, "fingerprint": 0.0})

    def test_load_similarity_policy_raises_for_unknown_weight_method(self) -> None:
        policy_path = self._policy_file(
            decision_policy="weighted_mean",
            method_weights={"metadata": 1.0, "unknown_method": 0.5},
        )

        with self.assertRaisesRegex(ValueError, "method_weights defines unknown methods: unknown_method"):
            agent._load_similarity_policy({"similarity_policy_path": policy_path})

    def test_load_similarity_policy_raises_for_weighted_mean_zero_or_negative_weights(self) -> None:
        zero_path = self._policy_file(
            decision_policy="weighted_mean",
            method_weights={"metadata": 0.0, "fingerprint": 0.0, "embedding": 0.0},
        )
        with self.assertRaisesRegex(ValueError, "requires at least one positive method_weights value"):
            agent._load_similarity_policy({"similarity_policy_path": zero_path})

        negative_path = self._policy_file(
            decision_policy="weighted_mean",
            method_weights={"metadata": -0.1},
        )
        with self.assertRaisesRegex(ValueError, "method_weights.metadata must be non-negative"):
            agent._load_similarity_policy({"similarity_policy_path": negative_path})

    def test_load_similarity_policy_allows_missing_method_weights_for_non_weighted_policies(self) -> None:
        policy_path = self._policy_file(decision_policy="max_similarity")

        policy = agent._load_similarity_policy({"similarity_policy_path": policy_path})

        self.assertEqual(policy.decision_policy, "max_similarity")
        self.assertEqual(policy.method_weights, {})

    def test_load_similarity_policy_raises_for_unknown_method(self) -> None:
        policy_path = self._policy_file(
            methods={
                "metadata": {
                    "version": "1.0.0",
                    "model_id": "jaccard-v1",
                    "required_for_release_intent": True,
                },
                "unknown_method": {
                    "version": "0.0.1",
                    "model_id": "custom-v1",
                    "required_for_release_intent": False,
                },
            }
        )

        with self.assertRaisesRegex(ValueError, "unsupported methods: unknown_method"):
            agent._load_similarity_policy({"similarity_policy_path": policy_path})

    @patch("core.agents.ip_agent.agent.append_stage_metric")
    @patch("core.agents.ip_agent.agent.append_provenance_entries")
    def test_run_enforces_required_release_method_for_subset_policy(self, mock_append_entries, mock_append_metric) -> None:
        mock_append_entries.return_value = [{"artifact_hash": "abc123"}]
        policy_path = self._policy_file(
            methods={
                "metadata": {
                    "version": "1.2.3",
                    "model_id": "jaccard-v123",
                    "required_for_release_intent": True,
                },
                "embedding": {
                    "version": "2.0.0",
                    "model_id": "embedding-v2",
                    "required_for_release_intent": False,
                },
            }
        )

        result = agent.run(
            {
                "job_id": "job-release-subset",
                "track_id": "track-release-subset",
                "output_files": ["registry/provenance_log.jsonl"],
                "release_intent": True,
                "embedding": [0.1, 0.2, 0.3],
                "similarity_policy_path": policy_path,
            }
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["stage_result_code"], "failure:similarity_audit_exception")
        self.assertIn("Missing required similarity inputs", result["error"])
        self.assertIn("metadata", result["error"])
        mock_append_entries.assert_not_called()
        self.assertEqual(mock_append_metric.call_count, 1)


if __name__ == "__main__":
    unittest.main()
