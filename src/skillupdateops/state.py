"""Project configuration, concurrency, and tamper-evident audit persistence."""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any

import yaml

from .content import atomic_json, read_json
from .errors import ConfigurationError, SkillOpsError
from .models import LockFile, SkillSpec, now_iso


class ProjectState:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.directory = self.root / ".skillops"
        self.config_path = self.directory / "skills.yml"
        self.policy_path = self.directory / "policy.yml"
        self.lock_path = self.root / "skills.lock"
        self.store = self.directory / "store"
        self.candidates = self.directory / "candidates"
        self.approvals = self.directory / "approvals"
        self.history = self.directory / "history"
        self.audit_path = self.directory / "audit.jsonl"

    def _last_audit_line(self) -> str | None:
        if not self.audit_path.exists() or self.audit_path.stat().st_size == 0:
            return None
        with self.audit_path.open("rb") as handle:
            position = handle.seek(0, os.SEEK_END)
            data = b""
            while position > 0:
                size = min(4096, position)
                position -= size
                handle.seek(position)
                data = handle.read(size) + data
                lines = data.splitlines()
                if len(lines) > 1 or position == 0:
                    for line in reversed(lines):
                        if line.strip():
                            return line.decode("utf-8")
        return None

    def initialize(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        self.store.mkdir(exist_ok=True)
        self.candidates.mkdir(exist_ok=True)
        self.approvals.mkdir(exist_ok=True)
        self.history.mkdir(exist_ok=True)
        if not self.config_path.exists():
            self.config_path.write_text(
                "schema_version: 1\nskills: []\n", encoding="utf-8", newline="\n"
            )
        if not self.policy_path.exists():
            self.policy_path.write_text(
                "schema_version: 1\n"
                "require_approval_for_all_updates: true\n"
                "block_approval_weakening: true\n"
                "block_destructive_instructions: true\n"
                "denied_commands:\n  - 'rm -rf *'\n  - '*force push*'\n  - '*--no-preserve-root*'\n"
                "denied_domains: []\n"
                "denied_paths:\n  - '~/.ssh*'\n  - '*.env'\n  - '*credentials*'\n  - '*id_rsa*'\n",
                encoding="utf-8",
                newline="\n",
            )
        if not self.lock_path.exists():
            self.save_lock(LockFile())

    def specs(self) -> dict[str, SkillSpec]:
        if not self.config_path.exists():
            raise ConfigurationError("not initialized; run 'skillops init'")
        try:
            data = yaml.safe_load(self.config_path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError) as exc:
            raise ConfigurationError(f"invalid skills.yml: {exc}") from exc
        if data.get("schema_version") != 1 or not isinstance(data.get("skills"), list):
            raise ConfigurationError("skills.yml requires schema_version: 1 and a skills list")
        specs = [SkillSpec.from_dict(item) for item in data["skills"]]
        if len({spec.name for spec in specs}) != len(specs):
            raise ConfigurationError("skill names must be unique")
        return {spec.name: spec for spec in specs}

    def save_specs(self, specs: dict[str, SkillSpec]) -> None:
        payload = {
            "schema_version": 1,
            "skills": [
                {
                    "name": spec.name,
                    "source": spec.source,
                    "ref": spec.ref,
                    "subpath": spec.subpath,
                    "target": spec.target,
                    "allow_local_source": spec.allow_local_source,
                }
                for spec in sorted(specs.values(), key=lambda item: item.name.casefold())
            ],
        }
        self.config_path.write_text(
            yaml.safe_dump(payload, sort_keys=False), encoding="utf-8", newline="\n"
        )

    def load_lock(self) -> LockFile:
        data = read_json(self.lock_path)
        if data is None:
            return LockFile()
        return LockFile.from_dict(data)

    def save_lock(self, lock: LockFile) -> None:
        lock.generated_at = now_iso()
        atomic_json(self.lock_path, lock.to_dict())

    def append_audit(self, event: str, details: dict[str, Any]) -> dict[str, Any]:
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        audit_lock = self.directory / "audit.lock"
        try:
            descriptor = os.open(audit_lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise SkillOpsError("another process is writing the audit trail") from exc
        try:
            previous_hash = "0" * 64
            sequence = 1
            last_line = self._last_audit_line()
            if last_line:
                last = json.loads(last_line)
                previous_hash = str(last["event_hash"])
                sequence = int(last["sequence"]) + 1
            record: dict[str, Any] = {
                "sequence": sequence,
                "timestamp": now_iso(),
                "event": event,
                "details": details,
                "previous_event_hash": previous_hash,
            }
            canonical = json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
            record["event_hash"] = hashlib.sha256(canonical).hexdigest()
            with self.audit_path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            return record
        finally:
            os.close(descriptor)
            audit_lock.unlink(missing_ok=True)

    def verify_audit(self) -> tuple[bool, int]:
        previous = "0" * 64
        count = 0
        if not self.audit_path.exists():
            return True, 0
        for expected_sequence, line in enumerate(
            self.audit_path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not line:
                continue
            record = json.loads(line)
            supplied = record.pop("event_hash", None)
            canonical = json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
            calculated = hashlib.sha256(canonical).hexdigest()
            if (
                supplied != calculated
                or record.get("previous_event_hash") != previous
                or record.get("sequence") != expected_sequence
            ):
                return False, count
            previous = calculated
            count += 1
        return True, count

    @contextmanager
    def exclusive(self) -> Iterator[None]:
        self.directory.mkdir(parents=True, exist_ok=True)
        lock_path = self.directory / "operation.lock"
        try:
            descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            age = time.time() - lock_path.stat().st_mtime
            message = "another SkillUpdateOps operation is running"
            if age > 600:
                message += (
                    "; remove stale .skillops/operation.lock after confirming no process is active"
                )
            raise SkillOpsError(message) from exc
        try:
            os.write(descriptor, f"pid={os.getpid()} time={now_iso()}\n".encode())
            os.close(descriptor)
            yield
        finally:
            with suppress(OSError):
                os.close(descriptor)
            lock_path.unlink(missing_ok=True)
