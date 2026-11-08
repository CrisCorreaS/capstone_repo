import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import traceback

import nbformat
from nbclient import NotebookClient
from jupyter_client import AsyncKernelManager
from jupyter_client.kernelspec import KernelSpecManager


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from src.analysis_config import load_analysis_config
from src.check_outputs import check_outputs

NOTEBOOKS = ("01_data_exploration.ipynb", "02_metrics.ipynb")
TABLES = ("metrics_summary.csv", "final_dataset.csv", "group_comparison.csv")


def check_output_path(path, directory=False):
    """Reject redirected paths before inspecting or removing generated files."""
    for component in reversed((path, *path.parents)):
        if component.is_symlink() or component.is_junction():
            raise RuntimeError(f"Refusing a link or junction: {component}")
    resolved = path.resolve()
    if resolved != path or not resolved.is_relative_to(PROJECT_ROOT):
        raise RuntimeError(f"Output path escapes the project: {path}")
    if path.exists() and not (path.is_dir() if directory else path.is_file()):
        raise RuntimeError(f"Unexpected output path type: {path}")


def prepare_outputs():
    processed = PROJECT_ROOT / "data/processed"
    interpolated = processed / "interpolated"
    tables = PROJECT_ROOT / "results/tables"
    for directory in (processed, interpolated, tables):
        check_output_path(directory, directory=True)

    outputs = [processed / "quality_summary.csv"]
    outputs.extend(tables / name for name in TABLES)
    if interpolated.exists():
        for path in interpolated.iterdir():
            if re.fullmatch(r"case_[0-9]+\.csv", path.name):
                outputs.append(path)
            elif path.name.lower().startswith("case_") and path.name.lower().endswith(".csv"):
                raise RuntimeError(f"Unrecognised participant CSV; left unchanged: {path}")

    # Validate the whole removal list before deleting anything, then recheck each file.
    for path in outputs:
        check_output_path(path)
    for directory in (interpolated, tables):
        directory.mkdir(parents=True, exist_ok=True)
    removed = 0
    for path in outputs:
        check_output_path(path)
        if path.exists():
            path.unlink()
            removed += 1
    print(f"Prepared output directories; removed {removed} recognised generated CSVs.", flush=True)


def execute_notebook(name, notebook, diagnostics, timeout_seconds):
    manager = AsyncKernelManager(
        kernel_name="cgm-pixi",
        kernel_spec_manager=KernelSpecManager(
            kernel_dirs=[str(diagnostics / "kernels")], ensure_native_kernel=False
        ),
    )
    for cell in notebook.cells:
        if cell.cell_type == "code":
            cell.outputs = []
            cell.execution_count = None
    client = NotebookClient(
        notebook, km=manager, kernel_name="cgm-pixi",
        allow_errors=False, force_raise_errors=True, timeout=timeout_seconds,
    )
    print(f"Executing {name} in a fresh Pixi kernel...", flush=True)
    try:
        with (diagnostics / f"{name}.kernel.log").open("wb") as kernel_log:
            client.execute(
                cwd=str(PROJECT_ROOT / "notebooks"), cleanup_kc=True,
                stdout=kernel_log, stderr=kernel_log,
            )
    except Exception as error:
        raise RuntimeError(f"Failed notebook {name}: {error}") from error
    finally:
        nbformat.write(notebook, diagnostics / name)
    print(f"Completed {name}.", flush=True)


def analyse(analysis_config, diagnostics):
    """Verify existing raw inputs, prepare outputs and execute both notebooks."""
    print("Verifying raw inputs without downloading...", flush=True)
    subprocess.run(
        [sys.executable, "-I", "-B", str(PROJECT_ROOT / "src/download_data.py"), "--verify-only"],
        cwd=PROJECT_ROOT, check=True,
    )
    check_output_path(PROJECT_ROOT / "notebooks", directory=True)
    for name in NOTEBOOKS:
        check_output_path(PROJECT_ROOT / "notebooks" / name)
    notebooks = [
        (name, nbformat.read(PROJECT_ROOT / "notebooks" / name, as_version=4))
        for name in NOTEBOOKS
    ]
    prepare_outputs()

    kernel_directory = diagnostics / "kernels/cgm-pixi"
    kernel_directory.mkdir(parents=True)
    kernel_spec = {
        "argv": [sys.executable, "-I", "-B", "-m", "ipykernel_launcher", "-f", "{connection_file}"],
        "display_name": "Active Pixi Python", "language": "python",
        "env": {
            "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": "", "PYTHONNOUSERSITE": "1",
            "IPYTHONDIR": str(diagnostics / "ipython"),
            "MPLCONFIGDIR": str(diagnostics / "matplotlib"),
            "JUPYTER_CONFIG_DIR": str(diagnostics / "jupyter-config"),
        },
    }
    (kernel_directory / "kernel.json").write_text(
        json.dumps(kernel_spec, indent=2), encoding="utf-8"
    )
    for name, notebook in notebooks:
        execute_notebook(
            name, notebook, diagnostics,
            timeout_seconds=analysis_config["execution"]["notebook_cell_timeout_seconds"],
        )
    print("Processed data and result tables regenerated.", flush=True)


def render_report():
    """Render the report using the active environment and existing outputs."""
    print("Rendering the CGM data-quality report...", flush=True)
    try:
        subprocess.run(
            [sys.executable, "-I", "-B", str(PROJECT_ROOT / "src/quarto.py"),
             "render", "reports/cgm-report.qmd"],
            cwd=PROJECT_ROOT, check=True,
        )
    except subprocess.CalledProcessError as error:
        raise RuntimeError(f"Report rendering failed (exit code {error.returncode}).") from error
    report = PROJECT_ROOT / "reports/cgm-report.html"
    if not report.is_file() or report.stat().st_size == 0:
        raise RuntimeError(f"Report rendering did not produce a non-empty HTML file: {report}")
    print(f"Report created: {report}", flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run the CGM analysis or complete reproduction.")
    parser.add_argument(
        "--analyse-only", action="store_true",
        help="Verify existing inputs and execute the notebooks without downloading data.",
    )
    args = parser.parse_args(argv)
    task = "analyse" if args.analyse_only else "reproduce"
    action = "Analysis" if args.analyse_only else "Reproduction"
    diagnostics = None
    try:
        pixi_root = os.environ.get("PIXI_PROJECT_ROOT")
        prefix = os.environ.get("CONDA_PREFIX")
        if (
            not pixi_root or Path(pixi_root).resolve() != PROJECT_ROOT
            or not prefix or Path(prefix).resolve() != Path(sys.prefix).resolve()
        ):
            raise RuntimeError(f"Run this entry point with pixi run {task}.")

        analysis_config = load_analysis_config(PROJECT_ROOT)

        if not args.analyse_only:
            print("Acquiring or verifying raw inputs...", flush=True)
            subprocess.run(
                [sys.executable, "-I", "-B", str(PROJECT_ROOT / "src/download_data.py")],
                cwd=PROJECT_ROOT, check=True,
            )
        diagnostics = Path(tempfile.mkdtemp(prefix="cgm-reproduce-"))
        print(f"Execution copies and logs: {diagnostics}", flush=True)
        analyse(analysis_config, diagnostics)
        if not args.analyse_only:
            print("Validating generated outputs...", flush=True)
            check_outputs()
            render_report()
            print("Reproduction completed.", flush=True)
        return 0
    except Exception as error:
        if diagnostics is not None:
            (diagnostics / "error.log").write_text(traceback.format_exc(), encoding="utf-8")
        print(f"{action} failed: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print(f"{action} interrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
