from __future__ import annotations

from fastapi import Request

from app.api.store import FileStore
from app.config import Settings, get_settings


def get_store(request: Request) -> FileStore:
    store = getattr(request.app.state, "store", None)
    if not isinstance(store, FileStore):
        msg = "API file store is not configured"
        raise RuntimeError(msg)
    return store


def get_app_settings() -> Settings:
    return get_settings()
