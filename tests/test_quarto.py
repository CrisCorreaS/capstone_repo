from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "src/quarto.py"
SPEC = importlib.util.spec_from_file_location("quarto_launcher", LAUNCHER)
quarto = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(quarto)


class LauncherTests(unittest.TestCase):
    def test_platform_layouts_and_argument_forwarding(self):
        for platform, directory, executable, plugin in (
            ("win32", "Library", ".exe", "deno_dom.dll"),
            ("linux", "", "", "deno_dom.so"),
            ("darwin", "", "", "deno_dom.dylib"),
        ):
            with self.subTest(platform=platform), tempfile.TemporaryDirectory() as temporary:
                prefix = Path(temporary) / "environment with spaces"
                library = prefix / directory
                binary = library / "bin"
                share = library / "share/quarto"
                binary.mkdir(parents=True)
                (library / "lib").mkdir()
                (share / "jupyter").mkdir(parents=True)
                original = "# original Quarto Jupyter entry point\n"
                (share / "jupyter/jupyter.py").write_text(original, encoding="utf-8")
                (share / "version").write_text("1.11.9", encoding="utf-8")
                expected = {
                    "QUARTO_DENO": binary / f"deno{executable}",
                    "QUARTO_DENO_DOM": library / "lib" / plugin,
                    "QUARTO_PANDOC": binary / f"pandoc{executable}",
                    "QUARTO_ESBUILD": binary / f"esbuild{executable}",
                    "QUARTO_DART_SASS": binary / f"sass{executable}",
                    "QUARTO_TYPST": binary / f"typst{executable}",
                    "QUARTO_TYPST_GATHER": binary / f"typst-gather{executable}",
                }
                for path in (*expected.values(), binary / "quarto.js"):
                    path.touch()

                def run(command, *, env):
                    self.assertEqual(command[0], str(expected["QUARTO_DENO"]))
                    self.assertEqual(command[-3:], [str(binary / "quarto.js"), "inspect", "file with spaces.qmd"])
                    for name, path in expected.items():
                        self.assertEqual(env[name], str(path))
                    self.assertEqual(env["QUARTO_CONDA_PREFIX"], str(library))
                    self.assertEqual(env["QUARTO_BIN_PATH"], str(binary))
                    self.assertEqual(env["QUARTO_PYTHON"], sys.executable)
                    self.assertEqual(env["DENO_DOM_PLUGIN"], str(expected["QUARTO_DENO_DOM"]))
                    resources = Path(env["QUARTO_SHARE_PATH"])
                    self.assertNotEqual(resources, share)
                    self.assertEqual((resources / "jupyter/_quarto_jupyter_original.py").read_text(), original)
                    self.assertIn("'transport_encryption': 'required'", (resources / "jupyter/jupyter.py").read_text())
                    return SimpleNamespace(returncode=37)

                with (
                    patch.object(sys, "platform", platform),
                    patch.object(sys, "prefix", str(prefix)),
                    patch.object(sys, "argv", [str(LAUNCHER), "inspect", "file with spaces.qmd"]),
                    patch.dict(os.environ, {name: "stale external tool" for name in expected}),
                    patch.object(quarto.subprocess, "run", side_effect=run) as child,
                ):
                    self.assertEqual(quarto.main(), 37)
                    child.assert_called_once()
                    self.assertEqual((share / "jupyter/jupyter.py").read_text(), original)
                    expected["QUARTO_DENO_DOM"].unlink()
                    error = io.StringIO()
                    with redirect_stderr(error):
                        self.assertEqual(quarto.main(), 1)
                    child.assert_called_once()
                    self.assertIn(str(expected["QUARTO_DENO_DOM"]), error.getvalue())

    def test_failed_render_returns_status_and_full_log(self):
        output, error = io.StringIO(), io.StringIO()
        command = [sys.executable, "-I", "-B", "-c", "print('metadata'); print('  hidden detail'); print('render failed'); raise SystemExit(7)"]
        with redirect_stdout(output), redirect_stderr(error):
            self.assertEqual(quarto.render(command, os.environ.copy()), 7)
        self.assertIn("Quarto log:", output.getvalue())
        self.assertIn("exit code 7", error.getvalue())
        self.assertIn("  hidden detail", error.getvalue())
        self.assertIn("render failed", error.getvalue())


class RenderSmokeTest(unittest.TestCase):
    def test_version_and_fresh_jupyter_render(self):
        with tempfile.TemporaryDirectory(prefix="cgm-quarto-smoke-") as temporary:
            # Spaces exercise argument handling on every OS; Unicode is supported on POSIX.
            project = Path(temporary) / ("smoke project" if sys.platform == "win32" else "smoke project café")
            project.mkdir()
            env = os.environ.copy()
            env.update({
                "MPLBACKEND": "Agg",
                "MPLCONFIGDIR": str(project / "matplotlib"),
                "JUPYTER_CONFIG_DIR": str(project / "jupyter"),
                "IPYTHONDIR": str(project / "ipython"),
                "XDG_CACHE_HOME": str(project / "cache"),
                "XDG_CONFIG_HOME": str(project / "config"),
                "XDG_DATA_HOME": str(project / "user-data"),
                "XDG_RUNTIME_DIR": str(project / "runtime"),
            })
            (project / "runtime").mkdir(mode=0o700)
            if sys.platform != "win32":
                resources = Path(temporary) / "temporary resources café"
                resources.mkdir()
                env["TMPDIR"] = str(resources)

            def launch(*arguments):
                result = subprocess.run(
                    [sys.executable, "-I", "-B", str(LAUNCHER), *arguments],
                    cwd=project, env=env, capture_output=True, text=True,
                    encoding="utf-8", errors="backslashreplace", timeout=180,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                return result

            self.assertEqual(launch("--version").stdout.strip().split()[-1], "1.11.9")
            (project / "_quarto.yml").write_text(
                "project:\n  type: default\njupyter: python3\n"
                "format:\n  html:\n    embed-resources: true\n"
                "execute:\n  daemon: false\n  cache: false\n  freeze: false\n  error: false\n",
                encoding="utf-8",
            )
            (project / "smoke report.qmd").write_text(
                "---\ntitle: Launcher smoke test\n---\n\n```{python}\n"
                "import sys\nfrom pathlib import Path\n"
                "import numpy as np\nimport pandas as pd\n"
                "import scipy\nimport sklearn\nimport seaborn\nimport statsmodels.api\n"
                "import matplotlib.pyplot as plt\n"
                f"assert Path(sys.executable).resolve() == Path({sys.executable!r}).resolve()\n"
                "print('CGM_QUARTO_SMOKE_' + str(int(pd.Series(np.array([1, 2, 3])).sum())))\n"
                "plt.plot([0, 1], [0, 1])\nplt.show()\n```\n",
                encoding="utf-8",
            )
            launch("render", "smoke report.qmd")
            html = (project / "smoke report.html").read_text(encoding="utf-8")
            self.assertIn("CGM_QUARTO_SMOKE_6", html)
            self.assertIn("data:image/png;base64,", html)


if __name__ == "__main__":
    unittest.main(verbosity=2)
