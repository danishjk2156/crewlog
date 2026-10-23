"""Ring Partner API webhook verification and parsing.

Ring signs every webhook with HMAC-SHA256 over the *raw request body* and sends
``X-Signature: sha256=<hex>``. We verify against the raw bytes before parsing JSON.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass

SIGNATURE_HEADER = "X-Signature"
_PREFIX = "sha256="


def sign(secret: str, raw_body: bytes) -> str:
    return _PREFIX + hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()


def verify(secret: str, raw_body: bytes, received: str | None) -> bool:
    if not received:
        return False
    try:
        received_b = received.strip().encode("ascii")
    except (AttributeError, UnicodeEncodeError):
        return False
    return hmac.compare_digest(sign(secret, raw_body).encode("ascii"), received_b)


@dataclass
class ParsedWebhook:
    event_id: str
    request_id: str
    type: str
    source_type: str
    device_id: str | None
    sub_type: str | None
    ts_ms: int


class WebhookFormatError(ValueError):
    pass


def parse(raw_body: bytes) -> ParsedWebhook:
    try:
        doc = json.loads(raw_body)
        meta = doc.get("meta") or {}
        data = doc["data"]
        attrs = data.get("attributes") or {}
        source_type = attrs.get("source_type", "devices")
        return ParsedWebhook(
            event_id=str(data["id"]),
            request_id=str(meta.get("request_id", "")),
            type=str(data["type"]),
            source_type=source_type,
            device_id=attrs.get("source") if source_type == "devices" else None,
            sub_type=attrs.get("sub_type"),
            ts_ms=int(attrs["timestamp"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise WebhookFormatError(f"unrecognised Ring webhook payload: {exc}") from exc
