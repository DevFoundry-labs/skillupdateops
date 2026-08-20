"""Deterministic policy evaluation with evidence-backed findings."""

from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Any

import yaml

from .errors import ConfigurationError

DEFAULT_POLICY: dict[str, Any] = {
    "require_approval_for_all_updates": True,
    "block_approval_weakening": True,
    "block_destructive_instructions": True,
    "denied_commands": ["rm -rf *", "*force push*", "*--no-preserve-root*"],
    "denied_domains": [],
    "denied_paths": ["~/.ssh*", "*.env", "*credentials*", "*id_rsa*"],
}


def load_policy(path: Path) -> dict[str, Any]:
    if not path.exists():
        return dict(DEFAULT_POLICY)
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigurationError(f"invalid policy file {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigurationError("policy must be a YAML mapping")
    if raw.pop("schema_version", 1) != 1:
        raise ConfigurationError("unsupported policy schema_version")
    unknown = set(raw) - set(DEFAULT_POLICY)
    if unknown:
        raise ConfigurationError(f"unknown policy fields: {', '.join(sorted(unknown))}")
    policy = dict(DEFAULT_POLICY)
    policy.update(raw)
    for key in ("denied_commands", "denied_domains", "denied_paths"):
        if not isinstance(policy[key], list) or not all(
            isinstance(item, str) for item in policy[key]
        ):
            raise ConfigurationError(f"{key} must be a list of strings")
    return policy


def _matches(values: list[str], patterns: list[str]) -> list[str]:
    return sorted(
        value
        for value in values
        if any(fnmatch.fnmatch(value.casefold(), pattern.casefold()) for pattern in patterns)
    )


def evaluate(
    capabilities: dict[str, list[str]], change: dict[str, Any], policy: dict[str, Any]
) -> dict[str, Any]:
    findings: list[dict[str, str]] = []

    def finding(rule: str, severity: str, message: str) -> None:
        findings.append({"rule": rule, "severity": severity, "message": message})

    denied_commands = _matches(capabilities.get("commands", []), policy["denied_commands"])
    denied_domains = _matches(capabilities.get("domains", []), policy["denied_domains"])
    denied_paths = _matches(capabilities.get("sensitive_paths", []), policy["denied_paths"])
    if denied_commands:
        finding("denied-command", "critical", f"denied commands: {', '.join(denied_commands)}")
    if denied_domains:
        finding("denied-domain", "critical", f"denied domains: {', '.join(denied_domains)}")
    if denied_paths:
        finding("denied-path", "critical", f"sensitive paths: {', '.join(denied_paths)}")
    if capabilities.get("destructive") and policy["block_destructive_instructions"]:
        finding("destructive-instruction", "critical", "destructive instruction evidence detected")
    if change.get("approval_weakened") and policy["block_approval_weakening"]:
        finding("approval-weakened", "critical", "approval requirement appears weakened")
    if change.get("capability_expansion"):
        finding("capability-expansion", "high", "candidate requests new capabilities")

    hard_block = any(item["severity"] == "critical" for item in findings)
    approval_required = bool(change.get("changed")) and (
        bool(policy["require_approval_for_all_updates"])
        or bool(change.get("capability_expansion"))
        or hard_block
    )
    return {
        "decision": "blocked" if hard_block else "review" if approval_required else "pass",
        "approval_required": approval_required,
        "hard_block": hard_block,
        "findings": findings,
    }
