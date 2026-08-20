# SkillUpdateOps

**Dependabot-style lifecycle management for AI agent skills.**

[![CI](https://github.com/DevFoundry-labs/skillupdateops/actions/workflows/ci.yml/badge.svg)](https://github.com/DevFoundry-labs/skillupdateops/actions/workflows/ci.yml)
[![Security](https://github.com/DevFoundry-labs/skillupdateops/actions/workflows/security.yml/badge.svg)](https://github.com/DevFoundry-labs/skillupdateops/actions/workflows/security.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

AI skills are executable intent. A one-line Markdown change can add shell access, contact a
new endpoint, read credentials, or remove an approval step. SkillUpdateOps gives those changes
the workflow mature dependencies already have: inventory, immutable versions, explainable diffs,
policy gates, regression checks, explicit review, installation, drift detection, and rollback.

```text
Git/Local source → quarantine → canonical hash → capability diff → policy
       → exact-hash approval → atomic install → drift checks → rollback + audit
```

It does not claim to prove a skill safe. It makes updates reproducible, reviewable, and difficult
to apply accidentally.

## What is production-ready in v1.0

- GitHub HTTPS and explicitly enabled project-local sources
- Source acquisition with Git hooks and local Git transport disabled
- Content-addressed, size-bounded snapshots that reject symbolic links and traversal
- Cross-platform canonical SHA-256 tree hashes
- Deterministic extraction of commands, domains, tools, MCP servers, sensitive paths,
  destructive instructions, and approval language
- Explainable YAML policy with blocking and review decisions
- Approval records bound to one candidate hash, approver, expiry, and explicit critical override
- Transactional installation with verified staging and failure recovery
- Lockfile drift detection and exact snapshot rollback
- Tamper-evident hash-chained JSONL audit trail
- Static declarative fixtures and optional Docker-isolated executable fixtures
- Human-readable Markdown and machine-readable JSON reports
- CLI exit codes designed for CI and a reusable composite GitHub Action

## Install

Python 3.11 or newer and Git are required. Docker is needed only for executable fixtures.

Install the tagged release source directly:

```bash
pipx install "git+https://github.com/DevFoundry-labs/skillupdateops.git@v1.0.0"
```

With `uv`:

```bash
uv tool install "git+https://github.com/DevFoundry-labs/skillupdateops.git@v1.0.0"
```

## Five-minute workflow

Initialize a repository:

```bash
skillops init
```

Track one skill. Remote sources are restricted to credential-free GitHub HTTPS URLs:

```bash
skillops track invoice-review \
  --source https://github.com/example/agent-skills.git \
  --ref v1.4.0 \
  --path skills/invoice-review \
  --target .agents/skills/invoice-review
```

`track` fetches and analyzes the candidate but does not install or execute it. Review the report:

```bash
skillops report invoice-review --output skillops-reports/invoice-review.md
```

Approve and apply the exact displayed hash:

```bash
skillops approve invoice-review --hash sha256:EXACT_HASH_FROM_REPORT
skillops apply invoice-review --hash sha256:EXACT_HASH_FROM_REPORT
```

If policy found a critical issue, normal approval fails. A named reviewer must make the exception
explicit and the audit trail records it:

```bash
skillops approve invoice-review \
  --hash sha256:EXACT_HASH_FROM_REPORT \
  --approver security-owner \
  --override-policy
```

Check for upstream changes and local drift:

```bash
skillops check invoice-review --report skillops-reports/invoice-review.md
skillops status
skillops audit
```

From a clean Git checkout, turn the exact candidate into a draft approval PR without changing the
current checkout:

```bash
skillops pr invoice-review --hash sha256:EXACT_HASH_FROM_REPORT
```

The command uses a disposable Git worktree, stages only the target skill, lockfile, and evidence
report, pushes a dedicated branch, and opens one draft PR through the authenticated GitHub CLI.

Restore the previous approved snapshot:

```bash
skillops rollback invoice-review
```

## Exit codes

| Code | Meaning |
|---:|---|
| `0` | Success; no change or drift requiring attention |
| `1` | Configuration, source, or operational error |
| `2` | Candidate changed and needs review |
| `3` | Policy, approval, fixture, or audit gate blocked |
| `4` | Installed content drifted or is missing |

Use global `--json` before the command for automation:

```bash
skillops --json check invoice-review
```

## Configuration

`skillops init` creates:

```text
.skillops/
├── skills.yml        # tracked source, ref, subpath, and target
├── policy.yml        # committed review policy
├── audit.jsonl       # local tamper-evident event trail
├── candidates/       # local review state
├── approvals/        # short-lived exact-hash approvals
├── history/          # rollback metadata
└── store/            # immutable local snapshots
skills.lock           # portable approved state; commit this
```

Commit `.skillops/skills.yml`, `.skillops/policy.yml`, and `skills.lock`. The supplied `.gitignore`
pattern shows which runtime state should remain local.

The default policy blocks destructive instructions, approval weakening, and sensitive path
evidence. Review [the policy reference](docs/policy.md) before changing it.

## Declarative regression fixtures

Fixtures are controlled by the repository owner, never loaded from an untrusted candidate:

```yaml
tests:
  - name: preserves-approval-gate
    contains:
      - "ask for approval"
    not_contains:
      - "without confirmation"
```

Run them against an installed, locked skill:

```bash
skillops test invoice-review --fixtures tests/fixtures/invoice-review.yml
```

An optional `command` list runs only in Docker with no network, a read-only root filesystem,
dropped capabilities, `no-new-privileges`, bounded memory/CPU/PIDs, a read-only skill mount, and a
disposable workspace. If Docker is unavailable, SkillUpdateOps fails closed and executes nothing.

See [fixture documentation](docs/fixtures.md) for the complete schema and security boundary.

## GitHub Actions

Use the repository action after checkout:

```yaml
name: Skill update review
on:
  workflow_dispatch:
  schedule:
    - cron: "17 6 * * 1"

permissions:
  contents: read

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: DevFoundry-labs/skillupdateops@v1
        with:
          command: check
```

The action intentionally reports and exits; it does not auto-merge or install an update. Teams can
upload the generated report as an artifact or wrap the JSON output in their existing PR automation.

## Security model

Candidate repositories are untrusted data. Inspection does not import candidate code, install its
dependencies, execute hooks, or run its scripts. Static analysis is conservative and evidence-based.
Executable fixtures are a separate, owner-authored opt-in path guarded by Docker.

Read [Threat model](docs/threat-model.md) and [SECURITY.md](SECURITY.md) before using policy overrides.

## Supported and deliberately unsupported

Supported skill content is a directory containing at least one UTF-8 Markdown file, commonly
`SKILL.md`. The analyzer recognizes common Claude Code, Codex, and Agent Skills conventions without
requiring a platform-specific runtime.

v1.0 deliberately does not:

- guarantee that natural-language instructions are safe;
- execute a real AI agent as part of update checking;
- accept arbitrary Git hosts, SSH URLs, credentials in URLs, symlinks, or files over the limits;
- auto-approve, auto-install, or auto-merge changes;
- provide fleet management or a hosted dashboard.

These boundaries are controls, not unfinished buttons.

## Development

```bash
git clone https://github.com/DevFoundry-labs/skillupdateops.git
cd skillupdateops
uv sync --extra dev
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest
uv build
```

See [CONTRIBUTING.md](CONTRIBUTING.md), [architecture](docs/architecture.md), and the
[changelog](CHANGELOG.md).

## Why now

Skills are becoming a shared software supply chain, while recent research demonstrates attacks that
can live entirely in semantic instructions rather than conventional executable payloads. The correct
response is not another opaque score; it is provenance, deterministic evidence, human approval, and
recoverable state transitions.

## License

Apache-2.0. See [LICENSE](LICENSE).
