"""Non-executing local and Git source acquisition."""

from __future__ import annotations

import re
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from .content import ensure_within
from .errors import SecurityError, SourceError
from .models import SkillSpec

HTTPS_GIT = re.compile(r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?$")


@dataclass(frozen=True)
class AcquiredSource:
    path: Path
    revision: str


def _run_git(arguments: list[str], cwd: Path | None = None) -> str:
    command = [
        "git",
        "-c",
        "core.hooksPath=NUL" if __import__("os").name == "nt" else "core.hooksPath=/dev/null",
        "-c",
        "protocol.file.allow=never",
        *arguments,
    ]
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SourceError(f"Git invocation failed: {exc}") from exc
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()[-1_000:]
        raise SourceError(f"Git failed ({result.returncode}): {detail}")
    return result.stdout.strip()


def _validate_remote(source: str) -> None:
    parsed = urlparse(source)
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise SecurityError("source URLs may not contain credentials, query strings, or fragments")
    if not HTTPS_GIT.fullmatch(source):
        raise SecurityError("remote sources must be HTTPS GitHub repository URLs")


@contextmanager
def acquire(spec: SkillSpec, project_root: Path) -> Iterator[AcquiredSource]:
    possible_local = Path(spec.source)
    if spec.allow_local_source:
        root = ensure_within(project_root, (project_root / possible_local))
        if not root.is_dir():
            raise SourceError(f"local source does not exist: {root}")
        selected = ensure_within(root, root / spec.subpath)
        if not selected.is_dir():
            raise SourceError(f"skill subpath does not exist: {spec.subpath}")
        yield AcquiredSource(selected, f"local:{root}")
        return

    _validate_remote(spec.source)
    with tempfile.TemporaryDirectory(prefix="skillops-source-") as temporary:
        repository = Path(temporary) / "repo"
        _run_git(
            [
                "clone",
                "--depth",
                "1",
                "--single-branch",
                "--branch",
                spec.ref,
                "--config",
                "core.hooksPath=NUL"
                if __import__("os").name == "nt"
                else "core.hooksPath=/dev/null",
                "--",
                spec.source,
                str(repository),
            ]
        )
        revision = _run_git(["rev-parse", "HEAD"], cwd=repository)
        if not re.fullmatch(r"[0-9a-f]{40,64}", revision):
            raise SourceError("Git returned an invalid revision")
        selected = ensure_within(repository, repository / spec.subpath)
        if not selected.is_dir():
            raise SourceError(f"skill subpath does not exist at {revision}: {spec.subpath}")
        yield AcquiredSource(selected, revision)
