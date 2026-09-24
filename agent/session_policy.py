"""Frozen, provider-neutral authorization for a single native agent session.

A trusted session constructor supplies the binding.  Provider data never supplies
or discovers that authority, and a snapshot never learns it on first use.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
import re
import stat
from pathlib import Path
from typing import Any, Mapping, Sequence
import threading


class UnsupportedPolicy(ValueError):
    """The provider requested semantics this native runtime cannot enforce."""


def _rhythm_wildcard_match(value: str, pattern: str) -> bool:
    """Match the scalar semantics of Rhythm's util/wildcard.ts.

    The canonical matcher normalizes slashes, treats brackets literally,
    allows newlines in wildcards and makes a final ``" *"`` optional. Its
    structured command matcher is a separate policy form and is not accepted
    as an N0 scalar rule.
    """
    value = value.replace("\\", "/")
    pattern = pattern.replace("\\", "/")
    optional_tail = pattern.endswith(" *")
    body = pattern[:-2] if optional_tail else pattern
    regex = re.escape(body).replace(r"\*", ".*").replace(r"\?", ".")
    if optional_tail:
        regex += r"(?: .*)?"
    flags = re.DOTALL | (re.IGNORECASE if os.name == "nt" else 0)
    return re.fullmatch(regex, value, flags=flags) is not None


def _canonical_path_pattern(pattern: str) -> str:
    """Keep realpath confinement while refusing globs we cannot resolve.

    N0 supports a global ``*``, an exact absolute path, or a single trailing
    ``/*`` under a canonical directory. Mid-path wildcards and ``?`` cannot
    be safely realpathed, so they fail before a native session starts.
    """
    if pattern == "*":
        return pattern
    if "\x00" in pattern or (os.name != "nt" and "\\" in pattern):
        raise UnsupportedPolicy("unsupported path pattern")
    if not os.path.isabs(pattern) or "?" in pattern:
        raise UnsupportedPolicy("unsupported path pattern")
    if pattern.endswith("/*"):
        prefix = pattern[:-2] or os.path.sep
        if "*" in prefix:
            raise UnsupportedPolicy("unsupported path pattern")
        _reject_symlink_components(prefix)
        return os.path.realpath(prefix).rstrip(os.path.sep) + "/*"
    if "*" in pattern:
        raise UnsupportedPolicy("unsupported path pattern")
    _reject_symlink_components(pattern)
    return os.path.realpath(pattern)


def _reject_symlink_components(anchor: str) -> None:
    """Refuse an anchor that can be redirected by retargeting a symlink.

    Check both at snapshot construction and at dispatch. An ordinary
    directory replacement keeps the same lexical grant; a symlink replacement
    causes UnsupportedPolicy and the mandatory guard refuses the operation.
    The following realpath + use still has filesystem TOCTOU limits; this is
    not descriptor-root confinement.
    """
    path = Path(anchor)
    for component in (*reversed(path.parents), path):
        try:
            mode = os.lstat(component).st_mode
        except (FileNotFoundError, NotADirectoryError):
            continue  # A future write path may not exist yet.
        except OSError as exc:
            raise UnsupportedPolicy("unverifiable path pattern anchor") from exc
        if stat.S_ISLNK(mode):
            raise UnsupportedPolicy("symlink path pattern anchor")


def _fields(value: Any, expected: set[str], required: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != expected and (set(value) - expected or required - set(value)):
        raise UnsupportedPolicy(f"unsupported {label} shape")
    return value


def _text(value: Any, label: str, limit: int = 4096) -> str:
    if not isinstance(value, str) or not value or len(value) > limit:
        raise UnsupportedPolicy(f"invalid {label}")
    return value


@dataclass(frozen=True)
class PolicyBinding:
    session_id: str
    owner_id: str
    profile_id: str
    runtime_generation: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "PolicyBinding":
        fields = {"session_id", "owner_id", "profile_id", "runtime_generation"}
        data = _fields(value, fields, fields, "binding")
        return cls(**{field: _text(data[field], f"binding {field}", 256) for field in fields})


@dataclass(frozen=True)
class PolicySource:
    agent_id: str
    revision: int


@dataclass(frozen=True)
class PolicyModel:
    provider: str
    model: str
    reasoning: str


@dataclass(frozen=True)
class PolicyRule:
    tool: str
    argument: str
    pattern: str
    effect: str


@dataclass(frozen=True)
class PolicyDecision:
    effect: str

    @property
    def requires_approval(self) -> bool:
        return self.effect == "ask"


@dataclass(frozen=True)
class SessionPolicySnapshot:
    version: int
    source: PolicySource
    instructions: str
    model: PolicyModel
    allowed_tools: tuple[str, ...] | None
    rules: tuple[PolicyRule, ...]
    binding: PolicyBinding

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any], *, binding: Mapping[str, Any]) -> "SessionPolicySnapshot":
        # Validate trusted authority before even examining provider data.
        bound = PolicyBinding.from_mapping(binding)
        data = _fields(payload, {"version", "source", "instructions", "model", "allowed_tools", "rules"},
                       {"version", "source", "instructions", "model", "allowed_tools", "rules"}, "policy")
        if type(data["version"]) is not int or data["version"] != 1:
            raise UnsupportedPolicy("unsupported policy version")
        source = _fields(data["source"], {"agent_id", "revision"}, {"agent_id", "revision"}, "source")
        if type(source["revision"]) is not int or source["revision"] < 0:
            raise UnsupportedPolicy("invalid source revision")
        model = _fields(data["model"], {"provider", "model", "reasoning"},
                        {"provider", "model", "reasoning"}, "model")
        tools = data["allowed_tools"]
        if tools is not None:
            if not isinstance(tools, (list, tuple)) or len(tools) > 128:
                raise UnsupportedPolicy("invalid allowed tools")
            tools = tuple(_text(t, "tool name", 128) for t in tools)
            if len(set(tools)) != len(tools):
                raise UnsupportedPolicy("duplicate allowed tool")
        raw_rules = data["rules"]
        if not isinstance(raw_rules, (list, tuple)) or len(raw_rules) > 256:
            raise UnsupportedPolicy("invalid policy rules")
        rules = []
        for raw in raw_rules:
            r = _fields(raw, {"tool", "argument", "pattern", "effect"},
                        {"tool", "argument", "pattern", "effect"}, "rule")
            tool = _text(r["tool"], "rule tool", 128)
            argument = _text(r["argument"], "rule argument", 128)
            if (tool, argument) not in {("terminal", "command"), ("read_file", "path"),
                                        ("write_file", "path"), ("edit_file", "path")}:
                raise UnsupportedPolicy("unsupported policy rule target")
            effect = r["effect"]
            if effect not in ("allow", "ask", "deny"):
                raise UnsupportedPolicy("unsupported policy rule effect")
            pattern = _text(r["pattern"], "rule pattern")
            if pattern.count("*") + pattern.count("?") > 64:
                raise UnsupportedPolicy("unsupported policy pattern complexity")
            if argument == "path":
                _canonical_path_pattern(pattern)
            rules.append(PolicyRule(tool, argument, pattern, effect))
        return cls(1, PolicySource(_text(source["agent_id"], "source ID", 256), source["revision"]),
                   _text(data["instructions"], "instructions", 65536),
                   PolicyModel(*(_text(model[name], f"model {name}", 256)
                                 for name in ("provider", "model", "reasoning"))), tools,
                   tuple(rules), bound)

    def _check_binding(self, binding: Mapping[str, Any]) -> None:
        if PolicyBinding.from_mapping(binding) != self.binding:
            raise UnsupportedPolicy("policy binding mismatch")

    def to_mapping(self) -> dict[str, Any]:
        """Return only immutable policy data for native session persistence."""
        return {
            "version": self.version,
            "source": {"agent_id": self.source.agent_id, "revision": self.source.revision},
            "instructions": self.instructions,
            "model": {"provider": self.model.provider, "model": self.model.model,
                      "reasoning": self.model.reasoning},
            "allowed_tools": list(self.allowed_tools) if self.allowed_tools is not None else None,
            "rules": [vars(rule).copy() for rule in self.rules],
        }

    def filter_tool_schemas(self, native: Sequence[Mapping[str, Any]], *, binding: Mapping[str, Any]) -> list[dict[str, Any]]:
        self._check_binding(binding)
        if len(native) > 1024:
            raise UnsupportedPolicy("invalid native tool catalog")
        return [dict(tool) for tool in native
                if not self.blocks_native_tool(str(tool.get("name") or tool.get("function", {}).get("name") or ""))
                and (self.allowed_tools is None or
                     (tool.get("name") or tool.get("function", {}).get("name")) in self.allowed_tools)]

    @staticmethod
    def blocks_native_tool(name: str) -> bool:
        return (name.startswith("skills_") or name.startswith("delegate_") or
                name.startswith("subagent_") or name in {"skill", "load_skill", "skill_manage", "delegate", "execute_code"})

    @staticmethod
    def native_tool_schemas(native: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        return [dict(tool) for tool in native]

    def authorize_tool_call(self, *, tool_name: str, arguments: Mapping[str, Any],
                            binding: Mapping[str, Any], final_arguments: Mapping[str, Any] | None = None) -> PolicyDecision:
        self._check_binding(binding)
        args = final_arguments if final_arguments is not None else arguments
        if not isinstance(args, Mapping) or len(str(args)) > 65536:
            raise UnsupportedPolicy("invalid policy tool input")
        if self.allowed_tools is not None and tool_name not in self.allowed_tools:
            return PolicyDecision("deny")
        # N0 has no delegation roster or skill grant.  Never inherit these.
        if self.blocks_native_tool(tool_name):
            return PolicyDecision("deny")
        effect = "deny" if any(rule.tool == tool_name for rule in self.rules) else "allow"
        for rule in self.rules:
            if rule.tool == tool_name:
                value = args.get(rule.argument)
                if not isinstance(value, str):
                    return PolicyDecision("deny")
                if rule.argument == "path":
                    value = os.path.realpath(value)
                    pattern = _canonical_path_pattern(rule.pattern)
                else:
                    pattern = rule.pattern
                if _rhythm_wildcard_match(value, pattern):
                    effect = rule.effect
        return PolicyDecision(effect)


# Registered by a trusted plugin inside the native process. The RPC supplies
# only an opaque selection; the provider authenticates its transport and returns
# the owner identity along with the policy data. No caller-supplied owner field
# is ever accepted as authority.
_provider_lock = threading.RLock()
_provider = None


def register_session_policy_provider(provider):
    global _provider
    with _provider_lock:
        if _provider is not None:
            raise UnsupportedPolicy("session policy provider already registered")
        _provider = provider

    def dispose():
        global _provider
        with _provider_lock:
            if _provider is provider:
                _provider = None

    return dispose


def resolve_session_policy(selection: str, *, session_id: str, profile_id: str,
                           runtime_generation: str, transport) -> SessionPolicySnapshot:
    _text(selection, "policy selection", 1024)
    with _provider_lock:
        provider = _provider
    if provider is None:
        raise UnsupportedPolicy("session policy provider unavailable")
    try:
        payload, owner_id = provider.resolve(
            selection, session_id=session_id, profile_id=profile_id,
            runtime_generation=runtime_generation, transport=transport,
        )
        binding = {"session_id": session_id, "owner_id": owner_id,
                   "profile_id": profile_id, "runtime_generation": runtime_generation}
        return SessionPolicySnapshot.from_mapping(payload, binding=binding)
    except Exception as exc:
        raise UnsupportedPolicy("session policy resolution failed") from exc
