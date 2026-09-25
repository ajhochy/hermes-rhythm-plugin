"""Closed dashboard routes for the local Rhythm shared-agent bridge."""

from __future__ import annotations

import re
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, model_validator

router = APIRouter()
_AGENT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
_EDITABLE_FIELDS = {
    "label", "icon", "enabled", "isAgent", "isManager", "systemPrompt",
    "allowedMcpsJson", "allowedSkillsJson", "corePermissionsJson", "allowedDelegatesJson",
    "modelProvider", "modelId", "ocAgent", "sessionSelectable", "schedulable",
    "imageGenerationEnabled", "modelTierHint", "defaultAnthropicAccountId",
    "reasoningEffort", "autoApproveActions",
}


class SaveBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expectedRevision: StrictInt = Field(ge=0)
    changes: dict[str, StrictStr | StrictBool | None] = Field(min_length=1, max_length=len(_EDITABLE_FIELDS))

    @model_validator(mode="after")
    def validate_changes(self):
        if not set(self.changes).issubset(_EDITABLE_FIELDS):
            raise ValueError("unsupported change")
        for value in self.changes.values():
            if value is not None and type(value) not in {str, bool}:
                raise ValueError("invalid change")
            if isinstance(value, str) and len(value) > 65536:
                raise ValueError("invalid change")
        return self


class SaveStatusBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmationId: str = Field(min_length=1, max_length=256)


def _client():
    from ..agent_bridge import BridgeClient

    return BridgeClient()


def _agent_id(value: str) -> str:
    if _AGENT_ID_RE.fullmatch(value) is None:
        raise HTTPException(400, detail={"error": "invalid_agent_id"})
    return value


def _bridge_call(op: str, **kwargs) -> dict:
    from ..agent_bridge import BridgeError

    try:
        return _client().call(op, **kwargs)
    except BridgeError as exc:
        status = {
            "bridge_unavailable": 503,
            "bridge_capability_unknown": 503,
            "bridge_rate_limited": 429,
            "agent_not_found": 404,
            "revision_conflict": 409,
            "agent_locked": 409,
            "invalid_change": 400,
        }.get(exc.code, 502)
        raise HTTPException(status, detail={"error": exc.code}) from None


@router.get("/shared-agents")
def shared_agents_catalog():
    return _bridge_call("catalog.list")


@router.get("/shared-agents/{agent_id:path}")
def shared_agent_detail(agent_id: str, sessionRevision: int | None = Query(default=None, ge=0)):
    validated = _agent_id(agent_id)
    query = {"sessionRevision": sessionRevision} if sessionRevision is not None else None
    return _bridge_call("catalog.get", path_params={"agentId": validated}, query=query)


@router.post("/shared-agents/{agent_id:path}/save")
def shared_agent_save(agent_id: str, payload: SaveBody):
    validated = _agent_id(agent_id)
    result = _bridge_call(
        "agent.patch",
        path_params={"agentId": validated},
        body={"expectedRevision": payload.expectedRevision, "changes": payload.changes},
    )
    return JSONResponse(result, status_code=202 if result.get("status") == "confirmation_required" else 200)


@router.post("/shared-agents/{agent_id:path}/save-status")
def shared_agent_save_status(agent_id: str, payload: SaveStatusBody):
    validated = _agent_id(agent_id)
    return _bridge_call(
        "agent.patch-status",
        path_params={"agentId": validated},
        body={"confirmationId": payload.confirmationId},
    )
