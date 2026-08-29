"""Persist tool outputs as referenced JSON artifacts. No FastAPI. No secrets."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

JsonObject = dict[str, Any]
_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]+$")


class ArtifactRef(BaseModel):
    """Location and integrity of a stored tool payload."""

    model_config = ConfigDict(extra="forbid")

    artifact_id: str
    sha256: str
    kind: str
    relative_path: str
    byte_length: int


class ArtifactStore:
    """Write-once JSON artifacts under an allowlisted directory."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def write_json(
        self,
        *,
        run_id: str,
        artifact_id: str,
        body: str,
        sha256: str,
        kind: str = "tool_output",
    ) -> ArtifactRef:
        safe_run = sanitize_id(run_id, label="run_id")
        safe_aid = sanitize_id(artifact_id, label="artifact_id")
        directory = self.root / safe_run
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{safe_aid}.json"
        encoded = body if body.endswith("\n") else body + "\n"
        if path.exists():
            existing = path.read_text(encoding="utf-8")
            if existing == encoded:
                return ArtifactRef(
                    artifact_id=safe_aid,
                    sha256=sha256,
                    kind=kind,
                    relative_path=_relative(self.root, path),
                    byte_length=len(existing.encode("utf-8")),
                )
            msg = f"artifact {safe_aid} already exists with different content"
            raise ValueError(msg)
        path.write_text(encoded, encoding="utf-8", newline="\n")
        return ArtifactRef(
            artifact_id=safe_aid,
            sha256=sha256,
            kind=kind,
            relative_path=_relative(self.root, path),
            byte_length=len(encoded.encode("utf-8")),
        )

    def read_json(self, ref: ArtifactRef) -> JsonObject:
        path = (self.root / ref.relative_path).resolve()
        root = self.root.resolve()
        if path != root and root not in path.parents:
            msg = "artifact path escapes the store root"
            raise ValueError(msg)
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            msg = "artifact must be a JSON object"
            raise ValueError(msg)
        return payload


def sanitize_id(value: str, *, label: str) -> str:
    if not value or not _SAFE_ID.fullmatch(value) or ".." in value:
        msg = f"invalid {label}; use letters, digits, dot, underscore, or hyphen"
        raise ValueError(msg)
    return value


def _relative(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()
