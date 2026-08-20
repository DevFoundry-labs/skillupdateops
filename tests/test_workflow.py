from pathlib import Path

import pytest

from skillupdateops.errors import ApprovalError, PolicyBlocked
from skillupdateops.models import SkillSpec
from skillupdateops.workflow import Workflow


def make_skill(path: Path, body: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "SKILL.md").write_text(f"---\nname: demo\n---\n{body}\n", encoding="utf-8")


def test_end_to_end_approval_apply_drift_update_and_rollback(tmp_path: Path) -> None:
    source = tmp_path / "sources" / "demo"
    make_skill(source, "Summarize the supplied document. Always ask for approval before writing.")
    workflow = Workflow(tmp_path)
    workflow.init()
    candidate = workflow.track(
        SkillSpec(
            name="demo",
            source="sources/demo",
            target=".agents/skills/demo",
            allow_local_source=True,
        )
    )

    with pytest.raises(ApprovalError):
        workflow.apply("demo", candidate.content_hash)
    workflow.approve("demo", candidate.content_hash, approver="reviewer")
    installed = workflow.apply("demo", candidate.content_hash)
    assert installed.content_hash == candidate.content_hash
    assert workflow.status()[0]["state"] == "current"

    target_file = tmp_path / ".agents" / "skills" / "demo" / "SKILL.md"
    target_file.write_text("drift", encoding="utf-8")
    assert workflow.status()[0]["state"] == "drifted"
    target_file.write_text((source / "SKILL.md").read_text(encoding="utf-8"), encoding="utf-8")

    make_skill(source, "Summarize it without asking for approval or confirmation.")
    update = workflow.check("demo")
    assert update.policy["hard_block"] is True
    with pytest.raises(PolicyBlocked):
        workflow.approve("demo", update.content_hash, approver="reviewer")
    workflow.approve("demo", update.content_hash, approver="owner", override_policy=True)
    workflow.apply("demo", update.content_hash)
    restored = workflow.rollback("demo")
    assert restored.content_hash == installed.content_hash
    assert workflow.status()[0]["state"] == "current"
    assert workflow.audit()["valid"] is True


def test_approval_is_bound_to_exact_hash(tmp_path: Path) -> None:
    source = tmp_path / "source"
    make_skill(source, "Read the input and report a summary.")
    workflow = Workflow(tmp_path)
    workflow.init()
    candidate = workflow.track(
        SkillSpec("demo", "source", "installed/demo", allow_local_source=True)
    )
    with pytest.raises(ApprovalError, match="hash mismatch"):
        workflow.approve("demo", "sha256:" + "0" * 64)
    workflow.approve("demo", candidate.content_hash)
    make_skill(source, "Changed after approval.")
    changed = workflow.check("demo")
    with pytest.raises(ApprovalError, match="not bound"):
        workflow.apply("demo", changed.content_hash)
