from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict


def derive_intake_id(
    installation_id: int,
    repo_full_name: str,
    issue_number: int,
) -> str:
    raw = f"{installation_id}:{repo_full_name}:{issue_number}"
    return hashlib.sha256(raw.encode()).hexdigest()


class UserData(BaseModel):
    model_config = ConfigDict(extra="allow")
    login: str
    type: str = "User"


class LabelData(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: str


class IssueData(BaseModel):
    model_config = ConfigDict(extra="allow")
    number: int
    title: str
    body: Optional[str] = None
    state: str = "open"
    created_at: str = ""
    updated_at: str = ""
    html_url: str = ""
    user: UserData
    labels: List[Any] = []
    assignees: List[Any] = []


class OwnerData(BaseModel):
    model_config = ConfigDict(extra="allow")
    login: str
    type: str = "Organization"


class RepoData(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: int
    name: str
    full_name: str
    owner: OwnerData
    private: bool = False


class InstallationData(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: int


class WebhookPayload(BaseModel):
    model_config = ConfigDict(extra="allow")
    action: str
    issue: IssueData
    repository: RepoData
    sender: UserData
    installation: InstallationData
    changes: Optional[Dict[str, Any]] = None


class ProvenanceData(BaseModel):
    model_config = ConfigDict(extra="allow")
    payload_digest: str
    source_timestamp: str
    received_at: datetime


class DeadLetterData(BaseModel):
    model_config = ConfigDict(extra="allow")
    reason: str
    error_type: str = ""


class CanonicalIntakeRecord(BaseModel):
    model_config = ConfigDict(extra="allow")
    intake_id: str
    delivery_id: str
    installation_id: int
    repo_full_name: str
    issue_number: int
    action: str
    provenance: ProvenanceData
    state: str
    lifecycle_revision: int = 0
    dispatch_state: Optional[str] = None
    dead_letter: Optional[DeadLetterData] = None
    attempt_count: int = 0

    @classmethod
    def from_webhook(
        cls,
        payload: WebhookPayload,
        delivery_id: str,
        received_at: datetime,
    ) -> "CanonicalIntakeRecord":
        installation_id = payload.installation.id
        repo_full_name = payload.repository.full_name
        issue_number = payload.issue.number

        intake_id = derive_intake_id(installation_id, repo_full_name, issue_number)

        payload_dict = payload.model_dump(mode="json")
        payload_digest = hashlib.sha256(
            json.dumps(payload_dict, sort_keys=True).encode()
        ).hexdigest()

        return cls(
            intake_id=intake_id,
            delivery_id=delivery_id,
            installation_id=installation_id,
            repo_full_name=repo_full_name,
            issue_number=issue_number,
            action=payload.action,
            provenance=ProvenanceData(
                payload_digest=payload_digest,
                source_timestamp=payload.issue.updated_at,
                received_at=received_at,
            ),
            state=payload.issue.state,
            lifecycle_revision=0,
            dispatch_state=None,
            dead_letter=None,
            attempt_count=0,
        )
