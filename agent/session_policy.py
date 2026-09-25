"""Frozen, provider-neutral authorization for one native agent session."""
from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
import copy
import json
import os
import re
import stat
from pathlib import Path
from typing import Any, Mapping, Sequence
import threading


class UnsupportedPolicy(ValueError):
    def __init__(self, code: str, message: str = ""):
        self.code = code
        super().__init__(message or code)


POLICY_REASON_CODES = frozenset({
    "permission_shape_unsupported", "external_directory_pattern_unsupported",
    "oc_agent_unsupported", "account_binding_unmapped",
    "instructions_blocked_by_scanner", "model_unpinned",
    "model_provider_unmapped", "reasoning_invalid",
    "terminal_backend_unsupported", "agent_id_unsupported", "agent_locked",
    "agent_disabled", "agent_not_runnable", "viewer_unauthenticated",
    "runtime_unowned", "bridge_unavailable", "runtime_not_connected",
    "runtime_not_reported", "model_provider_unavailable",
    "launch_kind_not_allowed", "executor_not_ready", "policy_shape_invalid",
    "mcp_inherit_restricted", "mcp_unmapped", "skills_not_applied",
    "path_pattern_inert", "permission_key_not_applied", "write_permission_inert",
    "process_tool_not_applied", "image_generation_not_applied",
    "auto_approve_not_applied", "model_tier_hint_ignored",
    "schedulable_not_applied", "ask_headless_denied",
    "revision_newer_than_session",
    "projection_version_unsupported", "selection_invalid", "profile_unsupported",
    "transport_not_allowed", "revision_conflict", "projection_unsupported",
    "job_not_claimed", "lease_invalid", "target_revision_changed", "cwd_mismatch",
    "cwd_invalid", "session_key_reused", "binding_mismatch",
    "provider_runtime_mismatch", "projection_revoked", "rate_limited",
    "provider_failed",
})


def policy_error_code(exc: BaseException | None, default: str = "provider_failed") -> str:
    """Return only SA-v1 reason codes; arbitrary provider text never escapes."""
    code = getattr(exc, "code", None)
    if isinstance(code, str) and code in POLICY_REASON_CODES:
        return code
    return default if default in POLICY_REASON_CODES else "provider_failed"


def unsupported_policy_message(exc: BaseException | None, default: str = "provider_failed") -> tuple[str, str]:
    code = policy_error_code(exc, default)
    return f"unsupported_policy:{code}", code


def _rhythm_wildcard_match(value: str, pattern: str) -> bool:
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
    path = Path(anchor)
    for component in (*reversed(path.parents), path):
        try:
            mode = os.lstat(component).st_mode
        except (FileNotFoundError, NotADirectoryError):
            continue
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


def _v2_invalid(message: str = "") -> UnsupportedPolicy:
    return UnsupportedPolicy("policy_shape_invalid", message)


def _v2_fields(value: Any, expected: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != expected:
        raise _v2_invalid(f"invalid {label}")
    return value


def _v2_text(value: Any, label: str, limit: int, *, empty: bool = False) -> str:
    if not isinstance(value, str) or (not empty and not value) or len(value) > limit or "\x00" in value:
        raise _v2_invalid(f"invalid {label}")
    return value


def _absolute_realpath(value: Any, label: str) -> str:
    text = _v2_text(value, label, 1024)
    if not os.path.isabs(text) or os.path.realpath(text) != text:
        raise _v2_invalid(f"invalid {label}")
    return text


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
    reference: str | None = None


@dataclass(frozen=True)
class PolicyModel:
    provider: str
    model: str
    reasoning: str | None


@dataclass(frozen=True)
class PolicyRule:
    tool: str
    argument: str
    pattern: str
    effect: str


@dataclass(frozen=True)
class PolicyPaths:
    root: str
    boundary: tuple[str, ...]
    external: str
    protected: tuple[str, ...]


@dataclass(frozen=True)
class PolicyTaintGate:
    sources: tuple[str, ...]
    gated: tuple[str, ...]


@dataclass(frozen=True)
class PolicyLaunch:
    kind: str
    cwd: str | None


@dataclass(frozen=True)
class PolicyDecision:
    effect: str

    @property
    def requires_approval(self) -> bool:
        return self.effect == "ask"


_STRICTNESS = {"allow": 0, "ask": 1, "deny": 2}
_PATH_TOOLS = {"read_file", "write_file", "patch", "search_files"}
_CWD_COMMANDS = {"cd", "chdir", "popd", "pushd", "push-location", "set-location"}
_FILE_COMMANDS = _CWD_COMMANDS | {"rm", "cp", "mv", "mkdir", "touch", "chmod", "chown", "cat"}
_RESERVED = {"if", "then", "else", "elif", "fi", "for", "while", "until", "do", "done", "case", "esac", "select", "function", "time", "!", "{", "}", "[["}
_active_policy: ContextVar[tuple["SessionPolicySnapshot", str] | None] = ContextVar("native_session_policy", default=None)


def bind_active_policy(snapshot: "SessionPolicySnapshot", lineage_root: str):
    return _active_policy.set((snapshot, lineage_root))


def reset_active_policy(token) -> None:
    _active_policy.reset(token)


def current_policy() -> tuple["SessionPolicySnapshot", str] | None:
    return _active_policy.get()


def policy_scoped_tool_available(
    tool_name: str,
    snapshot: "SessionPolicySnapshot" | None = None,
) -> bool:
    """Return whether a policy-scoped tool belongs to a bound v2 snapshot."""
    if snapshot is None:
        active = current_policy()
        snapshot = active[0] if active is not None else None
    return bool(
        isinstance(snapshot, SessionPolicySnapshot)
        and snapshot.version == 2
        and snapshot.allowed_tools is not None
        and tool_name in snapshot.allowed_tools
    )


def _strictest(*effects: str) -> str:
    return max(effects, key=_STRICTNESS.__getitem__)


def _under(path: str, directory: str) -> bool:
    if directory == os.path.sep:
        return True
    directory = directory.rstrip(os.path.sep)
    return path == directory or path.startswith(directory + os.path.sep)


@dataclass(frozen=True)
class SessionPolicySnapshot:
    version: int
    source: PolicySource
    instructions: str | None
    model: PolicyModel
    allowed_tools: tuple[str, ...] | None
    rules: tuple[PolicyRule, ...]
    binding: PolicyBinding
    tool_effects: tuple[tuple[str, str], ...] = ()
    paths: PolicyPaths | None = None
    taint_gate: PolicyTaintGate | None = None
    launch: PolicyLaunch | None = None
    restored_tainted: bool = False
    persistence_extras: Mapping[str, Any] | None = None

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any], *, binding: Mapping[str, Any]) -> "SessionPolicySnapshot":
        bound = PolicyBinding.from_mapping(binding)
        if not isinstance(payload, Mapping):
            raise _v2_invalid("invalid policy")
        version = payload.get("version")
        if version == 2:
            return cls._from_v2(payload, bound)
        if version == 1:
            return cls._from_v1(payload, bound)
        if "version" not in payload:
            raise UnsupportedPolicy("policy_shape_invalid")
        raise UnsupportedPolicy("projection_version_unsupported")

    @classmethod
    def _from_v1(cls, payload: Mapping[str, Any], bound: PolicyBinding) -> "SessionPolicySnapshot":
        data = _fields(payload, {"version", "source", "instructions", "model", "allowed_tools", "rules"}, {"version", "source", "instructions", "model", "allowed_tools", "rules"}, "policy")
        if type(data["version"]) is not int or data["version"] != 1:
            raise UnsupportedPolicy("unsupported policy version")
        source = _fields(data["source"], {"agent_id", "revision"}, {"agent_id", "revision"}, "source")
        if type(source["revision"]) is not int or source["revision"] < 0:
            raise UnsupportedPolicy("invalid source revision")
        model = _fields(data["model"], {"provider", "model", "reasoning"}, {"provider", "model", "reasoning"}, "model")
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
            r = _fields(raw, {"tool", "argument", "pattern", "effect"}, {"tool", "argument", "pattern", "effect"}, "rule")
            tool = _text(r["tool"], "rule tool", 128)
            argument = _text(r["argument"], "rule argument", 128)
            if (tool, argument) not in {("terminal", "command"), ("read_file", "path"), ("write_file", "path"), ("edit_file", "path")}:
                raise UnsupportedPolicy("unsupported policy rule target")
            effect = r["effect"]
            if effect not in _STRICTNESS:
                raise UnsupportedPolicy("unsupported policy rule effect")
            pattern = _text(r["pattern"], "rule pattern")
            if pattern.count("*") + pattern.count("?") > 64:
                raise UnsupportedPolicy("unsupported policy pattern complexity")
            if argument == "path":
                _canonical_path_pattern(pattern)
            rules.append(PolicyRule(tool, argument, pattern, effect))
        return cls(1, PolicySource(_text(source["agent_id"], "source ID", 256), source["revision"]), _text(data["instructions"], "instructions", 65536), PolicyModel(*(_text(model[name], f"model {name}", 256) for name in ("provider", "model", "reasoning"))), tools, tuple(rules), bound)

    @classmethod
    def _from_v2(cls, payload: Mapping[str, Any], bound: PolicyBinding) -> "SessionPolicySnapshot":
        data = _v2_fields(payload, {"version", "source", "instructions", "model", "allowed_tools", "tool_effects", "paths", "rules", "taint_gate", "launch"}, "policy")
        source = _v2_fields(data["source"], {"agent_id", "revision", "reference"}, "source")
        if type(data["version"]) is not int or data["version"] != 2 or type(source["revision"]) is not int or source["revision"] < 0:
            raise _v2_invalid("invalid version or source")
        parsed_source = PolicySource(_v2_text(source["agent_id"], "source agent_id", 256), source["revision"], _v2_text(source["reference"], "source reference", 256))
        instructions = data["instructions"]
        if instructions is not None:
            instructions = _v2_text(instructions, "instructions", 65536, empty=True)
        model = _v2_fields(data["model"], {"provider", "model", "reasoning"}, "model")
        reasoning = model["reasoning"]
        if reasoning is not None:
            reasoning = _v2_text(reasoning, "model reasoning", 256)
            from hermes_constants import parse_reasoning_effort
            if parse_reasoning_effort(reasoning) is None:
                raise UnsupportedPolicy("reasoning_invalid")
        parsed_model = PolicyModel(_v2_text(model["provider"], "model provider", 256), _v2_text(model["model"], "model model", 256), reasoning)
        raw_tools = data["allowed_tools"]
        if not isinstance(raw_tools, (list, tuple)) or len(raw_tools) > 256:
            raise _v2_invalid("invalid allowed_tools")
        tools = tuple(_v2_text(tool, "tool name", 128) for tool in raw_tools)
        if len(set(tools)) != len(tools) or any(cls.blocks_native_tool(tool) for tool in tools):
            raise _v2_invalid("invalid allowed_tools")
        raw_effects = data["tool_effects"]
        if not isinstance(raw_effects, Mapping) or any(key not in tools or value not in {"allow", "ask"} for key, value in raw_effects.items()):
            raise _v2_invalid("invalid tool_effects")
        paths = _v2_fields(data["paths"], {"root", "boundary", "external", "protected"}, "paths")
        boundary, protected = paths["boundary"], paths["protected"]
        if not isinstance(boundary, (list, tuple)) or len(boundary) > 4 or not isinstance(protected, (list, tuple)) or len(protected) > 16 or paths["external"] not in _STRICTNESS:
            raise _v2_invalid("invalid paths")
        parsed_paths = PolicyPaths(_absolute_realpath(paths["root"], "paths root"), tuple(_absolute_realpath(v, "boundary") for v in boundary), paths["external"], tuple(_absolute_realpath(v, "protected") for v in protected))
        raw_rules = data["rules"]
        if not isinstance(raw_rules, (list, tuple)) or len(raw_rules) > 512:
            raise _v2_invalid("invalid rules")
        rules = []
        for raw in raw_rules:
            rule = _v2_fields(raw, {"tool", "argument", "pattern", "effect"}, "rule")
            tool = _v2_text(rule["tool"], "rule tool", 128)
            argument = _v2_text(rule["argument"], "rule argument", 128)
            pattern = _v2_text(rule["pattern"], "rule pattern", 4096, empty=True)
            if tool not in tools or rule["effect"] not in _STRICTNESS or pattern.count("*") + pattern.count("?") > 64:
                raise _v2_invalid("invalid rule")
            if tool in _PATH_TOOLS and (argument != "path" or pattern != "*" and os.path.isabs(pattern)):
                raise _v2_invalid("invalid path rule")
            if tool == "terminal" and argument != "command":
                raise _v2_invalid("invalid terminal rule")
            rules.append(PolicyRule(tool, argument, pattern, rule["effect"]))
        taint = _v2_fields(data["taint_gate"], {"sources", "gated"}, "taint_gate")
        for key in ("sources", "gated"):
            if not isinstance(taint[key], (list, tuple)) or len(set(taint[key])) != len(taint[key]) or any(name not in tools for name in taint[key]):
                raise _v2_invalid("invalid taint_gate")
        launch = _v2_fields(data["launch"], {"kind", "cwd"}, "launch")
        if launch["kind"] not in {"interactive", "delegated"}:
            raise _v2_invalid("invalid launch kind")
        launch_cwd = None if launch["cwd"] is None else _absolute_realpath(launch["cwd"], "launch cwd")
        return cls(2, parsed_source, instructions, parsed_model, tools, tuple(rules), bound, tuple((str(k), str(v)) for k, v in raw_effects.items()), parsed_paths, PolicyTaintGate(tuple(taint["sources"]), tuple(taint["gated"])), PolicyLaunch(launch["kind"], launch_cwd))

    def _check_binding(self, binding: Mapping[str, Any], *, lineage_root: str | None = None) -> None:
        candidate = PolicyBinding.from_mapping(binding)
        if lineage_root is not None and self.version == 2:
            candidate = PolicyBinding(lineage_root, candidate.owner_id, candidate.profile_id, candidate.runtime_generation)
        if candidate != self.binding:
            raise UnsupportedPolicy("binding_mismatch" if self.version == 2 else "policy binding mismatch")

    def to_mapping(self) -> dict[str, Any]:
        base = {"version": self.version, "source": {"agent_id": self.source.agent_id, "revision": self.source.revision}, "instructions": self.instructions, "model": {"provider": self.model.provider, "model": self.model.model, "reasoning": self.model.reasoning}, "allowed_tools": list(self.allowed_tools) if self.allowed_tools is not None else None, "rules": [vars(rule).copy() for rule in self.rules]}
        if self.version == 1:
            return base
        base["source"]["reference"] = self.source.reference
        base["tool_effects"] = dict(self.tool_effects)
        base["paths"] = {"root": self.paths.root, "boundary": list(self.paths.boundary), "external": self.paths.external, "protected": list(self.paths.protected)}
        base["taint_gate"] = {"sources": list(self.taint_gate.sources), "gated": list(self.taint_gate.gated)}
        base["launch"] = {"kind": self.launch.kind, "cwd": self.launch.cwd}
        return base

    def filter_tool_schemas(self, native: Sequence[Mapping[str, Any]], *, binding: Mapping[str, Any]) -> list[dict[str, Any]]:
        self._check_binding(binding, lineage_root=self.binding.session_id if self.version == 2 else None)
        if len(native) > 1024:
            raise UnsupportedPolicy("policy_shape_invalid" if self.version == 2 else "invalid native tool catalog")
        return [dict(tool) for tool in native if not self._blocks_tool(str(tool.get("name") or tool.get("function", {}).get("name") or "")) and (self.allowed_tools is None or (tool.get("name") or tool.get("function", {}).get("name")) in self.allowed_tools)]

    @staticmethod
    def blocks_native_tool(name: str) -> bool:
        return name in {"delegate_task", "delegate", "execute_code", "skill", "skill_view", "skill_manage", "load_skill", "memory", "session_search", "cronjob", "send_message", "process", "vision_analyze", "text_to_speech", "image_generate"} or name.startswith(("delegate_", "subagent_", "skills_", "browser_", "ha_", "mcp__"))

    def _blocks_tool(self, name: str) -> bool:
        if self.version == 2:
            return self.blocks_native_tool(name)
        return (
            name in {"skill", "load_skill", "skill_manage", "delegate", "execute_code"}
            or name.startswith(("skills_", "delegate_", "subagent_"))
        )

    def persistence_entry(self, *, tainted: bool = False) -> dict[str, Any]:
        """Build the durable entry used by initial and compression child rows."""
        entry = copy.deepcopy(dict(self.persistence_extras or {}))
        entry.update({
            "payload": self.to_mapping(),
            "owner_id": self.binding.owner_id,
            "profile_id": self.binding.profile_id,
        })
        if self.version == 2:
            entry.update({
                "lineage_root": self.binding.session_id,
                "tainted": bool(tainted or self.restored_tainted),
            })
        return entry

    @staticmethod
    def native_tool_schemas(native: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        return [dict(tool) for tool in native]

    def taints(self, tool_name: str) -> bool:
        return self.version == 2 and tool_name in self.taint_gate.sources

    def _last_match(self, rules: Sequence[PolicyRule], value: str) -> str:
        effect = "deny"
        for rule in rules:
            if _rhythm_wildcard_match(value, rule.pattern):
                effect = rule.effect
        return effect

    def _path_gate(self, path: str) -> str:
        from hermes_constants import get_hermes_home
        if any(_under(path, item) for item in (*self.paths.protected, os.path.realpath(str(get_hermes_home())))):
            return "deny"
        if not any(_under(path, item) for item in self.paths.boundary):
            return self.paths.external
        return "allow"

    def _argument_gate(self, value: str, cwd: str) -> str:
        if any(char in value for char in "$*?~`"):
            return "ask"
        return self._path_gate(os.path.realpath(os.path.join(cwd, value)))

    def _redirection_effect(self, command: str, cwd: str) -> tuple[str, bool]:
        """Gate unquoted shell redirect targets and flag malformed grammar."""
        effect = "allow"
        uncertain = False
        index = 0
        quote = None
        escaped = False
        operators = ("&>>", "&>", "<<<", "<<", "<>", ">>", ">|", "<&", ">&", ">", "<")
        while index < len(command):
            char = command[index]
            if escaped:
                escaped = False
                index += 1
                continue
            if char == "\\" and quote != "'":
                escaped = True
                index += 1
                continue
            if quote:
                if char == quote:
                    quote = None
                index += 1
                continue
            if char in {"'", '"'}:
                quote = char
                index += 1
                continue
            start = index
            if char.isdigit() and (index == 0 or command[index - 1].isspace() or command[index - 1] in ";|&"):
                while index < len(command) and command[index].isdigit():
                    index += 1
            operator = next((op for op in operators if command.startswith(op, index)), None)
            if operator is None:
                index = start + 1
                continue
            index += len(operator)
            if operator in {"<<", "<<<"}:
                uncertain = True
            while index < len(command) and command[index].isspace():
                index += 1
            target_start = index
            target_quote = None
            target_escaped = False
            while index < len(command):
                current = command[index]
                if target_escaped:
                    target_escaped = False
                elif current == "\\" and target_quote != "'":
                    target_escaped = True
                elif target_quote:
                    if current == target_quote:
                        target_quote = None
                elif current in {"'", '"'}:
                    target_quote = current
                elif current.isspace() or current in ";|&<>":
                    break
                index += 1
            raw_target = command[target_start:index]
            if not raw_target or target_quote:
                uncertain = True
                continue
            try:
                import shlex
                parsed = shlex.split(raw_target, posix=True)
            except ValueError:
                parsed = []
            if len(parsed) != 1:
                uncertain = True
                continue
            target = parsed[0]
            if not re.fullmatch(r"&\d+", target) and target != "/dev/null":
                effect = _strictest(effect, self._argument_gate(target, cwd))
        return effect, uncertain

    def _terminal_effect(self, arguments: Mapping[str, Any], task_id: str, rules: Sequence[PolicyRule]) -> str:
        from tools.approval import _command_parser_limit_exceeded, _iter_top_level_shell_segments, _shell_segment_tokens
        from tools.file_tools import _resolve_base_dir
        command = arguments.get("command")
        if not isinstance(command, str) or _command_parser_limit_exceeded(command):
            return "deny"
        cwd = str(_resolve_base_dir(task_id))
        effect = "allow"
        floor = "ask" if any(marker in command for marker in ("$(", "`", "<(", ">(", "<<")) else "allow"
        workdir = arguments.get("workdir")
        if workdir:
            if not isinstance(workdir, str):
                return "deny"
            expanded_workdir = os.path.expanduser(workdir)
            cwd = os.path.realpath(os.path.join(cwd, expanded_workdir))
            effect = _strictest(effect, self._path_gate(cwd))
        redirect_effect, uncertain_redirect = self._redirection_effect(command, cwd)
        effect = _strictest(effect, redirect_effect)
        if uncertain_redirect:
            floor = "ask"
        for segment in _iter_top_level_shell_segments(command):
            text = segment.strip()
            if not text:
                continue
            tokens = _shell_segment_tokens(text, 0)
            if tokens is None:
                floor = "ask"
                effect = _strictest(effect, self._last_match(rules, text))
                continue
            if tokens and (tokens[0] in _RESERVED or tokens[0].startswith("(")):
                floor = "ask"
            words, index = [], 0
            while index < len(tokens):
                token = tokens[index]
                if token in {">", ">>", "<", "&>"} or re.fullmatch(r"\d+>", token):
                    if index + 1 < len(tokens):
                        target = tokens[index + 1]
                        if not re.fullmatch(r"&\d+", target) and target != "/dev/null":
                            effect = _strictest(effect, self._argument_gate(target, cwd))
                        index += 2
                        continue
                words.append(token)
                index += 1
            had_assignment_prefix = False
            while words and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", words[0]):
                words.pop(0)
                had_assignment_prefix = True
            if not words:
                continue
            command_name = words[0].lower()
            if command_name in _CWD_COMMANDS:
                target = next((word for word in words[1:] if not word.startswith("-")), "~")
                effect = _strictest(effect, self._argument_gate(target, cwd))
                if had_assignment_prefix:
                    floor = "ask"
                elif not any(char in target for char in "$*?~`"):
                    cwd = os.path.realpath(os.path.join(cwd, target))
                continue
            effect = _strictest(effect, self._last_match(rules, text))
            if command_name in _FILE_COMMANDS:
                args = [word for word in words[1:] if not word.startswith("-")]
                if command_name == "chmod":
                    args = [word for word in args if not word.startswith("+")]
                for arg in args:
                    effect = _strictest(effect, self._argument_gate(arg, cwd))
        return _strictest(effect, floor)

    def authorize_tool_call(self, *, tool_name: str, arguments: Mapping[str, Any], binding: Mapping[str, Any], task_id: str = "default", tainted: bool = False, lineage_root: str | None = None, final_arguments: Mapping[str, Any] | None = None) -> PolicyDecision:
        self._check_binding(binding, lineage_root=lineage_root)
        args = final_arguments if final_arguments is not None else arguments
        if not isinstance(args, Mapping) or len(str(args)) > 65536:
            raise UnsupportedPolicy("policy_shape_invalid" if self.version == 2 else "invalid policy tool input")
        if self.allowed_tools is not None and tool_name not in self.allowed_tools or self._blocks_tool(tool_name):
            return PolicyDecision("deny")
        if self.version == 1:
            effect = "deny" if any(rule.tool == tool_name for rule in self.rules) else "allow"
            for rule in self.rules:
                if rule.tool == tool_name:
                    value = args.get(rule.argument)
                    if not isinstance(value, str):
                        return PolicyDecision("deny")
                    pattern = rule.pattern
                    if rule.argument == "path":
                        value, pattern = os.path.realpath(value), _canonical_path_pattern(pattern)
                    if _rhythm_wildcard_match(value, pattern):
                        effect = rule.effect
            return PolicyDecision(effect)
        effect = dict(self.tool_effects).get(tool_name, "allow")
        rules = tuple(rule for rule in self.rules if rule.tool == tool_name)
        if tool_name in _PATH_TOOLS:
            if tool_name == "patch" and args.get("mode", "replace") != "replace":
                return PolicyDecision("deny")
            raw = args.get("path", "." if tool_name == "search_files" else None)
            if not isinstance(raw, str):
                return PolicyDecision("deny")
            from tools.file_tools import _resolve_path_for_task, _uses_container_paths
            if _uses_container_paths(task_id):
                return PolicyDecision("deny")
            path = os.path.realpath(str(_resolve_path_for_task(raw, task_id)))
            effect = _strictest(effect, self._path_gate(path), self._last_match(rules, os.path.relpath(path, self.paths.root)))
        elif tool_name == "terminal":
            effect = _strictest(effect, self._terminal_effect(args, task_id, rules))
        elif rules:
            value = args.get(rules[0].argument)
            if not isinstance(value, str):
                return PolicyDecision("deny")
            effect = _strictest(effect, self._last_match(rules, value))
        if tainted and tool_name in self.taint_gate.gated:
            effect = _strictest(effect, "ask")
        if self.launch.kind == "delegated" and effect == "ask":
            effect = "deny"
        return PolicyDecision(effect)

    def filter_search_result(self, result: Any, *, task_id: str) -> Any:
        """Remove protected/external-denied hits returned beneath an allowed root."""
        if self.version != 2:
            return result
        was_text = isinstance(result, str)
        try:
            data = json.loads(result) if was_text else copy.deepcopy(result)
        except (TypeError, ValueError):
            return result
        if not isinstance(data, dict):
            return result
        from tools.file_tools import _resolve_path_for_task

        def allowed(raw: Any) -> bool:
            if not isinstance(raw, str):
                return False
            try:
                path = os.path.realpath(str(_resolve_path_for_task(raw, task_id)))
            except Exception:
                return False
            return self._path_gate(path) == "allow"

        omitted = 0
        if isinstance(data.get("matches"), list):
            kept = []
            for item in data["matches"]:
                if isinstance(item, dict) and allowed(item.get("path")):
                    kept.append(item)
                else:
                    omitted += 1
            data["matches"] = kept
        if isinstance(data.get("files"), list):
            kept = [path for path in data["files"] if allowed(path)]
            omitted += len(data["files"]) - len(kept)
            data["files"] = kept
        if isinstance(data.get("counts"), dict):
            kept = {path: count for path, count in data["counts"].items() if allowed(path)}
            omitted += len(data["counts"]) - len(kept)
            data["counts"] = kept
        # Dense results cannot be safely separated without re-parsing their
        # display encoding. Refuse the block rather than leak an unverified hit.
        if "matches_text" in data:
            data.pop("matches_text", None)
            data.pop("matches_format", None)
            omitted += 1
        if omitted:
            data["_policy_omitted"] = omitted
        return json.dumps(data, ensure_ascii=False) if was_text else data


_provider_lock = threading.RLock()
_provider = None


def register_session_policy_provider(provider):
    global _provider
    with _provider_lock:
        if _provider is not None:
            raise UnsupportedPolicy("provider_failed", "session policy provider already registered")
        _provider = provider
    def dispose():
        global _provider
        with _provider_lock:
            if _provider is provider:
                _provider = None
    return dispose


def _registered_provider():
    with _provider_lock:
        return _provider


def _provider_failure(exc: Exception) -> UnsupportedPolicy:
    return UnsupportedPolicy(policy_error_code(exc))


def resolve_session_policy(selection: str, *, session_id: str, profile_id: str, runtime_generation: str, transport, cwd: str | None = None) -> SessionPolicySnapshot:
    if not isinstance(selection, str) or not selection or len(selection) > 1024 or "\x00" in selection:
        raise UnsupportedPolicy("selection_invalid")
    provider = _registered_provider()
    if provider is None:
        raise UnsupportedPolicy("provider_failed", "session policy provider unavailable")
    try:
        payload, owner_id = provider.resolve(selection, session_id=session_id, profile_id=profile_id, runtime_generation=runtime_generation, transport=transport, cwd=cwd)
        return SessionPolicySnapshot.from_mapping(payload, binding={"session_id": session_id, "owner_id": owner_id, "profile_id": profile_id, "runtime_generation": runtime_generation})
    except Exception as exc:
        raise _provider_failure(exc) from exc


def restore_session_policy(reference: str, *, lineage_root: str, profile_id: str, runtime_generation: str) -> SessionPolicySnapshot:
    provider = _registered_provider()
    if provider is None:
        raise UnsupportedPolicy("provider_failed")
    try:
        payload, owner_id = provider.restore(reference, lineage_root=lineage_root, profile_id=profile_id)
        snapshot = SessionPolicySnapshot.from_mapping(payload, binding={"session_id": lineage_root, "owner_id": owner_id, "profile_id": profile_id, "runtime_generation": runtime_generation})
        if snapshot.version != 2 or snapshot.source.reference != reference:
            raise UnsupportedPolicy("binding_mismatch")
        return snapshot
    except Exception as exc:
        raise _provider_failure(exc) from exc


def check_session_policy(snapshot: SessionPolicySnapshot, *, lineage_root: str, profile_id: str) -> None:
    if snapshot.version != 2:
        return
    provider = _registered_provider()
    if provider is None:
        raise UnsupportedPolicy("provider_failed")
    try:
        provider.check(snapshot.source.reference, lineage_root=lineage_root, profile_id=profile_id)
    except Exception as exc:
        raise _provider_failure(exc) from exc
