"""Regenerate data/evaluation CSVs from the case registry. Run from the repo root."""

from __future__ import annotations

from evaluation.cases.generators.write_csv import generate_catalog_csvs


def main() -> None:
    paths = generate_catalog_csvs()
    for path in paths:
        print(path)


if __name__ == "__main__":
    main()
