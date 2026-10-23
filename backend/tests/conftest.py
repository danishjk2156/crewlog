import os
import tempfile

# Configure before the app is imported.
_TMP = tempfile.mkdtemp(prefix="crewlog-test-")
os.environ.update(
    {
        "DATA_DIR": _TMP,
        "STORE": "local",
        "AI_PROVIDER": "offline",
        "SCHEDULER": "false",
        "DEMO_MODE": "true",
        "RING_WEBHOOK_SECRET": "test-secret",
        "DEFAULT_TZ": "Asia/Kolkata",
        "STATIC_DIR": os.path.join(_TMP, "no-static"),
    }
)

import pytest  # noqa: E402

from app.store import get_store  # noqa: E402


@pytest.fixture(autouse=True)
def clean_store():
    get_store().reset()
    yield
