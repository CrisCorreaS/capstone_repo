from contextlib import redirect_stderr, redirect_stdout
import hashlib
import importlib.util
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("download_data", ROOT / "src/download_data.py")
download_data = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(download_data)


@unittest.skipIf(sys.platform == "win32", "Requires POSIX directory symlinks")
class AcquisitionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="cgm-acquisition-test-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve(strict=True)
        self.files = {
            Path("cases/case  1.csv"): b"time,glucose\n00:00,100\n",
            Path("readme.txt"): b"Synthetic acquisition fixture\n",
        }
        self.mappings = {path: f"S1/{path.as_posix()}" for path in self.files}
        self.checksums = {
            path: hashlib.sha256(content).hexdigest() for path, content in self.files.items()
        }
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as archive:
            for path, content in self.files.items():
                archive.writestr(self.mappings[path], content)
        self.archive = payload.getvalue()
        self.metadata = (
            "https://example.invalid/source.zip",
            hashlib.md5(self.archive).hexdigest(),
            self.mappings,
            self.checksums,
        )

    def test_acquisition_stages_under_symlinked_temporary_parent(self):
        physical_parent = self.root / "temporary"
        physical_parent.mkdir()
        linked_parent = self.root / "temporary-link"
        linked_parent.symlink_to(physical_parent, target_is_directory=True)
        destination = self.root / "raw"
        temporary_directory = tempfile.TemporaryDirectory
        created = []

        def create_temporary_directory(**kwargs):
            directory = temporary_directory(dir=linked_parent, **kwargs)
            path = Path(directory.name)
            created.append((path, path.resolve(strict=True)))
            return directory

        output, error = io.StringIO(), io.StringIO()
        with (
            patch.object(download_data, "read_metadata", return_value=self.metadata),
            patch.object(download_data.tempfile, "TemporaryDirectory", side_effect=create_temporary_directory),
            patch.object(download_data.urllib.request, "urlopen", return_value=io.BytesIO(self.archive)) as request,
            patch.object(download_data, "stage_archive", wraps=download_data.stage_archive) as stage,
            redirect_stdout(output), redirect_stderr(error),
        ):
            self.assertEqual(download_data.main(["--destination", str(destination)]), 0, error.getvalue())
            lexical, canonical = created[0]
            self.assertIn(linked_parent, lexical.parents)
            self.assertEqual(stage.call_args.args[-1], canonical)
            self.assertFalse(lexical.exists())
            self.assertFalse(canonical.exists())
            self.assertEqual(list(physical_parent.iterdir()), [])
            for relative, content in self.files.items():
                target = destination / relative
                self.assertEqual(target.read_bytes(), content)
                self.assertEqual(target.stat().st_mode & download_data.WRITE_BITS, 0)
            self.assertEqual(download_data.main(["--destination", str(destination), "--verify-only"]), 0)
            self.assertEqual(download_data.main(["--destination", str(destination)]), 0)
            request.assert_called_once()
            stage.assert_called_once()

    def test_destination_symlinks_are_rejected_without_downloading(self):
        outside = self.root / "outside"
        outside.mkdir()
        protected = outside / "protected.csv"
        content = self.files[Path("cases/case  1.csv")]
        protected.write_bytes(content)
        linked_parent = self.root / "destination-link"
        linked_parent.symlink_to(outside, target_is_directory=True)
        nested = self.root / "nested-destination"
        nested.mkdir()
        (nested / "cases").symlink_to(outside, target_is_directory=True)
        file_destination = self.root / "file-destination"
        (file_destination / "cases").mkdir(parents=True)
        linked_file = file_destination / "cases/case  1.csv"
        linked_file.symlink_to(protected)
        original_mode = protected.stat().st_mode

        for destination in (linked_parent, linked_parent / "raw", nested, file_destination):
            with (
                self.subTest(destination=destination),
                patch.object(download_data, "read_metadata", return_value=self.metadata),
                patch.object(download_data.urllib.request, "urlopen") as request,
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as error,
            ):
                self.assertEqual(download_data.main(["--destination", str(destination)]), 1)
                self.assertIn("Refusing a symbolic link or junction:", error.getvalue())
                request.assert_not_called()
                self.assertEqual(protected.read_bytes(), content)
                self.assertEqual(protected.stat().st_mode, original_mode)
                self.assertEqual(list(outside.iterdir()), [protected])
                self.assertTrue(linked_parent.is_symlink())
                self.assertTrue((nested / "cases").is_symlink())
                self.assertTrue(linked_file.is_symlink())


if __name__ == "__main__":
    unittest.main(verbosity=2)
