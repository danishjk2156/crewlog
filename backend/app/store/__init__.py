from __future__ import annotations

from functools import lru_cache

from ..config import settings
from .base import Store


@lru_cache(maxsize=1)
def get_store() -> Store:
    if settings.store == "dynamo":
        from .dynamo import DynamoStore

        return DynamoStore(settings.dynamo_table, settings.aws_region)
    from .local import LocalStore

    return LocalStore(settings.data_dir / "crewlog.json")
