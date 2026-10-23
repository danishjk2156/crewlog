"""CrewLog FastAPI application."""

from __future__ import annotations

import asyncio
import contextlib
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api.routes import router
from .config import settings
from .core.scheduler import tick
from .store import get_store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("crewlog")


async def _scheduler_loop() -> None:
    while True:
        try:
            done = await asyncio.to_thread(tick, get_store())
            if done["noshow"] or done["digest"]:
                log.info("scheduler: %s", done)
        except Exception:  # noqa: BLE001
            log.exception("scheduler loop error")
        await asyncio.sleep(60)


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI):
    task = asyncio.create_task(_scheduler_loop()) if settings.scheduler else None
    log.info(
        "CrewLog up — store=%s ai=%s ring=%s demo=%s", settings.store, settings.ai_provider, settings.ring_api_base, settings.demo_mode
    )
    yield
    if task:
        task.cancel()


app = FastAPI(title="CrewLog", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(router)


@app.get("/api/health")
def health():
    return {"ok": True, "store": settings.store, "ai": settings.ai_provider, "demo": settings.demo_mode}


# Serve the built React app (frontend/ → npm run build → backend/static)
if (settings.static_dir / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=settings.static_dir / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        candidate = settings.static_dir / path
        if path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(settings.static_dir / "index.html")
