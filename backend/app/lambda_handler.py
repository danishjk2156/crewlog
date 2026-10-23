"""AWS Lambda entry points.

- ``api``:       API Gateway (HTTP API) → FastAPI via Mangum
- ``scheduled``: EventBridge Scheduler rate(5 minutes) → no-show + digest checks
"""

from __future__ import annotations

from mangum import Mangum

from .core.scheduler import tick
from .main import app
from .store import get_store

api = Mangum(app, lifespan="off")


def scheduled(event, context):  # noqa: ARG001
    return tick(get_store())
