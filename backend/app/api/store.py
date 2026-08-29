"""File-backed API records. No production database. No forecast math."""

from __future__ import annotations

import threading
from pathlib import Path

from app.api.errors import ApiError
from app.api.ids import require_resource_id
from app.api.schemas import (
    DatasetResponse,
    EvaluationResponse,
    ForecastResponse,
    RunResponse,
)


class FileStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.datasets_dir = root / "datasets"
        self.forecasts_dir = root / "forecasts"
        self.runs_dir = root / "runs"
        self.evaluations_dir = root / "evaluations"
        self.trajectories_dir = root / "trajectories"
        self._lock = threading.Lock()

    def ensure(self) -> None:
        for path in (
            self.datasets_dir,
            self.forecasts_dir,
            self.runs_dir,
            self.evaluations_dir,
            self.trajectories_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)

    def assert_under(self, directory: Path, path: Path) -> Path:
        """Resolve `path` and refuse anything outside `directory`."""
        root = directory.resolve()
        resolved = path.resolve()
        if not resolved.is_relative_to(root):
            raise ApiError(
                500,
                "storage_error",
                "Refusing to access a path outside the store.",
            )
        return resolved

    def contained_file(self, directory: Path, filename: str) -> Path:
        """Join a basename onto `directory` and refuse traversal."""
        if filename != Path(filename).name or filename in {".", ".."}:
            raise ApiError(
                500,
                "storage_error",
                "Refusing to access a path outside the store.",
            )
        return self.assert_under(directory, directory / filename)

    def dataset_csv_path(self, dataset_id: str) -> Path:
        require_resource_id(dataset_id)
        return self.contained_file(self.datasets_dir, f"{dataset_id}.csv")

    def dataset_meta_path(self, dataset_id: str) -> Path:
        require_resource_id(dataset_id)
        return self.contained_file(self.datasets_dir, f"{dataset_id}.json")

    def forecast_path(self, forecast_id: str) -> Path:
        require_resource_id(forecast_id)
        return self.contained_file(self.forecasts_dir, f"{forecast_id}.json")

    def run_path(self, run_id: str) -> Path:
        require_resource_id(run_id)
        return self.contained_file(self.runs_dir, f"{run_id}.json")

    def evaluation_path(self, evaluation_id: str) -> Path:
        require_resource_id(evaluation_id)
        return self.contained_file(self.evaluations_dir, f"{evaluation_id}.json")

    def evaluation_result_dir(self, evaluation_id: str) -> Path:
        require_resource_id(evaluation_id)
        return self.assert_under(self.evaluations_dir, self.evaluations_dir / evaluation_id)

    def trajectory_path(self, run_id: str) -> Path:
        require_resource_id(run_id)
        return self.contained_file(self.trajectories_dir, f"{run_id}.jsonl")

    def put_dataset(self, record: DatasetResponse, csv_bytes: bytes) -> None:
        self.ensure()
        csv_path = self.dataset_csv_path(record.id)
        meta_path = self.dataset_meta_path(record.id)
        with self._lock:
            csv_path.write_bytes(csv_bytes)
            _atomic_write(meta_path, record.model_dump_json())

    def get_dataset(self, dataset_id: str) -> DatasetResponse:
        path = self.dataset_meta_path(dataset_id)
        if not path.is_file():
            raise ApiError(404, "not_found", "Dataset was not found.")
        return DatasetResponse.model_validate_json(path.read_text(encoding="utf-8"))

    def put_forecast(self, record: ForecastResponse) -> None:
        self.ensure()
        with self._lock:
            _atomic_write(self.forecast_path(record.id), record.model_dump_json())

    def get_forecast(self, forecast_id: str) -> ForecastResponse:
        path = self.forecast_path(forecast_id)
        if not path.is_file():
            raise ApiError(404, "not_found", "Forecast was not found.")
        return ForecastResponse.model_validate_json(path.read_text(encoding="utf-8"))

    def put_run(self, record: RunResponse) -> None:
        self.ensure()
        with self._lock:
            _atomic_write(self.run_path(record.id), record.model_dump_json())

    def get_run(self, run_id: str) -> RunResponse:
        path = self.run_path(run_id)
        if not path.is_file():
            raise ApiError(404, "not_found", "Run was not found.")
        return RunResponse.model_validate_json(path.read_text(encoding="utf-8"))

    def put_evaluation(self, record: EvaluationResponse) -> None:
        self.ensure()
        with self._lock:
            _atomic_write(self.evaluation_path(record.id), record.model_dump_json())

    def get_evaluation(self, evaluation_id: str) -> EvaluationResponse:
        path = self.evaluation_path(evaluation_id)
        if not path.is_file():
            raise ApiError(404, "not_found", "Evaluation was not found.")
        return EvaluationResponse.model_validate_json(path.read_text(encoding="utf-8"))


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    tmp.replace(path)
