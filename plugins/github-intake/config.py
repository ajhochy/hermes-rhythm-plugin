from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import yaml
from pydantic import BaseModel, ConfigDict


class AllowlistConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    owners: List[str] = []
    repositories: List[str] = []


class WebhookConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    secret_env: str = "GITHUB_INTAKE_WEBHOOK_SECRET"
    max_payload_bytes: int = 1048576
    secret: Optional[str] = None


class RoutingConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    default_board: str = "local-test-board"
    rules: List = []


class RecoveryConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    max_attempts: int = 5
    base_backoff_seconds: float = 1.0
    max_backoff_seconds: float = 300.0


class AuditConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    enabled: bool = True
    redact_body: bool = True


class PluginConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    plugin: str = "github-intake"
    enabled: bool = False
    dry_run: bool = True
    kill_switch: bool = False
    webhook: WebhookConfig = WebhookConfig()
    allowlist: AllowlistConfig = AllowlistConfig()
    routing: RoutingConfig = RoutingConfig()
    recovery: RecoveryConfig = RecoveryConfig()
    audit: AuditConfig = AuditConfig()

    def __repr__(self) -> str:
        return (
            f"PluginConfig(plugin={self.plugin!r}, enabled={self.enabled}, "
            f"dry_run={self.dry_run}, kill_switch={self.kill_switch})"
        )

    def __str__(self) -> str:
        return self.__repr__()


def load_config(path) -> PluginConfig:
    with open(path) as f:
        data = yaml.safe_load(f)
    cfg = PluginConfig.model_validate(data)
    cfg = cfg.model_copy(update={"webhook": cfg.webhook.model_copy(update={"secret": None})})
    return cfg
