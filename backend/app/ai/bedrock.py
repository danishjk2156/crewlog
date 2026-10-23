"""Amazon Bedrock (Converse API) wrapper with an offline fallback.

``AI_PROVIDER=bedrock`` uses any Converse model that accepts images
(default: Amazon Nova Lite). ``AI_PROVIDER=offline`` returns deterministic
text so the app and tests run without AWS credentials.
"""

from __future__ import annotations

import json
import logging
import re
from functools import lru_cache

from ..config import settings

log = logging.getLogger("crewlog.bedrock")

DIGEST_SYSTEM = (
    "You are a neutral site-progress reporter for a homeowner whose home is being renovated. "
    "You compare two photos from the same fixed camera: Image 1 was taken in the morning, "
    "Image 2 in the evening. Describe ONLY visible changes to the space, materials and work. "
    "Never identify, describe or speculate about people. Be factual, specific and brief. "
    'Reply with JSON only: {"summary": "<max 2 sentences>", "changes": ["..."], "concerns": ["..."]}. '
    'If nothing visibly changed, say so plainly in the summary and leave "changes" empty.'
)

NOSHOW_SYSTEM = (
    "You write short, polite, non-accusatory text messages from a homeowner to their contractor. "
    "Max 2 sentences. No greeting line breaks, no sign-off, no emojis."
)


@lru_cache(maxsize=1)
def _client():
    import boto3

    return boto3.client("bedrock-runtime", region_name=settings.aws_region)


def _converse(system: str, content: list[dict], max_tokens: int = 400) -> str:
    resp = _client().converse(
        modelId=settings.bedrock_model_id,
        system=[{"text": system}],
        messages=[{"role": "user", "content": content}],
        inferenceConfig={"maxTokens": max_tokens, "temperature": 0.2},
    )
    parts = resp["output"]["message"]["content"]
    return "".join(p.get("text", "") for p in parts).strip()


def parse_json_reply(text: str) -> dict:
    """Models sometimes wrap JSON in code fences or add prose; extract the object."""
    cleaned = re.sub(r"```(?:json)?", "", text).strip()
    match = re.search(r"\{.*\}", cleaned, re.S)
    if match:
        try:
            data = json.loads(match.group(0))
            return {
                "summary": str(data.get("summary", "")).strip(),
                "changes": [str(c) for c in data.get("changes", []) if str(c).strip()],
                "concerns": [str(c) for c in data.get("concerns", []) if str(c).strip()],
            }
        except json.JSONDecodeError:
            pass
    return {"summary": cleaned[:400], "changes": [], "concerns": []}


def _img_fmt(mime: str) -> str:
    return {"image/png": "png", "image/jpeg": "jpeg", "image/jpg": "jpeg", "image/webp": "webp", "image/gif": "gif"}.get(mime, "jpeg")


def describe_progress(am: tuple[bytes, str] | None, pm: tuple[bytes, str] | None, facts: str) -> tuple[dict, str]:
    """Return (digest_dict, model_name). digest_dict["progress"] is visible / none / unknown."""
    if settings.ai_provider != "bedrock" or not (am and pm):
        return _offline_digest(facts, same_image=bool(am and pm and am[0] == pm[0])), "offline"
    content = [
        {"text": f"Site facts: {facts}"},
        {"text": "Image 1 (morning):"},
        {"image": {"format": _img_fmt(am[1]), "source": {"bytes": am[0]}}},
        {"text": "Image 2 (evening):"},
        {"image": {"format": _img_fmt(pm[1]), "source": {"bytes": pm[0]}}},
    ]
    try:
        result = parse_json_reply(_converse(DIGEST_SYSTEM, content))
    except Exception as exc:  # noqa: BLE001 — a Bedrock outage must not break the daily note
        log.warning("Bedrock digest failed, using offline summary: %s", exc)
        return _offline_digest(facts, same_image=am[0] == pm[0]), "offline"
    result["progress"] = "visible" if result["changes"] else "none"
    return result, settings.bedrock_model_id


def draft_contractor_message(contractor: str, job_name: str, expected: str) -> tuple[str, str]:
    if settings.ai_provider == "bedrock":
        try:
            prompt = (
                f"Contractor: {contractor}. Project: {job_name}. The crew was expected around {expected} "
                "today and nobody has arrived yet. Ask politely whether the team is coming today and when."
            )
            return _converse(NOSHOW_SYSTEM, [{"text": prompt}], max_tokens=120), settings.bedrock_model_id
        except Exception:  # noqa: BLE001 — never block an alert on the LLM
            pass
    first = contractor.split()[0].removesuffix("'s") if contractor else "there"
    return (
        f"Hi {first}, just checking in on the {job_name.lower()} — we were expecting the team around "
        f"{expected} today. Is the crew still coming, and roughly when?",
        "offline",
    )


def draft_checkin_message(contractor: str, job_name: str, days: str) -> tuple[str, str]:
    """A neutral question for when the crew was on site but nothing visibly changed."""
    if settings.ai_provider == "bedrock":
        try:
            prompt = (
                f"Contractor: {contractor}. Project: {job_name}. The crew was on site on {days}, but the "
                "work-area camera shows no visible change. Some work is not visible (behind walls, drying, "
                "inspections). Ask politely what was done and whether anything is slowing things down. Do not accuse."
            )
            return _converse(NOSHOW_SYSTEM, [{"text": prompt}], max_tokens=120), settings.bedrock_model_id
        except Exception:  # noqa: BLE001 — never block an alert on the LLM
            pass
    first = contractor.split()[0].removesuffix("'s") if contractor else "there"
    return (
        f"Hi {first}, thanks for having the team out on {days}. We couldn't see changes in the work area "
        f"on the camera, so just checking in: what's been happening on the {job_name.lower()}, and is anything slowing things down?",
        "offline",
    )


def _offline_digest(facts: str, same_image: bool = False) -> dict:
    if same_image:  # byte-identical stills: certainly nothing changed, no model needed
        return {
            "summary": f"No visible change between the morning and evening stills. {facts[0].upper()}{facts[1:]}.",
            "changes": [],
            "concerns": [],
            "progress": "none",
        }
    return {
        "summary": f"{facts[0].upper()}{facts[1:]}.",
        "changes": [],
        "concerns": [],
        "progress": "unknown",
    }
