from pathlib import Path

import pytest

from skillupdateops.errors import ConfigurationError, SecurityError
from skillupdateops.models import LockFile, SkillSpec
from skillupdateops.sources import acquire


def test_rejects_untrusted_remote_url(tmp_path: Path) -> None:
    spec = SkillSpec("demo", "http://example.com/repo.git", "target")
    with pytest.raises(SecurityError, match="GitHub"), acquire(spec, tmp_path):
        pass


def test_remote_acquisition_pins_revision(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    revision = "a" * 40

    def fake_git(arguments: list[str], cwd: Path | None = None) -> str:
        if arguments[0] == "clone":
            repository = Path(arguments[-1])
            (repository / "skills" / "demo").mkdir(parents=True)
            (repository / "skills" / "demo" / "SKILL.md").write_text("safe", encoding="utf-8")
            return ""
        assert cwd is not None
        return revision

    monkeypatch.setattr("skillupdateops.sources._run_git", fake_git)
    spec = SkillSpec(
        "demo", "https://github.com/example/repository.git", "target", subpath="skills/demo"
    )
    with acquire(spec, tmp_path) as acquired:
        assert acquired.revision == revision
        assert (acquired.path / "SKILL.md").exists()


def test_model_validation_rejects_unknown_fields() -> None:
    with pytest.raises(ConfigurationError, match="unknown"):
        SkillSpec.from_dict({"name": "x", "source": "s", "target": "t", "unexpected": True})
    with pytest.raises(ConfigurationError, match="schema_version"):
        LockFile.from_dict({"schema_version": 99})
