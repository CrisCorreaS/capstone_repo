import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


def configure_jupyter(resources):
    entry = resources / "jupyter/jupyter.py"
    original = entry.with_name("_quarto_jupyter_original.py")
    shutil.copyfile(entry, original)
    entry.write_text(
        "from functools import partial\n"
        "from pathlib import Path\n"
        "from nbclient import NotebookClient\n"
        "from traitlets.config import Config\n"
        "import notebook\n"
        "notebook.NotebookClient = partial(NotebookClient, config=Config({\n"
        "    'KernelManager': {'transport_encryption': 'required'}\n"
        "}))\n"
        "original = Path(__file__).with_name('_quarto_jupyter_original.py')\n"
        "exec(compile(original.read_bytes(), str(original), 'exec'),\n"
        "     {'__name__': '__main__', '__file__': str(original)})\n",
        encoding="utf-8",
    )


def render(command, env):
    routine = re.compile(
        r"(?:Starting python3 kernel\.\.\.Done|Executing '[^']+\.quarto_ipynb'|"
        r"  Cell \d+/\d+: '[^']+'\.*Done|Output created: .+)"
    )
    metadata = False
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", prefix="cgm-quarto-", suffix=".log", delete=False,
    ) as log:
        print(f"Quarto log: {log.name}", flush=True)
        with subprocess.Popen(
            command, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="backslashreplace",
        ) as process:
            for line in process.stdout:
                log.write(line)
                log.flush()
                if line.startswith("pandoc ") or line.rstrip() == "metadata":
                    metadata = True
                    continue
                if metadata and line.startswith("  "):
                    continue
                metadata = False
                if line.strip() and not routine.fullmatch(line.rstrip()):
                    print(line, end="", file=sys.stderr, flush=True)
            code = process.wait()
    if code:
        print(f"Quarto failed (exit code {code}); full render log follows:", file=sys.stderr)
        print(Path(log.name).read_text(encoding="utf-8"), file=sys.stderr, end="")
    return code


def main():
    library = Path(sys.prefix) / "Library"
    binary = library / "bin"
    share = library / "share/quarto"
    tools = {
        "QUARTO_DENO": binary / "deno.exe",
        "QUARTO_DENO_DOM": library / "lib/deno_dom.dll",
        "QUARTO_PANDOC": binary / "pandoc.exe",
        "QUARTO_ESBUILD": binary / "esbuild.exe",
        "QUARTO_DART_SASS": binary / "sass.exe",
        "QUARTO_TYPST": binary / "typst.exe",
        "QUARTO_TYPST_GATHER": binary / "typst-gather.exe",
    }
    script = binary / "quarto.js"
    for path in (*tools.values(), script, share / "version"):
        if not path.is_file():
            print(f"Missing Quarto environment file: {path}. Run through Pixi.", file=sys.stderr)
            return 1

    env = os.environ.copy()
    env.update({name: str(path) for name, path in tools.items()})
    env.update({
        "QUARTO_BIN_PATH": str(binary),
        "QUARTO_SHARE_PATH": str(share),
        "QUARTO_CONDA_PREFIX": str(library),
        "DENO_DOM_PLUGIN": str(tools["QUARTO_DENO_DOM"]),
        "QUARTO_PYTHON": sys.executable,
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
        "NO_COLOR": "TRUE",
        "DENO_TLS_CA_STORE": "system,mozilla",
        "DENO_NO_UPDATE_CHECK": "1",
    })

    command = [
        str(tools["QUARTO_DENO"]), "run", "--cached-only", "--unstable-kv",
        "--unstable-ffi", "--no-config", "--no-lock", "--allow-all", "--no-check",
        "--v8-flags=--enable-experimental-regexp-engine,--max-old-space-size=8192,"
        "--max-heap-size=8192,--stack-trace-limit=100",
        str(script), *sys.argv[1:],
    ]
    try:
        with tempfile.TemporaryDirectory(prefix="quarto-resources-") as temporary:
            if not temporary.isascii():
                raise OSError("Quarto requires an ASCII temporary-directory path on Windows")
            resources = Path(temporary) / "share"
            shutil.copytree(share, resources)
            configure_jupyter(resources)
            env["QUARTO_SHARE_PATH"] = str(resources)
            if sys.argv[1:2] == ["render"]:
                return render(command, env)
            return subprocess.run(command, env=env).returncode
    except OSError as error:
        print(f"Could not launch Quarto: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
