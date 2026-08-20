from pathlib import Path

from skillupdateops.models import SkillSpec
from skillupdateops.workflow import Workflow


def test_stages_exact_candidate_and_report_for_pr(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "SKILL.md").write_text("# Safe skill\n", encoding="utf-8")
    workflow = Workflow(tmp_path)
    workflow.init()
    candidate = workflow.track(SkillSpec("demo", "source", "skills/demo", allow_local_source=True))
    checkout = tmp_path / "worktree"
    checkout.mkdir()
    paths = workflow.stage_for_review("demo", candidate.content_hash, checkout)
    assert (checkout / "skills" / "demo" / "SKILL.md").exists()
    assert (checkout / "skills.lock").exists()
    report = next(path for path in paths if path.startswith("skillops-reports/"))
    assert "Candidate" in (checkout / report).read_text(encoding="utf-8")
