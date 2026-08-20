"""Stable Markdown and JSON candidate reports."""

from __future__ import annotations

import json
from typing import Any

from .models import Candidate, LockEntry


def candidate_markdown(candidate: Candidate, current: LockEntry | None) -> str:
    policy = candidate.policy
    change = candidate.change
    lines = [
        f"# Skill update report: `{candidate.name}`",
        "",
        f"- Current: `{current.content_hash if current else 'not installed'}`",
        f"- Candidate: `{candidate.content_hash}`",
        f"- Revision: `{candidate.resolved_revision}`",
        f"- Decision: **{str(policy['decision']).upper()}**",
        f"- Checked: {candidate.checked_at}",
        "",
        "## Capability changes",
        "",
    ]
    categories = change.get("categories", {})
    if not categories:
        lines.append("No capability changes detected.")
    for category, delta in sorted(categories.items()):
        lines.append(f"### {category.replace('_', ' ').title()}")
        lines.append("")
        lines.extend(f"- Added: `{value}`" for value in delta.get("added", []))
        lines.extend(f"- Removed: `{value}`" for value in delta.get("removed", []))
        lines.append("")
    lines.extend(["## Policy findings", ""])
    findings = policy.get("findings", [])
    if not findings:
        lines.append("No policy findings.")
    for item in findings:
        lines.append(f"- **{item['severity'].upper()}** `{item['rule']}` — {item['message']}")
    lines.extend(
        [
            "",
            "## Decision controls",
            "",
            "Approval is bound to the exact candidate SHA-256 hash. "
            "Any content change invalidates it.",
            "Critical policy findings additionally require an explicit policy override "
            "during approval.",
            "",
            "```console",
            f"skillops approve {candidate.name} --hash {candidate.content_hash}",
            f"skillops apply {candidate.name} --hash {candidate.content_hash}",
            "```",
        ]
    )
    return "\n".join(lines) + "\n"


def json_text(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True) + "\n"
