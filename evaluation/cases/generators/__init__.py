"""Deterministic synthetic-series generators for the shared evaluation catalog."""

from evaluation.cases.generators.catalog import (
    DATA_DIR,
    REGISTRY_PATH,
    REPO_ROOT,
    REQUIRED_CASE_IDS,
    CaseSpec,
    EvaluationCatalog,
    load_catalog,
)
from evaluation.cases.generators.synthesize import generate_case_frame
from evaluation.cases.generators.write_csv import generate_catalog_csvs, write_case_csv

__all__ = [
    "DATA_DIR",
    "REGISTRY_PATH",
    "REPO_ROOT",
    "REQUIRED_CASE_IDS",
    "CaseSpec",
    "EvaluationCatalog",
    "generate_case_frame",
    "generate_catalog_csvs",
    "load_catalog",
    "write_case_csv",
]
