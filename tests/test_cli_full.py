import json
from pathlib import Path

from skillupdateops.cli import run
from skillupdateops.errors import EXIT_CHANGES, EXIT_DRIFT, EXIT_ERROR, EXIT_OK
from skillupdateops.workflow import Workflow


def test_complete_cli_lifecycle(tmp_path: Path, capsys: object) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "SKILL.md").write_text(
        "# Demo\nAlways ask for approval before saving.\n", encoding="utf-8"
    )
    project = ["--project", str(tmp_path)]
    assert run([*project, "init"]) == EXIT_OK
    assert (
        run(
            [
                *project,
                "track",
                "demo",
                "--source",
                "source",
                "--target",
                "installed/demo",
                "--allow-local-source",
            ]
        )
        == EXIT_CHANGES
    )
    workflow = Workflow(tmp_path)
    candidate = workflow.load_candidate("demo")
    report = tmp_path / "reports" / "demo.md"
    assert run([*project, "report", "demo", "--output", str(report)]) == EXIT_OK
    assert "Skill update report" in report.read_text(encoding="utf-8")
    assert run([*project, "apply", "demo", "--hash", candidate.content_hash]) == EXIT_ERROR
    assert (
        run(
            [
                *project,
                "approve",
                "demo",
                "--hash",
                candidate.content_hash,
                "--approver",
                "cli-reviewer",
            ]
        )
        == EXIT_OK
    )
    assert run([*project, "apply", "demo", "--hash", candidate.content_hash]) == EXIT_OK
    assert run([*project, "status"]) == EXIT_OK

    fixture = tmp_path / "fixture.yml"
    fixture.write_text(
        "tests:\n  - name: approval\n    contains: ['ask for approval']\n",
        encoding="utf-8",
    )
    assert run([*project, "test", "demo", "--fixtures", "fixture.yml"]) == EXIT_OK
    assert run([*project, "audit", "--limit", "2"]) == EXIT_OK

    installed = tmp_path / "installed" / "demo" / "SKILL.md"
    installed.write_text("drift", encoding="utf-8")
    assert run([*project, "status"]) == EXIT_DRIFT
    installed.write_text((source / "SKILL.md").read_text(encoding="utf-8"), encoding="utf-8")

    (source / "SKILL.md").write_text(
        "# Demo v2\nAlways ask for approval before saving.\n", encoding="utf-8"
    )
    generated = tmp_path / "candidate.md"
    assert run([*project, "check", "demo", "--report", str(generated)]) == EXIT_CHANGES
    update = workflow.load_candidate("demo")
    assert run([*project, "approve", "demo", "--hash", update.content_hash]) == EXIT_OK
    assert run([*project, "apply", "demo", "--hash", update.content_hash]) == EXIT_OK
    assert run([*project, "rollback", "demo"]) == EXIT_OK

    capsys.readouterr()  # type: ignore[attr-defined]
    assert run([*project, "--json", "audit", "--limit", "1"]) == EXIT_OK
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert json.loads(captured.out)["valid"] is True


def test_check_all_empty(tmp_path: Path) -> None:
    assert run(["--project", str(tmp_path), "init"]) == EXIT_OK
    assert run(["--project", str(tmp_path), "check"]) == EXIT_OK
