from __future__ import annotations

import json
import logging
import urllib.request
from typing import Any, cast

from eidolon_v16.artifacts.store import ArtifactStore
from eidolon_v16.kernel.base import Kernel, SolutionCandidate
from eidolon_v16.ucr.canonical import canonical_json_bytes
from eidolon_v16.ucr.models import Interpretation, TaskInput

logger = logging.getLogger(__name__)


class HttpKernel(Kernel):
    def __init__(self, base_url: str, store: ArtifactStore, timeout_s: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.store = store
        self.timeout_s = timeout_s

    def propose_interpretations(self, task: TaskInput, *, seed: int) -> list[Interpretation]:
        payload = {"seed": seed, "task": task.model_dump(mode="json")}
        response = self._call("propose_interpretations", payload)
        raw = response.get("interpretations", [])
        if not isinstance(raw, list):
            raise ValueError("kernel http response missing interpretations list")
        return [Interpretation.model_validate(item) for item in raw]

    def propose_solution(
        self, task: TaskInput, interpretation: Interpretation, *, seed: int
    ) -> SolutionCandidate:
        payload = {
            "seed": seed,
            "task": task.model_dump(mode="json"),
            "interpretation": interpretation.model_dump(mode="json"),
        }
        response = self._call("propose_solution", payload)
        if "solution_kind" not in response:
            raise ValueError("kernel http response missing solution_kind")
        return SolutionCandidate(
            output=response.get("output"),
            solution_kind=str(response.get("solution_kind")),
            program=cast(dict[str, Any] | None, response.get("program")),
            trace=cast(dict[str, Any] | None, response.get("trace")),
        )

    def critique(self, task: TaskInput, solution: SolutionCandidate, *, seed: int) -> str:
        payload = {
            "seed": seed,
            "task": task.model_dump(mode="json"),
            "solution": {
                "output": solution.output,
                "solution_kind": solution.solution_kind,
                "program": solution.program,
                "trace": solution.trace,
            },
        }
        response = self._call("critique", payload)
        critique = response.get("critique", "")
        if not isinstance(critique, str):
            raise ValueError("kernel http response missing critique string")
        return critique

    def _call(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}/{method}"
        logger.info("kernel http call start method=%s url=%s", method, url)
        request_body = canonical_json_bytes(payload)
        request = urllib.request.Request(
            url,
            data=request_body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        record: dict[str, Any] = {"method": method, "url": url, "request": payload}
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                response_body = response.read()
                status = response.status
            response_json = json.loads(response_body.decode("utf-8"))
            record.update({"response": response_json, "status": status})
            self.store.put_json(record, artifact_type="kernel_call", producer="kernel_http")
            logger.info("kernel http call done method=%s status=%s", method, status)
            return cast(dict[str, Any], response_json)
        except Exception as exc:
            record["error"] = repr(exc)
            self.store.put_json(record, artifact_type="kernel_call", producer="kernel_http")
            logger.exception("kernel http call failed method=%s", method)
            raise
