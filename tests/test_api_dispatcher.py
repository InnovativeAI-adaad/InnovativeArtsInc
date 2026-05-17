from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from services.integration.api_dispatcher import ApiDispatcher, DispatchError, DispatchRequestEnvelope


class ApiDispatcherTests(unittest.TestCase):
    def _policy(self, root: Path) -> None:
        (root / "config").mkdir(parents=True, exist_ok=True)
        (root / "config" / "generation_policy.json").write_text(
            json.dumps(
                {
                    "operations": {"generate_audio": {"provider": "stub"}},
                    "fallback_order": [{"provider": "stub"}],
                    "retry": {"max_attempts": 3, "retryable_error_types": ["timeout", "transient", "provider_error"]},
                }
            ),
            encoding="utf-8",
        )

    def test_successful_dispatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._policy(root)
            dispatcher = ApiDispatcher(adapters={"generate_audio": {"stub": lambda payload: {"ok": True, "echo": payload}}}, project_root=root)
            response = dispatcher.dispatch(DispatchRequestEnvelope(operation="generate_audio", job_id="job-1", payload={"prompt": "x"}))
            self.assertEqual(response.provider, "stub")
            self.assertEqual(response.attempt, 1)
            self.assertTrue(response.result["ok"])

    def test_transient_failure_then_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._policy(root)
            calls = {"n": 0}

            def flaky(_: dict[str, object]) -> dict[str, object]:
                calls["n"] += 1
                if calls["n"] == 1:
                    raise DispatchError(error_type="transient", message="temp")
                return {"ok": True}

            dispatcher = ApiDispatcher(adapters={"generate_audio": {"stub": flaky}}, project_root=root, sleep_fn=lambda _s: None)
            response = dispatcher.dispatch(DispatchRequestEnvelope(operation="generate_audio", job_id="job-2", payload={"prompt": "x"}))
            self.assertEqual(calls["n"], 2)
            self.assertEqual(response.attempt, 2)

    def test_hard_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._policy(root)

            def hard(_: dict[str, object]) -> dict[str, object]:
                raise DispatchError(error_type="invalid_request", message="nope")

            dispatcher = ApiDispatcher(adapters={"generate_audio": {"stub": hard}}, project_root=root, sleep_fn=lambda _s: None)
            with self.assertRaises(DispatchError):
                dispatcher.dispatch(DispatchRequestEnvelope(operation="generate_audio", job_id="job-3", payload={"prompt": "x"}))

    def test_duplicate_suppression(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._policy(root)
            calls = {"n": 0}

            def handler(payload: dict[str, object]) -> dict[str, object]:
                calls["n"] += 1
                return {"ok": True, "payload": payload}

            dispatcher = ApiDispatcher(adapters={"generate_audio": {"stub": handler}}, project_root=root)
            request = DispatchRequestEnvelope(operation="generate_audio", job_id="job-4", payload={"prompt": "same"})
            first = dispatcher.dispatch(request)
            second = dispatcher.dispatch(request)
            self.assertEqual(calls["n"], 1)
            self.assertEqual(second.attempt, 0)
            self.assertEqual(first.result, second.result)


if __name__ == "__main__":
    unittest.main()
