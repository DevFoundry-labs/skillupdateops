"""Measure deterministic inventory, analysis, hashing, and persistence for 100 skills."""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

from skillupdateops.content import tree_manifest
from skillupdateops.models import SkillSpec
from skillupdateops.workflow import Workflow


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="skillops-benchmark-", dir=Path.cwd()) as temporary:
        root = Path(temporary)
        workflow = Workflow(root)
        workflow.init()
        specs: dict[str, SkillSpec] = {}
        for index in range(100):
            name = f"skill-{index:03d}"
            source = root / "sources" / name
            source.mkdir(parents=True)
            (source / "SKILL.md").write_text(
                f"# {name}\nSummarize input {index}. Always ask for approval before writing.\n",
                encoding="utf-8",
            )
            specs[name] = SkillSpec(
                name=name,
                source=f"sources/{name}",
                target=f".agents/skills/{name}",
                allow_local_source=True,
            )
        started = time.perf_counter()
        for spec in specs.values():
            tree_manifest(root / spec.source)
        inventory_elapsed = time.perf_counter() - started

        workflow.state.save_specs(specs)
        started = time.perf_counter()
        workflow.check_all()
        full_check_elapsed = time.perf_counter() - started
        result = {
            "skills": 100,
            "inventory_and_hash_seconds": round(inventory_elapsed, 4),
            "inventory_skills_per_second": round(100 / inventory_elapsed, 2),
            "full_check_seconds": round(full_check_elapsed, 4),
            "executed_candidate_code": False,
            "audit_valid": workflow.audit(limit=0)["valid"],
        }
        print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
