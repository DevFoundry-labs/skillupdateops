from pathlib import Path
from types import SimpleNamespace

import pytest

from skillupdateops.errors import SkillOpsError
from skillupdateops.github_pr import _run, open_draft_pr


def test_open_draft_pr_uses_disposable_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []

    def fake_run(arguments: list[str], cwd: Path) -> str:
        calls.append(arguments)
        if arguments[:3] == ["git", "branch", "--show-current"]:
            return "main"
        if arguments[:4] == ["git", "worktree", "add", "-b"]:
            Path(arguments[-2]).mkdir(parents=True)
        if arguments[:4] == ["git", "diff", "--cached", "--name-only"]:
            return "skills/demo/SKILL.md"
        if arguments[:3] == ["gh", "pr", "create"]:
            return "https://github.com/example/repo/pull/1"
        return ""

    def stage(_: str, __: str, checkout: Path) -> list[str]:
        report = checkout / "skillops-reports" / "demo.md"
        report.parent.mkdir(parents=True)
        report.write_text("report", encoding="utf-8")
        return ["skills/demo", "skills.lock", "skillops-reports/demo.md"]

    workflow = SimpleNamespace(state=SimpleNamespace(root=tmp_path), stage_for_review=stage)
    monkeypatch.setattr("skillupdateops.github_pr._run", fake_run)
    result = open_draft_pr(workflow, "demo", "sha256:" + "a" * 64)  # type: ignore[arg-type]
    assert result.endswith("/pull/1")
    assert any(call[:3] == ["git", "push", "--set-upstream"] for call in calls)
    assert any(call[:3] == ["gh", "pr", "create"] for call in calls)
    assert any(call[:3] == ["git", "worktree", "remove"] for call in calls)


def test_pr_refuses_dirty_checkout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("skillupdateops.github_pr._run", lambda *_: "dirty")
    workflow = SimpleNamespace(state=SimpleNamespace(root=tmp_path))
    with pytest.raises(SkillOpsError, match="dirty"):
        open_draft_pr(workflow, "demo", "sha256:" + "a" * 64)  # type: ignore[arg-type]


def test_command_error_is_sanitized(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result = SimpleNamespace(returncode=2, stdout="", stderr="failure")
    monkeypatch.setattr("skillupdateops.github_pr.subprocess.run", lambda *_, **__: result)
    with pytest.raises(SkillOpsError, match="failure"):
        _run(["git", "status"], tmp_path)
