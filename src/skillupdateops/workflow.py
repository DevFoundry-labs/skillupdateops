"""End-to-end update, approval, installation, drift, and rollback workflow."""

from __future__ import annotations

import getpass
import json
import os
import shutil
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .analysis import analyze, compare
from .content import atomic_json, ensure_within, read_json, replace_tree, snapshot, tree_manifest
from .errors import ApprovalError, ConfigurationError, PolicyBlocked, SkillOpsError
from .models import Approval, Candidate, LockEntry, SkillSpec, now_iso
from .policy import evaluate, load_policy
from .reporting import candidate_markdown
from .sources import acquire
from .state import ProjectState


def _safe_name(name: str) -> str:
    if not name or len(name) > 80 or not all(ch.isalnum() or ch in "-_." for ch in name):
        raise ConfigurationError(
            "name must use 1-80 letters, numbers, dots, dashes, or underscores"
        )
    if name in {".", ".."}:
        raise ConfigurationError("invalid skill name")
    return name


class Workflow:
    def __init__(self, root: Path):
        self.state = ProjectState(root)

    def init(self) -> None:
        first_initialization = not self.state.config_path.exists()
        self.state.initialize()
        if first_initialization:
            self.state.append_audit("project.initialized", {"schema_version": 1})

    def track(self, spec: SkillSpec) -> Candidate:
        _safe_name(spec.name)
        self.state.initialize()
        specs = self.state.specs()
        specs[spec.name] = spec
        self.state.save_specs(specs)
        self.state.append_audit(
            "skill.tracked",
            {"name": spec.name, "source": spec.source, "ref": spec.ref, "subpath": spec.subpath},
        )
        return self.check(spec.name)

    def _candidate_path(self, name: str) -> Path:
        return self.state.candidates / f"{_safe_name(name)}.json"

    def _approval_path(self, name: str) -> Path:
        return self.state.approvals / f"{_safe_name(name)}.json"

    def load_candidate(self, name: str) -> Candidate:
        data = read_json(self._candidate_path(name))
        if data is None:
            raise SkillOpsError(f"no candidate for {name}; run 'skillops check {name}'")
        return Candidate.from_dict(data)

    def check(self, name: str) -> Candidate:
        specs = self.state.specs()
        if name not in specs:
            raise ConfigurationError(f"untracked skill: {name}")
        lock = self.state.load_lock()
        current = lock.skills.get(name)
        policy = load_policy(self.state.policy_path)
        with acquire(specs[name], self.state.root) as acquired:
            content_hash, files, stored = snapshot(acquired.path, self.state.store)
            capabilities = analyze(stored)
        change = compare(current.capabilities if current else None, capabilities)
        if current and current.content_hash != content_hash:
            change["changed"] = True
        result = evaluate(capabilities, change, policy)
        candidate = Candidate(
            name=name,
            content_hash=content_hash,
            resolved_revision=acquired.revision,
            files=files,
            capabilities=capabilities,
            snapshot=stored.name,
            checked_at=now_iso(),
            change=change,
            policy=result,
        )
        atomic_json(self._candidate_path(name), candidate.to_dict())
        self.state.append_audit(
            "candidate.checked",
            {
                "name": name,
                "hash": content_hash,
                "revision": acquired.revision,
                "decision": result["decision"],
                "changed": change["changed"],
            },
        )
        return candidate

    def check_all(self) -> list[Candidate]:
        return [self.check(name) for name in sorted(self.state.specs())]

    def report(self, name: str) -> str:
        candidate = self.load_candidate(name)
        return candidate_markdown(candidate, self.state.load_lock().skills.get(name))

    def stage_for_review(self, name: str, candidate_hash: str, destination_root: Path) -> list[str]:
        """Stage a candidate in a disposable checkout; PR review is the approval boundary."""
        candidate = self.load_candidate(name)
        if candidate.content_hash != candidate_hash:
            raise ApprovalError("--hash must exactly match the checked candidate")
        spec = self.state.specs().get(name)
        if spec is None:
            raise ConfigurationError(f"untracked skill: {name}")
        destination = destination_root.resolve()
        target = ensure_within(destination, destination / spec.target)
        if target == destination or destination / ".git" in target.parents:
            raise ConfigurationError("invalid target for PR staging")
        source = ensure_within(self.state.store, self.state.store / candidate.snapshot)
        verified_hash, verified_files = tree_manifest(source)
        if verified_hash != candidate.content_hash or verified_files != candidate.files:
            raise ApprovalError("candidate snapshot changed before PR staging")
        if target.exists():
            if not target.is_dir():
                raise ConfigurationError("PR target exists but is not a directory")
            shutil.rmtree(target)
        from .content import copy_tree

        copy_tree(source, target)
        destination_state = ProjectState(destination)
        lock = self.state.load_lock()
        current = lock.skills.get(name)
        lock.skills[name] = LockEntry(
            name=name,
            source=spec.source,
            target=spec.target,
            requested_ref=spec.ref,
            resolved_revision=candidate.resolved_revision,
            subpath=spec.subpath,
            content_hash=candidate.content_hash,
            files=candidate.files,
            capabilities=candidate.capabilities,
            installed_at=candidate.checked_at,
            previous_hash=current.content_hash if current else None,
        )
        destination_state.save_lock(lock)
        report_path = destination / "skillops-reports" / f"{name}-{candidate.snapshot[:12]}.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            candidate_markdown(candidate, current), encoding="utf-8", newline="\n"
        )
        return [spec.target, "skills.lock", report_path.relative_to(destination).as_posix()]

    def approve(
        self,
        name: str,
        candidate_hash: str,
        *,
        approver: str | None = None,
        ttl_hours: int = 24,
        override_policy: bool = False,
    ) -> Approval:
        candidate = self.load_candidate(name)
        if candidate.content_hash != candidate_hash:
            raise ApprovalError(
                "hash mismatch: checked candidate is "
                f"{candidate.content_hash}, not {candidate_hash}"
            )
        if ttl_hours < 1 or ttl_hours > 168:
            raise ApprovalError("approval TTL must be between 1 and 168 hours")
        if candidate.policy.get("hard_block") and not override_policy:
            raise PolicyBlocked("critical policy findings require --override-policy")
        actor = approver or os.getenv("GITHUB_ACTOR") or getpass.getuser()
        approved = datetime.now(UTC)
        approval = Approval(
            name=name,
            candidate_hash=candidate_hash,
            approver=actor,
            approved_at=approved.replace(microsecond=0).isoformat(),
            expires_at=(approved + timedelta(hours=ttl_hours)).replace(microsecond=0).isoformat(),
            override_policy=override_policy,
        )
        atomic_json(self._approval_path(name), approval.to_dict())
        self.state.append_audit(
            "candidate.approved",
            {
                "name": name,
                "hash": candidate_hash,
                "approver": actor,
                "override_policy": override_policy,
                "expires_at": approval.expires_at,
            },
        )
        return approval

    def _valid_approval(self, candidate: Candidate) -> Approval:
        data = read_json(self._approval_path(candidate.name))
        if not isinstance(data, dict):
            raise ApprovalError("exact-hash approval is required before apply")
        try:
            approval = Approval(
                name=str(data["name"]),
                candidate_hash=str(data["candidate_hash"]),
                approver=str(data["approver"]),
                approved_at=str(data["approved_at"]),
                expires_at=str(data["expires_at"]),
                override_policy=bool(data.get("override_policy", False)),
            )
            expires = datetime.fromisoformat(approval.expires_at)
        except (KeyError, TypeError, ValueError) as exc:
            raise ApprovalError("approval record is invalid") from exc
        if approval.name != candidate.name or approval.candidate_hash != candidate.content_hash:
            raise ApprovalError("approval is not bound to the current candidate hash")
        if expires <= datetime.now(UTC):
            raise ApprovalError("approval has expired")
        if candidate.policy.get("hard_block") and not approval.override_policy:
            raise PolicyBlocked("critical policy findings require an override approval")
        return approval

    def apply(self, name: str, candidate_hash: str) -> LockEntry:
        candidate = self.load_candidate(name)
        if candidate.content_hash != candidate_hash:
            raise ApprovalError("--hash must exactly match the checked candidate")
        approval = self._valid_approval(candidate)
        spec = self.state.specs().get(name)
        if spec is None:
            raise ConfigurationError(f"untracked skill: {name}")
        source = ensure_within(self.state.store, self.state.store / candidate.snapshot)
        verified_hash, verified_files = tree_manifest(source)
        if verified_hash != candidate.content_hash or verified_files != candidate.files:
            raise ApprovalError("candidate snapshot changed after approval")
        target = ensure_within(self.state.root, self.state.root / spec.target)
        if (
            target == self.state.root
            or self.state.directory in target.parents
            or target == self.state.directory
        ):
            raise ConfigurationError("target cannot be project root or inside .skillops")

        with self.state.exclusive():
            lock = self.state.load_lock()
            previous = lock.skills.get(name)
            if previous and previous.content_hash == candidate.content_hash:
                return previous
            history_path = self.state.history / f"{name}.json"
            history = read_json(history_path, default=[])
            if previous:
                history.append(asdict(previous))
                atomic_json(history_path, history)
            backup = (
                self.state.directory
                / "backups"
                / name
                / (previous.content_hash.removeprefix("sha256:") if previous else "untracked")
            )
            if target.exists() and not target.is_dir():
                raise ConfigurationError(f"target exists but is not a directory: {target}")
            replace_tree(source, target, backup)
            entry = LockEntry(
                name=name,
                source=spec.source,
                target=spec.target,
                requested_ref=spec.ref,
                resolved_revision=candidate.resolved_revision,
                subpath=spec.subpath,
                content_hash=candidate.content_hash,
                files=candidate.files,
                capabilities=candidate.capabilities,
                installed_at=now_iso(),
                previous_hash=previous.content_hash if previous else None,
            )
            lock.skills[name] = entry
            self.state.save_lock(lock)
            self._approval_path(name).unlink(missing_ok=True)
            self.state.append_audit(
                "candidate.applied",
                {
                    "name": name,
                    "hash": candidate.content_hash,
                    "previous_hash": previous.content_hash if previous else None,
                    "approver": approval.approver,
                    "target": spec.target,
                },
            )
            return entry

    def rollback(self, name: str) -> LockEntry:
        history_path = self.state.history / f"{_safe_name(name)}.json"
        history = read_json(history_path, default=[])
        if not isinstance(history, list) or not history:
            raise SkillOpsError(f"no rollback history for {name}")
        with self.state.exclusive():
            lock = self.state.load_lock()
            current = lock.skills.get(name)
            previous = LockEntry.from_dict(history.pop())
            source = self.state.store / previous.content_hash.removeprefix("sha256:")
            verified, _ = tree_manifest(source)
            if verified != previous.content_hash:
                raise SkillOpsError("rollback snapshot failed verification")
            target = ensure_within(self.state.root, self.state.root / previous.target)
            backup = self.state.directory / "backups" / name / "rollback-current"
            replace_tree(source, target, backup)
            lock.skills[name] = previous
            self.state.save_lock(lock)
            atomic_json(history_path, history)
            self.state.append_audit(
                "skill.rolled_back",
                {
                    "name": name,
                    "from_hash": current.content_hash if current else None,
                    "to_hash": previous.content_hash,
                },
            )
            return previous

    def status(self) -> list[dict[str, Any]]:
        lock = self.state.load_lock()
        result: list[dict[str, Any]] = []
        for name, entry in sorted(lock.skills.items()):
            target = ensure_within(self.state.root, self.state.root / entry.target)
            if not target.is_dir():
                actual = None
                state = "missing"
            else:
                actual, _ = tree_manifest(target)
                state = "current" if actual == entry.content_hash else "drifted"
            result.append(
                {
                    "name": name,
                    "state": state,
                    "expected_hash": entry.content_hash,
                    "actual_hash": actual,
                }
            )
        return result

    def audit(self, limit: int = 20) -> dict[str, Any]:
        valid, count = self.state.verify_audit()
        records: list[dict[str, Any]] = []
        if self.state.audit_path.exists():
            lines = [
                line
                for line in self.state.audit_path.read_text(encoding="utf-8").splitlines()
                if line
            ]
            records = [json.loads(line) for line in lines[-limit:]]
        return {"valid": valid, "events": count, "records": records}
