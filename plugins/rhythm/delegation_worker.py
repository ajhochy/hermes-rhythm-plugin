"""Serving-process worker for Rhythm-to-Hermes delegation jobs."""

from __future__ import annotations

import json
import re
import threading
import time
from typing import Any, Callable

from agent import host_capabilities

from .agent_bridge import BridgeClient, BridgeError
from .shared_agents import worker_claim


RUNTIME_REPORT_INTERVAL_SECONDS = 300
PROGRESS_INTERVAL_SECONDS = 20
MAX_CONCURRENT_JOBS = 2
_CLAIM_WAIT_MS = 20_000
_RESULT_CHARS = 16_384
_REPORT_BODY_BYTES = 65_536
_TRUNCATION_MARKER = "\n[truncated]"
_ERROR_CODE_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_TERMINAL_REPORT_BACKOFF_SECONDS = (1, 2, 4, 8, 16, 30, 30, 30, 30, 30)
_TERMINAL_REPORT_RETRY_CODES = frozenset(
    {"bridge_unavailable", "bridge_capability_unknown", "bridge_rate_limited"}
)
_worker_lock = threading.RLock()
_worker = None


def _report_size(body: dict[str, Any]) -> int:
    return len(
        json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )


def _bounded_result_text(value: str, body: dict[str, Any]) -> str:
    """Fit stored-result and bridge-body limits with an explicit marker."""
    if len(value) <= _RESULT_CHARS:
        if _report_size({**body, "resultText": value}) <= _REPORT_BODY_BYTES:
            return value

    high = min(len(value), _RESULT_CHARS - len(_TRUNCATION_MARKER))
    low = 0
    while low < high:
        midpoint = (low + high + 1) // 2
        candidate = value[:midpoint] + _TRUNCATION_MARKER
        if _report_size({**body, "resultText": candidate}) <= _REPORT_BODY_BYTES:
            low = midpoint
        else:
            high = midpoint - 1
    return value[:low] + _TRUNCATION_MARKER


def _bounded_error_code(value: Any, default: str) -> str:
    candidate = str(value or "")
    if candidate.startswith("unsupported_policy:"):
        candidate = candidate.partition(":")[2]
    return candidate if _ERROR_CODE_RE.fullmatch(candidate) else default


def _runtime_report() -> dict[str, Any]:
    from hermes_cli import __version__
    from hermes_constants import VALID_REASONING_EFFORTS

    ready_by_slug: dict[str, bool] = {}
    try:
        from hermes_cli.inventory import build_models_payload, load_picker_context

        inventory = build_models_payload(
            load_picker_context(),
            include_unconfigured=True,
            picker_hints=True,
            probe_custom_providers=False,
            probe_current_custom_provider=False,
        )
        ready_by_slug = {
            str(row.get("slug") or "").lower(): bool(row.get("authenticated"))
            for row in inventory.get("providers", [])
            if isinstance(row, dict)
        }
    except Exception:
        pass
    providers = [
        {"id": provider_id, "ready": ready_by_slug.get(slug, False)}
        for provider_id, slug in (
            ("anthropic", "anthropic"),
            ("openrouter", "openrouter"),
            ("openai-api", "openai-api"),
            ("gemini", "gemini"),
        )
    ]
    try:
        from tui_gateway.server import _effective_terminal_backend

        raw_backend = _effective_terminal_backend()
    except Exception:
        raw_backend = ""
    if raw_backend == "local":
        terminal_backend = "local"
    elif raw_backend in {"docker", "singularity"}:
        terminal_backend = "container"
    elif raw_backend in {"ssh", "modal", "daytona"}:
        terminal_backend = "remote"
    else:
        terminal_backend = "unknown"
    return {
        "hermesVersion": str(__version__)[:64],
        "pluginVersion": "0.1.0",
        "providers": providers,
        "reasoningEfforts": ["none", *VALID_REASONING_EFFORTS],
        "terminalBackend": terminal_backend,
    }


class DelegationWorker:
    def __init__(
        self,
        *,
        client: BridgeClient | None = None,
        session_factory: Callable[..., Any] | None = None,
    ) -> None:
        self._client = client or BridgeClient()
        if session_factory is None:
            # session_driver imports the gateway server on first use; loading
            # the plugin in an ordinary CLI process must remain side-effect free.
            from tui_gateway.session_driver import create_session

            session_factory = create_session
        self._session_factory = session_factory
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._slots = threading.BoundedSemaphore(MAX_CONCURRENT_JOBS)
        self._jobs_lock = threading.Lock()
        self._job_threads: set[threading.Thread] = set()

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, name="rhythm-delegation-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _report_runtime(self) -> bool:
        try:
            self._client.call("runtime.report", body=_runtime_report())
            return True
        except BridgeError:
            return False

    def _loop(self) -> None:
        backoff = 2.0
        next_report = 0.0
        while not self._stop.is_set():
            now = time.monotonic()
            if now >= next_report:
                if self._report_runtime():
                    backoff = 2.0
                    next_report = now + RUNTIME_REPORT_INTERVAL_SECONDS
                else:
                    self._stop.wait(backoff)
                    backoff = min(backoff * 2, 30.0)
                    continue
            if not self._slots.acquire(timeout=1.0):
                continue
            try:
                response = self._client.call("delegation.claim", body={"waitMs": _CLAIM_WAIT_MS}, timeout=25.0)
            except BridgeError as exc:
                self._slots.release()
                if exc.code in {"bridge_capability_unknown", "bridge_unavailable"}:
                    self._stop.wait(backoff)
                    backoff = min(backoff * 2, 30.0)
                else:
                    self._stop.wait(2.0)
                continue
            backoff = 2.0
            job = response.get("job") if isinstance(response, dict) else None
            if not isinstance(job, dict):
                self._slots.release()
                continue
            thread = threading.Thread(target=self._run_job, args=(job,), name="rhythm-delegation-job", daemon=True)
            with self._jobs_lock:
                self._job_threads.add(thread)
            thread.start()

    def _run_job(self, job: dict[str, Any]) -> None:
        try:
            self.run_claim(job)
        finally:
            with self._jobs_lock:
                self._job_threads.discard(threading.current_thread())
            self._slots.release()

    def run_claim(self, job: dict[str, Any]) -> None:
        job_id = str(job.get("jobId") or "")
        lease_token = str(job.get("leaseToken") or "")
        target_label = str(job.get("targetLabel") or job.get("targetAgentId") or "agent")
        done = threading.Event()
        state_lock = threading.Lock()
        state = {"phase": "running", "result": "", "error": "", "steps": 0, "latest": "message"}
        session_holder: dict[str, Any] = {}

        def interrupt() -> None:
            session = session_holder.get("session")
            if session is not None:
                try:
                    session.interrupt()
                except Exception:
                    pass

        def report(phase: str, *, progress: bool = False) -> dict[str, Any] | None:
            body: dict[str, Any] = {"leaseToken": lease_token, "phase": phase}
            session = session_holder.get("session")
            if session is not None:
                body["childSessionKey"] = session.session_key
            with state_lock:
                if progress:
                    body["progress"] = {"steps": state["steps"], "latestKind": state["latest"]}
                if phase == "succeeded":
                    body["resultText"] = _bounded_result_text(state["result"], body)
                elif phase == "failed":
                    body["errorCode"] = _bounded_error_code(
                        state["error"], "driver_error"
                    )
            retry_index = 0
            while True:
                try:
                    response = self._client.call(
                        "delegation.report",
                        path_params={"jobId": job_id},
                        body=body,
                    )
                    break
                except BridgeError as exc:
                    if exc.code == "job_terminal" and session is not None:
                        interrupt()
                        with state_lock:
                            state["phase"] = "cancelled"
                        done.set()
                    is_terminal = phase in {"succeeded", "failed", "cancelled"}
                    if (
                        not is_terminal
                        or exc.code not in _TERMINAL_REPORT_RETRY_CODES
                        or retry_index >= len(_TERMINAL_REPORT_BACKOFF_SECONDS)
                    ):
                        return None
                    # A lease can become unknown during a bridge outage. The
                    # stable childSessionKey above lets this retry reconcile it.
                    delay = _TERMINAL_REPORT_BACKOFF_SECONDS[retry_index]
                    retry_index += 1
                    if self._stop.wait(delay):
                        return None
            if response.get("cancelRequested") and session is not None:
                interrupt()
                with state_lock:
                    state["phase"] = "cancelled"
                done.set()
            return response

        def on_event(event: dict[str, Any]) -> None:
            kind = event.get("type")
            if kind == "tool.complete":
                with state_lock:
                    state["steps"] += 1
                    state["latest"] = "tool"
                report("progress", progress=True)
            elif kind == "approval.request":
                request_id = event.get("request_id") or event.get("requestId")
                session = session_holder.get("session")
                if session is not None and isinstance(request_id, str):
                    session.respond_approval(request_id, "deny")
                with state_lock:
                    state["steps"] += 1
                    state["latest"] = "approval_denied"
                report("progress", progress=True)
            elif kind == "message.complete":
                with state_lock:
                    status = event.get("status")
                    if status == "error":
                        state["phase"] = "failed"
                        state["error"] = _bounded_error_code(
                            event.get("errorCode") or event.get("message"),
                            "agent_error",
                        )
                    elif status in {"interrupted", "cancelled"}:
                        state["phase"] = "cancelled"
                    else:
                        text = event.get("text")
                        state["steps"] += 1
                        state["latest"] = "message"
                        state["phase"] = "succeeded"
                        state["result"] = text if isinstance(text, str) else ""
                done.set()
            elif kind == "error":
                with state_lock:
                    state["phase"] = "failed"
                    state["error"] = _bounded_error_code(
                        event.get("code") or event.get("message"), "agent_error"
                    )
                done.set()

        session = None
        try:
            params = {
                "policy_selection": f"rhythm-job:v1:{job_id}",
                "cwd": job.get("cwd"),
                "title": f"Rhythm delegation: {target_label}",
                "source": "desktop",
            }
            with worker_claim(job_id, lease_token):
                session = self._session_factory(params, on_event=on_event, timeout=30.0)
            session_holder["session"] = session
            report("running")
            if not done.is_set():
                context = job.get("context")
                prompt = str(job.get("prompt") or "")
                text = f"{context}\n\n{prompt}" if isinstance(context, str) and context else prompt
                session.submit(text)
            while not done.wait(PROGRESS_INTERVAL_SECONDS):
                report("progress", progress=True)
            with state_lock:
                terminal = state["phase"]
            report(terminal, progress=False)
        except Exception as exc:
            with state_lock:
                state["phase"] = "failed"
                state["error"] = _bounded_error_code(
                    getattr(exc, "code", None), "driver_error"
                )
            report("failed")
        finally:
            if session is not None:
                try:
                    session.close()
                except Exception:
                    pass


def start_delegation_worker() -> DelegationWorker | None:
    global _worker
    if not host_capabilities.is_serving_process() or host_capabilities.get("rhythm_bridge") is None:
        return None
    with _worker_lock:
        if _worker is None:
            _worker = DelegationWorker()
            _worker.start()
        return _worker


def _reset_worker_for_tests() -> None:
    global _worker
    with _worker_lock:
        if _worker is not None:
            _worker.stop()
        _worker = None
