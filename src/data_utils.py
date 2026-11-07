
from pathlib import Path
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _resolve_data_path(data_path):
    """Resolve relative data paths from the project root; preserve absolute paths."""
    data_path = Path(data_path)
    return data_path if data_path.is_absolute() else PROJECT_ROOT / data_path


def load_clinical_data(data_path="data/raw", filename="clinical_data.txt"):
    """Load clinical data; data_path is project-relative or absolute."""
    data_path = _resolve_data_path(data_path)
    clinical_path = data_path / filename

    if not clinical_path.exists():
        raise FileNotFoundError(f"Clinical file not found: {clinical_path}")

    # sep=None + engine="python" intenta detectar automáticamente el separador
    clinical = pd.read_csv(clinical_path, sep=None, engine="python")
    return clinical


def load_case(case_id, data_path="data/raw", cases_folder="cases"):
    """Load one participant; data_path is project-relative or absolute."""
    data_path = _resolve_data_path(data_path)
    # Usar doble espacio para coincidir con los nombres reales
    filename = f"case  {case_id}.csv"
    if cases_folder is None:
        case_path = data_path / filename
    else:
        case_path = data_path / cases_folder / filename

    if not case_path.exists():
        raise FileNotFoundError(f"Case file not found: {case_path}")

    df = pd.read_csv(case_path)
    return df


def load_all_cases(data_path="data/raw", cases_folder="cases", n_cases=208):
    """Load participants in case-number order; data_path is project-relative or absolute."""
    patients = {}

    for case_id in range(1, n_cases + 1):
        patients[case_id] = load_case(
            case_id=case_id,
            data_path=data_path,
            cases_folder=cases_folder
        )

    return patients


def load_dataset(data_path="data/raw", clinical_filename="clinical_data.txt", n_cases=208):
    """Load clinical data and participants; data_path is project-relative or absolute."""
    data_path = _resolve_data_path(data_path)
    clinical = load_clinical_data(
        data_path=data_path,
        filename=clinical_filename
    )

    # Detectar automáticamente el folder de casos
    cases_folder = "cases" if (data_path / "cases").exists() else None
    patients = load_all_cases(
        data_path=data_path,
        cases_folder=cases_folder,
        n_cases=n_cases
    )

    return clinical, patients

# Normalización de estructura de los casos individuales
def standardize_case(df):
    df = df.copy()

    # Remove index column if present
    if "Unnamed: 0" in df.columns:
        df = df.drop(columns=["Unnamed: 0"])

    # Rename columns
    df = df.rename(columns={
        "hora": "time",
        "glucemia": "glucose"
    })

    df = df[["time", "glucose"]]

    # Step 1: group duplicates
    df = df.groupby("time", as_index=False)["glucose"].mean()

    # Step 2: convert time to datetime
    df["time"] = pd.to_datetime(df["time"], format="%H:%M:%S")

    # Step 3: create complete timeline (5 min intervals)
    full_time = pd.date_range(
        start=df["time"].min(),
        end=df["time"].max(),
        freq="5min"
    )
    df = df.set_index("time").reindex(full_time)
    df = df.rename_axis("time").reset_index()

    return df