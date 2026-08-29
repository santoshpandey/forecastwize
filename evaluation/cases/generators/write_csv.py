"""Write evaluation CSVs with a stable UTF-8, LF-only layout. No FastAPI or LLM."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from evaluation.cases.generators.catalog import DATA_DIR, CaseSpec, load_catalog
from evaluation.cases.generators.synthesize import generate_case_frame


def generate_catalog_csvs(
    *,
    output_dir: Path | None = None,
    registry_path: Path | None = None,
) -> list[Path]:
    """Regenerate every catalog CSV. Does not score models or write eval artifacts."""
    catalog = load_catalog(registry_path)
    target = output_dir if output_dir is not None else DATA_DIR
    target.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for case in catalog.cases:
        frame = generate_case_frame(case)
        path = target / case.csv_filename
        write_case_csv(path, frame, case=case)
        written.append(path)
    return written


def write_case_csv(path: Path, frame: pd.DataFrame, *, case: CaseSpec) -> None:
    if len(frame) != case.n_rows:
        msg = f"{case.case_id}: generated {len(frame)} rows, expected {case.n_rows}"
        raise ValueError(msg)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(_to_csv_text(frame))


def _to_csv_text(frame: pd.DataFrame) -> str:
    columns = [str(col) for col in frame.columns]
    lines = [",".join(columns)]
    for row in frame.itertuples(index=False, name=None):
        cells = [_format_cell(value) for value in row]
        lines.append(",".join(cells))
    return "\n".join(lines) + "\n"


def _format_cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float | np.floating):
        number = float(value)
        if not np.isfinite(number):
            return ""
        return format(number, ".17g")
    if isinstance(value, np.integer | int) and not isinstance(value, bool):
        return str(int(value))
    if isinstance(value, pd.Timestamp):
        stamp = value
        if stamp.tzinfo is None:
            stamp = stamp.tz_localize("UTC")
        else:
            stamp = stamp.tz_convert("UTC")
        return stamp.strftime("%Y-%m-%dT%H:%M:%SZ")
    text = str(value)
    if text.lower() == "nan":
        return ""
    return text
