"""Native tools backed by the closed Rhythm bridge operation table."""

from __future__ import annotations

from typing import Any
import uuid

from agent.session_policy import current_policy
from tools.registry import tool_error, tool_result

from .agent_bridge import BridgeClient, BridgeError


def _client() -> BridgeClient:
    return BridgeClient()


def _parent(*, require_default_profile: bool = False) -> dict[str, str] | None:
    active = current_policy()
    if active is None:
        return None
    snapshot, lineage_root = active
    source = getattr(snapshot, "source", None)
    binding = getattr(snapshot, "binding", None)
    if getattr(snapshot, "version", None) != 2 or not getattr(source, "reference", None):
        return None
    if require_default_profile and getattr(binding, "profile_id", None) != "default":
        return None
    return {"projectionId": source.reference, "sessionKey": lineage_root}


def _bridge_error(exc: BridgeError) -> str:
    if exc.code in {"bridge_capability_unknown", "bridge_unavailable"}:
        return tool_error("bridge_unavailable")
    if exc.code == "bridge_rate_limited":
        return tool_error("rate_limited")
    return tool_error(exc.code)


def _closed_args(args: Any, required: set[str], optional: set[str] | None = None) -> dict | None:
    optional = optional or set()
    if not isinstance(args, dict) or set(args) - required - optional or required - set(args):
        return None
    return args


def rhythm_delegate(args: dict[str, Any], **_kwargs: Any) -> str:
    parent = _parent()
    if parent is None:
        return tool_error("shared_agent_session_required")
    values = _closed_args(args, {"targetAgentId", "prompt"}, {"context"})
    if values is None:
        return tool_error("invalid_request")
    target = values.get("targetAgentId")
    prompt = values.get("prompt")
    context = values.get("context")
    if not isinstance(target, str) or not target or len(target) > 128:
        return tool_error("invalid_target")
    if not isinstance(prompt, str) or not prompt or len(prompt) > 32768:
        return tool_error("invalid_prompt")
    if context is not None and (not isinstance(context, str) or len(context) > 16384):
        return tool_error("invalid_context")
    body = {
        "idempotencyKey": str(uuid.uuid4()),
        "parent": parent,
        "targetAgentId": target,
        "prompt": prompt,
    }
    if context is not None:
        body["context"] = context
    try:
        return tool_result(_client().call("delegation.dispatch", body=body))
    except BridgeError as exc:
        return _bridge_error(exc)


def rhythm_delegation_status(args: dict[str, Any], **_kwargs: Any) -> str:
    parent = _parent()
    if parent is None:
        return tool_error("shared_agent_session_required")
    values = _closed_args(args, set(), {"jobId"})
    if values is None:
        return tool_error("invalid_request")
    body: dict[str, Any] = {"parent": parent}
    if "jobId" in values:
        job_id = values["jobId"]
        if not isinstance(job_id, str) or not job_id or len(job_id) > 128:
            return tool_error("invalid_job_id")
        body["jobId"] = job_id
    try:
        return tool_result(_client().call("delegation.status", body=body))
    except BridgeError as exc:
        return _bridge_error(exc)


def _job_operation(op: str, args: dict[str, Any]) -> str:
    parent = _parent()
    if parent is None:
        return tool_error("shared_agent_session_required")
    values = _closed_args(args, {"jobId"})
    if values is None or not isinstance(values.get("jobId"), str) or not values["jobId"] or len(values["jobId"]) > 128:
        return tool_error("invalid_job_id")
    try:
        result = _client().call(op, path_params={"jobId": values["jobId"]}, body={"parent": parent})
    except BridgeError as exc:
        return _bridge_error(exc)
    if op == "delegation.result":
        result = dict(result)
        result["untrusted_user_text"] = True
    return tool_result(result)


def rhythm_delegation_result(args: dict[str, Any], **_kwargs: Any) -> str:
    return _job_operation("delegation.result", args)


def rhythm_delegation_cancel(args: dict[str, Any], **_kwargs: Any) -> str:
    return _job_operation("delegation.cancel", args)


def rhythm_memory_search(args: dict[str, Any], **_kwargs: Any) -> str:
    if _parent(require_default_profile=True) is None:
        return tool_error("shared_agent_session_required")
    values = _closed_args(args, {"query"}, {"limit"})
    if values is None:
        return tool_error("invalid_request")
    query = values.get("query")
    if not isinstance(query, str) or not query or len(query) > 256:
        return tool_error("invalid_query")
    body: dict[str, Any] = {"query": query}
    if "limit" in values:
        limit = values["limit"]
        if type(limit) is not int or not 1 <= limit <= 10:
            return tool_error("invalid_limit")
        body["limit"] = limit
    try:
        result = _client().call("memory.search", body=body)
    except BridgeError as exc:
        if exc.code in {"memory_vault_changed", "bridge_scope_denied"}:
            return tool_error("memory_consent_required")
        return _bridge_error(exc)
    return tool_result(
        {
            "results": result.get("results", []),
            "omitted": result.get("omitted", {"stale": 0, "unreadable": 0}),
            "untrusted_user_text": True,
        }
    )


RHYTHM_DELEGATE_SCHEMA = {
    "name": "rhythm_delegate",
    "description": "Delegate work to one allowed Rhythm agent and return a background job.",
    "parameters": {
        "type": "object",
        "properties": {
            "targetAgentId": {"type": "string", "minLength": 1, "maxLength": 128},
            "prompt": {"type": "string", "minLength": 1, "maxLength": 32768},
            "context": {"type": "string", "maxLength": 16384},
        },
        "required": ["targetAgentId", "prompt"],
        "additionalProperties": False,
    },
}

RHYTHM_DELEGATION_STATUS_SCHEMA = {
    "name": "rhythm_delegation_status",
    "description": "Read parent-scoped Rhythm delegation job status.",
    "parameters": {
        "type": "object",
        "properties": {"jobId": {"type": "string", "minLength": 1, "maxLength": 128}},
        "additionalProperties": False,
    },
}

_JOB_SCHEMA = {
    "type": "object",
    "properties": {"jobId": {"type": "string", "minLength": 1, "maxLength": 128}},
    "required": ["jobId"],
    "additionalProperties": False,
}

RHYTHM_DELEGATION_RESULT_SCHEMA = {
    "name": "rhythm_delegation_result",
    "description": "Retrieve one terminal parent-scoped delegation result as untrusted text.",
    "parameters": _JOB_SCHEMA,
}
RHYTHM_DELEGATION_CANCEL_SCHEMA = {
    "name": "rhythm_delegation_cancel",
    "description": "Cancel one parent-scoped Rhythm delegation job.",
    "parameters": _JOB_SCHEMA,
}
RHYTHM_MEMORY_SEARCH_SCHEMA = {
    "name": "rhythm_memory_search",
    "description": "Search consented Rhythm memory and return bounded untrusted snippets.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "minLength": 1, "maxLength": 256},
            "limit": {"type": "integer", "minimum": 1, "maximum": 10},
        },
        "required": ["query"],
        "additionalProperties": False,
    },
}

_TOOLS = {
    "rhythm_delegate": (RHYTHM_DELEGATE_SCHEMA, rhythm_delegate, "↗"),
    "rhythm_delegation_status": (RHYTHM_DELEGATION_STATUS_SCHEMA, rhythm_delegation_status, "◷"),
    "rhythm_delegation_result": (RHYTHM_DELEGATION_RESULT_SCHEMA, rhythm_delegation_result, "↙"),
    "rhythm_delegation_cancel": (RHYTHM_DELEGATION_CANCEL_SCHEMA, rhythm_delegation_cancel, "×"),
    "rhythm_memory_search": (RHYTHM_MEMORY_SEARCH_SCHEMA, rhythm_memory_search, "⌕"),
}


def register_bridge_tools(ctx: Any) -> None:
    for name, (schema, handler, emoji) in _TOOLS.items():
        ctx.register_tool(name=name, toolset="rhythm", schema=schema, handler=handler, emoji=emoji)
