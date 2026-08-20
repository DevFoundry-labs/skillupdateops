"""Declarative static assertions and Docker-isolated executable fixtures."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import yaml

from .content import ensure_within
from .errors import ConfigurationError, SecurityError, SkillOpsError


def _load(path: Path) -> list[dict[str, Any]]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigurationError(f"invalid fixture file: {exc}") from exc
    tests = data.get("tests") if isinstance(data, dict) else None
    if not isinstance(tests, list):
        raise ConfigurationError("fixture file must contain a tests list")
    return [dict(item) for item in tests]


def _text(root: Path) -> str:
    chunks: list[str] = []
    for path in sorted(root.rglob("*.md")):
        if path.is_symlink():
            raise SecurityError("fixture input contains a symbolic link")
        chunks.append(path.read_text(encoding="utf-8"))
    return "\n".join(chunks)


def _docker_test(root: Path, test: dict[str, Any]) -> dict[str, Any]:
    if shutil.which("docker") is None:
        raise SkillOpsError("Docker is required for executable fixtures; nothing was executed")
    command = test.get("command")
    if (
        not isinstance(command, list)
        or not command
        or not all(isinstance(item, str) for item in command)
    ):
        raise ConfigurationError("executable fixture command must be a non-empty string list")
    timeout = int(test.get("timeout_seconds", 30))
    if timeout < 1 or timeout > 300:
        raise ConfigurationError("fixture timeout must be between 1 and 300 seconds")
    with tempfile.TemporaryDirectory(prefix="skillops-fixture-") as workspace:
        arguments = [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--pids-limit",
            "64",
            "--memory",
            "256m",
            "--cpus",
            "1",
            "--user",
            "65534:65534",
            "--mount",
            f"type=bind,src={root.resolve()},dst=/skill,readonly",
            "--mount",
            f"type=bind,src={Path(workspace).resolve()},dst=/work",
            "--workdir",
            "/work",
            "python:3.12-alpine",
            *command,
        ]
        try:
            result = subprocess.run(
                arguments, check=False, capture_output=True, text=True, timeout=timeout + 10
            )
        except subprocess.TimeoutExpired as exc:
            raise SkillOpsError(f"fixture timed out after {timeout} seconds") from exc
    expected_exit = int(test.get("expect_exit", 0))
    marker = str(test.get("stdout_contains", ""))
    passed = result.returncode == expected_exit and (not marker or marker in result.stdout)
    return {
        "passed": passed,
        "exit_code": result.returncode,
        "expected_exit": expected_exit,
        "stdout_contains": marker or None,
    }


def run_fixtures(project_root: Path, skill_root: Path, fixture_path: Path) -> list[dict[str, Any]]:
    root = ensure_within(project_root, skill_root)
    fixtures = ensure_within(project_root, fixture_path)
    combined = _text(root)
    results: list[dict[str, Any]] = []
    for index, test in enumerate(_load(fixtures), start=1):
        name = str(test.get("name", f"test-{index}"))
        contains = test.get("contains", [])
        excludes = test.get("not_contains", [])
        if not isinstance(contains, list) or not isinstance(excludes, list):
            raise ConfigurationError("contains and not_contains must be lists")
        missing = [str(value) for value in contains if str(value) not in combined]
        forbidden = [str(value) for value in excludes if str(value) in combined]
        result: dict[str, Any] = {
            "name": name,
            "passed": not missing and not forbidden,
            "missing": missing,
            "forbidden": forbidden,
            "mode": "static",
        }
        if "command" in test:
            executable = _docker_test(root, test)
            result["mode"] = "docker"
            result["execution"] = executable
            result["passed"] = result["passed"] and executable["passed"]
        results.append(result)
    return results
