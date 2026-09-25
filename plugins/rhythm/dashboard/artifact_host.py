"""Local-only authority for the vendored ArtifactHostPort.

The shared React artifact receives only the result of ``open`` and can ask for
the two classified state capabilities below.  It never receives an upstream
URL, a filesystem path, credentials, or a transport object.
"""

from __future__ import annotations

import hashlib
import html
import json
import secrets
import threading
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any


_ALLOWED_TAGS = frozenset({"article", "aside", "b", "blockquote", "br", "code", "div", "em", "h1", "h2", "h3", "header", "li", "main", "ol", "p", "pre", "section", "small", "span", "strong", "ul"})
# ``state.update`` is the exact typed capability emitted by shared revision
# 685ab24e; it is the classified state-set operation, not arbitrary storage.
_CAPABILITIES = frozenset({"state.get", "state.update"})
_MAX_TEXT = 32_768


class _SanitizingParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.stack: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag in _ALLOWED_TAGS:
            self.parts.append(f"<{tag}>")
            self.stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag in _ALLOWED_TAGS and tag in self.stack:
            while self.stack:
                current = self.stack.pop()
                self.parts.append(f"</{current}>")
                if current == tag:
                    break

    def handle_data(self, data: str) -> None:
        self.parts.append(html.escape(data, quote=False))

    def value(self) -> str:
        while self.stack:
            self.parts.append(f"</{self.stack.pop()}>")
        return "".join(self.parts)[:_MAX_TEXT]


def sanitize_html(value: object) -> str:
    parser = _SanitizingParser()
    parser.feed(value if isinstance(value, str) else "")
    parser.close()
    return parser.value()


def sanitize_style(value: object) -> str:
    # The shared frame CSP permits only this host-provided style nonce.  Keep
    # the bundle declarative: imports, URLs, and closing tags are removed.
    text = value if isinstance(value, str) else ""
    for forbidden in ("@import", "url(", "</style"):
        text = text.replace(forbidden, "")
    return text[:_MAX_TEXT]


@dataclass
class _ArtifactSession:
    artifact_id: str
    session_id: str
    bundle_generation: str
    state_generation: str = "state-1"
    state: dict[str, Any] = field(default_factory=dict)


_lock = threading.Lock()
_sessions: dict[str, _ArtifactSession] = {}


def open_document(artifact_id: str, body_html: object, style_text: object = "", script_text: object = "") -> dict[str, object]:
    """Mint a short opaque session around a sanitized, script-free bundle."""
    del script_text
    safe_body = sanitize_html(body_html)
    safe_style = sanitize_style(style_text)
    digest = hashlib.sha256(f"{artifact_id}\0{safe_body}\0{safe_style}".encode()).hexdigest()[:24]
    session = _ArtifactSession(artifact_id=artifact_id, session_id=secrets.token_urlsafe(24), bundle_generation=f"bundle-{digest}")
    with _lock:
        _sessions[session.session_id] = session
    return {
        "artifactId": artifact_id,
        "sessionId": session.session_id,
        "bundleGeneration": session.bundle_generation,
        "stateGeneration": session.state_generation,
        "bodyHtml": safe_body,
        "styleText": safe_style,
        "scriptText": "",
        "capabilities": ["state.get", "state.update"],
    }


def receive(artifact_id: str, message: object) -> dict[str, object]:
    """Resolve one classified message without widening upstream authority."""
    if not isinstance(message, dict):
        return {"status": "rejected"}
    session_id = message.get("sessionId")
    capability = message.get("capability")
    if not isinstance(session_id, str) or capability not in _CAPABILITIES:
        return {"status": "rejected"}
    with _lock:
        session = _sessions.get(session_id)
        if session is None or session.artifact_id != artifact_id:
            return {"status": "rejected"}
        if message.get("artifactId") != artifact_id or message.get("bundleGeneration") != session.bundle_generation:
            return {"status": "conflict", "bundleGeneration": session.bundle_generation, "stateGeneration": session.state_generation}
        if message.get("stateGeneration") != session.state_generation:
            return {"status": "conflict", "bundleGeneration": session.bundle_generation, "stateGeneration": session.state_generation}
        if capability == "state.get":
            return {"status": "ok", "payload": {"value": session.state}, "bundleGeneration": session.bundle_generation, "stateGeneration": session.state_generation}
        payload = message.get("payload")
        try:
            encoded = json.dumps(payload, separators=(",", ":"))
        except (TypeError, ValueError):
            return {"status": "rejected"}
        if len(encoded.encode()) > _MAX_TEXT or not isinstance(payload, dict) or set(payload) != {"value"} or not isinstance(payload["value"], dict):
            return {"status": "rejected"}
        session.state = payload["value"]
        session.state_generation = f"state-{int(session.state_generation.removeprefix('state-')) + 1}"
        return {"status": "ok", "payload": {"value": session.state}, "bundleGeneration": session.bundle_generation, "stateGeneration": session.state_generation}
