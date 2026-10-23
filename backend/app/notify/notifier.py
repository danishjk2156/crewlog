"""Alert delivery: always stored in-app; also published to SNS when configured."""

from __future__ import annotations

import logging
from functools import lru_cache

from ..config import settings

log = logging.getLogger("crewlog.notify")


@lru_cache(maxsize=1)
def _sns():
    import boto3

    return boto3.client("sns", region_name=settings.aws_region)


def send(subject: str, message: str) -> list[str]:
    channels = ["in_app"]
    if settings.sns_topic_arn:
        try:
            _sns().publish(TopicArn=settings.sns_topic_arn, Subject=subject[:100], Message=message)
            channels.append("sns")
        except Exception as exc:  # noqa: BLE001 — in-app alert still exists
            log.warning("SNS publish failed: %s", exc)
    log.info("ALERT %s — %s", subject, message)
    return channels
