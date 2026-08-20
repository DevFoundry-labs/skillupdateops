from pathlib import Path

from skillupdateops.cli import run
from skillupdateops.errors import EXIT_CHANGES, EXIT_OK


def test_cli_initialization_and_static_fixture(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "SKILL.md").write_text("# Demo\nExpected marker\n", encoding="utf-8")
    assert run(["--project", str(tmp_path), "init"]) == EXIT_OK
    result = run(
        [
            "--project",
            str(tmp_path),
            "track",
            "demo",
            "--source",
            "source",
            "--target",
            "installed/demo",
            "--allow-local-source",
        ]
    )
    assert result == EXIT_CHANGES
