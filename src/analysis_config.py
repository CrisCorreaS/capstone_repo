import math
from pathlib import Path
import tomllib


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_analysis_config(project_root=None):
    """Read and validate analysis settings from the supplied or module-derived root."""
    root = PROJECT_ROOT if project_root is None else Path(project_root).resolve()
    path = root / "config/analysis.toml"
    try:
        with path.open("rb") as stream:
            config = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ValueError(f"Cannot read analysis configuration {path}: {error}") from error

    def number(section, key, *, integer=False, minimum=0, maximum=None, exclusive=False):
        table = config.get(section)
        if not isinstance(table, dict):
            raise ValueError(f"Missing or invalid [{section}] table in {path}")
        if key not in table:
            raise ValueError(f"Missing {section}.{key} in {path}")
        value = table[key]
        valid = type(value) is int if integer else type(value) in (int, float)
        if valid and not integer:
            try:
                valid = math.isfinite(value)
            except OverflowError:
                valid = False
        if valid:
            valid = value > minimum if exclusive else value >= minimum
        if valid and maximum is not None:
            valid = value <= maximum
        if not valid:
            kind = "an integer" if integer else "a finite number"
            bound = f"greater than {minimum}" if exclusive else f"at least {minimum}"
            if maximum is not None:
                bound += f" and at most {maximum}"
            raise ValueError(f"{section}.{key} in {path} must be {kind} {bound}")
        return value

    good = number("quality", "good_missing_pct_threshold", maximum=100)
    medium = number("quality", "medium_missing_pct_threshold", maximum=100)
    if good >= medium:
        raise ValueError(
            f"quality.good_missing_pct_threshold must be less than "
            f"quality.medium_missing_pct_threshold in {path}"
        )
    number("quality", "edge_window_samples", integer=True, minimum=1)
    number("quality", "selection_edge_window_samples", integer=True, minimum=1)
    number("quality", "terminal_missing_samples", integer=True)
    number("sample_entropy", "embedding_dimension", integer=True, minimum=1)
    number("sample_entropy", "tolerance_sd_multiplier", exclusive=True)
    number("dfa", "min_window_samples", integer=True, minimum=2)
    number("dfa", "window_count", integer=True, minimum=2)
    number("gaps", "long_gap_minutes", exclusive=True)
    number("execution", "notebook_cell_timeout_seconds", integer=True, minimum=1)
    return config
