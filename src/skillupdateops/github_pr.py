"""Create a reviewable draft pull request without mutating the current checkout."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from .errors import SkillOpsError
from .workflow import Workflow


def _run(arguments: list[str], cwd: Path) -> str:
    try:
        result = subprocess.run(
            arguments, cwd=cwd, check=False, capture_output=True, text=True, timeout=120
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SkillOpsError(f"command failed to start: {arguments[0]}: {exc}") from exc
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()[-1_000:]
        raise SkillOpsError(f"{arguments[0]} failed ({result.returncode}): {detail}")
    return result.stdout.strip()


def open_draft_pr(workflow: Workflow, name: str, candidate_hash: str) -> str:
    root = workflow.state.root
    if _run(["git", "status", "--porcelain"], root):
        raise SkillOpsError("refusing PR creation from a dirty worktree")
    base = _run(["git", "branch", "--show-current"], root)
    if not base:
        raise SkillOpsError("PR creation requires a named local branch")
    _run(["gh", "auth", "status"], root)
    branch = f"skillops/update-{name}-{candidate_hash.removeprefix('sha256:')[:10]}"
    with tempfile.TemporaryDirectory(prefix="skillops-pr-") as temporary:
        checkout = Path(temporary) / "checkout"
        added = False
        try:
            _run(["git", "worktree", "add", "-b", branch, str(checkout), "HEAD"], root)
            added = True
            paths = workflow.stage_for_review(name, candidate_hash, checkout)
            _run(["git", "add", "--", *paths], checkout)
            if not _run(["git", "diff", "--cached", "--name-only"], checkout):
                raise SkillOpsError("candidate produces no reviewable Git changes")
            _run(["git", "commit", "-m", f"chore(skills): update {name}"], checkout)
            _run(["git", "push", "--set-upstream", "origin", branch], checkout)
            report = next(path for path in paths if path.startswith("skillops-reports/"))
            return _run(
                [
                    "gh",
                    "pr",
                    "create",
                    "--draft",
                    "--base",
                    base,
                    "--head",
                    branch,
                    "--title",
                    f"chore(skills): update {name}",
                    "--body-file",
                    report,
                ],
                checkout,
            )
        finally:
            if added:
                _run(["git", "worktree", "remove", "--force", str(checkout)], root)
