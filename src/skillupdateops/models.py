"""Persisted data models with strict validation and stable serialization."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from .errors import ConfigurationError


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"{field_name} must be a non-empty string")
    return value.strip()


@dataclass(frozen=True)
class SkillSpec:
    name: str
    source: str
    target: str
    ref: str = "main"
    subpath: str = "."
    allow_local_source: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SkillSpec:
        allowed = {"name", "source", "target", "ref", "subpath", "allow_local_source"}
        unknown = set(data) - allowed
        if unknown:
            raise ConfigurationError(f"unknown skill fields: {', '.join(sorted(unknown))}")
        return cls(
            name=_string(data.get("name"), "name"),
            source=_string(data.get("source"), "source"),
            target=_string(data.get("target"), "target"),
            ref=_string(data.get("ref", "main"), "ref"),
            subpath=_string(data.get("subpath", "."), "subpath"),
            allow_local_source=bool(data.get("allow_local_source", False)),
        )


@dataclass
class LockEntry:
    name: str
    source: str
    target: str
    requested_ref: str
    resolved_revision: str
    subpath: str
    content_hash: str
    files: list[str]
    capabilities: dict[str, list[str]]
    installed_at: str
    previous_hash: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LockEntry:
        try:
            return cls(
                name=_string(data["name"], "name"),
                source=_string(data["source"], "source"),
                target=_string(data["target"], "target"),
                requested_ref=_string(data["requested_ref"], "requested_ref"),
                resolved_revision=_string(data["resolved_revision"], "resolved_revision"),
                subpath=_string(data["subpath"], "subpath"),
                content_hash=_string(data["content_hash"], "content_hash"),
                files=[str(item) for item in data["files"]],
                capabilities={
                    str(k): [str(v) for v in values] for k, values in data["capabilities"].items()
                },
                installed_at=_string(data["installed_at"], "installed_at"),
                previous_hash=str(data["previous_hash"]) if data.get("previous_hash") else None,
            )
        except (KeyError, TypeError) as exc:
            raise ConfigurationError(f"invalid lock entry: {exc}") from exc


@dataclass
class LockFile:
    schema_version: int = 1
    generated_at: str = field(default_factory=now_iso)
    skills: dict[str, LockEntry] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "skills": {name: asdict(entry) for name, entry in sorted(self.skills.items())},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LockFile:
        if data.get("schema_version") != 1:
            raise ConfigurationError("unsupported skills.lock schema_version")
        raw = data.get("skills", {})
        if not isinstance(raw, dict):
            raise ConfigurationError("skills must be an object")
        return cls(
            schema_version=1,
            generated_at=str(data.get("generated_at", now_iso())),
            skills={str(name): LockEntry.from_dict(entry) for name, entry in raw.items()},
        )


@dataclass
class Candidate:
    name: str
    content_hash: str
    resolved_revision: str
    files: list[str]
    capabilities: dict[str, list[str]]
    snapshot: str
    checked_at: str
    change: dict[str, Any]
    policy: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Candidate:
        try:
            return cls(
                name=str(data["name"]),
                content_hash=str(data["content_hash"]),
                resolved_revision=str(data["resolved_revision"]),
                files=[str(item) for item in data["files"]],
                capabilities={
                    str(k): [str(v) for v in values] for k, values in data["capabilities"].items()
                },
                snapshot=str(data["snapshot"]),
                checked_at=str(data["checked_at"]),
                change=dict(data["change"]),
                policy=dict(data["policy"]),
            )
        except (KeyError, TypeError) as exc:
            raise ConfigurationError(f"invalid candidate record: {exc}") from exc


@dataclass(frozen=True)
class Approval:
    name: str
    candidate_hash: str
    approver: str
    approved_at: str
    expires_at: str
    override_policy: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
