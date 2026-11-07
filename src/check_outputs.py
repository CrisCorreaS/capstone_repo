from pathlib import Path
import sys

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from src.data_utils import load_dataset


def check_outputs():
    _, participants = load_dataset(data_path=PROJECT_ROOT / "data/raw")
    participant_count = len(participants)
    record_count = sum(len(records) for records in participants.values())
    print(f"Participants: {participant_count}; raw CGM records: {record_count:,}")
    if participant_count != 208:
        raise ValueError(f"Expected 208 participants, got {participant_count}")
    if record_count != 114_912:
        raise ValueError(f"Expected 114,912 raw CGM records, got {record_count:,}")

    quality_path = Path("data/processed/quality_summary.csv")
    quality = pd.read_csv(PROJECT_ROOT / quality_path)
    required = {"case_id", "final_quality_v2"}
    missing_columns = required - set(quality.columns)
    if missing_columns:
        raise ValueError(f"{quality_path}: missing columns {sorted(missing_columns)}")
    case_ids = quality["case_id"]
    if case_ids.isna().any() or not pd.api.types.is_integer_dtype(case_ids):
        raise ValueError(f"{quality_path}: case_id must contain integers without missing values")
    if not case_ids.is_unique or set(case_ids) != set(participants):
        raise ValueError(f"{quality_path}: expected one row for each of the 208 raw participants")
    if not quality["final_quality_v2"].isin(("good", "medium", "bad")).all():
        raise ValueError(f"{quality_path}: final_quality_v2 must contain good, medium or bad")

    selected = quality.loc[quality["final_quality_v2"] == "good", "case_id"]
    expected = {Path(f"data/processed/interpolated/case_{case_id}.csv") for case_id in selected}
    expected.add(quality_path)
    expected.update(Path("results/tables") / name for name in (
        "metrics_summary.csv", "final_dataset.csv", "group_comparison.csv"
    ))
    actual = {
        path.relative_to(PROJECT_ROOT)
        for directory in ("data/processed", "results/tables")
        for path in (PROJECT_ROOT / directory).rglob("*.csv")
    }
    missing = expected - actual
    unexpected = actual - expected
    not_files = {path for path in expected & actual if not (PROJECT_ROOT / path).is_file()}
    problems = []
    for label, paths in (("Missing CSVs", missing), ("Unexpected CSVs", unexpected),
                         ("Expected CSV paths that are not files", not_files)):
        if paths:
            problems.append(f"{label}: {', '.join(sorted(path.as_posix() for path in paths))}")
    if problems:
        raise ValueError("\n".join(problems))
    print(f"Verified {len(expected)} generated CSVs for {len(selected)} selected participants.")


def main():
    try:
        check_outputs()
    except (OSError, ValueError) as error:
        print(f"Output validation failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
