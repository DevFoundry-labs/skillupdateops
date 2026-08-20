# Implementation Plan

## Product contract

SkillUpdateOps replaces manual skill inventory, update review, permission inspection, regression checking, approval, installation, and rollback with a deterministic local-first workflow. It never executes a candidate merely to inspect it, and capability-expanding updates require a recorded human approval.

## Phases

1. Implement reproducible discovery, snapshots, hashes, source resolution, and lockfiles.
2. Implement capability extraction, semantic diffs, policy evaluation, and audit records.
3. Implement candidate checking, explicit approval, transactional application, drift detection, and rollback.
4. Add declarative tests and an optional Docker-isolated command runner.
5. Add CLI, machine-readable reports, GitHub Action integration, docs, fixtures, and packaging.
6. Run cross-platform-oriented unit/integration/E2E, type, lint, build, security, and performance checks.
7. Publish, verify CI, create v1.0.0, and record completion.

## Modules

- `models`: validated lockfile, policy, capability, candidate, and audit schemas.
- `content`: safe path handling, canonical hashing, snapshots, and atomic writes.
- `sources`: local and Git source acquisition without install-time execution.
- `analysis`: deterministic Markdown/frontmatter capability extraction and semantic diffing.
- `policy`: explainable rule evaluation and approval gates.
- `workflow`: orchestration, transactions, audit trail, drift, and rollback.
- `fixtures`: static assertions and Docker-isolated behavioral commands.
- `cli`: stable human and JSON interfaces with actionable exit codes.

## Acceptance tests

- Same content produces the same hash independent of traversal order and line endings.
- Traversal/symlink escapes are rejected.
- Seeded capability expansion and weakened approval language are blocked.
- Candidate inspection never runs repository hooks or installers.
- Approval is bound to the exact candidate hash and expires.
- Apply is atomic, records history, and rollback restores the exact prior hash.
- Drift is detected; duplicate checks are idempotent.
- Docker runner uses no network, a read-only root, dropped capabilities, and bounded resources.
- CLI happy path, block/approve/apply, exception, audit, and rollback paths pass end-to-end.

## Risk areas

- Natural-language capability inference can produce false positives; results remain evidence-backed and never claim proof of safety.
- Host-independent hard sandboxing is unavailable; executable fixtures require Docker and fail closed when it is absent.
- Git tags can move; accepted content is always pinned by commit plus SHA-256 tree hash.
- Atomic directory replacement differs by OS; transactions use sibling staging/backup directories with recovery records.

## External requirements

- Python 3.11+
- Git for remote sources
- Docker only for executable behavioral fixtures
- GitHub CLI only for `update --pr`
