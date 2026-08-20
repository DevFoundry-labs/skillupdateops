"""Explainable capability extraction and semantic comparison."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from .content import canonical_bytes
from .errors import ConfigurationError, SecurityError

URL = re.compile(r"https?://([A-Za-z0-9.-]+)(?::\d+)?(?:[/\s)`'\"]|$)", re.IGNORECASE)
COMMAND = re.compile(
    r"(?:run|execute|invoke|shell|command)\s+(?:the\s+)?(?:command\s+)?[`'\"]([^`'\"\n]{1,200})[`'\"]",
    re.IGNORECASE,
)
TOOL = re.compile(
    r"\b(?:use|call|invoke|requires?)\s+(?:the\s+)?(?:"
    r"tool\s+[`'\"]?([A-Za-z][\w.-]{1,80})|"
    r"[`'\"]([A-Za-z][\w.-]{1,80})[`'\"]\s+tool)",
    re.IGNORECASE,
)
MCP = re.compile(r"\b(?:mcp|server)[:/\s]+([A-Za-z][\w.-]{1,80})", re.IGNORECASE)
PATH = re.compile(
    r"(?:~[/\\][\w./\\-]+|(?:/etc|/var|/home|/root|C:\\Users)[\w .:/\\-]*|"
    r"\.env\b|credentials?\b|id_rsa\b)",
    re.IGNORECASE,
)
DESTRUCTIVE = re.compile(
    r"\b(?:rm\s+-rf|del\s+/[sq]|remove-item\s+.*-recurse|force[- ]push|"
    r"drop\s+(?:table|database)|delete\s+all)\b",
    re.IGNORECASE,
)
APPROVAL_STRONG = re.compile(
    r"(?:must|required to|always)\s+(?:ask|obtain|request|receive|require).{0,50}"
    r"(?:approval|confirmation|permission)",
    re.IGNORECASE,
)
APPROVAL_WEAK = re.compile(
    r"(?:without|skip|bypass|do not (?:ask|request)).{0,50}(?:approval|confirmation|permission)",
    re.IGNORECASE,
)

CATEGORIES = (
    "commands",
    "domains",
    "tools",
    "mcp_servers",
    "sensitive_paths",
    "destructive",
    "approval",
)


def _frontmatter(text: str) -> dict[str, Any]:
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}
    try:
        value = yaml.safe_load(text[4:end]) or {}
    except yaml.YAMLError as exc:
        raise ConfigurationError(f"invalid YAML frontmatter: {exc}") from exc
    if not isinstance(value, dict):
        raise ConfigurationError("SKILL.md frontmatter must be a mapping")
    return value


def _strings(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in re.split(r"[,\n]", value) if item.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


def analyze(root: Path) -> dict[str, list[str]]:
    evidence: dict[str, set[str]] = {category: set() for category in CATEGORIES}
    markdown = sorted(root.rglob("*.md"))
    if not markdown:
        raise SecurityError("skill contains no Markdown files")
    for path in markdown:
        if path.is_symlink():
            raise SecurityError(f"symbolic link rejected during analysis: {path}")
        raw = path.read_bytes()
        if len(raw) > 2 * 1024 * 1024:
            raise SecurityError(f"Markdown file too large to analyze: {path.name}")
        try:
            text = canonical_bytes(raw).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise SecurityError(f"Markdown is not UTF-8: {path.name}") from exc
        metadata = _frontmatter(text)
        for key in ("allowed-tools", "allowed_tools", "tools"):
            evidence["tools"].update(_strings(metadata.get(key)))
        for key in ("mcp-servers", "mcp_servers"):
            evidence["mcp_servers"].update(_strings(metadata.get(key)))
        for match in URL.finditer(text):
            evidence["domains"].add(match.group(1).lower().rstrip("."))
        for match in COMMAND.finditer(text):
            evidence["commands"].add(" ".join(match.group(1).split()))
        for match in TOOL.finditer(text):
            evidence["tools"].add(match.group(1) or match.group(2))
        for match in MCP.finditer(text):
            evidence["mcp_servers"].add(match.group(1))
        evidence["sensitive_paths"].update(match.group(0) for match in PATH.finditer(text))
        evidence["destructive"].update(
            match.group(0).lower() for match in DESTRUCTIVE.finditer(text)
        )
        if APPROVAL_STRONG.search(text):
            evidence["approval"].add("required")
        if APPROVAL_WEAK.search(text):
            evidence["approval"].add("bypass-language")
    return {category: sorted(values, key=str.casefold) for category, values in evidence.items()}


def compare(old: dict[str, list[str]] | None, new: dict[str, list[str]]) -> dict[str, Any]:
    previous = old or {category: [] for category in CATEGORIES}
    changes: dict[str, dict[str, list[str]]] = {}
    expanded = False
    for category in CATEGORIES:
        before = set(previous.get(category, []))
        after = set(new.get(category, []))
        added = sorted(after - before, key=str.casefold)
        removed = sorted(before - after, key=str.casefold)
        if added or removed:
            changes[category] = {"added": added, "removed": removed}
        if added and category != "approval":
            expanded = True
    approval_before = set(previous.get("approval", []))
    approval_after = set(new.get("approval", []))
    weakened = (
        "required" in approval_before and "required" not in approval_after
    ) or "bypass-language" in approval_after
    return {
        "changed": bool(changes),
        "capability_expansion": expanded,
        "approval_weakened": weakened,
        "categories": changes,
    }
