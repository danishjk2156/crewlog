"""Minimal Ring Partner API client (JSON:API over HTTPS).

Points at ``ring-sandbox`` in development and ``https://api.amazonvision.com`` in
production — only ``RING_API_BASE`` and the OAuth access token change.
"""

from __future__ import annotations

from typing import Any

import httpx

from ..config import settings


class RingClient:
    def __init__(self, base_url: str | None = None, token: str | None = None, timeout: float = 10.0):
        self.base_url = (base_url or settings.ring_api_base).rstrip("/")
        self.token = token or settings.ring_access_token
        self.timeout = timeout

    def _client(self) -> httpx.Client:
        return httpx.Client(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {self.token}", "Accept": "application/vnd.api+json"},
            timeout=self.timeout,
            follow_redirects=True,  # image download answers 303 → pre-signed URL
        )

    def list_devices(self) -> list[dict[str, Any]]:
        """GET /v1/devices → simplified [{id, name, kind}]."""
        with self._client() as c:
            r = c.get("/v1/devices")
            r.raise_for_status()
            out = []
            for d in r.json().get("data", []):
                attrs = d.get("attributes") or {}
                out.append(
                    {
                        "id": d.get("id"),
                        "name": attrs.get("name") or attrs.get("description") or d.get("id"),
                        "kind": attrs.get("kind") or attrs.get("device_type") or d.get("type"),
                    }
                )
            return out

    def history(self, device_id: str, event_types: str = "motion.human,motion.vehicle") -> list[dict[str, Any]]:
        """GET /v1/history/devices/{id}/events — follows pagination links."""
        out: list[dict[str, Any]] = []
        path: str | None = f"/v1/history/devices/{device_id}/events?event_types={event_types}"
        with self._client() as c:
            while path:
                r = c.get(path)
                r.raise_for_status()
                doc = r.json()
                out.extend(doc.get("data", []))
                path = (doc.get("links") or {}).get("next")
        return out

    def snapshot(self, device_id: str, ts_ms: int) -> tuple[bytes, str]:
        """POST /v1/devices/{id}/media/image/download at a timestamp → (bytes, mime)."""
        body = {"type": "at_timestamp", "timestamp": ts_ms, "image_options": {"format": "jpeg"}}
        with self._client() as c:
            r = c.post(f"/v1/devices/{device_id}/media/image/download", json=body)
            r.raise_for_status()
            return r.content, r.headers.get("content-type", "image/jpeg")
