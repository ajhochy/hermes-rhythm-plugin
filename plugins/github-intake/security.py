from __future__ import annotations

import hashlib
import hmac
from typing import Optional


class MissingSignature(Exception):
    pass


class PayloadTooLarge(Exception):
    pass


class AllowlistViolation(Exception):
    pass


def verify_signature(
    body: bytes,
    signature_header: Optional[str],
    secret: str,
) -> bool:
    if signature_header is None:
        raise MissingSignature("X-Hub-Signature-256 header is missing")
    if not signature_header:
        return False
    if not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    provided = signature_header[len("sha256="):]
    return hmac.compare_digest(expected, provided)


def validate_payload_size(body: bytes, max_bytes: int) -> None:
    if len(body) > max_bytes:
        raise PayloadTooLarge(
            f"Payload size {len(body)} exceeds maximum {max_bytes} bytes"
        )


def check_allowlist(owner: str, repo_full_name: str, allowlist) -> bool:
    if owner not in allowlist.owners:
        return False
    if repo_full_name not in allowlist.repositories:
        return False
    return True
