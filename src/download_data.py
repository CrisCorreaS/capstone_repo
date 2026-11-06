import argparse
import csv
import hashlib
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys
import tempfile
import urllib.request
import zipfile


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WRITE_BITS = stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH


class AcquisitionError(Exception):
    """A source, checksum or destination failed validation."""


def safe_relative_path(value):
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or path.as_posix() != value
        or any(part in {".", ".."} for part in path.parts)
        or "\\" in value
        or ":" in value
    ):
        raise AcquisitionError(f"Unsafe metadata or archive path: {value!r}")
    return path


def read_metadata():
    """Expand this dataset's three source records and read its SHA-256 values."""
    with (PROJECT_ROOT / "metadata/sources.tsv").open(
        encoding="utf-8", newline=""
    ) as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        fields = reader.fieldnames or []
        rows = list(reader)
    required = {"download_url", "provider_archive_md5", "archive_member", "destination"}
    if len(fields) != len(set(fields)) or not required.issubset(fields):
        raise AcquisitionError("Missing or duplicate source metadata columns.")
    if len(rows) != 3:
        raise AcquisitionError("Expected three S1 source records in metadata/sources.tsv.")
    if any(not isinstance(row[field], str) or not row[field] for row in rows for field in required):
        raise AcquisitionError("Source records must have non-empty download, checksum and mapping fields.")
    urls = {row["download_url"] for row in rows}
    md5s = {row["provider_archive_md5"] for row in rows}
    if len(urls) != 1 or len(md5s) != 1:
        raise AcquisitionError("S1 source records must agree on the archive URL and MD5.")
    url, archive_md5 = urls.pop(), md5s.pop()
    if not url.startswith("https://") or not re.fullmatch(r"[0-9a-f]{32}", archive_md5):
        raise AcquisitionError("Invalid S1 download URL or provider MD5.")

    mappings = {}
    for row in rows:
        numbers = range(1, 209) if "{n}" in row["archive_member"] else (None,)
        for number in numbers:
            member = row["archive_member"].format(n=number)
            safe_relative_path(member)
            destination = safe_relative_path(row["destination"].format(n=number))
            relative = Path(destination.relative_to("data/raw"))
            if relative in mappings:
                raise AcquisitionError(f"Duplicate destination mapping: {relative}")
            mappings[relative] = member

    expected = {
        Path("cases") / f"case  {n}.csv": f"S1/case  {n}.csv"
        for n in range(1, 209)
    }
    expected.update(
        {Path(name): f"S1/{name}" for name in ("clinical_data.txt", "readme.txt")}
    )
    if mappings != expected:
        raise AcquisitionError("Source mappings must describe the 210 original S1 files.")

    checksums = {}
    manifest = PROJECT_ROOT / "metadata/checksums.sha256"
    for line in manifest.read_text(encoding="utf-8").splitlines():
        # Split only after the digest, preserving the two spaces in case filenames.
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if match is None:
            raise AcquisitionError("Invalid line in metadata/checksums.sha256.")
        digest, name = match.groups()
        relative = Path(safe_relative_path(name).relative_to("data/raw"))
        if relative in checksums:
            raise AcquisitionError(f"Duplicate checksum entry: {name}")
        checksums[relative] = digest
    if checksums.keys() != mappings.keys():
        raise AcquisitionError("Source mappings and SHA-256 manifest must cover the same 210 files.")
    return url, archive_md5, mappings, checksums


def reject_links(path):
    for component in (path, *path.parents):
        if component.is_symlink() or component.is_junction():
            raise AcquisitionError(f"Refusing a symbolic link or junction: {component}")


def verify_file(path, expected):
    reject_links(path)
    if not path.exists():
        return False
    if not path.is_file():
        raise AcquisitionError(f"Expected a regular file: {path}")
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != expected:
        detail = ""
        if (
            b"\r\n" in content
            and hashlib.sha256(content.replace(b"\r\n", b"\n")).hexdigest() == expected
        ):
            detail = (
                " This file has CRLF line endings; the manifest describes the original LF bytes."
                " Use an isolated --destination until the separate raw-data migration."
            )
        raise AcquisitionError(f"SHA-256 mismatch: {path}.{detail} File left unchanged.")
    return True


def inspect_destination(destination, checksums):
    reject_links(destination)
    if destination.exists() and not destination.is_dir():
        raise AcquisitionError(f"Destination is not a directory: {destination}")
    return [
        relative for relative, digest in checksums.items()
        if not verify_file(destination / relative, digest)
    ]


def stage_archive(url, archive_md5, mappings, checksums, temporary):
    archive_path = temporary / "source.zip"
    request = urllib.request.Request(url, headers={"User-Agent": "capstone-cgm-acquisition/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response, archive_path.open("wb") as output:
        shutil.copyfileobj(response, output)
    with archive_path.open("rb") as stream:
        actual_md5 = hashlib.file_digest(stream, "md5").hexdigest()
    if actual_md5 != archive_md5:
        raise AcquisitionError(f"Archive MD5 mismatch: expected {archive_md5}, got {actual_md5}.")

    staged = temporary / "verified"
    with zipfile.ZipFile(archive_path) as archive:
        members = {}
        for info in archive.infolist():
            safe_relative_path(info.filename.rstrip("/") if info.is_dir() else info.filename)
            if info.filename in members:
                raise AcquisitionError(f"Duplicate ZIP member: {info.filename}")
            if stat.S_ISLNK(info.external_attr >> 16):
                raise AcquisitionError(f"Refusing a ZIP symbolic link: {info.filename}")
            members[info.filename] = info
        for relative, member in mappings.items():
            if member not in members or members[member].is_dir():
                raise AcquisitionError(f"Missing expected ZIP file: {member}")
            target = staged / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(members[member]) as source, target.open("xb") as output:
                shutil.copyfileobj(source, output)
            verify_file(target, checksums[relative])
    return staged


def publish(destination, staged, checksums):
    """Publish verified bytes without overwriting files; roll back handled failures."""
    created_files = []
    created_directories = []
    previous_modes = {}
    succeeded = False

    def ensure_directory(path):
        reject_links(path)
        if not path.exists():
            ensure_directory(path.parent)
            path.mkdir()
            created_directories.append(path)
        elif not path.is_dir():
            raise AcquisitionError(f"Expected a directory: {path}")

    try:
        # Recheck existing files after the download, before changing the destination.
        missing = inspect_destination(destination, checksums)
        if missing and staged is None:
            raise AcquisitionError("Destination changed during verification; run acquisition again.")
        for relative in missing:
            target = destination / relative
            ensure_directory(target.parent)
            with target.open("xb") as output:
                created_files.append(target)
                with (staged / relative).open("rb") as source:
                    shutil.copyfileobj(source, output)
            verify_file(target, checksums[relative])
        for relative in checksums:
            target = destination / relative
            previous_modes[target] = stat.S_IMODE(target.stat().st_mode)
            target.chmod(previous_modes[target] & ~WRITE_BITS)
            if target.stat().st_mode & WRITE_BITS:
                raise AcquisitionError(f"Could not make file read-only: {target}")
        succeeded = True
    finally:
        if not succeeded:
            cleanup_errors = []
            for target, mode in previous_modes.items():
                if target not in created_files:
                    try:
                        target.chmod(mode)
                    except OSError as error:
                        cleanup_errors.append(str(error))
            for target in reversed(created_files):
                try:
                    target.chmod(stat.S_IREAD | stat.S_IWRITE)
                    target.unlink()
                except OSError as error:
                    cleanup_errors.append(str(error))
            for directory in reversed(created_directories):
                try:
                    directory.rmdir()
                except OSError as error:
                    cleanup_errors.append(str(error))
            if cleanup_errors:
                raise AcquisitionError(
                    "Could not completely roll back publication: " + "; ".join(cleanup_errors)
                )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--destination", type=Path, default=PROJECT_ROOT / "data/raw",
        help="Raw-data directory (default: project data/raw).",
    )
    parser.add_argument(
        "--verify-only", action="store_true",
        help="Check existing files without downloading or changing permissions.",
    )
    args = parser.parse_args(argv)
    destination = args.destination.absolute()
    try:
        url, archive_md5, mappings, checksums = read_metadata()
        missing = inspect_destination(destination, checksums)
        if args.verify_only:
            if missing:
                raise AcquisitionError(f"Missing {len(missing)} expected files; first: {destination / missing[0]}")
            print(f"Verified all 210 files in {destination}; no files modified.")
        elif not missing:
            publish(destination, None, checksums)
            print(f"All 210 files already match in {destination}; download skipped. Files are read-only.")
        else:
            print("Downloading the S1 archive and verifying all 210 files...", flush=True)
            with tempfile.TemporaryDirectory(prefix="cgm-download-") as folder:
                staged = stage_archive(url, archive_md5, mappings, checksums, Path(folder))
                publish(destination, staged, checksums)
            print(f"Downloaded and verified all 210 files in {destination}. Files are read-only.")
        return 0
    except (AcquisitionError, OSError, ValueError, KeyError, RuntimeError, zipfile.BadZipFile, EOFError) as error:
        print(f"Data acquisition failed: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Data acquisition interrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
