"""Safe, reproducible filesystem primitives."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from collections.abc import Iterator
from contextlib import suppress
from pathlib import Path
from typing import Any

from .errors import SecurityError

MAX_FILES = 2_000
MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_TOTAL_BYTES = 100 * 1024 * 1024
IGNORED_PARTS = {".git", ".skillops", "__pycache__", ".DS_Store"}


def ensure_within(root: Path, candidate: Path) -> Path:
    root_resolved = root.resolve()
    candidate_resolved = candidate.resolve()
    try:
        candidate_resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise SecurityError(f"path escapes allowed root: {candidate}") from exc
    return candidate_resolved


def _files(root: Path) -> Iterator[tuple[str, Path]]:
    if not root.is_dir():
        raise SecurityError(f"skill path is not a directory: {root}")
    count = 0
    total = 0
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix().casefold()):
        relative = path.relative_to(root)
        if any(part in IGNORED_PARTS for part in relative.parts):
            continue
        if path.is_symlink():
            raise SecurityError(f"symbolic links are not accepted: {relative.as_posix()}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise SecurityError(f"unsupported filesystem entry: {relative.as_posix()}")
        size = path.stat().st_size
        count += 1
        total += size
        if count > MAX_FILES:
            raise SecurityError(f"skill exceeds {MAX_FILES} files")
        if size > MAX_FILE_BYTES:
            raise SecurityError(f"file exceeds {MAX_FILE_BYTES} bytes: {relative.as_posix()}")
        if total > MAX_TOTAL_BYTES:
            raise SecurityError(f"skill exceeds {MAX_TOTAL_BYTES} total bytes")
        yield relative.as_posix(), path


def canonical_bytes(data: bytes) -> bytes:
    if b"\x00" in data:
        return data
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return data
    return text.replace("\r\n", "\n").replace("\r", "\n").encode()


def tree_manifest(root: Path) -> tuple[str, list[str]]:
    digest = hashlib.sha256()
    names: list[str] = []
    for relative, path in _files(root):
        data = canonical_bytes(path.read_bytes())
        name_bytes = relative.encode("utf-8")
        digest.update(len(name_bytes).to_bytes(8, "big"))
        digest.update(name_bytes)
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
        names.append(relative)
    if not names:
        raise SecurityError("skill directory contains no files")
    return f"sha256:{digest.hexdigest()}", names


def copy_tree(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    for relative, path in _files(source):
        target = ensure_within(destination, destination / Path(relative))
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SecurityError(f"cannot read valid JSON from {path}: {exc}") from exc


def snapshot(source: Path, store: Path) -> tuple[str, list[str], Path]:
    content_hash, files = tree_manifest(source)
    destination = store / content_hash.removeprefix("sha256:")
    store.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        existing_hash, existing_files = tree_manifest(destination)
        if existing_hash != content_hash or existing_files != files:
            raise SecurityError(f"stored snapshot is incomplete or corrupted: {destination.name}")
        return content_hash, files, destination

    lock_path = store / f".{destination.name}.lock"
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise SecurityError(
            f"snapshot {destination.name} is being created by another process"
        ) from exc
    temporary = store / f".{destination.name}.{os.getpid()}.tmp"
    try:
        copy_tree(source, temporary)
        with suppress(FileExistsError):
            shutil.copytree(temporary, destination)
        finalized_hash, finalized_files = tree_manifest(destination)
        if finalized_hash != content_hash or finalized_files != files:
            raise SecurityError("finalized snapshot failed content verification")
    except Exception:
        if destination.exists():
            shutil.rmtree(destination)
        raise
    finally:
        os.close(descriptor)
        lock_path.unlink(missing_ok=True)
        if temporary.exists():
            shutil.rmtree(temporary)
    return content_hash, files, destination


def replace_tree(source: Path, target: Path, backup: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    backup.parent.mkdir(parents=True, exist_ok=True)
    staging = target.parent / f".{target.name}.skillops-staging"
    if staging.exists():
        shutil.rmtree(staging)
    copy_tree(source, staging)
    staged_hash, _ = tree_manifest(staging)
    source_hash, _ = tree_manifest(source)
    if staged_hash != source_hash:
        shutil.rmtree(staging)
        raise SecurityError("staged tree failed content verification")
    moved_old = False
    try:
        if target.exists():
            if backup.exists():
                shutil.rmtree(backup)
            target.rename(backup)
            moved_old = True
        staging.rename(target)
    except Exception:
        if moved_old and not target.exists() and backup.exists():
            backup.rename(target)
        raise
