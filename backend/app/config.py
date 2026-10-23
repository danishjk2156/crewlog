"""Runtime configuration. Every AWS dependency has a local fallback so the app runs
with zero cloud setup; flip env vars to move to AWS."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """Read KEY=value lines from backend/.env. Variables already set in the shell win."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


_load_dotenv(BACKEND_DIR / ".env")


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    ring_api_base: str = field(default_factory=lambda: os.getenv("RING_API_BASE", "http://127.0.0.1:8787"))
    ring_access_token: str = field(default_factory=lambda: os.getenv("RING_ACCESS_TOKEN", "sandbox-token"))
    ring_webhook_secret: str = field(default_factory=lambda: os.getenv("RING_WEBHOOK_SECRET", "crewlog-dev-secret"))

    store: str = field(default_factory=lambda: os.getenv("STORE", "local"))
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("DATA_DIR", str(BACKEND_DIR / "data"))))
    dynamo_table: str = field(default_factory=lambda: os.getenv("DYNAMO_TABLE", "crewlog"))

    ai_provider: str = field(default_factory=lambda: os.getenv("AI_PROVIDER", "offline"))
    bedrock_model_id: str = field(default_factory=lambda: os.getenv("BEDROCK_MODEL_ID", "us.amazon.nova-lite-v1:0"))
    aws_region: str = field(default_factory=lambda: os.getenv("AWS_REGION", "us-east-1"))
    sns_topic_arn: str = field(default_factory=lambda: os.getenv("SNS_TOPIC_ARN", ""))

    default_tz: str = field(default_factory=lambda: os.getenv("DEFAULT_TZ", "Asia/Kolkata"))
    demo_mode: bool = field(default_factory=lambda: _bool("DEMO_MODE", True))
    scheduler: bool = field(default_factory=lambda: _bool("SCHEDULER", True))
    demo_media_dir: Path = field(default_factory=lambda: Path(os.getenv("DEMO_MEDIA_DIR", str(BACKEND_DIR / "demo_media"))))
    static_dir: Path = field(default_factory=lambda: Path(os.getenv("STATIC_DIR", str(BACKEND_DIR / "static"))))

    @property
    def snapshot_dir(self) -> Path:
        return self.data_dir / "snapshots"


settings = Settings()
