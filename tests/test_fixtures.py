from pathlib import Path
from types import SimpleNamespace

import pytest

from skillupdateops.errors import ConfigurationError, SkillOpsError
from skillupdateops.fixtures import run_fixtures


def test_static_fixture_pass_and_fail(tmp_path: Path) -> None:
    skill = tmp_path / "skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text("approval required", encoding="utf-8")
    fixture = tmp_path / "fixture.yml"
    fixture.write_text(
        "tests:\n"
        "  - name: pass\n    contains: [approval]\n    not_contains: [bypass]\n"
        "  - name: fail\n    contains: [missing]\n",
        encoding="utf-8",
    )
    result = run_fixtures(tmp_path, skill, fixture)
    assert result[0]["passed"] is True
    assert result[1]["passed"] is False


def test_executable_fixture_fails_closed_without_docker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    skill = tmp_path / "skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text("safe", encoding="utf-8")
    fixture = tmp_path / "fixture.yml"
    fixture.write_text("tests:\n  - name: exec\n    command: ['true']\n", encoding="utf-8")
    monkeypatch.setattr("skillupdateops.fixtures.shutil.which", lambda _: None)
    with pytest.raises(SkillOpsError, match="nothing was executed"):
        run_fixtures(tmp_path, skill, fixture)


def test_docker_fixture_uses_restricted_runner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    skill = tmp_path / "skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text("safe", encoding="utf-8")
    fixture = tmp_path / "fixture.yml"
    fixture.write_text(
        "tests:\n  - name: exec\n    command: ['python', '-V']\n    stdout_contains: Python\n",
        encoding="utf-8",
    )
    captured: list[str] = []

    def fake_run(arguments: list[str], **_: object) -> SimpleNamespace:
        captured.extend(arguments)
        return SimpleNamespace(returncode=0, stdout="Python 3.12", stderr="")

    monkeypatch.setattr("skillupdateops.fixtures.shutil.which", lambda _: "docker")
    monkeypatch.setattr("skillupdateops.fixtures.subprocess.run", fake_run)
    result = run_fixtures(tmp_path, skill, fixture)
    assert result[0]["passed"] is True
    assert "none" in captured
    assert "no-new-privileges" in captured
    assert "ALL" in captured


def test_invalid_fixture_schema(tmp_path: Path) -> None:
    skill = tmp_path / "skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text("safe", encoding="utf-8")
    fixture = tmp_path / "fixture.yml"
    fixture.write_text("tests: wrong\n", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="tests list"):
        run_fixtures(tmp_path, skill, fixture)
