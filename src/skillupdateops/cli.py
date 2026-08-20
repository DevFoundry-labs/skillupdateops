"""Command-line interface and stable automation exit codes."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from . import __version__
from .errors import (
    EXIT_BLOCKED,
    EXIT_CHANGES,
    EXIT_DRIFT,
    EXIT_ERROR,
    EXIT_OK,
    PolicyBlocked,
    SkillOpsError,
)
from .fixtures import run_fixtures
from .github_pr import open_draft_pr
from .models import SkillSpec
from .reporting import json_text
from .workflow import Workflow


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skillops",
        description="Safe lifecycle management for AI agent skills",
    )
    parser.add_argument("--project", type=Path, default=Path.cwd(), help="project root")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("init", help="initialize policy, config, lockfile, and audit storage")

    track = commands.add_parser("track", help="register a source and prepare its first candidate")
    track.add_argument("name")
    track.add_argument("--source", required=True)
    track.add_argument("--target", required=True)
    track.add_argument("--ref", default="main")
    track.add_argument("--path", dest="subpath", default=".")
    track.add_argument("--allow-local-source", action="store_true")

    check = commands.add_parser("check", help="fetch without executing and evaluate updates")
    check.add_argument("name", nargs="?")
    check.add_argument("--report", type=Path)

    report = commands.add_parser("report", help="render the latest candidate report")
    report.add_argument("name")
    report.add_argument("--output", type=Path)

    approve = commands.add_parser("approve", help="approve one exact candidate hash")
    approve.add_argument("name")
    approve.add_argument("--hash", required=True)
    approve.add_argument("--approver")
    approve.add_argument("--ttl-hours", type=int, default=24)
    approve.add_argument("--override-policy", action="store_true")

    apply = commands.add_parser("apply", help="transactionally install an approved candidate")
    apply.add_argument("name")
    apply.add_argument("--hash", required=True)

    rollback = commands.add_parser("rollback", help="restore the previous approved snapshot")
    rollback.add_argument("name")

    pr = commands.add_parser("pr", help="open a draft approval PR from a clean Git checkout")
    pr.add_argument("name")
    pr.add_argument("--hash", required=True)

    commands.add_parser("status", help="detect drift from the approved lockfile")

    audit = commands.add_parser("audit", help="verify and display the chained audit trail")
    audit.add_argument("--limit", type=int, default=20)

    test = commands.add_parser("test", help="run declarative fixtures against an installed skill")
    test.add_argument("name")
    test.add_argument("--fixtures", type=Path, required=True)
    return parser


def _emit(value: Any, as_json: bool) -> None:
    if as_json:
        print(
            json_text(value if isinstance(value, (dict, list)) else {"result": str(value)}), end=""
        )
    elif isinstance(value, str):
        print(value, end="" if value.endswith("\n") else "\n")
    else:
        print(json_text(value), end="")


def run(arguments: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(arguments)
    workflow = Workflow(args.project)
    try:
        if args.command == "init":
            workflow.init()
            _emit({"status": "initialized", "project": str(workflow.state.root)}, args.json)
        elif args.command == "track":
            candidate = workflow.track(
                SkillSpec(
                    name=args.name,
                    source=args.source,
                    target=args.target,
                    ref=args.ref,
                    subpath=args.subpath,
                    allow_local_source=args.allow_local_source,
                )
            )
            _emit(candidate.to_dict(), args.json)
            return EXIT_BLOCKED if candidate.policy["hard_block"] else EXIT_CHANGES
        elif args.command == "check":
            candidates = [workflow.check(args.name)] if args.name else workflow.check_all()
            if args.report:
                if len(candidates) != 1:
                    raise SkillOpsError("--report requires a skill name")
                args.report.parent.mkdir(parents=True, exist_ok=True)
                args.report.write_text(
                    workflow.report(candidates[0].name), encoding="utf-8", newline="\n"
                )
            _emit([candidate.to_dict() for candidate in candidates], args.json)
            if any(candidate.policy["hard_block"] for candidate in candidates):
                return EXIT_BLOCKED
            if any(candidate.change["changed"] for candidate in candidates):
                return EXIT_CHANGES
        elif args.command == "report":
            text = workflow.report(args.name)
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(text, encoding="utf-8", newline="\n")
                _emit({"report": str(args.output)}, args.json)
            else:
                _emit(text, args.json)
        elif args.command == "approve":
            approval = workflow.approve(
                args.name,
                args.hash,
                approver=args.approver,
                ttl_hours=args.ttl_hours,
                override_policy=args.override_policy,
            )
            _emit(approval.to_dict(), args.json)
        elif args.command == "apply":
            _emit(vars(workflow.apply(args.name, args.hash)), args.json)
        elif args.command == "rollback":
            _emit(vars(workflow.rollback(args.name)), args.json)
        elif args.command == "pr":
            _emit({"pull_request": open_draft_pr(workflow, args.name, args.hash)}, args.json)
        elif args.command == "status":
            status = workflow.status()
            _emit(status, args.json)
            if any(item["state"] != "current" for item in status):
                return EXIT_DRIFT
        elif args.command == "audit":
            result = workflow.audit(args.limit)
            _emit(result, args.json)
            if not result["valid"]:
                return EXIT_BLOCKED
        elif args.command == "test":
            entry = workflow.state.load_lock().skills.get(args.name)
            if entry is None:
                raise SkillOpsError(f"skill is not installed: {args.name}")
            target = workflow.state.root / entry.target
            fixtures = (
                args.fixtures
                if args.fixtures.is_absolute()
                else workflow.state.root / args.fixtures
            )
            fixture_results = run_fixtures(workflow.state.root, target, fixtures)
            _emit(fixture_results, args.json)
            if not all(item["passed"] for item in fixture_results):
                return EXIT_BLOCKED
        return EXIT_OK
    except PolicyBlocked as exc:
        print(f"blocked: {exc}", file=sys.stderr)
        return EXIT_BLOCKED
    except SkillOpsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
