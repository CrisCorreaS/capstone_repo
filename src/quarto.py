import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


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
            env["QUARTO_SHARE_PATH"] = str(resources)
            return subprocess.run(command, env=env).returncode
    except OSError as error:
        print(f"Could not launch Quarto: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
